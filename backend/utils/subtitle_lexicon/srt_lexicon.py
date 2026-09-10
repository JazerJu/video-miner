# -*- coding: utf-8 -*-
"""字幕术语词表：propose 出候选，人审，apply 全语料替换。

为什么要人审这一步：只靠共现结构无法区分「A' 是 A 的错版」和「A' 是另一个
真实存在的东西」。实测同一套判据既给出 kotlin bench -> kernelgen bench（对），
也给出 triton bench -> kernelgen bench（错，triton 是真实术语）。判断
「kotlin 不是这个领域的东西、triton 是」需要语义知识，工具给不了。

所以规则以**具体的 A(fake) -> A 这一对**为键，进表要过人眼；进表之后第二遍
才敢做全语料外推，包括那些自己永远匹配不上的出现。

    python srt_lexicon.py propose --srt-dir <dir> --out lexicon.yaml
    #   人工编辑 lexicon.yaml：把 decision 改成 accept / reject
    python srt_lexicon.py apply   --srt-dir <dir> --lexicon lexicon.yaml [--write]
"""
import argparse, json, re, sys
from collections import Counter, defaultdict
from pathlib import Path
sys.path.insert(0, "/data/推理框架/asr-onnx/Qwen3-ASR-CTC-GGUF")
from qwen3_asr_ctc.hotword import PhonemeCorrector

TS = re.compile(r"(\d\d:\d\d:\d\d[,.]\d+)\s*-->\s*(\d\d:\d\d:\d\d[,.]\d+)")
WORD = re.compile(r"[a-zA-Z][a-zA-Z0-9]*")

# 常见英文词不参与改写：它们在字幕里本来就该出现，误改代价高
STOP = set("""the a an and or of to in on for with is are was were be been this that
these those we you they it he she i my our your their there here what which who how
why when where can could will would should may might must do does did done have has
had not no yes so if then than as at by from up out over under about into
one two three four five six seven eight nine ten first second next last
ok okay well just like get got go going make made take took see look know think
say said want need use used using new old good bad big small more most less
code open close start end run set add call pass point line time case type""".split())


def blocks_of(path):
    out = []
    for blk in Path(path).read_text(encoding="utf-8", errors="ignore").split("\n\n"):
        m = TS.search(blk)
        if not m:
            continue
        lines = [l for l in blk.splitlines() if not TS.search(l)]
        idx = next((l.strip() for l in lines if l.strip().isdigit()), "?")
        txt = " ".join(l for l in lines if not l.strip().isdigit()).strip()
        if txt:
            out.append((idx, m.group(1), txt))
    return out


def corpus(srt_dir):
    docs = {}
    for p in sorted(Path(srt_dir).glob("*_zh.srt")):
        b = blocks_of(p)
        if b:
            docs[p.name] = b
    return docs


def ngram_counts(docs, n_max=3):
    cnt = Counter()
    for blocks in docs.values():
        for _, _, t in blocks:
            ws = [w.lower() for w in WORD.findall(t)]
            for n in range(1, n_max + 1):
                for i in range(len(ws) - n + 1):
                    cnt[" ".join(ws[i:i + n])] += 1
    return cnt


def derive(bad, good, score):
    """从匹配上的一对里抽词级规则。两类证据分开走门。"""
    b, g = bad.split(), good.split()
    if len(b) == len(g):
        diff = [i for i in range(len(b)) if b[i] != g[i]]
        if len(diff) != 1:
            return None
        shared = sum(len(b[i]) for i in range(len(b)) if i not in diff)
        # 单词对没有上下文可共享，靠自身音素相似度；多词对靠共享上下文许可
        if len(b) == 1:
            if score < 0.70:
                return None
        elif shared < 4:
            return None
        src, dst = b[diff[0]], g[diff[0]]
        return None if len(dst) < 3 else (src, dst)
    if len("".join(g)) < 4 or len(b) > len(g) + 1 or score < 0.70:
        return None
    if b[:1] == g[:1] or b[-1:] == g[-1:] or len(b) == 1 or len(g) == 1:
        return bad, good
    return None


