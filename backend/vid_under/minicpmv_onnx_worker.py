# coding=utf-8
"""Persistent MiniCPM-V ONNX worker for process-isolated visual encoding."""
from __future__ import annotations

import atexit
import os
import queue
import time
import traceback
import multiprocessing as mp
from pathlib import Path
from typing import Any


_READY_REQUEST_ID = 0


def _provider_list(provider: str) -> list[str]:
    if provider.lower() == "cpu":
        return ["CPUExecutionProvider"]
    return ["CUDAExecutionProvider", "CPUExecutionProvider"]


def _compute_onnx_inputs_v45(h, w, npps=70, resampler_embed_dim=4096):
    import numpy as np
    from preprocess import get_2d_sincos_pos_embed_numpy

    bucket_h = np.clip((np.arange(h) * npps) // h, 0, npps - 1)
    bucket_w = np.clip((np.arange(w) * npps) // w, 0, npps - 1)
    pos_ids = (bucket_h[:, None] * npps + bucket_w).flatten().astype(np.int64)
    spatial_pos_embed = get_2d_sincos_pos_embed_numpy(resampler_embed_dim, (h, w))
    spatial_pos_embed = spatial_pos_embed.reshape(h * w, -1).astype(np.float32)
    return {"pos_ids": pos_ids, "spatial_pos_embed": spatial_pos_embed}


def _worker_main(
    request_q,
    response_q,
    export_dir: str,
    provider: str,
    threads: int,
) -> None:
    if provider:
        os.environ["VIDUNDER_MINICPM_ONNX_PROVIDER"] = provider
        os.environ["VIDUNDER_ONNX_PROVIDER"] = provider
    if threads > 0:
        os.environ["OMP_NUM_THREADS"] = str(threads)

    try:
        import numpy as np
        import onnxruntime as ort
        from config import EMBED_DIM, NPPS
        from preprocess import (
            compute_temporal_embeddings_for_group,
            encode_video_temporal_ids,
            get_2d_sincos_pos_embed_numpy,
        )

        opts = ort.SessionOptions()
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        if threads > 0:
            opts.intra_op_num_threads = int(threads)
            opts.inter_op_num_threads = 1
        providers = _provider_list(provider)
        export_path = Path(export_dir)
        siglip = ort.InferenceSession(
            str(export_path / "minicpmv_v45_siglip.fp32.onnx"),
            sess_options=opts,
            providers=providers,
        )
        resampler = ort.InferenceSession(
            str(export_path / "minicpmv_v45_resampler_temporal.fp16.onnx"),
            sess_options=opts,
            providers=providers,
        )
        response_q.put((_READY_REQUEST_ID, True, {
            "pid": os.getpid(),
            "siglip_providers": siglip.get_providers(),
            "resampler_providers": resampler.get_providers(),
        }))
    except BaseException:
        response_q.put((_READY_REQUEST_ID, False, traceback.format_exc()))
        return

    while True:
        item = request_q.get()
        if item is None:
            break

        req_id, tiles, num_frames, video_fps = item
        try:
            siglip_features, patch_counts, tile_temporal_ids = [], [], []
            frame_ids = np.linspace(0, num_frames - 1, num_frames, dtype=int)
            temporal_ids = encode_video_temporal_ids(frame_ids, video_fps)

            for pv, h, w, frame_idx in tiles:
                inputs = _compute_onnx_inputs_v45(h, w, NPPS)
                feat = siglip.run(
                    ["siglip_features"],
                    {
                        "pixel_values": pv.astype(np.float32, copy=False),
                        "pos_ids": inputs["pos_ids"],
                    },
                )[0]
                siglip_features.append(feat)
                patch_counts.append(h * w)
                tile_temporal_ids.append(temporal_ids[min(int(frame_idx), len(temporal_ids) - 1)])

            gf = np.concatenate(siglip_features, axis=0)
            sp = np.concatenate(
                [
                    get_2d_sincos_pos_embed_numpy(EMBED_DIM, (h, w)).reshape(h * w, -1)
                    for _, h, w, _ in tiles
                ],
                axis=0,
            )
            te = compute_temporal_embeddings_for_group(patch_counts, tile_temporal_ids, EMBED_DIM)
            vt = resampler.run(None, {
                "siglip_features": gf.astype(np.float16),
                "spatial_pos_embeds": sp.astype(np.float16),
                "temporal_pos_embeds": te.astype(np.float16),
            })[0]
            response_q.put((req_id, True, vt.astype(np.float32)))
        except BaseException:
            response_q.put((req_id, False, traceback.format_exc()))


class MiniCpmvOnnxWorker:
    """One long-lived ONNX Runtime process, separate from llama.cpp CUDA."""

    def __init__(
        self,
        export_dir: str | Path,
        provider: str = "cuda",
        threads: int = 0,
        timeout: int = 180,
    ) -> None:
        self.export_dir = str(export_dir)
        self.provider = provider
        self.threads = int(threads)
        self.timeout = int(timeout)
        self._ctx = mp.get_context(os.environ.get("VIDUNDER_MINICPM_ONNX_WORKER_START_METHOD", "spawn"))
        self._request_q = None
        self._response_q = None
        self._process = None
        self._request_id = 1
        self.info: dict[str, Any] = {}

    def start(self) -> None:
        if self._process is not None and self._process.is_alive():
            return

        self._request_q = self._ctx.Queue(maxsize=1)
        self._response_q = self._ctx.Queue(maxsize=1)
        self._process = self._ctx.Process(
            target=_worker_main,
            args=(self._request_q, self._response_q, self.export_dir, self.provider, self.threads),
            daemon=True,
        )
        self._process.start()

        req_id, ok, payload = self._read_response(_READY_REQUEST_ID, self.timeout)
        if req_id != _READY_REQUEST_ID:
            raise RuntimeError(f"MiniCPM-V ONNX worker returned unexpected ready id: {req_id}")
        if not ok:
            self.stop(force=True)
            raise RuntimeError(f"MiniCPM-V ONNX worker failed to start:\n{payload}")
        self.info = payload

    def encode_tiles(self, tiles, num_frames: int, video_fps: float, timeout: int | None = None):
        self.start()
        req_id = self._request_id
        self._request_id += 1
        assert self._request_q is not None

        payload = [
            (t["pixel_values"], int(t["h"]), int(t["w"]), int(t.get("frame", 0)))
            for t in tiles
        ]
        self._request_q.put((req_id, payload, int(num_frames), float(video_fps)))
        _, ok, result = self._read_response(req_id, self.timeout if timeout is None else int(timeout))
        if not ok:
            raise RuntimeError(f"MiniCPM-V ONNX worker error:\n{result}")
        return result

    def stop(self, force: bool = False) -> None:
        process = self._process
        if process is None:
            return

        if process.pid is None:
            self._process = None
            self._request_q = None
            self._response_q = None
            self.info = {}
            return

        if process.is_alive() and self._request_q is not None and not force:
            try:
                self._request_q.put(None, timeout=0.5)
            except Exception:
                force = True

        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
        if process.is_alive():
            process.kill()
            process.join(timeout=5)

        self._process = None
        self._request_q = None
        self._response_q = None
        self.info = {}

    def _read_response(self, expected_req_id: int, timeout: int) -> tuple[int, bool, Any]:
        assert self._response_q is not None
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.stop(force=True)
                raise TimeoutError(f"MiniCPM-V ONNX worker timed out after {timeout}s")

            try:
                req_id, ok, payload = self._response_q.get(timeout=min(0.2, remaining))
            except queue.Empty:
                process = self._process
                if process is not None and not process.is_alive():
                    exitcode = process.exitcode
                    self.stop(force=True)
                    raise RuntimeError(f"MiniCPM-V ONNX worker exited unexpectedly with code {exitcode}")
                continue

            if req_id == expected_req_id:
                return req_id, ok, payload


_worker: MiniCpmvOnnxWorker | None = None


def get_minicpmv_onnx_worker(
    export_dir: str | Path,
    provider: str = "cuda",
    threads: int = 0,
    timeout: int = 180,
) -> MiniCpmvOnnxWorker:
    global _worker
    cfg = (str(export_dir), provider, int(threads), int(timeout))
    if _worker is not None:
        old_cfg = (_worker.export_dir, _worker.provider, _worker.threads, _worker.timeout)
        if old_cfg != cfg:
            _worker.stop()
            _worker = None
    if _worker is None:
        _worker = MiniCpmvOnnxWorker(
            export_dir=export_dir,
            provider=provider,
            threads=threads,
            timeout=timeout,
        )
    return _worker


def shutdown_minicpmv_onnx_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None


atexit.register(shutdown_minicpmv_onnx_worker)


__all__ = [
    "MiniCpmvOnnxWorker",
    "get_minicpmv_onnx_worker",
    "shutdown_minicpmv_onnx_worker",
]
