# coding=utf-8
import json
import base64
import io
import os
import urllib.request
import urllib.error
import numpy as np
from config import (GEMINI_API_URL, EMBED_MODEL_PATH, STEP_API_KEY, STEP_BASE_URL,
                              STEP_MODEL, GEMINI_API_KEY,
                              DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
                              OPENROUTER_KEY, OPENROUTER_BASE_URL,
                              DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_MODEL,
                              MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL,
                              GLM_OCR_GGUF, GLM_OCR_N_GPU_LAYERS,
                              GLM_OCR_ONNX_DIR, GLM_OCR_ONNX_PROVIDER,
                              GLM_OCR_ONNX_PRECISION, GLM_OCR_ONNX_THREADS,
                              GLM_OCR_MODE, GLM_OCR_WORKER_TIMEOUT)


_embed_session = None
_embed_tokenizer = None


def _get_embed_session():
    global _embed_session, _embed_tokenizer
    if _embed_session is None:
        import onnxruntime as ort
        from pathlib import Path
        model_dir = Path(EMBED_MODEL_PATH + "-onnx")
        if not model_dir.exists():
            model_dir = Path(EMBED_MODEL_PATH)
        _embed_session = ort.InferenceSession(str(model_dir / "model.onnx"), providers=["CPUExecutionProvider"])
        from tokenizers import Tokenizer
        _embed_tokenizer = Tokenizer.from_file(str(model_dir / "tokenizer.json"))
        _embed_tokenizer.enable_truncation(max_length=512)
        _embed_tokenizer.enable_padding(length=512)
    return _embed_session, _embed_tokenizer


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    session, tokenizer = _get_embed_session()
    encoded = [tokenizer.encode(t) for t in texts]
    input_ids = np.array([e.ids for e in encoded], dtype=np.int64)
    attention_mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids)
    outputs = session.run(None, {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "token_type_ids": token_type_ids,
    })
    last_hidden = outputs[0]
    mask_expanded = attention_mask[:, :, None].astype(np.float32)
    pooled = (last_hidden * mask_expanded).sum(axis=1) / mask_expanded.sum(axis=1)
    norms = np.linalg.norm(pooled, axis=1, keepdims=True)
    pooled = pooled / (norms + 1e-8)
    return pooled.tolist()


def cosine_similarity(a: list[float], b: list[float]) -> float:
    a_np, b_np = np.array(a), np.array(b)
    return float(np.dot(a_np, b_np) / (np.linalg.norm(a_np) * np.linalg.norm(b_np) + 1e-8))


