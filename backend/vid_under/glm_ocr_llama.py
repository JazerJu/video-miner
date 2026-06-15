# coding=utf-8
"""GLM-OCR hybrid inference: ONNX vision encoder + llama.cpp ctypes decoder."""
import time
import json
import ctypes
from pathlib import Path

import numpy as np

import minicpmv_llama

LlamaBatch = minicpmv_llama.LlamaBatch
LlamaSampler = minicpmv_llama.LlamaSampler


class _OcrLlamaModel(minicpmv_llama.LlamaModel):
    def __del__(self):
        self.ptr = None


class _OcrLlamaContext(minicpmv_llama.LlamaContext):
    def __del__(self):
        self.ptr = None

from config import GLM_OCR_ONNX_DIR


class GlmOcrLlama:
    """GLM-OCR inference using ONNX vision encoder + llama.cpp LLM decoder."""

    MROPE_DIMS = 4  # llama.cpp uses 4 position IDs per token for mRoPE

    def __init__(
        self,
        gguf_path: str = "",
        onnx_dir: str | None = None,
        n_ctx: int = 4096,
        n_gpu_layers: int = 99,
        load_onnx: bool = True,
    ):
        if not gguf_path:
            raise ValueError("gguf_path is required (e.g. 'models/GLM-OCR-GGUF/GLM-OCR-Q8_0.gguf')")
        if onnx_dir is None:
            onnx_dir = GLM_OCR_ONNX_DIR

        self.onnx = None
        if load_onnx:
            from glm_ocr_onnx import GlmOcrOnnx
            self.onnx = GlmOcrOnnx(onnx_dir, max_tokens=2048)

        self.model = _OcrLlamaModel(gguf_path, n_gpu_layers=n_gpu_layers)
        self.n_embd = self.model.n_embd
        self.ctx = _OcrLlamaContext(self.model, n_ctx=n_ctx, n_batch=n_ctx)

        with open(Path(onnx_dir) / "config.json") as f:
            cfg = json.load(f)
        self.eos_tokens = set(cfg["text_config"]["eos_token_id"])
        self.image_start_token_id = cfg["image_start_token_id"]
        self.image_end_token_id = cfg["image_end_token_id"]
        self.image_token_id = cfg["image_token_id"]
        self.mrope_section = cfg["text_config"]["rope_parameters"]["mrope_section"]
        self.spatial_merge_size = cfg["vision_config"]["spatial_merge_size"]

    def close(self) -> None:
        self.onnx = None
        self.ctx = None
        self.model = None
        import gc
        gc.collect()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _build_input_ids(self, prompt: str, num_image_tokens: int) -> list[int]:
        """Build token IDs using the ONNX module's Jinja template."""
        if self.onnx is None:
            raise RuntimeError("GLM-OCR ONNX encoder is not loaded in this process")
        ids_np = self.onnx._build_input_ids(prompt, num_image_tokens)
        return ids_np[0].tolist()

    def _compute_mrope_positions(self, input_ids: list[int], image_grid_thw: np.ndarray) -> tuple[np.ndarray, int]:
        """Compute mRoPE positions in llama.cpp's grouped layout: [all_t, all_h, all_w, all_x].

        Layout: pos[j * n_tokens + i] where j=dimension (0-3), i=token index.
        Returns (positions array, next_position).
        """
        n_tokens = len(input_ids)
        t_pos = np.zeros(n_tokens, dtype=np.int32)
        h_pos = np.zeros(n_tokens, dtype=np.int32)
        w_pos = np.zeros(n_tokens, dtype=np.int32)
        x_pos = np.zeros(n_tokens, dtype=np.int32)

        image_idx = 0
        current_pos = 0
        i = 0

        while i < n_tokens:
            if input_ids[i] == self.image_start_token_id:
                t_pos[i] = current_pos
                h_pos[i] = current_pos
                w_pos[i] = current_pos
                x_pos[i] = 0
                i += 1

                img_start = i
                while i < n_tokens and input_ids[i] == self.image_token_id:
                    i += 1

                t, h, w = image_grid_thw[image_idx]
                image_idx += 1
                llm_t = int(t)
                llm_h = int(h) // self.spatial_merge_size
                llm_w = int(w) // self.spatial_merge_size
                num_img_tokens = llm_t * llm_h * llm_w
                img_end = img_start + num_img_tokens

                # llama.cpp MTMD_POS_TYPE_MROPE layout (row-major):
                # section 0 (t) = fixed pos_0 for all image tokens
                # section 1 (y) = row index = i / nx
                # section 2 (x) = col index = i % nx
                # section 3 (z) = 0
                n_img = llm_t * llm_h * llm_w
                t_pos_img = np.full(n_img, current_pos, dtype=np.int32)
                h_pos_img = np.array([j // llm_w for j in range(n_img)], dtype=np.int32) + current_pos
                w_pos_img = np.array([j % llm_w for j in range(n_img)], dtype=np.int32) + current_pos

                t_pos[img_start:img_end] = t_pos_img
                h_pos[img_start:img_end] = h_pos_img
                w_pos[img_start:img_end] = w_pos_img

                for idx in range(img_start, img_end):
                    x_pos[idx] = 0

                current_pos += max(int(h), int(w)) // self.spatial_merge_size

                if i < n_tokens and input_ids[i] == self.image_end_token_id:
                    t_pos[i] = current_pos
                    h_pos[i] = current_pos
                    w_pos[i] = current_pos
                    x_pos[i] = 0
                    current_pos += 1
                    i += 1
            else:
                t_pos[i] = current_pos
                h_pos[i] = current_pos
                w_pos[i] = current_pos
                x_pos[i] = 0
                current_pos += 1
                i += 1

        positions = np.concatenate([t_pos, h_pos, w_pos, x_pos])
        return positions, current_pos

    def _alloc_mrope_batch(self, n_tokens: int, embd_dim: int) -> LlamaBatch:
        # Allocate 4 * n_tokens to get enough pos slots for mRoPE layout
        batch = LlamaBatch(n_tokens * self.MROPE_DIMS, embd_dim, 1)
        batch.n_tokens = n_tokens
        return batch

    def _set_embd_mrope(self, batch: LlamaBatch, embeds: np.ndarray,
                        positions: np.ndarray) -> LlamaBatch:
        """Inject embeddings with 4D mRoPE positions into batch."""
        n_tokens = embeds.shape[0]
        if not embeds.flags["C_CONTIGUOUS"]:
            embeds = np.ascontiguousarray(embeds)
        ctypes.memmove(batch.embd, embeds.ctypes.data, embeds.nbytes)

        # Copy 4D positions: positions is [4 * n_tokens] int32
        pos_array = (ctypes.c_int32 * len(positions))(*positions.tolist())
        ctypes.memmove(batch.struct.pos, pos_array, len(positions) * 4)

        for i in range(n_tokens):
            batch.n_seq_id[i] = 1
            batch.seq_id[i][0] = 0
            batch.logits[i] = 1 if i == n_tokens - 1 else 0
        batch.n_tokens = n_tokens
        return batch

    def ocr_batch(
        self,
        images: list,
        prompt: str = "请识别图中的文字",
        max_tokens: int = 512,
        repeat_penalty: float = 1.1,
    ) -> list[str]:
        """Run OCR on multiple PIL images sequentially with one reused llama.cpp context."""
        if self.onnx is None:
            raise RuntimeError("GLM-OCR ONNX encoder is not loaded in this process")

        results: list[str] = []
        for image in images:
            encoded = self.onnx.encode_for_llama(image, prompt)
            results.append(self.decode_precomputed(
                encoded["input_ids"],
                encoded["embeds"],
                encoded["grid_thw"],
                max_tokens=max_tokens,
                repeat_penalty=repeat_penalty,
            ))

        return results

    def decode_precomputed(
        self,
        input_ids,
        embeds,
        grid_thw,
        max_tokens: int = 512,
        repeat_penalty: float = 1.1,
    ) -> str:
        """Decode precomputed ONNX embeddings with the llama.cpp GLM-OCR decoder."""
        input_ids_np = np.asarray(input_ids, dtype=np.int64).reshape(-1)
        embeds_np = np.asarray(embeds, dtype=np.float32)
        if embeds_np.ndim == 3:
            embeds_np = embeds_np[0]
        embeds_np = np.ascontiguousarray(embeds_np)
        grid_thw_np = np.asarray(grid_thw, dtype=np.int64).reshape(-1, 3)

        if embeds_np.shape[0] != input_ids_np.shape[0]:
            raise ValueError(f"embeds length mismatch: {embeds_np.shape[0]} vs {input_ids_np.shape[0]}")
        if embeds_np.shape[1] != self.n_embd:
            raise ValueError(f"embedding dim mismatch: {embeds_np.shape[1]} vs {self.n_embd}")

        self.ctx.clear_kv()
        input_ids_list = input_ids_np.tolist()
        positions, next_pos = self._compute_mrope_positions(input_ids_list, grid_thw_np)

        batch = self._alloc_mrope_batch(len(input_ids_list), self.n_embd)
        self._set_embd_mrope(batch, embeds_np, positions)

        ret = self.ctx.decode(batch)
        if ret != 0:
            raise RuntimeError(f"Prefill decode failed: {ret}")

        sampler = LlamaSampler(temperature=0.0, repeat_penalty=repeat_penalty)
        try:
            token = sampler.sample(self.ctx)
            sampler.accept(token)

            generated: list[int] = []
            for _ in range(max_tokens):
                if token in self.eos_tokens:
                    break
                generated.append(token)

                tok_batch = LlamaBatch(self.MROPE_DIMS, 0, 1)
                tok_batch.n_tokens = 1
                tok_batch.token[0] = token
                tok_batch.n_seq_id[0] = 1
                tok_batch.seq_id[0][0] = 0
                tok_batch.logits[0] = 1
                mrope_pos = (ctypes.c_int32 * 4)(next_pos, next_pos, next_pos, next_pos)
                ctypes.memmove(tok_batch.struct.pos, mrope_pos, 4 * 4)
                next_pos += 1

                ret = self.ctx.decode(tok_batch)
                if ret != 0:
                    break
                token = sampler.sample(self.ctx)
                sampler.accept(token)
        finally:
            sampler.free()

        raw = bytearray()
        for token_id in generated:
            raw.extend(self.model.detokenize(token_id))
        return raw.decode("utf-8", errors="replace").strip()

    def ocr(
        self,
        image,
        prompt: str = "请识别图中的文字",
        max_tokens: int = 512,
        repeat_penalty: float = 1.1,
    ) -> str:
        """Run OCR on a PIL image."""
        return self.ocr_batch([image], prompt, max_tokens, repeat_penalty)[0]


if __name__ == "__main__":
    import argparse
    from PIL import Image

    parser = argparse.ArgumentParser()
    project_dir = Path(__file__).resolve().parents[1]
    parser.add_argument("--image", default=str(project_dir / "tests" / "example.png"))
    parser.add_argument("--gguf", default=str(project_dir / "models" / "GLM-OCR-GGUF" / "GLM-OCR-Q8_0.gguf"))
    parser.add_argument("--onnx-dir", default=str(project_dir / "models" / "export"))
    parser.add_argument("--prompt", default="请识别图中的所有文字")
    parser.add_argument("--max-tokens", type=int, default=512)
    args = parser.parse_args()

    img = Image.open(args.image).convert("RGB")
    print(f"Image: {img.size}")

    engine = GlmOcrLlama(gguf_path=args.gguf, onnx_dir=args.onnx_dir)
    t0 = time.time()
    text = engine.ocr(img, prompt=args.prompt, max_tokens=args.max_tokens)
    dt = time.time() - t0
    print(f"OCR ({dt:.2f}s):\n{text}")
