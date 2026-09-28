import json
import os
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "skills" / "triage" / "scripts" / "triage.py"
sys.path.insert(0, str(SCRIPT.parent))
sys.path.insert(0, str(ROOT / "benchmark"))

from eval_rules import load_cases  # noqa: E402
from triage import DEFAULT_RULES, clinic_for, clinic_ids, load_providers, load_rules, triage  # noqa: E402

RULES = load_rules(DEFAULT_RULES)
PROVIDERS = load_providers()
ENV = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_BASE_URL", "CLAUDE_TRIAGE", "CLAUDE_TRIAGE_PROVIDER")}


def run(*args, stdin=""):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", env=ENV)


class Roster(unittest.TestCase):
    def test_clinics_are_ordered_by_min_score(self):
        scores = [c["min_score"] for c in RULES["clinics"][1:]]
        self.assertIsNone(RULES["clinics"][0]["min_score"])
        self.assertEqual(scores, sorted(scores))

    def test_score_bands(self):
        self.assertEqual([clinic_for(s, RULES) for s in (-3, 1, 2, 4, 5, 7, 8, 11, 12, 30)],
                         ["quick", "quick", "standard", "standard", "deep", "deep",
                          "deep-max", "deep-max", "frontier", "frontier"])

    def test_every_provider_covers_every_clinic(self):
        for name, p in PROVIDERS.items():
            for cid in clinic_ids(RULES):
                self.assertIn(cid, p["models"], f"{name} lacks {cid}")


class BenchmarkCases(unittest.TestCase):
    def test_every_seed_case(self):
        for case in load_cases():
            with self.subTest(case["id"]):
                self.assertEqual(triage(case["prompt"], RULES)["clinic"], case["expected"], case["prompt"])


class Behaviour(unittest.TestCase):
    def test_override_wins_and_skips_second_opinion(self):
        r = triage("@quick 帮我设计一个分布式系统的架构", RULES)
        self.assertEqual((r["clinic"], r["confidence"], r["needs_second_opinion"]), ("quick", "manual", False))

    def test_longest_override_token_wins(self):
        self.assertEqual(triage("@opus-max 看看这个", RULES)["clinic"], "deep-max")
        self.assertEqual(triage("@opus 看看这个", RULES)["clinic"], "deep")

    def test_exact_model_and_effort(self):
        r = triage("@deep-max 看看这个", RULES, PROVIDERS, "claude")
        self.assertEqual((r["model_id"], r["model_name"], r["effort"]), ("claude-opus-5-5", "Claude Opus 5.5", "max"))
        r = triage("@frontier 看看这个", RULES, PROVIDERS, "claude")
        self.assertEqual((r["model_id"], r["effort"]), ("claude-fable-5-1", "max"))
        self.assertEqual(r["agent"], "claude-triage:triage-frontier")

    def test_cjk_next_to_english_keyword(self):
        self.assertTrue(any(s["id"] == "bug_fix" for s in triage("这个bug怎么修", RULES)["signals"]))

    def test_unrecognised_request_needs_second_opinion(self):
        self.assertTrue(triage("看看这个", RULES)["needs_second_opinion"])

    def test_mixed_signals_need_second_opinion(self):
        self.assertTrue(triage("把这份微服务架构文档翻译成英文", RULES)["needs_second_opinion"])

    def test_cost_estimate_is_cheaper_than_top_clinic(self):
        e = triage("Translate 'hello' into French", RULES, PROVIDERS, "claude")["estimate"]
        self.assertLess(e["cost_usd"], e["strongest_cost_usd"])
        self.assertGreater(e["saving_pct"], 50)


class Cli(unittest.TestCase):
    def test_reads_stdin(self):
        out = run("--format", "json", stdin="证明这个算法的时间复杂度是 O(n log n)")
        self.assertEqual(json.loads(out.stdout)["clinic"], "deep")

    def test_slip_names_exact_version(self):
        out = run("--format", "slip", "--provider", "claude", stdin="@deep-max 看看这个")
        self.assertIn("Claude Opus 5.5（claude-opus-5-5", out.stdout)
        self.assertIn("思考深度  max", out.stdout)

    def test_rejects_empty_input(self):
        self.assertEqual(run(stdin="   ").returncode, 2)


class Hook(unittest.TestCase):
    def test_hook_attaches_slip(self):
        out = run("--hook", stdin=json.dumps({"prompt": "@deep-max 帮我看看", "session_id": "x"}))
        ctx = json.loads(out.stdout)["hookSpecificOutput"]
        self.assertEqual(ctx["hookEventName"], "UserPromptSubmit")
        self.assertIn("<triage-slip>", ctx["additionalContext"])
        self.assertIn('"agent": "claude-triage:triage-deep-max"', ctx["additionalContext"])

    def test_hook_skips_slash_commands_and_bad_input(self):
        for stdin in (json.dumps({"prompt": "/help"}), "not json", json.dumps({"prompt": "  "})):
            out = run("--hook", stdin=stdin)
            self.assertEqual((out.returncode, out.stdout), (0, ""), stdin)

    def test_hook_can_be_switched_off(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "--hook"], input=json.dumps({"prompt": "hi"}),
                             capture_output=True, text=True, env={**ENV, "CLAUDE_TRIAGE": "off"})
        self.assertEqual(out.stdout, "")

    def test_hook_uses_detected_provider(self):
        out = subprocess.run([sys.executable, str(SCRIPT), "--hook"], input=json.dumps({"prompt": "hi"}),
                             capture_output=True, text=True, encoding="utf-8",
                             env={**ENV, "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic"})
        ctx = json.loads(out.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn('"agent": "triage-quick-deepseek"', ctx)


if __name__ == "__main__":
    unittest.main()
