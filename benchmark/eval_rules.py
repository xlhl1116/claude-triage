#!/usr/bin/env python3
"""Run the rule engine over benchmark/triage-cases.jsonl and print accuracy + confusion matrix."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "skills" / "triage" / "scripts"))

from triage import DEFAULT_RULES, TIER_ORDER, load_rules, triage  # noqa: E402

CASES = Path(__file__).resolve().parent / "triage-cases.jsonl"


def load_cases(path: Path = CASES) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def main() -> int:
    rules = load_rules(DEFAULT_RULES)
    cases = load_cases()
    matrix = {e: {p: 0 for p in TIER_ORDER} for e in TIER_ORDER}
    misses = []
    nurse = 0
    for c in cases:
        r = triage(c["prompt"], rules)
        matrix[c["expected"]][r["tier"]] += 1
        nurse += r["needs_nurse"]
        if r["tier"] != c["expected"]:
            misses.append((c["id"], c["expected"], r["tier"], r["score"], c["prompt"][:60]))

    correct = sum(matrix[t][t] for t in TIER_ORDER)
    print(f"accuracy: {correct}/{len(cases)} = {correct / len(cases):.1%}")
    print(f"sent to nurse (low confidence): {nurse}/{len(cases)}\n")
    print("expected \\ predicted  " + "  ".join(f"{t:>8}" for t in TIER_ORDER))
    for e in TIER_ORDER:
        print(f"{e:>20}  " + "  ".join(f"{matrix[e][p]:>8}" for p in TIER_ORDER))
    if misses:
        print("\nmisses:")
        for m in misses:
            print(f"  {m[0]}: expected {m[1]}, got {m[2]} (score {m[3]}) — {m[4]}")
    return 0 if not misses else 1


if __name__ == "__main__":
    sys.exit(main())