def call_gemini(payload: dict, timeout: int = 120) -> dict | None:
    if not GEMINI_API_KEY:
        return None
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(GEMINI_API_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        print(f"  API Error {e.code}: {e.read().decode()[:300]}", flush=True)
        return None
    except Exception as e:
        print(f"  API exception: {e}", flush=True)
        return None


def extract_text(result: dict | None) -> str:
    if not result:
        return ""
    for c in result.get("candidates", []):
        for part in c.get("content", {}).get("parts", []):
            t = part.get("text", "")
            if t:
                return t
    return ""


def call_deepseek(prompt: str, system: str = "你是视频分析助手。", max_tokens: int = 1024) -> str:
    return _call_openai_compat(DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, "deepseek-chat", prompt, system, max_tokens)


def call_step(prompt: str, system: str = "你是视频分析助手。", max_tokens: int = 1024) -> str:
    return _call_openai_compat(STEP_BASE_URL, STEP_API_KEY, STEP_MODEL, prompt, system, max_tokens)


def call_step_with_images(prompt: str, images: list, system: str = "你是视频分析助手。", max_tokens: int = 4096) -> str:
    if STEP_API_KEY:
        r = _call_openai_compat(STEP_BASE_URL, STEP_API_KEY, STEP_MODEL, prompt, system, max_tokens, images)
        if r and len(r) > 20:
            return r
    if not GEMINI_API_KEY:
        return ""
    return _call_gemini_vision(prompt, images, system, max_tokens)


def _call_gemini_vision(prompt: str, images: list, system: str, max_tokens: int) -> str:
    if not GEMINI_API_KEY:
        return ""
    parts = [{"text": prompt}]
    for img in images:
        b64 = _pil_to_base64(img) if hasattr(img, 'save') else img
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": b64}})
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "systemInstruction": {"parts": [{"text": system}]},
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            for c in result.get("candidates", []):
                for part in c.get("content", {}).get("parts", []):
                    if part.get("text"):
                        return part["text"]
    except Exception as e:
        print(f"  Gemini vision error: {e}", flush=True)
    return ""


def call_deepseek_tools(messages: list[dict], tools: list[dict], max_tokens: int = 1024) -> dict:
    """Call DeepSeek with tool-calling support. Returns raw response dict."""
    return _call_openai_compat_raw(DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, "deepseek-chat", messages, max_tokens, tools)


def _call_openai_compat_raw(base_url: str, api_key: str, model: str, messages: list[dict], max_tokens: int, tools: list[dict] = None) -> dict:
    """Raw OpenAI-compatible call returning full response dict (for tool-calling)."""
    if not api_key:
        return {}
    url = f"{base_url}/chat/completions"
    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        print(f"  API Error {e.code}: {body}", flush=True)
        return {}
    except Exception as e:
        print(f"  API exception: {e}", flush=True)
        return {}


def _call_openai_compat(base_url: str, api_key: str, model: str, prompt: str, system: str, max_tokens: int, images: list = None) -> str:
    if not api_key:
        return ""
    url = f"{base_url}/chat/completions"
    messages = [{"role": "system", "content": system}]
    if images:
        content = [{"type": "text", "text": prompt}]
        for img in images:
            b64 = _pil_to_base64(img) if hasattr(img, 'save') else img
            content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
        messages.append({"role": "user", "content": content})
    else:
        messages.append({"role": "user", "content": prompt})

    payload = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0}
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            msg = result["choices"][0]["message"]
            content = msg.get("content") or ""
            if not content and (msg.get("reasoning") or msg.get("reasoning_content")):
                content = (msg.get("reasoning") or msg.get("reasoning_content", ""))[:max_tokens]
            return content
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        print(f"  API Error {e.code}: {body}", flush=True)
        return ""
    except Exception as e:
        print(f"  API exception: {e}", flush=True)
        return ""


def _pil_to_base64(img) -> str:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


_glm_ocr_engine = None
_glm_ocr_engine_mode = None


def _get_glm_ocr_engine(load_onnx: bool):
    global _glm_ocr_engine, _glm_ocr_engine_mode
    mode_key = "with_onnx" if load_onnx else "decoder_only"
    if _glm_ocr_engine is not None and _glm_ocr_engine_mode != mode_key:
        if hasattr(_glm_ocr_engine, "close"):
            _glm_ocr_engine.close()
        _glm_ocr_engine = None
        _glm_ocr_engine_mode = None

    if _glm_ocr_engine is None:
        from glm_ocr_llama import GlmOcrLlama
        _glm_ocr_engine = GlmOcrLlama(
            gguf_path=GLM_OCR_GGUF,
            n_gpu_layers=GLM_OCR_N_GPU_LAYERS,
            load_onnx=load_onnx,
        )
        _glm_ocr_engine_mode = mode_key
    return _glm_ocr_engine


def _glm_ocr_runtime_mode() -> str:
    return os.environ.get("VIDUNDER_GLM_OCR_MODE", GLM_OCR_MODE).lower()


