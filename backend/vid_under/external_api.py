# coding=utf-8
import json
import base64
import io
import urllib.request
import urllib.error
import numpy as np
from config import (GEMINI_API_URL, EMBED_MODEL_PATH, STEP_API_KEY, STEP_BASE_URL,
                              STEP_MODEL,
                              DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL,
                              OPENROUTER_KEY, OPENROUTER_BASE_URL, OPENROUTER_MODEL,
                              DOUBAO_API_KEY, DOUBAO_BASE_URL, DOUBAO_MODEL,
                              MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL,
                              GLM_OCR_GGUF, GLM_OCR_N_GPU_LAYERS)


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
    import numpy as np
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


def call_step_with_images(prompt: str, images: list, system: str = "你是视频分析助手。", max_tokens: int = 1024) -> str:
    return _call_openai_compat(OPENROUTER_BASE_URL, OPENROUTER_KEY, "stepfun/step-3.7-flash", prompt, system, max_tokens, images)


def call_deepseek_tools(messages: list[dict], tools: list[dict], max_tokens: int = 1024) -> dict:
    """Call DeepSeek with tool-calling support. Returns raw response dict."""
    return _call_openai_compat_raw(DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, "deepseek-chat", messages, max_tokens, tools)


def _call_openai_compat_raw(base_url: str, api_key: str, model: str, messages: list[dict], max_tokens: int, tools: list[dict] = None) -> dict:
    """Raw OpenAI-compatible call returning full response dict (for tool-calling)."""
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
            return result["choices"][0]["message"]["content"]
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

def call_glm_ocr(image, prompt="Text Recognition:", max_tokens=2048) -> str:
    global _glm_ocr_engine
    from PIL import Image as PILImage
    from pathlib import Path

    if isinstance(image, str) and Path(image).exists():
        image = PILImage.open(image).convert("RGB")
    elif hasattr(image, 'convert'):
        image = image.convert("RGB")
    else:
        return ""

    if _glm_ocr_engine is None:
        from glm_ocr_llama import GlmOcrLlama
        _glm_ocr_engine = GlmOcrLlama(
            gguf_path=GLM_OCR_GGUF,
            n_gpu_layers=GLM_OCR_N_GPU_LAYERS,
        )

    try:
        return _glm_ocr_engine.ocr(image, prompt=prompt, max_tokens=min(max_tokens, 2048))
    except Exception as e:
        print(f"  GLM-OCR ctypes error: {e}", flush=True)
        return ""


def call_openrouter(prompt: str, model: str = None,
                    system: str = "You are a helpful assistant.", max_tokens: int = 4096) -> str:
    model = model or OPENROUTER_MODEL
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
            OPENROUTER_BASE_URL, OPENROUTER_KEY, OPENROUTER_MODEL,
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
    r = call_openrouter(prompt, model=OPENROUTER_MODEL, max_tokens=max_tokens)
    if r and len(r) > 50:
        return r
    return ""
