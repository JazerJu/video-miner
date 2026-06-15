# coding=utf-8
"""Persistent GLM-OCR ONNX worker for CUDA process isolation."""
from __future__ import annotations

import atexit
import io
import os
import queue
import time
import traceback
import multiprocessing as mp
from pathlib import Path
from typing import Any


_READY_REQUEST_ID = 0


def _worker_main(
    request_q,
    response_q,
    onnx_dir: str,
    max_tokens: int,
    provider: str,
    precision: str,
    threads: int,
) -> None:
    if provider:
        os.environ["VIDUNDER_GLM_OCR_ONNX_PROVIDER"] = provider
    if precision:
        os.environ["VIDUNDER_GLM_OCR_ONNX_PRECISION"] = precision
    if threads > 0:
        os.environ["VIDUNDER_GLM_OCR_ONNX_THREADS"] = str(threads)

    try:
        from PIL import Image
        from glm_ocr_onnx import GlmOcrOnnx

        encoder = GlmOcrOnnx(onnx_dir, max_tokens=max_tokens)
        response_q.put((_READY_REQUEST_ID, True, {
            "pid": os.getpid(),
            "providers": encoder.providers,
            "precision": encoder.precision,
        }))
    except BaseException:
        response_q.put((_READY_REQUEST_ID, False, traceback.format_exc()))
        return

    while True:
        item = request_q.get()
        if item is None:
            break

        req_id, image_bytes, prompt = item
        try:
            image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            payload = encoder.encode_for_llama(image, prompt)
            response_q.put((req_id, True, payload))
        except BaseException:
            response_q.put((req_id, False, traceback.format_exc()))


class GlmOcrOnnxWorker:
    """One long-lived ONNX Runtime process, separate from llama.cpp CUDA."""

    def __init__(
        self,
        onnx_dir: str | Path,
        provider: str = "cuda",
        precision: str = "q4",
        threads: int = 4,
        max_tokens: int = 2048,
        timeout: int = 180,
    ) -> None:
        self.onnx_dir = str(onnx_dir)
        self.provider = provider
        self.precision = precision
        self.threads = int(threads)
        self.max_tokens = int(max_tokens)
        self.timeout = int(timeout)
        self._ctx = mp.get_context(os.environ.get("VIDUNDER_GLM_OCR_WORKER_START_METHOD", "spawn"))
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
            args=(
                self._request_q,
                self._response_q,
                self.onnx_dir,
                self.max_tokens,
                self.provider,
                self.precision,
                self.threads,
            ),
            daemon=True,
        )
        self._process.start()

        req_id, ok, payload = self._read_response(_READY_REQUEST_ID, self.timeout)
        if req_id != _READY_REQUEST_ID:
            raise RuntimeError(f"GLM-OCR ONNX worker returned unexpected ready id: {req_id}")
        if not ok:
            self.stop(force=True)
            raise RuntimeError(f"GLM-OCR ONNX worker failed to start:\n{payload}")
        self.info = payload

    def infer(self, image, prompt: str, timeout: int | None = None) -> dict[str, Any]:
        self.start()
        req_id = self._request_id
        self._request_id += 1
        assert self._request_q is not None

        self._request_q.put((req_id, self._image_to_bytes(image), prompt))
        _, ok, payload = self._read_response(req_id, self.timeout if timeout is None else int(timeout))
        if not ok:
            raise RuntimeError(f"GLM-OCR ONNX worker error:\n{payload}")
        return payload

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
                raise TimeoutError(f"GLM-OCR ONNX worker timed out after {timeout}s")

            try:
                req_id, ok, payload = self._response_q.get(timeout=min(0.2, remaining))
            except queue.Empty:
                process = self._process
                if process is not None and not process.is_alive():
                    exitcode = process.exitcode
                    self.stop(force=True)
                    raise RuntimeError(f"GLM-OCR ONNX worker exited unexpectedly with code {exitcode}")
                continue

            if req_id == expected_req_id:
                return req_id, ok, payload

    @staticmethod
    def _image_to_bytes(image) -> bytes:
        if hasattr(image, "convert"):
            image = image.convert("RGB")
        buf = io.BytesIO()
        image.save(buf, format="PNG", compress_level=1)
        return buf.getvalue()


_worker: GlmOcrOnnxWorker | None = None


def get_glm_ocr_onnx_worker(
    onnx_dir: str | Path,
    provider: str = "cuda",
    precision: str = "q4",
    threads: int = 4,
    timeout: int = 180,
) -> GlmOcrOnnxWorker:
    global _worker
    cfg = (str(onnx_dir), provider, precision, int(threads), int(timeout))
    if _worker is not None:
        old_cfg = (
            _worker.onnx_dir,
            _worker.provider,
            _worker.precision,
            _worker.threads,
            _worker.timeout,
        )
        if old_cfg != cfg:
            _worker.stop()
            _worker = None
    if _worker is None:
        _worker = GlmOcrOnnxWorker(
            onnx_dir=onnx_dir,
            provider=provider,
            precision=precision,
            threads=threads,
            timeout=timeout,
        )
    return _worker


def shutdown_glm_ocr_onnx_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None


atexit.register(shutdown_glm_ocr_onnx_worker)


__all__ = [
    "GlmOcrOnnxWorker",
    "get_glm_ocr_onnx_worker",
    "shutdown_glm_ocr_onnx_worker",
]
