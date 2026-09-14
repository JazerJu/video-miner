# -*- coding: utf-8 -*-
"""硬字幕提取 —— 由用户手动框选字幕区域。

和 utils/subtitle_lexicon/hardsub/hardsub_bi.py 的关系：管线相同，但区域来自人工框选，
因此去掉了候选带扫描和黑边检测（交接文档里的坑 1 和坑 3 都是「位置推错」造成的，
人工框选从源头消掉了这两类失效）。其余经验值原样保留：

  极性自适应      两种极性各算掩膜占比，取落在 [0.004, 0.15] 且更小的那个。
                  写死阈值会让整张幻灯片进掩膜（黑字白底），分段退化成一整段。
  阈值 60 / 245   文字在带内只占百分之几，暗区/亮底动辄几十个百分点。
  IoU < 0.55      相邻帧掩膜交并比低于此值判为换了一句。帧差对锯齿太敏感。
  MX/MY 24/16     包围盒余量，12/8 会丢字。
  顺序解码        ffmpeg 只解字幕带走管道，不逐帧 seek。
  保留换行        GLM-OCR 在中英两行间吐 \n，整行判 CJK 分轨，绝不逐字符删中文。
  视觉塔 fp16     int4 会把「框架」读成「栀驾」，正确率只有 25%。

用法:
  extract_hardsub.py --video a.mp4 --out zh.srt --region 0.0,0.84,1.0,0.13 [--en-out en.srt]
  --region 是 x,y,w,h，取值 0-1，相对整帧。
"""
import argparse, json, os, re, subprocess, sys, time

import cv2
import numpy as np
from PIL import Image

OCR_RUNTIME = os.environ.get(
    "VIDGO_GLM_OCR_RUNTIME", "/data/推理框架/asr-onnx/GLM-OCR-GGUF/runtime"
)
OCR_ONNX_DIR = os.environ.get(
    "VIDGO_GLM_OCR_ONNX", "/data/推理框架/asr-onnx/GLM-OCR-GGUF/models/export"
)
OCR_GGUF = os.environ.get("VIDGO_GLM_OCR_GGUF", "/data/其他模型/ocr/GLM-OCR-Q8_0.gguf")
sys.path.insert(0, OCR_RUNTIME)
os.environ.setdefault("GLM_OCR_PRECISION", "fp16")

CJK = re.compile(r"[一-鿿]")
MX, MY = 24, 16
MIN_SEG_SECONDS = 0.4
MIN_INK_PIXELS = 50
IOU_SPLIT = 0.55
BLANK_MASK_RATIO = 0.004


def emit(kind, **fields):
    """给父进程解析的进度行。"""
    print(json.dumps({"type": kind, **fields}, ensure_ascii=False), flush=True)


def probe(video):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", video],
        capture_output=True, text=True).stdout.strip()
    w, h = (int(x) for x in out.split("x")[:2])
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", video], capture_output=True, text=True).stdout.strip())
    return w, h, dur


def pick_polarity(video, dur, x0, y0, bw, bh):
    """采样 12 帧定极性。文字占比小，暗区/亮底占比大，据此区分。"""
    cap = cv2.VideoCapture(video)
    grays = []
    for f in np.linspace(0.08, 0.92, 12):
        cap.set(cv2.CAP_PROP_POS_MSEC, dur * f * 1000)
        ok, fr = cap.read()
        if ok:
            grays.append(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY))
    cap.release()
    if not grays:
        raise SystemExit("读不出帧，无法判定极性")
    lo, hi = 0.004, 0.15
    fr_hi = float(np.mean([(g[y0:y0 + bh, x0:x0 + bw] > 245).mean() for g in grays]))
    fr_lo = float(np.mean([(g[y0:y0 + bh, x0:x0 + bw] < 60).mean() for g in grays]))
    ok_hi, ok_lo = lo <= fr_hi <= hi, lo <= fr_lo <= hi
    if ok_hi and ok_lo:
        dark = fr_lo < fr_hi
    elif ok_hi:
        dark = False
    elif ok_lo:
        dark = True
    else:
        dark = fr_lo < fr_hi
    return dark, fr_hi, fr_lo


def srt_ts(t):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return "%02d:%02d:%02d,%03d" % (h, m, int(s), round((s - int(s)) * 1000))


