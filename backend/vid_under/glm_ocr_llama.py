# coding=utf-8
"""GLM-OCR hybrid inference: ONNX vision encoder + llama.cpp ctypes decoder."""
import time
import json
import ctypes
from pathlib import Path

import numpy as np

from llama_cpp_bindings import (
    LlamaModel, LlamaContext, LlamaBatch, LlamaSampler
)

from config import GLM_OCR_ONNX_DIR
from glm_ocr_onnx import GlmOcrOnnx


class GlmOcrLlama:
    """GLM-OCR inference using ONNX vision encoder + llama.cpp LLM decoder."""

    MROPE_DIMS = 4  # llama.cpp uses 4 position IDs per token for mRoPE

    def __init__(
        self,
        gguf_path: str = "",
        onnx_dir: str | None = None,
        n_ctx: int = 4096,
        n_gpu_layers: int = 99,
    ):
        if not gguf_path:
            raise ValueError("gguf_path is required (e.g. 'models/GLM-OCR-GGUF/GLM-OCR-Q8_0.gguf')")
        if onnx_dir is None:
            onnx_dir = GLM_OCR_ONNX_DIR

        self.onnx = GlmOcrOnnx(onnx_dir, max_tokens=2048)

        self.model = LlamaModel(gguf_path, n_gpu_layers=n_gpu_layers)
        self.n_embd = self.model.n_embd
        self.ctx = LlamaContext(self.model, n_ctx=n_ctx, n_batch=n_ctx)

        with open(Path(onnx_dir) / "config.json") as f:
            cfg = json.load(f)
        self.eos_tokens = set(cfg["text_config"]["eos_token_id"])
        self.image_start_token_id = cfg["image_start_token_id"]
        self.image_end_token_id = cfg["image_end_token_id"]
        self.image_token_id = cfg["image_token_id"]
        self.mrope_section = cfg["text_config"]["rope_parameters"]["mrope_section"]
        self.spatial_merge_size = cfg["vision_config"]["spatial_merge_size"]

    def close(self) -> None:
        self.ctx = None
        self.model = None
        self.onnx = None
        import gc
        gc.collect()

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _build_input_ids(self, prompt: str, num_image_tokens: int) -> list[int]:
        """Build token IDs using the ONNX module's Jinja template."""
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
        results: list[str] = []
        for image in images:
            self.ctx.clear_kv()

            # 1. ONNX vision encoder
            pixel_values, grid_thw = self.onnx._preprocess_image(image)
            image_features = self.onnx._run_vision_encoder(pixel_values, grid_thw)
            num_image_tokens = int(image_features.shape[0])

            # 2. Build input IDs and embeddings
            input_ids = self._build_input_ids(prompt, num_image_tokens)
            embeds = self.onnx._embed_input_ids(np.array([input_ids], dtype=np.int64))

            img_positions = [i for i, tid in enumerate(input_ids) if tid == self.image_token_id]
            if len(img_positions) != num_image_tokens:
                raise ValueError(
                    f"image token count mismatch: {len(img_positions)} vs {num_image_tokens}"
                )
            embeds[0, img_positions, :] = image_features.astype(embeds.dtype, copy=False)

            # 3. Compute 4D mRoPE positions
            positions, next_pos = self._compute_mrope_positions(input_ids, grid_thw)

            # 4. Prefill
            batch = self._alloc_mrope_batch(len(input_ids), self.n_embd)
            self._set_embd_mrope(batch, embeds[0], positions)

            ret = self.ctx.decode(batch)
            if ret != 0:
                raise RuntimeError(f"Prefill decode failed: {ret}")

            sampler = LlamaSampler(temperature=0.0, repeat_penalty=repeat_penalty)
            token = sampler.sample(self.ctx)
            sampler.accept(token)

            # 5. Auto-regressive decode
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

            sampler.free()
            raw = bytearray()
            for t in generated:
                raw.extend(self.model.detokenize(t))
            results.append(raw.decode("utf-8", errors="replace").strip())

        return results

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
