import json, re
d = json.load(open("/tmp/lexicon.json", encoding="utf-8"))
R = d["rules"]
DOMAIN = re.compile(r"vllm|sglang|tile|triton|ascend|cann|npu|cuda|kuda|torch|onnx|"
                    r"tensor|kernel|kernal|kotlin|flash|clash|flag|deepseek|agent|"
                    r"gpu|hccl|nccl|mlir|tvm|bench|softmax|attention|moe|mla|token|"
                    r"cube|vector|buffer|matmul|gemm|算子", re.I)
hits = {k: v for k, v in R.items() if DOMAIN.search(k) or DOMAIN.search(v["dst"])}
print("全部规则 %d 条；与 AI infra 相关 %d 条\n" % (len(R), len(hits)))
print("%-22s -> %-22s %5s %6s %6s %8s %s" % ("改什么","改成","命中","源频","标频","初判","分数"))
for k, v in sorted(hits.items(), key=lambda kv: -kv[1]["hits"])[:40]:
    print("%-22s -> %-22s %5d %6d %6d %8s %.2f"
          % (k, v["dst"], v["hits"], v["src_freq"], v["dst_freq"], v["decision"], v["score"]))
print("\n=== 三条样例的原文 ===")
for k in list(hits)[:3]:
    print("\n%s -> %s" % (k, hits[k]["dst"]))
    for e in hits[k]["examples"][:2]:
        print("   %s #%s %s  %s" % (e["file"], e["n"], e["ts"], e["text"][:70]))