def is_inflection(src, dst):
    """src 和 dst 只差一个词形变化时，不是转写错误，是语言本身。

    buffers/buffer、cubes/cube、explains/explain、graphic/graphics 这类
    改了反而制造错误。判据是去掉常见词尾后词干相同。
    """
    def stem(w):
        for suf in ("ing", "ies", "es", "ed", "s"):
            if w.endswith(suf) and len(w) - len(suf) >= 3:
                return w[:-len(suf)]
        return w
    a, b = src.replace(" ", ""), dst.replace(" ", "")
    return stem(a) == stem(b) or a == stem(b) or stem(a) == b


def is_split_artifact(docs, src, ratio=0.5):
    """片段是不是字幕分段把一个词从中间劈开造成的。

    实测 470_zh.srt：
        line 950  ...it's like multiplyi
        line 954  ng rows by columns...        <- 下一段
    "multiplyi" 不是 ASR 错误，是切分器在词中间断的。按规则改成 multiply，
    拼回去就是 multiplyng —— 把本来正确的文本改坏。

    判据：该片段的出现里有超过 ratio 落在段首或段尾。真正的转写错误会散布在
    段落中间，不会系统性地贴着边界。
    """
    pat = re.compile(r"(?<![a-zA-Z0-9])" + re.escape(src) + r"(?![a-zA-Z0-9])", re.I)
    edge = total = 0
    for blocks in docs.values():
        for _, _, txt in blocks:
            m = pat.search(txt)
            if not m:
                continue
            total += 1
            head = txt[:m.start()].strip()
            tail = txt[m.end():].strip()
            if not head or not tail:
                edge += 1
    return total > 0 and edge / total > ratio


def loses_word(src, dst):
    """替换后词数变少 —— 说明有一个真实的词被吞掉了，不是转写纠正。

    实测这批全是这个形状（左边两个词都是语料里的真实术语）：
        compile cuda        -> compiler
        cuda provides       -> provided
        softmax calculation -> calculations
    cuda 在语料里出现 485 次，把它丢掉显然不对。

    单字母不计入词数：ASR 常把词首字母切出去（t taken 其实是 token，
    m ascend 其实是 ascend），那个孤立字母不是词。有这个例外
    t taken -> token 才算 1->1 得以保留。
    """
    wc = lambda ph: sum(1 for w in ph.split() if len(w) > 1)
    return wc(dst) < wc(src)


def find_hits(docs, src):
    pat = re.compile(r"(?<![a-zA-Z0-9])" + re.escape(src) + r"(?![a-zA-Z0-9])", re.I)
    out = []
    for name, blocks in docs.items():
        for idx, ts, txt in blocks:
            if pat.search(txt):
                out.append((name, idx, ts, txt))
    return out