def call_glm_ocr(image, prompt="Text Recognition:", max_tokens=2048) -> str:
    from PIL import Image as PILImage
    from pathlib import Path

    if isinstance(image, str) and Path(image).exists():
        image = PILImage.open(image).convert("RGB")
    elif hasattr(image, 'convert'):
        image = image.convert("RGB")
    else:
        return ""

    try:
        mode = _glm_ocr_runtime_mode()
        if mode in ("cuda_isolated", "isolated_cuda"):
            from glm_ocr_worker import get_glm_ocr_onnx_worker

            provider = os.environ.get("VIDUNDER_GLM_OCR_ONNX_PROVIDER")
            if provider is None:
                provider = "cuda"
            precision = os.environ.get("VIDUNDER_GLM_OCR_ONNX_PRECISION", GLM_OCR_ONNX_PRECISION)
            threads = int(os.environ.get("VIDUNDER_GLM_OCR_ONNX_THREADS", str(GLM_OCR_ONNX_THREADS)))
            timeout = int(os.environ.get("VIDUNDER_GLM_OCR_WORKER_TIMEOUT", str(GLM_OCR_WORKER_TIMEOUT)))
            worker = get_glm_ocr_onnx_worker(
                GLM_OCR_ONNX_DIR,
                provider=provider.lower(),
                precision=precision.lower(),
                threads=threads,
                timeout=timeout,
            )
            encoded = worker.infer(image, prompt, timeout=timeout)
            engine = _get_glm_ocr_engine(load_onnx=False)
            return engine.decode_precomputed(
                encoded["input_ids"],
                encoded["embeds"],
                encoded["grid_thw"],
                max_tokens=min(max_tokens, 2048),
            )

        if mode not in ("cpu", "same_process", "legacy"):
            print(f"  Unknown GLM-OCR mode '{mode}', using same-process mode", flush=True)
        engine = _get_glm_ocr_engine(load_onnx=True)
        return engine.ocr(image, prompt=prompt, max_tokens=min(max_tokens, 2048))
    except Exception as e:
        print(f"  GLM-OCR error: {e}", flush=True)
        return ""


def shutdown_glm_ocr_workers(stop_decoder: bool = False) -> None:
    global _glm_ocr_engine, _glm_ocr_engine_mode, _ocr_pool
    try:
        from glm_ocr_worker import shutdown_glm_ocr_onnx_worker
        shutdown_glm_ocr_onnx_worker()
    except Exception:
        pass

    if _ocr_pool is not None:
        _ocr_pool.shutdown(wait=False, cancel_futures=True)
        _ocr_pool = None

    if stop_decoder and _glm_ocr_engine is not None:
        if hasattr(_glm_ocr_engine, "close"):
            _glm_ocr_engine.close()
        _glm_ocr_engine = None
        _glm_ocr_engine_mode = None


# ── Parallel GLM-OCR via multiprocessing ──────────────────────

_ocr_pool = None

def _ocr_worker_init():
    """Each worker process loads its own GlmOcrLlama instance."""
    global _ocr_worker_engine
    from glm_ocr_llama import GlmOcrLlama
    _ocr_worker_engine = GlmOcrLlama(gguf_path=GLM_OCR_GGUF, n_gpu_layers=GLM_OCR_N_GPU_LAYERS)

def _ocr_worker_call(args):
    """Worker function: (image_bytes, prompt, max_tokens) -> text."""
    import io
    from PIL import Image as PILImage
    image_bytes, prompt, max_tokens = args
    try:
        img = PILImage.open(io.BytesIO(image_bytes)).convert("RGB")
        return _ocr_worker_engine.ocr(img, prompt=prompt, max_tokens=min(max_tokens, 2048))
    except Exception as e:
        return f"ERROR: {e}"

def ocr_parallel(images_prompts, num_workers=2):
    """Run GLM-OCR on multiple images in parallel.
    images_prompts: list of (PIL.Image, prompt, max_tokens)
    Returns: list of str results, same order.
    """
    import io
    from concurrent.futures import ProcessPoolExecutor
    global _ocr_pool

    serialized = []
    for img, prompt, max_tokens in images_prompts:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        serialized.append((buf.getvalue(), prompt, max_tokens))

    if _ocr_pool is None:
        _ocr_pool = ProcessPoolExecutor(
            max_workers=num_workers,
            initializer=_ocr_worker_init,
        )

    results = list(_ocr_pool.map(_ocr_worker_call, serialized))
    return results


def call_openrouter(prompt: str, model: str = "google/gemini-2.5-flash",
                    system: str = "You are a helpful assistant.", max_tokens: int = 4096) -> str:
    url = f"{OPENROUTER_BASE_URL}/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {OPENROUTER_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  OpenRouter API error: {e}", flush=True)
        return ""


