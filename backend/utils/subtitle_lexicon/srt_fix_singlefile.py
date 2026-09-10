# -*- coding: utf-8 -*-
"""字幕术语纠正：文档内两轮匹配 + 规则外推。

依据：整个文件出自同一个 ASR、同一段音频、同一个说话人，所以同一个术语的
多次出现声学实现相同。模型有时吐对有时吐错，错的在音上必然接近对的。
于是规范写法可以从文档自己的高频片段里长出来，不需要外部术语表。

两轮：
  第一轮  低频片段 ←音素匹配→ 高频规范形式          抓「音上糊掉」的
  第二轮  从匹配上的多词对里抽出词级替换规则，再全文外推

第二轮是关键。举例：kotlin 在 525 里出现 17 次、kernelgen 只有 9 次，
按「高频即规范」kotlin 会被当成正确的。但二元组 kotlin bench(2) 对
kernelgen bench(7) 方向明确 —— 从这一对抽出 kotlin→kernelgen，
再应用到全部 17 处，不用管 kotlin 单独出现时多频繁。

复核方式是**审规则，不是审实例**：十几条规则点头之后，工具全文替换。
"""
import argparse, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, "/data/推理框架/asr-onnx/Qwen3-ASR-CTC-GGUF")
from qwen3_asr_ctc.hotword import PhonemeCorrector

TS = re.compile(r"(\d\d:\d\d:\d\d[,.]\d+)\s*-->\s*(\d\d:\d\d:\d\d[,.]\d+)")
WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9]*")


def load(path):
    """srt -> [(序号, 起, 止, 文本)]"""
    out = []
    for blk in Path(path).read_text(encoding="utf-8", errors="ignore").split("\n\n"):
        m = TS.search(blk)
        if not m:
            continue
        lines = [l for l in blk.splitlines() if not TS.search(l)]
        idx = next((l.strip() for l in lines if l.strip().isdigit()), "?")
        txt = " ".join(l for l in lines if not l.strip().isdigit()).strip()
        if txt:
            out.append((idx, m.group(1), m.group(2), txt))
    return out


def ngrams(blocks, n_max=3):
    """拉丁 n 元组频次。中文不参与——它没有稳定的词边界可依。"""
    cnt = Counter()
    for _, _, _, t in blocks:
        ws = [w.lower() for w in WORD.findall(t)]
        for n in range(1, n_max + 1):
            for i in range(len(ws) - n + 1):
                cnt[" ".join(ws[i:i + n])] += 1
    return cnt


