# -*- coding: utf-8 -*-
"""硬字幕提取（v12）—— 由用户手动框选字幕区域。

流程：
  1. VideoSubFinder 切区间     逐帧看字幕区域的 Sobel 边缘，找字幕出现、换句、消失（utils/hardsub/vsf.py）
  2. 固定区域识别              每个区间取起点一帧，裁出框选区域、四周补黑边，送 GLM-OCR
  3. 删画面固定文字            同一行在 ≥3 段不相邻区间、且 ≥10% 的区间里出现，就是标签、台标、叠加条
  4. 合并相邻同句              文字相似度 ≥0.8、间隔 ≤1 s 合成一条

替换掉的旧做法（v0–v10）：按亮度阈值做掩膜、判极性、相邻帧 IoU 分段、再用 deslide 按出现次数删行。
在 7 个对照视频上，旧做法把同一句切成很多段，deslide 又把重复出现的真字幕删掉（598 覆盖 97% → 30%）；
v12 覆盖 96–99%，GLM-ASR 转写对照的召回/查准不低于 video-subtitle-extractor + GLM-OCR。

经验值：
  补黑边 16/24     贴边裁剪会丢首字（598：6 条里 3 条丢首字，补边后全对）
  视觉塔 fp16      int4 会把「框架」读成「栀驾」
  模糊匹配限长度   只比长度相近的行：不限长度时「它搬运也是它有TILE_LENGTH=128，」被当成标注「TILE_LENGTH = 128」整句删掉
  双语分轨         同一区间既有中文行又有纯英文行时，英文行算翻译轨；只有英文行时算中文字幕里的英文（如「JetBrains」「CopyIn」）

用法:
  extract_hardsub.py --video a.mp4 --out zh.srt --region 0.0,0.84,1.0,0.13 [--en-out en.srt]
  --region 是 x,y,w,h，取值 0-1，相对整帧。
"""
import argparse, collections, json, os, re, subprocess, sys, time
from difflib import SequenceMatcher

import cv2
from PIL import Image

OCR_RUNTIME = os.environ.get(
    "VIDGO_GLM_OCR_RUNTIME", "/data/推理框架/asr-onnx/GLM-OCR-GGUF/runtime"
)
OCR_ONNX_DIR = os.environ.get(
    "VIDGO_GLM_OCR_ONNX", "/data/推理框架/asr-onnx/GLM-OCR-GGUF/models/export"
)
OCR_GGUF = os.environ.get("VIDGO_GLM_OCR_GGUF", "/data/其他模型/ocr/GLM-OCR-Q8_0.gguf")
sys.path.insert(0, OCR_RUNTIME)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("GLM_OCR_PRECISION", "fp16")

CJK = re.compile(r"[一-鿿]")
PROMPT = "请识别图中的所有文字，只输出文字本身"
PAD_Y, PAD_X = 16, 24
STATIC_RUNS, STATIC_FRAC, STATIC_SIM = 3, 0.10, 0.75
MERGE_SIM, MERGE_GAP = 0.80, 1.0
VSF_SHARE = 50          # 进度条里 VideoSubFinder 占前一半，识别占后一半


def norm(s):
    return re.sub(r"[^一-鿿A-Za-z0-9]", "", s or "").lower()


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


def srt_ts(t):
    h, r = divmod(t, 3600)
    m, s = divmod(r, 60)
    return "%02d:%02d:%02d,%03d" % (h, m, int(s), round((s - int(s)) * 1000) % 1000)


def write_srt(path, segs):
    with open(path, "w", encoding="utf-8") as f:
        for i, (a, b, txt) in enumerate(segs, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, srt_ts(a), srt_ts(b), txt))


def static_filter(lines):
    """返回判断「画面固定文字」的函数。lines：每个区间识别出的行列表。"""
    occ = collections.defaultdict(set)
    for k, ls in enumerate(lines):
        for n in set(map(norm, ls)):
            if len(n) >= 3:
                occ[n].add(k)

    def runs(ks):
        ks = sorted(ks)
        return sum(1 for i, k in enumerate(ks) if i == 0 or k != ks[i - 1] + 1)

    static = {n for n, ks in occ.items() if runs(ks) >= STATIC_RUNS and len(ks) >= STATIC_FRAC * len(lines)}

    def is_static(line):
        n = norm(line)
        return n in static or (len(n) >= 3 and any(
            0.7 <= len(n) / len(s) <= 1.4 and SequenceMatcher(None, n, s).ratio() >= STATIC_SIM for s in static))

    return is_static, static


