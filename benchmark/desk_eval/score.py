"""Score a desk_eval run: right executor per language, and cost / time."""
import json, sys, statistics
rows = [json.loads(l) for l in open(sys.argv[1])]
def ok(r):
    if r["expected_agent"] == "desk": return r["desk_agent"] is None
    return r["desk_agent"] == r["expected_agent"]
for lang in ("en", "zh", ""):
    s = [r for r in rows if f"-{lang}-" in r["id"] or not lang]
    print(lang or "all", f"{sum(map(ok, s))}/{len(s)}", "no-dispatch", sum(r["desk_agent"] is None for r in s),
          "unclear-agent", sum((r["desk_agent"] or "").endswith("t3-read") and r["expected_agent"]!=r["desk_agent"] for r in s))
c = [r["cost"] for r in rows if r["cost"]]; t = [r["secs"] for r in rows]
print("cost mean", round(sum(c)/len(c), 4), "median secs", statistics.median(t))
