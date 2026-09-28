#!/usr/bin/env python3
"""Routing regression: does the rule engine put each request in the expected category?

Checks two sets:
  - every category's own `example` in skills/triage/taxonomy.json
  - the hand-labelled prompts in benchmark/triage-cases.jsonl
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "triage" / "scripts"))

from triage import load_rules, load_taxonomy, triage  # noqa: E402

CASES = Path(__file__).resolve().parent / "triage-cases.jsonl"


def load_cases(path: Path = CASES) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def check(rows: list[tuple[str, str, str, str | None]], rules: dict, tax: dict) -> tuple[int, int, list[str]]:
    ok_cat = ok_dom = 0
    misses = []
    for rid, prompt, expected, expected_tier in rows:
        r = triage(prompt, rules, tax)
        got = r["category"]
        ok_dom += got.split(".")[0] == expected.split(".")[0]
        if got == expected and (expected_tier is None or r["tier"] == expected_tier):
            ok_cat += 1
        else:
            misses.append(f"  {rid}: expected {expected}{'/' + expected_tier if expected_tier else ''}, "
                          f"got {got}/{r['tier']} ({r['confidence']}) — {prompt[:50]!r}")
    return ok_cat, ok_dom, misses


def main() -> int:
    rules, tax = load_rules(), load_taxonomy()
    examples = [(c["id"], c["example"], c["id"], None) for c in tax["_by_id"].values() if c.get("example")]
    cases = [(c["id"], c["prompt"], c["expected_category"], c.get("expected_tier")) for c in load_cases()]
    failed = 0
    for name, rows in (("taxonomy examples", examples), ("labelled cases", cases)):
        ok_cat, ok_dom, misses = check(rows, rules, tax)
        n = len(rows)
        print(f"{name}: category {ok_cat}/{n} ({ok_cat / n:.0%}), domain {ok_dom}/{n} ({ok_dom / n:.0%})")
        for m in misses:
            print(m)
        failed += len(misses)
    low = sum(triage(p, rules, tax)["needs_second_opinion"] for _, p, _, _ in cases)
    print(f"labelled cases needing the desk's second opinion: {low}/{len(cases)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