def merge_cues(cues):
    out = []
    for a, b, t in cues:
        if out and a - out[-1][1] <= MERGE_GAP and SequenceMatcher(None, norm(t), norm(out[-1][2])).ratio() >= MERGE_SIM:
            out[-1][1] = b
            if len(norm(t)) > len(norm(out[-1][2])):
                out[-1][2] = t
        else:
            out.append([a, b, t])
    return out


def postprocess(intervals, lines):
    """删固定文字、分中英轨、合并同句。返回 (zh_cues, en_cues, 固定文字集合)。"""
    is_static, static = static_filter(lines)
    zh, en = [], []
    for (a, b), ls in zip(intervals, lines):
        keep = [l for l in ls if not is_static(l)]
        cjk = [l for l in keep if CJK.search(l)]
        if cjk:
            latin = [l for l in keep if not CJK.search(l)]
            if latin:
                en.append([a, b, " ".join(latin)])
            zh.append([a, b, " ".join(cjk)])
        elif keep:
            zh.append([a, b, " ".join(keep)])
    return merge_cues(zh), merge_cues(en), static


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True, help="中文轨 SRT")
    ap.add_argument("--en-out", default="", help="英文轨 SRT，留空则丢弃翻译行")
    ap.add_argument("--region", required=True, help="x,y,w,h，0-1，相对整帧")
    ap.add_argument("--fps", type=float, default=4.0, help="v12 不再按帧率抽帧，保留参数只为兼容旧调用")
    args = ap.parse_args()

    try:
        rx, ry, rw, rh = (float(v) for v in args.region.split(","))
    except ValueError:
        raise SystemExit("--region 要写成 x,y,w,h")
    if not (0 <= rx < 1 and 0 <= ry < 1 and 0 < rw <= 1 and 0 < rh <= 1):
        raise SystemExit("--region 的取值要在 0-1 之间")

    # 导入 llama.cpp 绑定时可能用 LD_PRELOAD 重启解释器（os.execv），必须放在任何耗时步骤之前
    from glm_ocr_llama import GlmOcrLlama
    from vsf import find_intervals

    W, H, dur = probe(args.video)
    x0, y0 = min(int(W * rx), W - 2), min(int(H * ry), H - 2)
    bw, bh = min(max(2, int(W * rw)), W - x0), min(max(2, int(H * rh)), H - y0)
    emit("setup", width=W, height=H, duration=round(dur, 2), region=[x0, y0, bw, bh], engine="v12")

    t0 = time.time()
    last = [0.0]

    def vsf_progress(sec):
        if time.time() - last[0] >= 2:
            last[0] = time.time()
            emit("progress", stage="vsf", percent=round(VSF_SHARE * min(sec, dur) / max(dur, 1e-6), 1),
                 seconds=round(sec, 1), duration=round(dur, 1), segments=0)

    intervals = find_intervals(args.video, (x0, y0, x0 + bw, y0 + bh), (W, H), on_progress=vsf_progress)
    emit("progress", stage="vsf", percent=VSF_SHARE, seconds=round(dur, 1), duration=round(dur, 1),
         segments=0, intervals=len(intervals), elapsed=round(time.time() - t0, 1))

    lines = []
    if intervals:
        eng = GlmOcrLlama(gguf_path=OCR_GGUF, onnx_dir=OCR_ONNX_DIR)
        cap = cv2.VideoCapture(args.video)
        for i, (a, b) in enumerate(intervals):
            cap.set(cv2.CAP_PROP_POS_MSEC, a * 1000)
            ok, fr = cap.read()
            if not ok:
                lines.append([])
                continue
            crop = cv2.copyMakeBorder(fr[y0:y0 + bh, x0:x0 + bw], PAD_Y, PAD_Y, PAD_X, PAD_X,
                                      cv2.BORDER_CONSTANT, value=(0, 0, 0))
            raw = eng.ocr(Image.fromarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)), prompt=PROMPT)
            lines.append([l.strip() for l in raw.split("\n") if norm(l)])
            if i % 10 == 0 or i == len(intervals) - 1:
                emit("progress", stage="ocr",
                     percent=round(VSF_SHARE + (100 - VSF_SHARE) * (i + 1) / len(intervals), 1),
                     seconds=round(a, 1), duration=round(dur, 1), segments=i + 1, intervals=len(intervals))
        cap.release()

    zh, en, static = postprocess(intervals, lines)
    write_srt(args.out, zh)
    if args.en_out and en:
        write_srt(args.en_out, en)
    emit("done", segments=len(zh), en_segments=len(en), intervals=len(intervals), static_lines=len(static),
         elapsed=round(time.time() - t0, 1), out=args.out, en_out=args.en_out if (args.en_out and en) else "")


if __name__ == "__main__":
    main()
