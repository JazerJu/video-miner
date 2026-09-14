# coding=utf-8
"""WeMM-Embedding-4B 常驻编码服务。

本环境（autocut312）没有 torch，所以 WeMM 只能跑在独立的 wemm-venv 里，
由 external_api 以常驻子进程方式拉起，避免每次调用都重新加载 9.7GB 权重。

协议（stdin/stdout 逐行 JSON）：
    请求  {"texts": [...], "batch_size": 8}
          {"items": [{"text": "...", "video": "/path/clip.mp4"}, ...], "fps": 2.0}
          items 里 text、video 可以只给一个；同一条里两者都给就是合编成一个向量（find_clips 用）
    响应  {"ok": true, "n": N, "dim": D, "b64": "<float32 小端 base64>"}
          {"ok": false, "error": "..."}
    就绪  模型加载完成后先发一行 {"ready": true}
"""
import base64
import json
import os
import sys


def _die_with_parent():
    """父进程没了就退出，别留下占着显存的孤儿。

    不用 prctl(PR_SET_PDEATHSIG)：它绑定的是创建子进程的那个线程而不是进程。Django 每个请求一个线程，
    请求线程一结束内核就给服务发 SIGTERM，下一个请求撞上正在退出的服务（实测检索一次成功一次失败）。
    改成盯父进程号：只有整个父进程死掉（包括被 kill -9），父进程号才会变。"""
    import threading
    import time
    parent = os.getppid()

    def _watch():
        while True:
            time.sleep(2)
            if os.getppid() != parent:
                os._exit(0)

    threading.Thread(target=_watch, name="parent-watchdog", daemon=True).start()


def main():
    _die_with_parent()
    # 优先用预量化副本：原版每次都要读 9.7GB bf16 再当场量化（冷启动约 300 秒），
    # 副本只有 4.5GB 且无需量化（实测 7 秒），两者编码结果逐位一致（MRR 均为 0.7906）。
    default_model = "/media/jju/ExtraDisk/models/WeMM-Embedding-4B-nf4"
    if not os.path.isdir(default_model):
        default_model = "/media/jju/ExtraDisk/models/WeMM-Embedding-4B"
    model_path = os.environ.get("VIDUNDER_WEMM_MODEL", default_model)
    # 加载期间 transformers/tqdm 会往 stdout 打进度，会污染协议管道，先把 stdout 引到 stderr
    real_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        import numpy as np
        import torch
        import torch.nn.functional as F
        from sentence_transformers import SentenceTransformer
        from transformers import BitsAndBytesConfig

        # 已经量化过的副本自带 quantization_config，再传一次会出错，只有原版才需要传
        already_quantized = False
        try:
            with open(os.path.join(model_path, "config.json"), encoding="utf-8") as fh:
                already_quantized = "quantization_config" in json.load(fh)
        except Exception:
            pass
        if already_quantized:
            mk = {}
        else:
            mk = {"dtype": torch.bfloat16,
                  "quantization_config": BitsAndBytesConfig(
                      load_in_4bit=True, bnb_4bit_quant_type="nf4",
                      bnb_4bit_compute_dtype=torch.bfloat16,
                      llm_int8_skip_modules=["lm_head"])}
        try:
            model = SentenceTransformer(model_path, trust_remote_code=True,
                                        device="cuda", model_kwargs=mk)
        except Exception:
            model = SentenceTransformer(model_path, trust_remote_code=True,
                                        model_kwargs={**mk, "device_map": "cuda"})

        root = model[0].auto_model if hasattr(model[0], "auto_model") else model[0].model
        pe = root.model.visual.patch_embed
        _W = pe.proj.weight.reshape(pe.proj.weight.shape[0], -1)
        _b = pe.proj.bias
        # Conv3d(kernel == stride) 在这张卡上极慢，F.linear 是等价运算
        pe.forward = lambda h: F.linear(h.to(_W.dtype), _W, _b).view(-1, _W.shape[0])
    except Exception as exc:
        sys.stdout = real_stdout
        sys.stdout.write(json.dumps({"ok": False, "error": "load failed: %s: %s"
                                     % (type(exc).__name__, exc)}) + "\n")
        sys.stdout.flush()
        return 1
    sys.stdout = real_stdout

    sys.stdout.write(json.dumps({"ready": True}) + "\n")
    sys.stdout.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if "items" in req:
                import qwen_vl_utils.vision_process as vp
                vp.FPS = float(req.get("fps", 2.0))
                # 每两帧的视觉 token 上限：默认 768，会把 1920x1080 静默压到 1152x640；按请求设置、用完复原
                default_cap = vp.VIDEO_MAX_TOKEN_NUM
                if req.get("video_max_tokens"):
                    vp.VIDEO_MAX_TOKEN_NUM = int(req["video_max_tokens"])
                payload = []
                for it in req["items"]:
                    one = {}
                    if str(it.get("text") or "").strip():
                        one["text"] = it["text"]
                    if it.get("video"):
                        one["video"] = it["video"]
                    payload.append(one or {"text": " "})
                batch = 1                                   # 视频片段逐条编，显存可控
            else:
                default_cap = None
                payload = [t if str(t).strip() else " " for t in req["texts"]]
                batch = int(req.get("batch_size", 8))
            sys.stdout, keep = sys.stderr, sys.stdout      # encode 内部也可能打印
            try:
                vec = model.encode(payload, batch_size=batch,
                                   normalize_embeddings=True, convert_to_numpy=True,
                                   show_progress_bar=False)
            finally:
                sys.stdout = keep
                if default_cap is not None:
                    vp.VIDEO_MAX_TOKEN_NUM = default_cap
            vec = vec.astype(np.float32)
            out = {"ok": True, "n": int(vec.shape[0]), "dim": int(vec.shape[1]),
                   "b64": base64.b64encode(vec.tobytes()).decode("ascii")}
        except Exception as exc:
            out = {"ok": False, "error": "%s: %s" % (type(exc).__name__, exc)}
        sys.stdout.write(json.dumps(out) + "\n")
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