def cmd_propose(a):
    docs = corpus(a.srt_dir)
    cnt = ngram_counts(docs)
    # 第一版这里只查了整串 in STOP，于是 "in the"(6 字符) 进了规范集，
    # 再由 "in memory" -> "in the" 抽出 memory -> the，780 处。
    # 含任何停用词的 n 元组一律不参与。
    clean = lambda w: not any(x in STOP for x in w.split())
    canon = sorted({w for w, n in cnt.items()
                    if n >= a.min_canon and len(w) >= 4 and clean(w)},
                   key=lambda w: -cnt[w])[:a.canon_size]
    variants = [(w, n) for w, n in cnt.items()
                if 1 <= n <= a.max_variant and len(w) >= 4
                and w not in canon and clean(w)]
    c = PhonemeCorrector(threshold=a.threshold)
    c.update_hotwords(canon)

    rules, seen = {}, set()
    for w, n in sorted(variants, key=lambda x: -x[1]):
        best = None
        for _, hw, sc in c.correct(w, k=8).matchs:
            # 打分是 1-距离/热词长度，分母是热词长度，短热词天然占便宜。
            # 长度差太多的规范形式不是好解释。
            if not (0.6 <= len(hw) / max(len(w), 1) <= 1.8):
                continue
            if hw != w and cnt[hw] > n and (best is None or sc > best[1]):
                best = (hw, sc)
        if not best:
            continue
        r = derive(w, best[0], best[1])
        if not r:
            continue
        src, dst = r
        if src == dst or src in seen or src in STOP or dst in STOP:
            continue
        # 长度比要在**导出的这一对**上查，不是在 n 元组上。
        # in memory -> in the 整体比 0.67 能过，但 memory -> the 是 0.5。
        if not (0.6 <= len(dst) / max(len(src), 1) <= 1.8) or len(dst) < 4:
            continue
        if is_inflection(src, dst):
            continue
        if is_split_artifact(docs, src):
            continue
        if loses_word(src, dst):
            continue
        seen.add(src)
        hits = find_hits(docs, src)
        if not hits:
            continue
        sf, df = cnt.get(src, 0), cnt.get(dst, 0)
        # 初判：证据强且规范形式压倒性更常见的，建议接受；其余一律 review。
        # 我判断不了「这个词是不是这个领域里真实存在的东西」，所以不敢默认接受。
        suggest = "accept" if (best[1] >= 0.80 and df >= sf * 3) else "review"
        rules[src] = dict(dst=dst, decision=suggest, score=round(best[1], 3),
                          via=f"{w} -> {best[0]}", src_freq=sf, dst_freq=df,
                          hits=len(hits), files=sorted({h[0] for h in hits}),
                          examples=[{"file": h[0], "n": h[1], "ts": h[2], "text": h[3]}
                                    for h in hits[:3]])

    ordered = dict(sorted(rules.items(), key=lambda kv: -kv[1]["hits"]))
    Path(a.out).write_text(json.dumps(
        {"_说明": "把 decision 改成 accept 或 reject，然后跑 apply。review 的默认不生效。",
         "_语料": {"字幕文件": len(docs), "字幕段": sum(len(b) for b in docs.values())},
         "rules": ordered}, ensure_ascii=False, indent=2), encoding="utf-8")

    n_acc = sum(1 for r in ordered.values() if r["decision"] == "accept")
    print("语料 %d 个字幕 / %d 段" % (len(docs), sum(len(b) for b in docs.values())))
    print("候选规则 %d 条（初判 accept %d，review %d），覆盖 %d 处\n"
          % (len(ordered), n_acc, len(ordered) - n_acc,
             sum(r["hits"] for r in ordered.values())))
    print("%-20s -> %-20s %6s %6s %6s %8s  %s"
          % ("改什么", "改成", "命中", "源频", "标频", "初判", "分数"))
    for src, r in list(ordered.items())[:40]:
        print("%-20s -> %-20s %6d %6d %6d %8s  %.2f"
              % (src, r["dst"], r["hits"], r["src_freq"], r["dst_freq"],
                 r["decision"], r["score"]))
    print("\n已写出 %s —— 编辑 decision 后跑 apply" % a.out)


def cmd_apply(a):
    lex = json.loads(Path(a.lexicon).read_text(encoding="utf-8"))
    acc = {s: r["dst"] for s, r in lex["rules"].items() if r["decision"] == "accept"}
    if not acc:
        print("词表里没有 accept 的规则，什么都没做"); return
    pats = {s: re.compile(r"(?<![a-zA-Z0-9])" + re.escape(s) + r"(?![a-zA-Z0-9])", re.I)
            for s in acc}
    total = 0
    for p in sorted(Path(a.srt_dir).glob("*_zh.srt")):
        raw = p.read_text(encoding="utf-8", errors="ignore")
        new, n_file = raw, 0
        for s, d in acc.items():
            new, k = pats[s].subn(d, new)
            n_file += k
        if not n_file:
            continue
        total += n_file
        print("%-18s %3d 处" % (p.name, n_file))
        if a.show_diff:
            for o, w in zip(raw.splitlines(), new.splitlines()):
                if o != w:
                    print("   - %s\n   + %s" % (o, w))
        if a.write:
            out = p if a.in_place else p.with_suffix(".fixed.srt")
            out.write_text(new, encoding="utf-8")
    print("\n合计 %d 处%s" % (total, "（已写入）" if a.write else "（预览，未写入；加 --write 生效）"))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("propose"); p1.set_defaults(fn=cmd_propose)
    p1.add_argument("--srt-dir", required=True)
    p1.add_argument("--out", default="lexicon.json")
    p1.add_argument("--min-canon", type=int, default=5)
    p1.add_argument("--max-variant", type=int, default=3)
    p1.add_argument("--canon-size", type=int, default=300)
    p1.add_argument("--threshold", type=float, default=0.6)
    p2 = sub.add_parser("apply"); p2.set_defaults(fn=cmd_apply)
    p2.add_argument("--srt-dir", required=True)
    p2.add_argument("--lexicon", required=True)
    p2.add_argument("--write", action="store_true")
    p2.add_argument("--in-place", action="store_true")
    p2.add_argument("--show-diff", action="store_true")
    a = ap.parse_args(); a.fn(a)
