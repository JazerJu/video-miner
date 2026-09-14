# -*- coding: utf-8 -*-
"""剔除渗进字幕带的幻灯片文字。

字幕每段都在变，幻灯片正文在几十段里逐字不变 —— 按出现段数过滤就够了，
不需要再去碰像素。OCR 的多行输出在写 SRT 时用空格连接，所以空格就是行边界。

用法: deslide.py in.srt out.srt [最低占比 0.01] [最少段数 2]
"""
import sys, collections, re

src, dst = sys.argv[1], sys.argv[2]
RATE = float(sys.argv[3]) if len(sys.argv) > 3 else 0.01
MIN_HITS = int(sys.argv[4]) if len(sys.argv) > 4 else 2
# 幻灯片文字通常成句，口语衬词（然后、就是、对对）很短却会在几十段里反复出现。
# 长度下限就是拿来分开这两类的 —— 509 里「然后」占 66 段，差点被当幻灯片删掉。
MIN_LEN = 6

blocks = [b for b in open(src, encoding="utf-8").read().split("\n\n") if b.strip()]
segs = []
for b in blocks:
    ln = b.splitlines()
    if len(ln) < 3: continue
    segs.append((ln[1], " ".join(ln[2:])))

cnt = collections.Counter()
for _, t in segs:
    for c in set(t.split()):
        if len(c) >= 2: cnt[c] += 1

n = len(segs)
# 两段判据：
#   出现率 > 30% 的一律删，不看长度 —— 没有哪句真字幕会在三成段落里逐字重复。
#     552（廖恒）的常驻章节横幅是「摩尔定律 18层宝塔 人才与算力」，三个词都短于
#     MIN_LEN，7138 段里有 7090 段带着它，把整期的术语密度稀释掉了。
#   低频段才用长度下限，保护口语衬词 —— 509 的「然后」占 66 段（1.1%），不能删。
bad = {c for c, k in cnt.items()
       if k >= n * 0.30 or (k >= MIN_HITS and k >= n * RATE and len(c) >= MIN_LEN)}
if bad:
    print("剔除 %d 个幻灯片片段（共 %d 段）:" % (len(bad), n))
    for c in sorted(bad, key=lambda c: -cnt[c])[:12]:
        print("   %3d 段  %s" % (cnt[c], c))

out, kept = [], 0
for ts, t in segs:
    chunks = [c for c in t.split() if c not in bad]
    txt = " ".join(chunks).strip()
    if txt:
        kept += 1
        out.append("%d\n%s\n%s\n" % (kept, ts, txt))
open(dst, "w", encoding="utf-8").write("\n".join(out) + "\n")
print("%d 段 → %d 段  %s" % (n, kept, dst))