def write_srt(path, segs):
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, txt) in enumerate(segs, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, srt_ts(a), srt_ts(b), txt))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True, help="中文轨 SRT")
    ap.add_argument("--en-out", default="", help="英文轨 SRT，留空则丢弃英文行")
    ap.add_argument("--region", required=True, help="x,y,w,h，0-1，相对整帧")
    ap.add_argument("--fps", type=float, default=4.0, help="4 或 8；8 把分句量化误差减半，耗时约 +20%%")
    args = ap.parse_args()

    try:
        rx, ry, rw, rh = (float(v) for v in args.region.split(","))
    except ValueError:
        raise SystemExit("--region 要写成 x,y,w,h")
    if not (0 <= rx < 1 and 0 <= ry < 1 and 0 < rw <= 1 and 0 < rh <= 1):
        raise SystemExit("--region 的取值要在 0-1 之间")

    W, H, dur = probe(args.video)
    x0, y0 = int(W * rx), int(H * ry)
    bw, bh = max(2, int(W * rw)), max(2, int(H * rh))
    x0, y0 = min(x0, W - 2), min(y0, H - 2)
    bw, bh = min(bw, W - x0), min(bh, H - y0)
    bw -= bw % 2
    bh -= bh % 2

    dark, fr_hi, fr_lo = pick_polarity(args.video, dur, x0, y0, bw, bh)
    thr = 60 if dark else 245
    emit("setup", width=W, height=H, duration=round(dur, 2),
         region=[x0, y0, bw, bh], polarity="dark_text" if dark else "light_text",
         threshold=thr, bright_ratio=round(fr_hi, 4), dark_ratio=round(fr_lo, 4))

    from glm_ocr_llama import GlmOcrLlama
    eng = GlmOcrLlama(gguf_path=OCR_GGUF, onnx_dir=OCR_ONNX_DIR)

    op = cv2.THRESH_BINARY_INV if dark else cv2.THRESH_BINARY
    ker = np.ones((5, 25), np.uint8)
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", args.video,
         "-vf", "crop=%d:%d:%d:%d,fps=%g" % (bw, bh, x0, y0, args.fps),
         "-f", "rawvideo", "-pix_fmt", "bgr24", "-"],
        stdout=subprocess.PIPE, bufsize=bw * bh * 3 * 4)

    fsz = bw * bh * 3
    zh_segs, en_segs = [], []
    idx, t0 = 0, time.time()
    cur_mask = cur_start = cur_frame = None

    def flush(end_t):
        nonlocal cur_mask, cur_start, cur_frame
        if cur_start is not None and end_t - cur_start >= MIN_SEG_SECONDS:
            closed = cv2.morphologyEx(cur_mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, ker)
            ys, xs = np.where(closed > 0)
            if len(xs) >= MIN_INK_PIXELS:
                crop = cur_frame[max(0, ys.min() - MY):min(bh, ys.max() + MY),
                                 max(0, xs.min() - MX):min(bw, xs.max() + MX)]
                raw = eng.ocr(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)),
                              prompt="请识别图中的所有文字，只输出文字本身")
                zh, en = [], []
                for line in raw.splitlines():
                    line = " ".join(line.split())
                    if not line:
                        continue
                    (zh if CJK.search(line) else en).append(line)
                if zh:
                    zh_segs.append((cur_start, end_t, " ".join(zh)))
                if en:
                    en_segs.append((cur_start, end_t, " ".join(en)))
        cur_mask = cur_start = cur_frame = None

    while True:
        buf = proc.stdout.read(fsz)
        if len(buf) < fsz:
            break
        fr = np.frombuffer(buf, np.uint8).reshape(bh, bw, 3)
        t = idx / args.fps
        idx += 1
        m = cv2.threshold(cv2.cvtColor(fr, cv2.COLOR_BGR2GRAY), thr, 255, op)[1] > 0
        if m.mean() <= BLANK_MASK_RATIO:
            flush(t)
            continue
        if cur_mask is None:
            cur_mask, cur_start, cur_frame = m, t, fr.copy()
            continue
        inter = (cur_mask & m).sum()
        union = (cur_mask | m).sum()
        if (inter / union if union else 1.0) < IOU_SPLIT:
            flush(t)
            cur_mask, cur_start, cur_frame = m, t, fr.copy()
        if idx % 2000 == 0:
            emit("progress", seconds=round(t, 1), duration=round(dur, 1),
                 segments=len(zh_segs), elapsed=round(time.time() - t0, 1))
    flush(idx / args.fps)
    proc.stdout.close()
    proc.wait()

    write_srt(args.out, zh_segs)
    if args.en_out and en_segs:
        write_srt(args.en_out, en_segs)
    emit("done", segments=len(zh_segs), en_segments=len(en_segs),
         elapsed=round(time.time() - t0, 1), out=args.out,
         en_out=args.en_out if (args.en_out and en_segs) else "")


if __name__ == "__main__":
    main()
