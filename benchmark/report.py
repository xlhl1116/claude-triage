#!/usr/bin/env python3
"""Summarise a benchmark run: results/<run-id>/ -> summary.json + summary.md.

    python3 benchmark/report.py benchmark/results/<run-id>
"""

from __future__ import annotations

import json
import statistics
import sys
from pathlib import Path

DIFFICULTIES = ["easy", "medium", "hard"]


def read_jsonl(path: Path) -> dict:
    rows = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                rows[row.get("key") or row["task_id"]] = row
    return rows


def summarise(run_dir: Path, config: dict) -> dict:
    from run_bench import CLINICS, gen_key, resolve_strategy  # local import: avoid a cycle at module load

    meta = json.loads((run_dir / "meta.json").read_text(encoding="utf-8"))
    gens = read_jsonl(run_dir / "generations.jsonl")
    routing = read_jsonl(run_dir / "routing.jsonl")
    strategies = {}
    for name in meta["strategies"]:
        rows, opinion_cost = [], 0.0
        for task_id in meta["task_ids"]:
            for rep in range(meta["repeats"]):
                target, effort = resolve_strategy(config, name, routing.get(f"{name.split(':')[0]}|{task_id}"))
                row = gens.get(gen_key(config, target, effort, task_id, rep))
                if row:
                    rows.append(row)
            rkey = f"{name.split(':')[0]}|{task_id}"
            if name.endswith(":triage") and rkey in routing:
                opinion_cost += (routing[rkey].get("second_opinion_cost_usd") or 0.0) * meta["repeats"]
        if not rows:
            continue
        passed = [r for r in rows if r["grade"]["passed"]]
        costs = [r["cost_usd"] for r in rows if r.get("cost_usd") is not None]
        priced = len(costs) == len(rows)
        total_cost = sum(costs) + opinion_cost if priced else None
        by_diff = {}
        for d in DIFFICULTIES:
            sub = [r for r in rows if r["difficulty"] == d]
            if sub:
                by_diff[d] = sum(r["grade"]["passed"] for r in sub) / len(sub)
        strategies[name] = {
            "models": sorted({config["targets"][r["target"]]["label"] for r in rows}),
            "n": len(rows),
            "passed": len(passed),
            "pass_rate": len(passed) / len(rows),
            "pass_rate_by_difficulty": by_diff,
            "mean_score": statistics.mean(r["grade"]["score"] for r in rows),
            "cost_usd": total_cost,
            "second_opinion_cost_usd": opinion_cost,
            "cost_per_pass_usd": (total_cost / len(passed)) if priced and passed else None,
            "median_latency_s": statistics.median(r.get("latency_s", 0.0) for r in rows),
            "output_tokens": sum(r.get("usage", {}).get("output_tokens", 0) for r in rows),
            "errors": sum(1 for r in rows if str(r.get("stop_reason", "")).startswith("error")),
        }

    # each provider is compared with always using its own strongest clinic
    for name, st in strategies.items():
        base = strategies.get(name.split(":")[0] + ":" + CLINICS[-1])
        if not base:
            continue
        if base["cost_usd"] and st["cost_usd"] is not None:
            st["cost_vs_baseline"] = st["cost_usd"] / base["cost_usd"]
        st["pass_rate_delta_vs_baseline"] = st["pass_rate"] - base["pass_rate"]

    confusion = {}
    for r in routing.values():
        c = confusion.setdefault(r["provider"], {}).setdefault(r["difficulty"], {})
        c[r["clinic"]] = c.get(r["clinic"], 0) + 1

    judge_cost = sum(r.get("judge_cost_usd", 0.0) for r in gens.values())
    return {"meta": meta, "strategies": strategies, "routing_confusion": confusion,
            "second_opinion_calls": sum(1 for r in routing.values() if r.get("second_opinion")),
            "judge_cost_usd": judge_cost}


def fmt_money(x) -> str:
    return "—" if x is None else f"${x:.3f}"


def fmt_pct(x) -> str:
    return "—" if x is None else f"{x:.0%}"


def render_md(s: dict) -> str:
    meta = s["meta"]
    lines = []
    if meta["backend"] == "mock":
        lines += ["> ⚠️ **MOCK RUN — fake answers from the offline mock backend. These numbers say nothing about real models.**", ""]
    lines += [f"# Benchmark run `{Path(meta.get('run_dir', '')).name or meta['started']}`", "",
              f"- backend: `{meta['backend']}` · started {meta['started']} · {len(meta['task_ids'])} tasks × {meta['repeats']} repeat(s)",
              f"- models: " + ", ".join(f"`{k}` = {v}" for k, v in meta["models"].items()),
              f"- baseline: each provider's own strongest clinic · second opinion: {'on' if meta.get('second_opinion') else 'off'} · region: {meta.get('region', 'cn')}", ""]

    lines += ["## Quality and cost", "",
              "| strategy | pass rate | easy | medium | hard | Δ vs strongest | cost | cost vs strongest | cost / pass | median latency |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for name, r in s["strategies"].items():
        d = r["pass_rate_by_difficulty"]
        delta = r.get("pass_rate_delta_vs_baseline")
        lines.append(
            f"| {name} ({', '.join(r['models'])}) | {r['passed']}/{r['n']} ({r['pass_rate']:.0%}) | {fmt_pct(d.get('easy'))} | {fmt_pct(d.get('medium'))} | "
            f"{fmt_pct(d.get('hard'))} | {'—' if delta is None else f'{delta:+.0%}'} | {fmt_money(r['cost_usd'])} | "
            f"{fmt_pct(r.get('cost_vs_baseline'))} | {fmt_money(r['cost_per_pass_usd'])} | {r['median_latency_s']:.1f}s |")
    lines += ["", "Cost is generation cost only (plus second-opinion calls for triage); “—” means no pricing is configured for that model. "
              f"Judge cost, not included above: {fmt_money(s['judge_cost_usd'])}.", ""]

    from run_bench import CLINICS
    tiers = CLINICS
    for provider, conf in s["routing_confusion"].items():
        lines += [f"## Routing on `{provider}` (human difficulty label → clinic chosen)", "",
                  "| difficulty | " + " | ".join(tiers) + " |", "|---|" + "---:|" * len(tiers)]
        for d in DIFFICULTIES:
            row = conf.get(d, {})
            lines.append(f"| {d} | " + " | ".join(str(row.get(t, 0)) for t in tiers) + " |")
        lines.append("")
    if s["routing_confusion"]:
        lines += [f"Second-opinion calls: {s['second_opinion_calls']}.", ""]
    return "\n".join(lines)


def write_report(run_dir: Path, config: dict) -> dict:
    s = summarise(run_dir, config)
    s["meta"]["run_dir"] = str(run_dir)
    (run_dir / "summary.json").write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    (run_dir / "summary.md").write_text(render_md(s), encoding="utf-8")
    return s


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from run_bench import load_config

    write_report(Path(sys.argv[1]), load_config())
    print((Path(sys.argv[1]) / "summary.md").read_text(encoding="utf-8"))
