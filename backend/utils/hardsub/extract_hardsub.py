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
  extract_hardsub.py --video a.mp4 --out primary.srt --region 0.0,0.84,1.0,0.13 [--en-out en.srt]
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
KANA = re.compile(r"[\u3040-\u30ff]")
LATIN = re.compile(r"[A-Za-z]")
# Share of the distinct subtitle lines that must be in a script for it to be the video's own language.
# Bilingual zh+en subtitles sit at ~0.5; an English video with a few misread 汉字 stays far below.
LANG_SHARE = 0.3
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


def _asian(line):
    """中文/日文行：汉字和假名按一个抵三个字母算，比拉丁字母多。英文行里误识别出的一个汉字
    翻不了它，「我们使用 JetBrains 的 IDE」这样夹英文词的中文行仍算中文。"""
    n = len(CJK.findall(line)) + len(KANA.findall(line))
    return n > 0 and n * 3 >= len(LATIN.findall(line))


def detect_lang(lines, is_static):
    """字幕自己的语言：zh / jp / en（拉丁字母一律按 en）。

    按去重后的不同行算占比，不按出现次数：一直挂着的水印在每个区间都出现（它连成一段，
    static_filter 认不出），按次数它能和字幕平分秋色，按不同行它只算一条；偶尔误识别出的
    一个汉字也只算一条。"""
    distinct = {norm(l): l for ls in lines for l in ls if not is_static(l) and len(norm(l)) >= 2}
    if not distinct:
        return ""
    n = len(distinct)
    if sum(1 for l in distinct.values() if KANA.search(l)) / n >= LANG_SHARE:
        return "jp"
    if sum(1 for l in distinct.values() if _asian(l)) / n >= LANG_SHARE:
        return "zh"
    return "en"


def postprocess(intervals, lines, lang=""):
    """删固定文字、分轨、合并同句。返回 (主轨, 译文轨, 主轨语言, 固定文字集合)。

    lang 是用户指定的字幕语言，留空则自动判断（detect_lang）。主轨语言是中文或日文时，汉字/
    假名行进主轨，同框的拉丁字母行进译文轨；主轨是拉丁字母语言时，汉字行是水印或误识别，丢掉。"""
    is_static, static = static_filter(lines)
    primary_lang = lang or detect_lang(lines, is_static)
    asian = primary_lang in ("zh", "jp")
    main, alt = [], []
    for (a, b), ls in zip(intervals, lines):
        keep = [l for l in ls if not is_static(l)]
        own = [l for l in keep if _asian(l)]
        latin = [l for l in keep if not _asian(l)]
        if asian and own:
            main.append([a, b, " ".join(own)])
            if latin:
                alt.append([a, b, " ".join(latin)])
        elif latin:
            # 中文字幕里夹的纯英文行（「JetBrains」「CopyIn」），或拉丁字母视频本身的字幕
            main.append([a, b, " ".join(latin)])
    return merge_cues(main), merge_cues(alt), primary_lang, static


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video", required=True)
    ap.add_argument("--out", required=True, help="主轨 SRT（视频自己的语言，中文或英文）")
    ap.add_argument("--en-out", default="", help="译文轨 SRT（双语时才写），留空则丢弃译文行")
    ap.add_argument("--region", required=True, help="x,y,w,h，0-1，相对整帧")
    ap.add_argument("--lang", default="", choices=["", "zh", "en", "jp", "de"],
                    help="字幕语言，留空自动判断")
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

    primary, alt, primary_lang, static = postprocess(intervals, lines, args.lang)
    write_srt(args.out, primary)
    if args.en_out and alt:
        write_srt(args.en_out, alt)
    emit("done", segments=len(primary), en_segments=len(alt), primary_lang=primary_lang,
         intervals=len(intervals), static_lines=len(static),
         elapsed=round(time.time() - t0, 1), out=args.out, en_out=args.en_out if (args.en_out and alt) else "")


if __name__ == "__main__":
    main()
