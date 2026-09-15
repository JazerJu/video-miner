# coding=utf-8
"""WeMM-Embedding-4B 常驻编码服务，ONNX 版（不依赖 torch）。

协议与 wemm_embed_server.py 相同（stdin/stdout 逐行 JSON）：
    请求  {"texts": [...], "batch_size": 8}
          {"items": [{"text": "...", "video": "/path/clip.mp4"}, ...], "fps": 2.0, "video_max_tokens": 768}
    响应  {"ok": true, "n": N, "dim": D, "b64": "<float32 小端 base64>"}
          {"ok": false, "error": "..."}
    就绪  模型加载完成后先发一行 {"ready": true}

模型目录（VIDUNDER_WEMM_MODEL）里是三个 ONNX：vision_encoder、embedding、decoder，外加 tokenizer.json。
权重是线上 NF4 副本的 4 bit 字节原样搬过来的（MatMulBnb4），与 torch 版向量余弦约 0.999，旧索引不用重建。
decoder 的线性注意力用 com.microsoft.GatedDeltaNet，需要 onnxruntime-gpu 1.30 及以上（PyPI 上的是 CUDA 13 版；
Docker 镜像和本机用的是自己按 CUDA 12.8 编的 1.30.0）。
预处理（取帧、缩放、切 patch、带时间戳的 prompt、M-RoPE 位置）在 wemm_prep.py，与 torch 流水线逐项核对过。
"""
import base64
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DIM = 2560


def _die_with_parent():
    """父进程没了就退出，别留下占着显存的孤儿（原因见 wemm_embed_server.py 同名函数）。"""
    import threading
    parent = os.getppid()

    def _watch():
        while True:
            time.sleep(2)
            if os.getppid() != parent:
                os._exit(0)

    threading.Thread(target=_watch, name="parent-watchdog", daemon=True).start()