def derive_rule(bad, good, score):
    """从一对匹配上的片段里抽词级替换规则。

    只在能干净对齐时出规则：词数相同且恰好一个位置不同，或者
    一对多／多对一的整体替换。含糊的情况宁可不出，交给人。
    """
    b, g = bad.split(), good.split()
    if len(b) == len(g):
        diff = [i for i in range(len(b)) if b[i] != g[i]]
        if len(diff) != 1:
            return None
        # 许可这条替换的是**共享上下文**，不是两个词本身有多像。
        # kotlin bench -> kernelgen bench：共享 bench（5 字母、独特），可信；
        # kotlin 和 kernelgen 本身音素相似度只有 0.33，靠它自己永远匹配不上。
        # tosh pi -> a pi：共享 pi（2 字母、到处都是），不足以许可。
        # 两类证据，各走各的门：
        #   单词对   —— 没有上下文可共享，靠自身音素相似度（kernal->kernel 0.83）
        #   多词对   —— 自身可以很不像，靠共享上下文许可（kotlin bench->kernelgen
        #              bench 共享 bench，而 kotlin 和 kernelgen 自身只有 0.33）
        shared = sum(len(b[i]) for i in range(len(b)) if i not in diff)
        if len(b) == 1:
            if score < 0.70:
                return None
        elif shared < 4:
            return None
        src, dst = b[diff[0]], g[diff[0]]
        if len(dst) < 3:            # 改成 "a" 这种一律不要
            return None
        return src, dst
    # 词数不同：只在前后缀能对齐时整体成规则（kernal gen -> kernelgen）
    # 词数不同：只在整体够长、且不是拿一堆词去换一个短词时才成规则
    if len("".join(g)) < 4 or len(b) > len(g) + 1 or score < 0.70:
        return None
    if b[:1] == g[:1] or b[-1:] == g[-1:] or len(b) == 1 or len(g) == 1:
        return bad, good
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("srt")
    ap.add_argument("--min-canon", type=int, default=3, help="规范形式的最低出现次数")
    ap.add_argument("--max-variant", type=int, default=2, help="变体的最高出现次数")
    ap.add_argument("--threshold", type=float, default=0.45)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    blocks = load(a.srt)
    cnt = ngrams(blocks)
    canon = sorted({w for w, n in cnt.items() if n >= a.min_canon and len(w) >= 4},
                   key=lambda w: -cnt[w])[:80]
    variants = [(w, n) for w, n in cnt.items()
                if 1 <= n <= a.max_variant and len(w) >= 4 and w not in canon]

    c = PhonemeCorrector(threshold=a.threshold)
    c.update_hotwords(canon)

    # ── 第一轮：变体 -> 规范 ───────────────────────────────────────
    pairs = []
    for w, n in variants:
        best = None
        for _, hw, sc in c.correct(w, k=8).matchs:
            # 打分是 1 - 距离/热词长度，分母是热词长度 —— 短热词天然拿高分。
            # 实测 "kotlin bench" 被 "a pi"(0.667) 压过正确的
            # "kernelgen bench"(0.571)，再被 k=3 截断，正例整个消失。
            # 长度差太多的规范形式不是好解释，直接排除。
            ratio = len(hw) / max(len(w), 1)
            if not (0.6 <= ratio <= 1.8):
                continue
            if hw != w and cnt[hw] > n and (best is None or sc > best[1]):
                best = (hw, sc)
        if best:
            pairs.append((w, n, best[0], cnt[best[0]], best[1]))
    # ── 通道 B（已停用）─────────────────────────────────────────────
    # 曾经想用「共享词」当证据：两个同词数片段只有一个位置不同、其余逐字相同，
    # 频次差数倍，就判低频那个是错版。它确实抓到了 kotlin bench -> kernelgen
    # bench，但同样的判据也给出 triton bench -> kernelgen bench（8 处）、
    # kernelgen ai -> kernelgen bench（33 处）—— 而 triton 和 ai 是这个视频里
    # 真实存在的不同东西，不是错版。
    # 文本层面区分不了这两种情况：要判断「kotlin 不是这个视频的主题」需要语义
    # 知识。这类错误留给带术语表的 LLM 逐句过，不要在这里猜。
    if False:
    # 音素匹配器在多热词场景下会漏（kotlin bench 的正确解释拿不到）。
    # 但这类证据本来就不需要它：两个同词数的片段，只有一个位置不同、
    # 其余逐字相同，且频次差出数倍 —— 低频那个就是同一个东西的错版。
    # 这正是「同一个 ASR、同一段音频」这个前提给出的信号。
        by_len = defaultdict(list)
        for w, n in cnt.items():
            if 2 <= len(w.split()) <= 3:
                by_len[len(w.split())].append((w, n))
        for k, items in by_len.items():
            for a1, n1 in items:
                w1 = a1.split()
                for a2, n2 in items:
                    if a1 == a2 or n2 < n1 * 3 or n1 > 2:
                        continue
                    w2 = a2.split()
                    diff = [i for i in range(k) if w1[i] != w2[i]]
                    if len(diff) != 1:
                        continue
                    shared = sum(len(w1[i]) for i in range(k) if i not in diff)
                    if shared < 4 or len(w2[diff[0]]) < 3:
                        continue
                    pairs.append((a1, n1, a2, n2, 0.99))   # 结构证据，标记为高置信

    pairs.sort(key=lambda x: -x[4])

    # ── 第二轮：抽规则并全文外推 ───────────────────────────────────
    rules, seen = {}, set()
    for bad, bn, good, gn, sc in pairs:
        r = derive_rule(bad, good, sc)
        if not r:
            continue
        src, dst = r
        if src == dst or src in seen:
            continue
        seen.add(src)
        rules[src] = dict(dst=dst, score=round(sc, 3), via=f"{bad} -> {good}",
                          via_freq=[bn, gn])

    # 统计每条规则在全文命中多少处（包括源词本身是高频的情况）
    for src, r in rules.items():
        pat = re.compile(r"(?<![a-z0-9])" + re.escape(src) + r"(?![a-z0-9])", re.I)
        hits = [(i, ts, txt) for i, ts, _, txt in blocks if pat.search(txt)]
        r["hits"] = len(hits)
        r["src_freq"] = cnt.get(src, 0)
        r["examples"] = [(i, ts, txt) for i, ts, txt in hits[:3]]

    print("=" * 78)
    print("%s   %d 段字幕   规范形式候选 %d   低频变体 %d"
          % (Path(a.srt).name, len(blocks), len(canon), len(variants)))
    print("=" * 78)
    print("\n【规则清单】审这个，不用审实例。src_freq 是源词在全文的出现次数。\n")
    # 命中 0 的规则是噪声：源片段在全文里不作为独立词出现，改不到任何地方。
    # 多词垃圾（kool plus vivo -> five）几乎全落在这里。
    rules = {k: v for k, v in rules.items() if v["hits"] > 0}
    print("%-22s -> %-22s %6s %6s  %s" % ("改什么", "改成", "命中", "源频次", "证据（低频对）"))
    for src, r in sorted(rules.items(), key=lambda kv: -kv[1]["hits"]):
        flag = "  ⚠源词更常见" if r["src_freq"] > cnt.get(r["dst"], 0) else ""
        print("%-22s -> %-22s %6d %6d  %s (%d vs %d) %.2f%s"
              % (src, r["dst"], r["hits"], r["src_freq"], r["via"],
                 r["via_freq"][0], r["via_freq"][1], r["score"], flag))
    dbg = [p for p in pairs if "kotlin" in p[0]]
    print("\n[诊断] 含 kotlin 的第一轮配对：%s" % (dbg or "无"))
    print("       kotlin 频次 %d / kotlin bench 频次 %d / kernelgen bench 频次 %d"
          % (cnt.get("kotlin", 0), cnt.get("kotlin bench", 0), cnt.get("kernelgen bench", 0)))
    print("\n共 %d 条规则，合计影响 %d 处"
          % (len(rules), sum(r["hits"] for r in rules.values())))

    if a.out:
        Path(a.out).write_text(json.dumps(
            {"srt": str(a.srt), "rules": rules,
             "pass1_pairs": [dict(zip(("bad","bad_n","good","good_n","score"), p)) for p in pairs]},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n已写出 %s" % a.out)


if __name__ == "__main__":
    main()
