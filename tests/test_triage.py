import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "triage" / "scripts" / "triage.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(ROOT / "benchmark"))

from eval_rules import load_cases  # noqa: E402
from triage import DEFAULT_RULES, load_providers, load_rules, triage  # noqa: E402

RULES = load_rules(DEFAULT_RULES)


class BenchmarkCases(unittest.TestCase):
    def test_every_seed_case(self):
        for case in load_cases():
            with self.subTest(case["id"]):
                self.assertEqual(triage(case["prompt"], RULES)["tier"], case["expected"], case["prompt"])


class Behaviour(unittest.TestCase):
    def test_override_wins_and_skips_nurse(self):
        r = triage("@quick 帮我设计一个分布式系统的架构", RULES)
        self.assertEqual((r["tier"], r["confidence"], r["needs_nurse"]), ("quick", "manual", False))

    def test_cjk_next_to_english_keyword(self):
        self.assertTrue(any(s["id"] == "bug_fix" for s in triage("这个bug怎么修", RULES)["signals"]))

    def test_unrecognised_request_goes_to_nurse(self):
        self.assertTrue(triage("看看这个", RULES)["needs_nurse"])

    def test_mixed_signals_go_to_nurse(self):
        self.assertTrue(triage("把这份微服务架构文档翻译成英文", RULES)["needs_nurse"])

    def test_cost_estimate_is_cheaper_below_deep(self):
        e = triage("Translate 'hello' into French", RULES, load_providers(), "claude")["estimate"]
        self.assertLess(e["cost_usd"], e["always_deep_cost_usd"])
        self.assertGreater(e["saving_pct"], 50)

    def test_cli_reads_stdin(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "--format", "json"],
                             input="证明这个算法的时间复杂度是 O(n log n)", capture_output=True,
                             text=True, encoding="utf-8", check=True).stdout
        self.assertEqual(json.loads(out)["tier"], "deep")

    def test_cli_rejects_empty_input(self):
        proc = subprocess.run([sys.executable, str(SCRIPT)], input="   ", capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)


if __name__ == "__main__":
    unittest.main()
