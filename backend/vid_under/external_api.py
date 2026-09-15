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
                              MIMO_API_KEY, MIMO_BASE_URL, MIMO_MODEL,
                              GLM_OCR_GGUF, GLM_OCR_N_GPU_LAYERS,
                              GLM_OCR_ONNX_DIR, GLM_OCR_ONNX_PROVIDER,
                              GLM_OCR_ONNX_PRECISION, GLM_OCR_ONNX_THREADS,
                              GLM_OCR_WORKER_TIMEOUT)


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


def _embed_texts_bge(texts: list[str]) -> list[list[float]]:
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


# ── WeMM 编码后端 ──────────────────────────────────────────────
# WeMM 跑在常驻子进程里，用 stdin/stdout 通信。两个后端协议相同，用 VIDUNDER_WEMM_BACKEND 选：
#   onnx（默认）：wemm_onnx_server.py，只需要 onnxruntime-gpu 1.30 以上（GatedDeltaNet 算子），不需要 torch。
#                 权重是 NF4 副本的原样搬运，与 torch 版向量余弦约 0.999，torch 建的旧索引照常能查。
#   torch：wemm_embed_server.py，sentence-transformers + bitsandbytes，跑在 wemm-venv 里。
# 实测：字幕行粒度上 WeMM 比 bge 显著更好（549 语音 0.50->0.79，548 0.46->0.76，
# 两个视频的置信区间都不跨 0）；caption 粒度收益跨 0，所以只在字幕行检索上启用。
WEMM_BACKEND = os.environ.get("VIDUNDER_WEMM_BACKEND", "onnx").strip().lower()
# 后端: (默认解释器, 服务脚本, MODEL_ROOT/wemm/ 下的模型目录, 判断模型已下载完整的文件)
_WEMM_BACKENDS = {
    "onnx": ("/media/jju/ExtraDisk/models/wemm-onnx-venv/bin/python", "wemm_onnx_server.py",
             "WeMM-Embedding-4B-onnx-nf4", os.path.join("decoder", "model.onnx.data")),
    "torch": ("/media/jju/ExtraDisk/models/wemm-venv/bin/python", "wemm_embed_server.py",
              "WeMM-Embedding-4B-nf4", "model.safetensors"),
}
_wemm_python, _wemm_script, WEMM_MODEL_DIRNAME, _WEMM_MODEL_MARKER = _WEMM_BACKENDS.get(
    WEMM_BACKEND, _WEMM_BACKENDS["onnx"])
if WEMM_BACKEND != "torch" and not os.path.isfile(_wemm_python):
    import sys as _sys
    _wemm_python = _sys.executable               # Docker 镜像里 onnxruntime 就装在主环境
WEMM_PYTHON = os.environ.get("VIDUNDER_WEMM_PYTHON", _wemm_python)
WEMM_SERVER = os.environ.get("VIDUNDER_WEMM_SERVER",
                             os.path.join(os.path.dirname(os.path.abspath(__file__)), _wemm_script))
WEMM_READY_TIMEOUT = float(os.environ.get("VIDUNDER_WEMM_READY_TIMEOUT", "600"))
WEMM_CALL_TIMEOUT = float(os.environ.get("VIDUNDER_WEMM_CALL_TIMEOUT", "300"))
# 实测常驻进程占 4.75 GB（torch）/ 4.8 GB（ONNX），留点余量按 5 GB 申请名额
WEMM_NEED_GB = float(os.environ.get("VIDUNDER_WEMM_NEED_GB", "5"))

_wemm_proc = None
_wemm_failed = False
_wemm_slot = None