def call_doubao(prompt: str, system: str = "You are a helpful assistant.", max_tokens: int = 4096) -> str:
    url = f"{DOUBAO_BASE_URL}/chat/completions"
    payload = {
        "model": DOUBAO_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  Doubao API error: {e}", flush=True)
        return ""


def call_doubao_with_image(prompt: str, image_b64: str,
                           system: str = "You are a helpful assistant.", max_tokens: int = 4096) -> str:
    url = f"{DOUBAO_BASE_URL}/chat/completions"
    payload = {
        "model": DOUBAO_MODEL,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                {"type": "text", "text": prompt},
            ]},
        ],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    data = json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DOUBAO_API_KEY}",
    })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode())
            return result["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"  Doubao vision API error: {e}", flush=True)
        return ""


def call_vision_for_corners(image_b64: str, img_width: int, img_height: int,
                            provider: str = "gemini") -> dict | None:
    """Ask a vision model to detect the 4 corner points of the main content area.

    Returns dict with keys: top_left, top_right, bottom_right, bottom_left,
    each containing {"x": int, "y": int}, or None on failure.
    """
    prompt = (
        f"This is a {img_width}x{img_height} image. It may be a screenshot or a photo "
        f"of a screen taken at an angle.\n\n"
        f"Find the 4 corner points of the main content area (the slide/presentation/document). "
        f"Return ONLY a JSON object, no explanation:\n"
        f'{{"top_left":{{"x":int,"y":int}},'
        f'"top_right":{{"x":int,"y":int}},'
        f'"bottom_right":{{"x":int,"y":int}},'
        f'"bottom_left":{{"x":int,"y":int}}}}'
    )
    content_parts = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
    ]

    if provider == "gemini":
        text = _call_openai_compat(
            OPENROUTER_BASE_URL, OPENROUTER_KEY, "google/gemini-2.5-flash",
            prompt, "You detect corners in images. Return JSON only.",
            max_tokens=500, images=[image_b64],
        )
    elif provider == "mimo":
        url = f"{MIMO_BASE_URL}/chat/completions"
        payload = {
            "model": MIMO_MODEL,
            "messages": [{"role": "user", "content": content_parts}],
            "max_completion_tokens": 8192,
            "temperature": 0,
        }
        data = json.dumps(payload, ensure_ascii=False).encode()
        req = urllib.request.Request(url, data=data, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {MIMO_API_KEY}",
        })
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                result = json.loads(resp.read().decode())
                text = result["choices"][0]["message"].get("content", "") or ""
        except Exception as e:
            print(f"  MiMo API error: {e}", flush=True)
            text = ""
    else:
        return None

    if not text:
        return None

    import re
    m = re.search(r'\{[\s\S]*\}', text)
    if not m:
        return None
    try:
        corners = json.loads(m.group())
    except json.JSONDecodeError:
        return None

    required = ("top_left", "top_right", "bottom_right", "bottom_left")
    if not all(k in corners for k in required):
        return None
    for k in required:
        if not isinstance(corners[k], dict) or "x" not in corners[k] or "y" not in corners[k]:
            return None
    return corners


def call_knowledge_llm(prompt: str, max_tokens: int = 4096) -> str:
    """Try Doubao first, then OpenRouter/gemini as fallback for world knowledge."""
    r = call_doubao(prompt, max_tokens=max_tokens)
    if r and len(r) > 50:
        return r
    r = call_openrouter(prompt, model="google/gemini-2.5-flash", max_tokens=max_tokens)
    if r and len(r) > 50:
        return r
    return ""


def ocr_long_image(image, max_chunk_height: int = 1800, overlap: int = 50,
                   prompt: str = "Text Recognition:") -> str:
    if image.height <= max_chunk_height:
        return call_glm_ocr(image, prompt)
    results = []
    y = 0
    while y < image.height:
        bottom = min(y + max_chunk_height, image.height)
        chunk = image.crop((0, y, image.width, bottom))
        results.append(call_glm_ocr(chunk, prompt))
        if bottom >= image.height:
            break
        y = max(bottom - overlap, y + 1)
    if len(results) == 1:
        return results[0]
    merge_prompt = "以下是对同一段内容的多段 OCR 识别结果，内容有重叠。请合并为一份完整、不重复的内容。\n\n"
    for i, r in enumerate(results, 1):
        merge_prompt += f"【第 {i} 段】\n{r}\n\n"
    return call_deepseek(merge_prompt, max_tokens=4096)
