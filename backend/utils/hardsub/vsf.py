# -*- coding: utf-8 -*-
"""调用 VideoSubFinder 找字幕区间（出现、换句、消失），不识别文字。

VideoSubFinder 逐帧处理字幕区域，按 Sobel 边缘找「像文字」的像素，前后段比较判断换句，
一句至少持续 6 帧（settings/general.cfg 的 sub_frame_length）。它看边缘不看亮度，
亮字暗底、暗字亮底、渐变底都不用判极性 —— 旧管线按亮度阈值分段反复踩坑的地方。

参数与 video-subtitle-extractor 的 Linux 调用一致（backend/main.py），只是不加 --use_cuda：
598 上 CPU 与 CUDA 切出的 63 个区间逐个相同，用时 13 s 对 12 s。
"""
import os
import re
import shutil
import subprocess
import tempfile
import multiprocessing

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VSF_DIR = os.environ.get("VIDGO_VSF_DIR", os.path.join(BACKEND_DIR, "third_party", "videosubfinder", "linux"))
_TS = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d+)\s*-->\s*(\d+):(\d\d):(\d\d)[,.](\d+)")


def _sec(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 10 ** len(ms)


def find_intervals(video, box, frame_size, on_progress=None, threads=None):
    """返回 [(start_sec, end_sec), ...]。

    video       视频路径
    box         字幕区域像素坐标 (x0, y0, x1, y1)，右、下边界不含
    frame_size  整帧 (W, H)
    on_progress 可选回调，参数为已处理到的视频秒数
    """
    x0, y0, x1, y1 = box
    W, H = frame_size
    run = os.path.join(VSF_DIR, "VideoSubFinderCli.run")
    if not os.path.exists(run):
        raise FileNotFoundError("找不到 VideoSubFinder: " + run)
    threads = threads or max(multiprocessing.cpu_count() - 2, 1)
    tmp = tempfile.mkdtemp(prefix="vsf_")
    raw = os.path.join(tmp, "raw_vsf.srt")
    # 启动脚本会先 cd 到自己的目录，路径一律用绝对路径
    cmd = [run, "-c", "-r", "-i", os.path.abspath(video), "-o", tmp, "-ces", raw,
           "-te", str(1 - y0 / H), "-be", str(1 - y1 / H), "-le", str(x0 / W), "-re", str(x1 / W),
           "-nthr", str(threads), "-dsi", "--open_video_opencv"]
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, errors="replace")
        for line in proc.stderr:
            # 进度行形如 "Frame: 00_01_07_900__..."
            if on_progress and line.startswith("Frame: "):
                try:
                    h, m, s, ms = line[7:].split("__")[0].split("_")[:4]
                    on_progress(int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000)
                except ValueError:
                    pass
        proc.wait()
        if not os.path.exists(raw):
            raise RuntimeError("VideoSubFinder 没有输出（退出码 %s）" % proc.returncode)
        text = open(raw, encoding="utf-8", errors="ignore").read()
        return [(_sec(*m.groups()[:4]), _sec(*m.groups()[4:])) for m in _TS.finditer(text)]
    finally:
        shutil.rmtree(tmp, True)