def _wemm_start():
    """拉起常驻编码进程。冷启动约 10 秒（预量化副本）/ 300 秒（未量化原版）。

    先申请一个跨进程 GPU 名额。名额数按显卡显存算：16GB 单卡只有 1 个，所以同一台
    机器上不会同时跑起第二个 WeMM；32GB 或双卡会算出更多，自动放开并发。
    申请不到名额时返回 None 让调用方回落 bge，但**不**置 _wemm_failed ——
    那是暂时性的资源竞争，过会儿可能就有名额了，而模型缺失才是永久性失败。
    """
    global _wemm_proc, _wemm_failed, _wemm_slot
    if _wemm_proc is not None and _wemm_proc.poll() is None:
        return _wemm_proc
    if _wemm_proc is not None:
        # 上一个服务已经死了：先还它占的名额。名额记的是本进程 PID，本进程活着就不会被当僵死锁回收，
        # 16GB 卡上只有 1 个名额，不还的话之后每次都申请不到
        _wemm_proc = None
        if _wemm_slot is not None:
            try:
                import gpu_slots
                gpu_slots.release(_wemm_slot)
            except ImportError:
                pass
            _wemm_slot = None
    if _wemm_failed:
        return None
    import select
    import subprocess
    import time
    if not os.path.isfile(WEMM_SERVER) or not os.path.isfile(WEMM_PYTHON):
        _wemm_failed = True
        print("  [wemm] 找不到解释器或服务脚本，回落 bge", flush=True)
        return None

    slot = None
    try:
        import gpu_slots
    except ImportError:
        gpu_slots = None
    if gpu_slots is not None:
        slot = gpu_slots.acquire(need_gb=WEMM_NEED_GB, tag="wemm")
        if slot is None:
            print("  [wemm] 无空闲 GPU 名额（本机共 %d 个），本次回落 bge"
                  % len(gpu_slots.plan(need_gb=WEMM_NEED_GB)), flush=True)
            return None

    env = dict(os.environ)
    if not env.get("VIDUNDER_WEMM_MODEL"):
        # 从设置页下载的模型放在 MODEL_ROOT/wemm/ 下；没下载的机器交给服务端用它自己的默认路径
        try:
            from config import MODEL_ROOT
            downloaded = os.path.join(str(MODEL_ROOT), "wemm", WEMM_MODEL_DIRNAME)
            if os.path.isfile(os.path.join(downloaded, _WEMM_MODEL_MARKER)):
                env["VIDUNDER_WEMM_MODEL"] = downloaded
        except Exception:
            pass
    if slot is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(slot[1])   # 多卡时把进程钉在分到的那张卡上
    proc = subprocess.Popen([WEMM_PYTHON, WEMM_SERVER],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env)
    deadline = time.time() + WEMM_READY_TIMEOUT
    while time.time() < deadline:
        if proc.stdout in select.select([proc.stdout], [], [], 1.0)[0]:
            line = proc.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if msg.get("ready"):
                _wemm_proc = proc
                _wemm_slot = slot
                return proc
            if msg.get("ok") is False:
                print("  [wemm] 启动失败: %s，回落 bge" % msg.get("error"), flush=True)
                break
        if proc.poll() is not None:
            break
    try:
        proc.kill()
    except OSError:
        pass
    if slot is not None and gpu_slots is not None:
        gpu_slots.release(slot)                      # 起不来就别占着名额
    _wemm_failed = True
    print("  [wemm] 未能就绪，回落 bge", flush=True)
    return None


