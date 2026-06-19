from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable, Iterable

import numpy as np
import onnxruntime as ort
from PIL import Image
from tokenizers import Tokenizer


class GlmOcrOnnx:
    """Pure ONNX Runtime GLM-OCR inference for one image at a time."""

    import os as _os
    _MODEL_ROOT = _os.environ.get("VIDUNDER_MODEL_ROOT", "")
    if _MODEL_ROOT:
        DEFAULT_MODEL_DIR = Path(_MODEL_ROOT) / "glm-ocr" / "glm-ocr-onnx"
    else:
        DEFAULT_MODEL_DIR = Path(__file__).resolve().parent / "models" / "glm-ocr" / "glm-ocr-onnx"

    def __init__(self, model_dir: str | Path | None = None, max_tokens: int = 2048) -> None:
        self.model_dir = Path(model_dir) if model_dir is not None else self.DEFAULT_MODEL_DIR
        self.onnx_dir = self.model_dir / "onnx"
        self.max_tokens = max_tokens

        with open(self.model_dir / "config.json", "r", encoding="utf-8") as f:
            self.config = json.load(f)
        with open(self.model_dir / "generation_config.json", "r", encoding="utf-8") as f:
            generation_config = json.load(f)

        text_config = self.config["text_config"]
        vision_config = self.config["vision_config"]
        self.num_layers = int(text_config["num_hidden_layers"])
        self.num_kv_heads = int(text_config["num_key_value_heads"])
        self.head_dim = int(text_config["head_dim"])
        self.hidden_size = int(text_config["hidden_size"])
        self.vocab_size = int(text_config["vocab_size"])
        self.eos_token_ids = set(int(x) for x in generation_config["eos_token_id"])
        self.pad_token_id = int(generation_config["pad_token_id"])

        self.image_start_token_id = int(self.config["image_start_token_id"])
        self.image_end_token_id = int(self.config["image_end_token_id"])
        self.image_token_id = int(self.config["image_token_id"])
        self.spatial_merge_size = int(vision_config["spatial_merge_size"])
        self.temporal_patch_size = int(vision_config["temporal_patch_size"])
        self.image_size = int(vision_config["image_size"])
        self.patch_size = int(vision_config["patch_size"])

        self.tokenizer = Tokenizer.from_file(str(self.model_dir / "tokenizer.json"))
        self.providers = self._select_providers()
        self.precision = os.environ.get("VIDUNDER_GLM_OCR_ONNX_PRECISION", "q4").lower()

        vision_onnx = self._select_model_file("vision_encoder", ["q4", "fp32"])
        self.vision_session = self._new_session(vision_onnx)
        embed_onnx = self._select_model_file("embed_tokens", ["q4", "fp32"])
        self.embed_session = self._new_session(embed_onnx)

        # Merger ONNX: proj -> LayerNorm -> GELU -> FFN (projects ViT output to LLM embedding space)
        merger_onnx = self._select_model_file("merger", ["fp16", "fp32"])
        self.merger_session = self._new_session(merger_onnx) if merger_onnx.exists() else None

        self._decoder_session = None
        self._decoder_output_names = None

    def _select_model_file(self, stem: str, default_order: list[str]) -> Path:
        if self.precision == "auto":
            order = default_order
        elif self.precision == "fp32":
            order = ["fp32", "fp16", "q4"]
        elif self.precision == "fp16":
            order = ["fp16", "fp32", "q4"]
        elif self.precision == "q4":
            order = ["q4", "fp16", "fp32"]
        else:
            raise ValueError(f"Unsupported GLM-OCR ONNX precision: {self.precision}")

        for precision in order:
            path = self.onnx_dir / f"{stem}_{precision}.onnx"
            if path.exists():
                return path
        raise FileNotFoundError(f"Missing ONNX file for {stem}; tried {order}")

    @staticmethod
    def _select_providers() -> list[str]:
        mode = os.environ.get("VIDUNDER_GLM_OCR_MODE", "cpu").lower()
        provider = os.environ.get("VIDUNDER_GLM_OCR_ONNX_PROVIDER", "").lower()
        if mode in {"cpu", "same_process", "legacy"}:
            provider = "cpu"
        elif not provider:
            provider = "cuda" if mode in {"cuda_isolated", "isolated_cuda"} else "cpu"
        available = ort.get_available_providers()
        if provider == "cpu":
            return ["CPUExecutionProvider"]
        providers: list[str] = []
        if provider == "cuda" and "CUDAExecutionProvider" in available:
            providers.append("CUDAExecutionProvider")
        providers.append("CPUExecutionProvider")
        return providers

    def _new_session(self, path: Path) -> ort.InferenceSession:
        options = ort.SessionOptions()
        options.log_severity_level = 3
        threads = int(os.environ.get("VIDUNDER_GLM_OCR_ONNX_THREADS", "4"))
        if threads > 0:
            options.intra_op_num_threads = threads
            options.inter_op_num_threads = 1
        try:
            return ort.InferenceSession(str(path), sess_options=options, providers=self.providers)
        except Exception:
            if self.providers != ["CPUExecutionProvider"]:
                self.providers = ["CPUExecutionProvider"]
                return ort.InferenceSession(str(path), sess_options=options, providers=self.providers)
            raise

    def ocr(
        self,
        image: Image.Image,
        prompt: str = "请识别图中的文字",
        max_tokens: int | None = None,
        repeat_penalty: float = 1.1,
        stream_callback: Callable[[str], None] | None = None,
    ) -> str:
        """Run OCR on a PIL image and return the recognized text."""
        limit = self.max_tokens if max_tokens is None else max_tokens
        pixel_values, image_grid_thw = self._preprocess_image(image)
        image_features = self._run_vision_encoder(pixel_values, image_grid_thw)
        num_image_tokens = int(image_features.shape[0])
        input_ids = self._build_input_ids(prompt, num_image_tokens)
        inputs_embeds = self._embed_input_ids(input_ids)
        image_positions = np.where(input_ids[0] == self.image_token_id)[0]
        if len(image_positions) != num_image_tokens:
            raise ValueError(
                f"image token count ({len(image_positions)}) does not match "
                f"vision features ({image_features.shape[0]})"
            )
        inputs_embeds[0, image_positions, :] = image_features.astype(inputs_embeds.dtype, copy=False)

        position_ids, next_position = self._get_rope_index(input_ids, image_grid_thw)
        past = self._empty_past()
        self._recent_tokens: list[int] = []
        attention_mask = np.ones((1, input_ids.shape[1]), dtype=np.int64)
        logits, past = self._run_decoder(inputs_embeds, attention_mask, position_ids, past)
        next_token = self._apply_penalty(logits, repeat_penalty)
        if next_token in self.eos_token_ids:
            return self._decode([]).strip()

        generated: list[int] = []
        streamed = ""
        for _ in range(limit):
            generated.append(next_token)

            text = self._decode(generated)
            if stream_callback is not None and text.startswith(streamed):
                delta = text[len(streamed) :]
                if delta:
                    stream_callback(delta)
                streamed = text

            token_ids = np.array([[next_token]], dtype=np.int64)
            token_embeds = self._embed_input_ids(token_ids)
            attention_mask = np.ones((1, past[0][0].shape[2] + 1), dtype=np.int64)
            decode_position_ids = np.full((3, 1, 1), next_position, dtype=np.int64)
            logits, past = self._run_decoder(token_embeds, attention_mask, decode_position_ids, past)
            next_position += 1
            next_token = self._apply_penalty(logits, repeat_penalty)
            if next_token in self.eos_token_ids:
                break

        return self._decode(generated).strip()

    def _apply_penalty(self, logits: np.ndarray, penalty: float) -> int:
        last_token_logits = logits[0, -1, :]
        if penalty != 1.0:
            for tid in set(self._recent_tokens):
                last_token_logits[tid] /= penalty
        self._recent_tokens.append(int(np.argmax(last_token_logits)))
        if len(self._recent_tokens) > 64:
            self._recent_tokens = self._recent_tokens[-64:]
        return self._recent_tokens[-1]

    def _build_input_ids(self, prompt: str, num_image_tokens: int) -> np.ndarray:
        from jinja2 import Environment

        with open(self.model_dir / "tokenizer_config.json", "r", encoding="utf-8") as f:
            cfg = json.load(f)
        chat_template = cfg.get("chat_template")
        if chat_template is None:
            template_path = self.model_dir / "chat_template.jinja"
            if not template_path.exists():
                raise FileNotFoundError(f"Missing chat template: {template_path}")
            chat_template = template_path.read_text(encoding="utf-8")
        template = Environment().from_string(chat_template)

        messages = [
            {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": prompt}]},
        ]
        rendered = template.render(messages=messages, add_generation_prompt=True, enable_thinking=False)
        raw_ids = self.tokenizer.encode(rendered, add_special_tokens=False).ids

        img_pos = None
        for i, tid in enumerate(raw_ids):
            if tid == self.image_token_id:
                img_pos = i
                break
        if img_pos is None:
            raise ValueError("no image token found in template output")

        ids = (
            raw_ids[:img_pos]
            + [self.image_token_id] * num_image_tokens
            + raw_ids[img_pos + 1 :]
        )
        return np.array([ids], dtype=np.int64)

    def _build_input_ids_simple(self, prompt: str, num_image_tokens: int) -> np.ndarray:
        prefix = "请\n\n\n"
        suffix = f"你说\n{prompt}\n\n\n"
        prefix_ids = self.tokenizer.encode(prefix, add_special_tokens=False).ids
        suffix_ids = self.tokenizer.encode(suffix, add_special_tokens=False).ids
        ids = (
            prefix_ids
            + [self.image_start_token_id]
            + [self.image_token_id] * num_image_tokens
            + [self.image_end_token_id]
            + suffix_ids
        )
        return np.array([ids], dtype=np.int64)

    def _compute_vision_position_ids(self, grid_thw: np.ndarray) -> np.ndarray:
        """Compute (hpos, wpos) position IDs for vision encoder (pure numpy).
        
        Mirrors transformers' get_vision_position_ids for single-image case.
        Returns shape (num_tokens, 2) int64.
        """
        t, h, w = int(grid_thw[0, 0]), int(grid_thw[0, 1]), int(grid_thw[0, 2])
        ms = self.spatial_merge_size

        # hpos: spatial merge pattern along height
        hpos = np.arange(h).reshape(-1, 1) * np.ones((1, w), dtype=np.int32)
        hpos = hpos.reshape(h // ms, ms, w // ms, ms).transpose(0, 2, 1, 3).reshape(-1)

        # wpos: spatial merge pattern along width
        wpos = np.ones((h, 1), dtype=np.int32) * np.arange(w).reshape(1, -1)
        wpos = wpos.reshape(h // ms, ms, w // ms, ms).transpose(0, 2, 1, 3).reshape(-1)

        # Stack and repeat for temporal dim
        pos = np.stack([hpos, wpos], axis=-1)  # (h*w, 2)
        pos = np.tile(pos, (t, 1))  # (t*h*w, 2)
        return pos.astype(np.int64)

    def _run_vision_encoder(self, pixel_values: np.ndarray, grid_thw: np.ndarray) -> np.ndarray:
        input_names = {inp.name for inp in self.vision_session.get_inputs()}
        feeds: dict[str, np.ndarray] = {"pixel_values": pixel_values}
        if "position_ids" in input_names:
            feeds["position_ids"] = self._compute_vision_position_ids(grid_thw)
        elif "image_grid_thw" in input_names:
            feeds["image_grid_thw"] = grid_thw
        features = self.vision_session.run(None, feeds)[0]
        if self.merger_session is not None:
            merger_input_type = self.merger_session.get_inputs()[0].type
            if merger_input_type == "tensor(float16)":
                features = features.astype(np.float16, copy=False)
            elif merger_input_type == "tensor(float)":
                features = features.astype(np.float32, copy=False)
            features = self.merger_session.run(None, {"hidden_states": features})[0]
        return features

    def _encode_image(self, image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        pixel_values, grid_thw = self._preprocess_image(image)
        image_features = self._run_vision_encoder(pixel_values, grid_thw)
        return image_features, grid_thw

    def encode_for_llama(self, image: Image.Image, prompt: str) -> dict[str, np.ndarray]:
        """Prepare GLM-OCR llama.cpp inputs without running the decoder."""
        image_features, image_grid_thw = self._encode_image(image)
        num_image_tokens = int(image_features.shape[0])
        input_ids = self._build_input_ids(prompt, num_image_tokens)
        inputs_embeds = self._embed_input_ids(input_ids)

        image_positions = np.where(input_ids[0] == self.image_token_id)[0]
        if len(image_positions) != num_image_tokens:
            raise ValueError(
                f"image token count ({len(image_positions)}) does not match "
                f"vision features ({image_features.shape[0]})"
            )
        inputs_embeds[0, image_positions, :] = image_features.astype(inputs_embeds.dtype, copy=False)

        return {
            "input_ids": np.ascontiguousarray(input_ids[0].astype(np.int64, copy=False)),
            "embeds": np.ascontiguousarray(inputs_embeds[0].astype(np.float32, copy=False)),
            "grid_thw": np.ascontiguousarray(image_grid_thw.astype(np.int64, copy=False)),
        }

    def _smart_resize(self, height: int, width: int) -> tuple[int, int]:
        factor = self.patch_size * self.spatial_merge_size  # 28
        size_cfg_path = self.model_dir / "processor_config.json"
        with open(size_cfg_path, "r", encoding="utf-8") as f:
            proc_cfg = json.load(f)
        size_info = proc_cfg.get("image_processor", {}).get("size", {})
        min_pixels = int(size_info.get("shortest_edge", 56 * factor))
        max_pixels_raw = int(size_info.get("longest_edge", 4 * min_pixels))
        max_pixels = min(max_pixels_raw, 1_000_000)

        beta = 1.0
        if height * width > max_pixels:
            beta = float(np.sqrt(max_pixels / (height * width)))

        h_bar = max(factor, round(height * beta / factor) * factor)
        w_bar = max(factor, round(width * beta / factor) * factor)

        while h_bar * w_bar > max_pixels and beta > 0:
            beta *= 0.9
            h_bar = max(factor, round(height * beta / factor) * factor)
            w_bar = max(factor, round(width * beta / factor) * factor)
        return int(h_bar), int(w_bar)

    def _preprocess_image(self, image: Image.Image) -> tuple[np.ndarray, np.ndarray]:
        orig_w, orig_h = image.size
        target_h, target_w = self._smart_resize(orig_h, orig_w)

        image = image.convert("RGB").resize((target_w, target_h), Image.Resampling.BICUBIC)
        array = np.asarray(image, dtype=np.float32) / 255.0
        mean = np.array([0.48145466, 0.4578275, 0.40821073], dtype=np.float32)
        std = np.array([0.26862954, 0.26130258, 0.27577711], dtype=np.float32)
        array = (array - mean) / std
        array = array.transpose(2, 0, 1)  # (H, W, C) -> (C, H, W)
        frames = np.stack([array] * self.temporal_patch_size, axis=0)  # (T, C, H, W)

        grid_t = 1
        grid_h = target_h // self.patch_size
        grid_w = target_w // self.patch_size
        patches = frames.reshape(
            grid_t,
            self.temporal_patch_size,
            3,
            grid_h // self.spatial_merge_size,
            self.spatial_merge_size,
            self.patch_size,
            grid_w // self.spatial_merge_size,
            self.spatial_merge_size,
            self.patch_size,
        )
        patches = patches.transpose(0, 3, 6, 4, 7, 2, 1, 5, 8)
        patches = patches.reshape(
            grid_t * grid_h * grid_w,
            3 * self.temporal_patch_size * self.patch_size * self.patch_size,
        )
        grid_thw = np.array([[grid_t, grid_h, grid_w]], dtype=np.int64)
        return np.ascontiguousarray(patches), grid_thw

    def _embed_input_ids(self, input_ids: np.ndarray) -> np.ndarray:
        return self.embed_session.run(None, {"input_ids": input_ids.astype(np.int64, copy=False)})[0]

    def _get_rope_index(self, input_ids: np.ndarray, image_grid_thw: np.ndarray) -> tuple[np.ndarray, int]:
        batch, seq_len = input_ids.shape
        position_ids = np.zeros((3, batch, seq_len), dtype=np.int64)
        image_idx = 0
        next_positions: list[int] = []

        for b in range(batch):
            ids = input_ids[b]
            current_pos = 0
            i = 0
            while i < len(ids):
                if ids[i] == self.image_start_token_id:
                    # image_start gets current position (same as text)
                    position_ids[:, b, i] = current_pos
                    i += 1
                    img_start = i
                    while i < len(ids) and ids[i] == self.image_token_id:
                        i += 1
                    t, h, w = image_grid_thw[image_idx]
                    image_idx += 1
                    llm_t = int(t)
                    llm_h = int(h) // self.spatial_merge_size
                    llm_w = int(w) // self.spatial_merge_size
                    num_img_tokens = llm_t * llm_h * llm_w
                    img_end = img_start + num_img_tokens
                    if img_end > i:
                        raise ValueError("not enough image tokens for image_grid_thw")

                    t_pos = np.repeat(np.arange(llm_t), llm_h * llm_w) + current_pos
                    h_pos = np.repeat(np.tile(np.arange(llm_h), llm_w), llm_t) + current_pos
                    w_pos = np.tile(np.arange(llm_w), llm_h * llm_t) + current_pos
                    position_ids[0, b, img_start:img_end] = t_pos
                    position_ids[1, b, img_start:img_end] = h_pos
                    position_ids[2, b, img_start:img_end] = w_pos

                    # image_end is text (type=0), position starts after image advance
                    current_pos += max(int(h), int(w)) // self.spatial_merge_size
                    position_ids[:, b, i] = current_pos
                    current_pos += 1
                    i += 1
                else:
                    position_ids[:, b, i] = current_pos
                    current_pos += 1
                    i += 1
            next_positions.append(current_pos)

        if len(set(next_positions)) != 1:
            raise ValueError("batched decoding is not supported")
        return position_ids, next_positions[0]

    def _empty_past(self) -> list[tuple[np.ndarray, np.ndarray]]:
        empty_shape = (1, self.num_kv_heads, 0, self.head_dim)
        return [
            (
                np.empty(empty_shape, dtype=np.float32),
                np.empty(empty_shape, dtype=np.float32),
            )
            for _ in range(self.num_layers)
        ]

    @property
    def decoder_session(self):
        if self._decoder_session is None:
            self._decoder_session = self._new_session(self.onnx_dir / "decoder_layers_q4.onnx")
            self._decoder_output_names = [out.name for out in self._decoder_session.get_outputs()]
        return self._decoder_session

    @property
    def decoder_output_names(self):
        if self._decoder_output_names is None:
            _ = self.decoder_session
        return self._decoder_output_names

    def _run_decoder(
        self,
        inputs_embeds: np.ndarray,
        attention_mask: np.ndarray,
        position_ids: np.ndarray,
        past: Iterable[tuple[np.ndarray, np.ndarray]],
    ) -> tuple[np.ndarray, list[tuple[np.ndarray, np.ndarray]]]:
        feeds: dict[str, np.ndarray] = {
            "inputs_embeds": inputs_embeds.astype(np.float32, copy=False),
            "attention_mask": attention_mask.astype(np.int64, copy=False),
            "position_ids": position_ids.astype(np.int64, copy=False),
            "num_logits_to_keep": np.array(1, dtype=np.int64),
        }
        for layer, (key, value) in enumerate(past):
            feeds[f"past_key_values.{layer}.key"] = key.astype(np.float32, copy=False)
            feeds[f"past_key_values.{layer}.value"] = value.astype(np.float32, copy=False)

        outputs = self.decoder_session.run(self.decoder_output_names, feeds)
        logits = outputs[0]
        present: list[tuple[np.ndarray, np.ndarray]] = []
        offset = 1
        for _ in range(self.num_layers):
            present.append((outputs[offset], outputs[offset + 1]))
            offset += 2
        return logits, present

    def _decode(self, token_ids: list[int]) -> str:
        if not token_ids:
            return ""
        return self.tokenizer.decode(token_ids, skip_special_tokens=True)


__all__ = ["GlmOcrOnnx"]