class WeMMOnnx:
    def __init__(self, model_dir):
        # onnxruntime 1.30 的 GroupQueryAttention 会自动改走 cuDNN SDPA；配 cuDNN 9.8（镜像底座自带）时建图直接失败（实测），
        # 关掉这条路径，用 flash / memory-efficient attention
        os.environ.setdefault("ORT_ENABLE_CUDNN_FLASH_ATTENTION", "0")
        import numpy as np
        import onnxruntime as ort
        import importlib.util
        if hasattr(ort, "preload_dlls") and importlib.util.find_spec("nvidia") is not None:
            try:
                ort.preload_dlls()          # CUDA 运行库是 pip 装的（nvidia-* 包）时要先预加载；系统装的不需要
            except Exception:
                pass
        sys.path.insert(0, HERE)
        import wemm_prep
        self.np, self.prep = np, wemm_prep
        so = ort.SessionOptions()
        so.log_severity_level = 3
        level = os.environ.get("VIDUNDER_WEMM_ONNX_OPT", "all")
        so.graph_optimization_level = {"all": ort.GraphOptimizationLevel.ORT_ENABLE_ALL,
                                       "extended": ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED,
                                       "basic": ort.GraphOptimizationLevel.ORT_ENABLE_BASIC}[level]
        cuda = [("CUDAExecutionProvider", {"device_id": 0}), "CPUExecutionProvider"]
        self.vision = ort.InferenceSession(os.path.join(model_dir, "vision_encoder", "model.onnx"), so, providers=cuda)
        self.decoder = ort.InferenceSession(os.path.join(model_dir, "decoder", "model.onnx"), so, providers=cuda)
        # 只是按 id 查表，放 CPU 上省 1.2GB 显存
        self.embedding = ort.InferenceSession(os.path.join(model_dir, "embedding", "model.onnx"), so,
                                              providers=["CPUExecutionProvider"])
        for name, sess in (("vision_encoder", self.vision), ("decoder", self.decoder)):
            # CUDA 装不上时 onnxruntime 会静默落到 CPU，慢几十倍：宁可启动失败
            if sess.get_providers()[0] != "CUDAExecutionProvider":
                raise RuntimeError(f"{name} is not on CUDAExecutionProvider: {sess.get_providers()}")
        self.prompter = wemm_prep.Prompter(os.path.join(model_dir, "tokenizer.json"))
        self.past_specs = [(i.name, i.shape) for i in self.decoder.get_inputs() if i.name.startswith("past_key_values")]
        self.dummy_features = np.zeros((1, DIM), np.float16)

    def _past(self, batch):
        np = self.np
        return {name: np.zeros([batch if d == "batch" else (0 if isinstance(d, str) else d) for d in shape], np.float16)
                for name, shape in self.past_specs}

    def _embed_ids(self, ids, features):
        np = self.np
        ids = np.where(ids == self.prep.VIDEO_TOKEN, self.prep.IMAGE_TOKEN, ids).astype(np.int64)
        feats = features if features is not None else self.dummy_features
        return self.embedding.run(None, {"input_ids": ids, "image_features": feats})[0]

    def _pool(self, hidden, last_index):
        np = self.np
        vec = hidden[np.arange(hidden.shape[0]), last_index].astype(np.float64)
        vec /= np.linalg.norm(vec, axis=1, keepdims=True) + 1e-12
        return vec.astype(np.float32)

    def encode_item(self, text=None, video=None, fps=2.0, video_max_tokens=None):
        np = self.np
        x = self.prep.prepare(self.prompter, text=text, video_path=video, fps=fps,
                              video_max_tokens=video_max_tokens or self.prep.VIDEO_MAX_TOKEN_NUM)
        features = None
        if x["pixel_values"] is not None:
            features = self.vision.run(None, {"pixel_values": x["pixel_values"].astype(np.float16),
                                              "image_grid_thw": np.array([x["grid_thw"]], np.int64)})[0]
        ids = x["input_ids"][None, :]
        embeds = self._embed_ids(ids, features)
        L = ids.shape[1]
        hidden = self.decoder.run(["last_hidden_state"], {"inputs_embeds": embeds, "attention_mask": np.ones((1, L), np.int64),
                                                          "position_ids": x["position_ids"], **self._past(1)})[0]
        return self._pool(hidden, np.array([L - 1]))[0]

    def encode_texts(self, texts, batch_size=8):
        """按长度排序分批，右侧补齐：线性注意力和因果卷积都是因果的，补在后面的 token 不影响取向量的那个位置。"""
        np = self.np
        rows = [self.prompter.build(text=t) for t in texts]
        order = sorted(range(len(rows)), key=lambda i: len(rows[i]))
        out = np.zeros((len(rows), DIM), np.float32)
        for s in range(0, len(order), max(1, batch_size)):
            chunk = order[s:s + batch_size]
            L = max(len(rows[i]) for i in chunk)
            ids = np.zeros((len(chunk), L), np.int64)
            mask = np.zeros((len(chunk), L), np.int64)
            for r, i in enumerate(chunk):
                ids[r, :len(rows[i])] = rows[i]
                mask[r, :len(rows[i])] = 1
            pos = np.broadcast_to(np.arange(L, dtype=np.int64), (3, len(chunk), L)).copy()
            embeds = self._embed_ids(ids, None)
            hidden = self.decoder.run(["last_hidden_state"], {"inputs_embeds": embeds, "attention_mask": mask,
                                                              "position_ids": pos, **self._past(len(chunk))})[0]
            out[chunk] = self._pool(hidden, mask.sum(1) - 1)
        return out


def main():
    _die_with_parent()
    default_model = "/media/jju/ExtraDisk/models/wemm-onnx/package/WeMM-Embedding-4B-onnx-nf4"
    model_dir = os.environ.get("VIDUNDER_WEMM_MODEL", default_model)
    real_stdout = sys.stdout
    sys.stdout = sys.stderr                  # 加载期间的打印不能进协议管道
    try:
        import numpy as np
        model = WeMMOnnx(model_dir)
    except Exception as exc:
        sys.stdout = real_stdout
        sys.stdout.write(json.dumps({"ok": False, "error": "load failed: %s: %s" % (type(exc).__name__, exc)}) + "\n")
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
            keep, sys.stdout = sys.stdout, sys.stderr
            try:
                if "items" in req:
                    vec = np.stack([model.encode_item(text=str(it.get("text") or "").strip() or None,
                                                      video=it.get("video") or None,
                                                      fps=float(req.get("fps", 2.0)),
                                                      video_max_tokens=req.get("video_max_tokens"))
                                    if (str(it.get("text") or "").strip() or it.get("video"))
                                    else model.encode_texts([" "])[0]
                                    for it in req["items"]])
                else:
                    texts = [t if str(t).strip() else " " for t in req["texts"]]
                    vec = model.encode_texts(texts, int(req.get("batch_size", 8)))
            finally:
                sys.stdout = keep
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