def _embed_texts_wemm(texts):
    """成功返回向量列表，任何失败返回 None 交给调用方回落 bge。"""
    global _wemm_proc, _wemm_slot
    proc = _wemm_start()
    if proc is None:
        return None
    import base64
    import select
    import time
    try:
        proc.stdin.write(json.dumps({"texts": list(texts)}, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        deadline = time.time() + WEMM_CALL_TIMEOUT
        while time.time() < deadline:
            if proc.stdout in select.select([proc.stdout], [], [], 1.0)[0]:
                line = proc.stdout.readline()
                if not line:
                    break
                resp = json.loads(line)
                if not resp.get("ok"):
                    print("  [wemm] 编码失败: %s，回落 bge" % resp.get("error"), flush=True)
                    return None
                buf = base64.b64decode(resp["b64"])
                arr = np.frombuffer(buf, dtype=np.float32).reshape(resp["n"], resp["dim"])
                return arr.tolist()
            if proc.poll() is not None:
                break
    except Exception as exc:
        print("  [wemm] 通信异常 %s: %s，回落 bge" % (type(exc).__name__, exc), flush=True)
    _wemm_proc = None
    if _wemm_slot is not None:                       # 进程没了，名额要还回去
        try:
            import gpu_slots
            gpu_slots.release(_wemm_slot)
        except ImportError:
            pass
        _wemm_slot = None
    return None


WEMM_IDLE_SECONDS = float(os.environ.get("VIDUNDER_WEMM_IDLE_SECONDS", "300"))
_wemm_idle_timer = None


def _wemm_touch(restart=True):
    """空闲计时：一段时间没人编码就自己退出，别一直占着 5GB 显存挡住转录和 OCR。"""
    global _wemm_idle_timer
    import threading
    if _wemm_idle_timer is not None:
        _wemm_idle_timer.cancel()
        _wemm_idle_timer = None
    if restart and WEMM_IDLE_SECONDS > 0:
        _wemm_idle_timer = threading.Timer(WEMM_IDLE_SECONDS, _wemm_shutdown)
        _wemm_idle_timer.daemon = True
        _wemm_idle_timer.start()


def wemm_release():
    """立刻关掉常驻 WeMM 服务、让出显存。建完一次索引就调。"""
    _wemm_touch(restart=False)
    _wemm_shutdown()


def embed_items_wemm(items, fps=2.0, video_max_tokens=None):
    """文字和视频片段合编成 WeMM 向量，给 find_clips 的索引和查询用。

    和 embed_texts 不同，失败直接抛异常、不回落 bge：索引是 2560 维，bge 是 512 维，混了就算不了余弦。
    items 形如 [{"text": "...", "video": "/path/clip.mp4"}]，两个键至少给一个。
    """
    global _wemm_proc, _wemm_slot
    import base64
    import select
    import time
    _wemm_touch(restart=False)
    proc = _wemm_start()
    if proc is None:
        raise RuntimeError("WeMM embedding server is unavailable "
                           "(model missing, or not enough free GPU memory)")
    req = {"items": list(items), "fps": float(fps)}
    if video_max_tokens:
        req["video_max_tokens"] = int(video_max_tokens)
    error = "WeMM embedding server died or timed out"
    try:
        proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        proc.stdin.flush()
        deadline = time.time() + WEMM_CALL_TIMEOUT
        while time.time() < deadline:
            if proc.stdout in select.select([proc.stdout], [], [], 1.0)[0]:
                line = proc.stdout.readline()
                if not line:
                    break
                resp = json.loads(line)
                if not resp.get("ok"):
                    _wemm_touch()
                    raise RuntimeError("WeMM encode failed: %s" % resp.get("error"))
                arr = np.frombuffer(base64.b64decode(resp["b64"]), dtype=np.float32)
                _wemm_touch()
                return arr.reshape(resp["n"], resp["dim"])
            if proc.poll() is not None:
                break
    except RuntimeError:
        raise
    except Exception as exc:
        error = "WeMM communication error %s: %s" % (type(exc).__name__, exc)
    # 进程挂了或超时：清掉句柄、还名额，下次调用会重新拉起
    _wemm_proc = None
    if _wemm_slot is not None:
        try:
            import gpu_slots
            gpu_slots.release(_wemm_slot)
        except ImportError:
            pass
        _wemm_slot = None
    raise RuntimeError(error)


def _wemm_shutdown():
    """进程正常退出时收掉常驻服务并归还名额，别留下占着显存又不在账上的孤儿。"""
    global _wemm_proc, _wemm_slot
    proc, _wemm_proc = _wemm_proc, None
    if proc is not None and proc.poll() is None:
        try:
            proc.stdin.close()
        except Exception:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=10)
        except Exception:
            try:
                proc.kill()
            except OSError:
                pass
    if _wemm_slot is not None:
        try:
            import gpu_slots
            gpu_slots.release(_wemm_slot)
        except ImportError:
            pass
        _wemm_slot = None


import atexit as _atexit

_atexit.register(_wemm_shutdown)


def embed_texts(texts: list[str], backend: str | None = None) -> list[list[float]]:
    """backend="wemm" 时走 WeMM（2560 维），否则走 bge（512 维）。

    注意：查询必须和它要比对的那张向量表用同一个 backend，否则维度对不上。
    WeMM 不可用时自动回落 bge，调用方需按维度判断是否重建向量表。
    设 VIDUNDER_WEMM_EMBED=0 可全局关掉 WeMM。
    """
    if not texts:
        return []
    if backend == "wemm" and os.environ.get("VIDUNDER_WEMM_EMBED", "1") != "0":
        vecs = _embed_texts_wemm(texts)
        if vecs is not None:
            return vecs
    return _embed_texts_bge(texts)


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


def call_deepseek(prompt: str, system: str = "你是视频分析助手。", max_tokens: int = 1024,
                  model: str | None = None, timeout: int = 120) -> str:
    return _call_openai_compat(DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, model or llm_model_name(), prompt, system, max_tokens,
                               timeout=timeout)


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


def call_deepseek_tools(messages: list[dict], tools: list[dict], max_tokens: int = 1024, model: str | None = None) -> dict:
    """Call DeepSeek with tool-calling support. Returns raw response dict."""
    return _call_openai_compat_raw(DEEPSEEK_BASE_URL, DEEPSEEK_API_KEY, model or llm_model_name(), messages, max_tokens, tools)


def llm_model_name() -> str:
    """The one model for chapter detection, chapter summaries and video Q&A.

    It comes from the "Summary and Q&A LLM" setting (config.DEEPSEEK_MODEL, set by the Django task layer).
    """
    import config as _cfg
    return (getattr(_cfg, "DEEPSEEK_MODEL", "") or "deepseek-flash").strip()


def _strip_reasoning(messages: list[dict]) -> list[dict]:
    return [{k: v for k, v in m.items() if k != "reasoning_content"} for m in messages]


def call_deepseek_tools_stream(messages: list[dict], tools: list[dict], max_tokens: int = 8192,
                               on_delta=None, model: str | None = None, cancel=None,
                               timeout: int = 180) -> dict:
    """Streaming variant of call_deepseek_tools.

    on_delta(kind, text) receives kind "reasoning" or "content" while tokens arrive. The return
    value keeps the non-streaming shape {"choices": [{"message": ..., "finish_reason": ...}]},
    so callers handle both the same way. Returns {} on failure or cancellation.
    """
    if not DEEPSEEK_API_KEY:
        return {}
    payload = {"model": model or llm_model_name(), "messages": messages,
               "max_tokens": max_tokens, "stream": True}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {DEEPSEEK_API_KEY}"}
    for attempt in (1, 2):
        req = urllib.request.Request(f"{DEEPSEEK_BASE_URL}/chat/completions",
                                     data=json.dumps(payload, ensure_ascii=False).encode(), headers=headers)
        content, reasoning, calls, finish = [], [], {}, ""
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                for raw in resp:
                    if cancel is not None and cancel.is_set():
                        return {}
                    line = raw.decode("utf-8", "ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except ValueError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    delta = choice.get("delta") or {}
                    piece = delta.get("reasoning_content") or delta.get("reasoning")
                    if piece:
                        reasoning.append(piece)
                        if on_delta:
                            on_delta("reasoning", piece)
                    piece = delta.get("content")
                    if piece:
                        content.append(piece)
                        if on_delta:
                            on_delta("content", piece)
                    for tc in delta.get("tool_calls") or []:
                        slot = calls.setdefault(tc.get("index", 0), {
                            "id": "", "type": "function", "function": {"name": "", "arguments": ""}})
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        slot["function"]["name"] += fn.get("name") or ""
                        slot["function"]["arguments"] += fn.get("arguments") or ""
                    if choice.get("finish_reason"):
                        finish = choice["finish_reason"]
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500]
            # 有的思考模式版本不接受历史里回传的 reasoning_content：去掉后重试一次
            if attempt == 1 and e.code == 400 and "reasoning" in body:
                payload["messages"] = _strip_reasoning(messages)
                continue
            print(f"  API Error {e.code}: {body}", flush=True)
            return {}
        except Exception as e:
            print(f"  API stream exception: {e}", flush=True)
            return {}
        message = {"role": "assistant", "content": "".join(content)}
        if reasoning:
            message["reasoning_content"] = "".join(reasoning)
        if calls:
            message["tool_calls"] = [calls[i] for i in sorted(calls)]
        return {"choices": [{"message": message, "finish_reason": finish}]}
    return {}


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


def _call_openai_compat(base_url: str, api_key: str, model: str, prompt: str, system: str, max_tokens: int, images: list = None, timeout: int = 120) -> str:
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
        with urllib.request.urlopen(req, timeout=timeout) as resp:
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


def _glm_ocr_onnx_provider() -> str:
    provider = os.environ.get("VIDUNDER_GLM_OCR_ONNX_PROVIDER", GLM_OCR_ONNX_PROVIDER)
    provider = provider.strip().lower()
    if provider in {"cuda", "cuda_isolated", "isolated_cuda"}:
        return "cuda"
    if provider in {"cpu", "same_process", "legacy"}:
        return "cpu"
    return provider


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
        provider = _glm_ocr_onnx_provider()
        if provider == "cuda":
            from glm_ocr_worker import get_glm_ocr_onnx_worker

            precision = os.environ.get("VIDUNDER_GLM_OCR_ONNX_PRECISION", GLM_OCR_ONNX_PRECISION)
            threads = int(os.environ.get("VIDUNDER_GLM_OCR_ONNX_THREADS", str(GLM_OCR_ONNX_THREADS)))
            timeout = int(os.environ.get("VIDUNDER_GLM_OCR_WORKER_TIMEOUT", str(GLM_OCR_WORKER_TIMEOUT)))
            worker = get_glm_ocr_onnx_worker(
                GLM_OCR_ONNX_DIR,
                provider=provider,
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

        if provider != "cpu":
            print(f"  Unknown GLM-OCR ONNX provider '{provider}', using CPU same-process mode", flush=True)
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
