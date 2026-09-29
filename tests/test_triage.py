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
from triage import adjust_tier, load_providers, load_rules, load_taxonomy, triage  # noqa: E402

RULES = load_rules()
TAX = load_taxonomy()
PROVIDERS = load_providers()
ENV = {k: v for k, v in os.environ.items() if k not in ("ANTHROPIC_BASE_URL", "CLAUDE_TRIAGE", "CLAUDE_TRIAGE_PROVIDER")}


def run(*args, stdin="", env=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], input=stdin, capture_output=True,
                          text=True, encoding="utf-8", env=env or ENV)


def route(text, **kw):
    return triage(text, RULES, TAX, PROVIDERS, kw.pop("provider", "claude"), **kw)


class Taxonomy(unittest.TestCase):
    def test_shape(self):
        self.assertEqual(len(TAX["domains"]), 17)
        self.assertEqual(len(TAX["_by_id"]), 120)
        self.assertEqual(sum(c["id"].startswith("software.") for c in TAX["_by_id"].values()), 40)

    def test_every_category_is_well_formed(self):
        tiers = RULES["_tier_ids"]
        for c in TAX["_by_id"].values():
            with self.subTest(c["id"]):
                self.assertIn(c["tools"], RULES["toolsets"])
                if c.get("handler") != "desk":
                    self.assertIn(c["tier"], tiers)
                    self.assertNotEqual(c["tier"], tiers[-1], "the top tier is reached only by stacking")
                for bound in ("floor", "ceiling"):
                    if c.get(bound):
                        self.assertIn(c[bound], tiers)
                if not c.get("fallback"):
                    self.assertTrue(c["keywords"])
                    self.assertTrue(c.get("example"))

    def test_every_example_routes_to_its_own_category(self):
        for c in TAX["_by_id"].values():
            if c.get("example"):
                with self.subTest(c["id"]):
                    r = triage(c["example"], RULES, TAX)
                    self.assertEqual(r["category"], c["id"])
                    self.assertNotEqual(r["confidence"], "low")

    def test_labelled_cases(self):
        for case in load_cases():
            with self.subTest(case["id"]):
                r = triage(case["prompt"], RULES, TAX)
                self.assertEqual(r["category"], case["expected_category"], case["prompt"])
                if "expected_tier" in case:
                    self.assertEqual(r["tier"], case["expected_tier"])

    def test_every_provider_covers_every_tier(self):
        for name, p in PROVIDERS.items():
            for t in RULES["_tier_ids"]:
                self.assertIn(t, p["models"], f"{name} lacks {t}")


class Routing(unittest.TestCase):
    def test_category_sets_exact_model(self):
        r = route("这段 Go 代码在高并发下会死锁，帮我分析原因并修复")
        self.assertEqual(r["category"], "software.concurrency-bug")
        self.assertEqual((r["model_id"], r["model_name"], r["effort"]), ("claude-opus-5-5", "Claude Opus 5.5", "max"))
        self.assertEqual(r["agent"], "claude-triage:triage-t7-code")

    def test_simple_request_goes_cheap(self):
        r = route("把这句话翻译成英文：明天见")
        self.assertEqual((r["category"], r["model_id"]), ("language.translate", "claude-haiku-4-5"))
        self.assertEqual(r["agent"], "claude-triage:triage-t1-read")

    def test_scope_and_risk_raise_the_model(self):
        base = route("把项目从 Vue 2 升级到 Vue 3")
        big = route("把整个项目从 Vue 2 升级到 Vue 3，生产环境不能停")
        self.assertEqual((base["tier"], big["tier"]), ("t6", "t8"))
        self.assertEqual({m["id"] for m in big["modifiers"]}, {"scale", "risk"})

    def test_top_tier_needs_stacking(self):
        c = TAX["_by_id"]["software.hard-debug"]  # default t7
        self.assertEqual(adjust_tier("t7", 1, c, RULES), "t7")
        self.assertEqual(adjust_tier("t7", 2, c, RULES), "t8")
        c5 = TAX["_by_id"]["software.cross-module-feature"]  # default t5
        self.assertEqual(adjust_tier("t5", 2, c5, RULES), "t7")

    def test_explicit_steps_lower_the_model(self):
        r = route("按以下步骤写一个函数：1. 读文件 2. 统计行数")
        self.assertEqual(r["tier"], "t2")

    def test_floor_holds(self):
        r = route("按以下步骤回答：布洛芬的常规剂量是多少？")
        self.assertEqual(r["category"], "health.medication")
        self.assertEqual(r["tier"], "t5")  # t6 - 1, never below the t5 floor
        self.assertIn("doctor", r["guidance"])

    def test_ceiling_holds(self):
        self.assertEqual(route("你好")["tier"], "t1")

    def test_override_forces_model_keeps_category(self):
        r = route("@opus-max 把这句话翻译成英文：你好")
        self.assertEqual((r["category"], r["tier"], r["confidence"]), ("language.translate", "t7", "manual"))
        self.assertFalse(r["needs_second_opinion"])
        self.assertEqual(route("@opus 看看这个")["tier"], "t5")  # longest token wins over @opus-max
        self.assertEqual(route("@deep 翻译：你好")["tier"], "t5")  # old tokens still work

    def test_forced_category_is_the_desk_second_opinion(self):
        r = route("看看这个", category="software.security-audit")
        self.assertEqual((r["category"], r["tier"], r["confidence"]), ("software.security-audit", "t7", "desk"))

    def test_unknown_request_falls_back(self):
        r = triage("嗯嗯", RULES, TAX)
        self.assertEqual((r["category"], r["confidence"], r["needs_second_opinion"]), ("other.unclear", "low", True))

    def test_questions_about_triage_stay_at_the_desk(self):
        r = route("为什么把我的问题分到这个科室？")
        self.assertEqual((r["handler"], r["tier"]), ("desk", None))
        self.assertNotIn("agent", r)

    def test_cjk_next_to_english_keyword(self):
        self.assertEqual(triage("这个 TypeError: 报错怎么修复", RULES, TAX)["category"], "software.debug-clear-error")

    def test_cost_estimate(self):
        e = route("Translate 'hello' into French")["estimate"]
        self.assertLess(e["cost_usd"], e["strongest_cost_usd"])
        self.assertGreater(e["saving_pct"], 90)


class Cli(unittest.TestCase):
    def test_slip_names_category_and_exact_version(self):
        out = run("--format", "slip", "--provider", "claude", stdin="这段 Go 代码在高并发下会死锁，帮我分析原因").stdout
        self.assertIn("软件开发 › 并发、竞态、死锁", out)
        self.assertIn("Claude Opus 5.5（claude-opus-5-5", out)
        self.assertIn("思考深度  max", out)
        self.assertNotIn("t7", out)  # tiers stay internal

    def test_forced_category_flag(self):
        out = json.loads(run("--category", "law.contract-review", stdin="看看这个").stdout)
        self.assertEqual((out["category"], out["tier"]), ("law.contract-review", "t6"))
        self.assertEqual(run("--category", "nope", stdin="x").returncode, 2)

    def test_list_categories(self):
        self.assertEqual(len(run("--list-categories").stdout.strip().splitlines()), 120)

    def test_rejects_empty_input(self):
        self.assertEqual(run(stdin="   ").returncode, 2)


class Hook(unittest.TestCase):
    def context(self, prompt, env=None):
        out = run("--hook", stdin=json.dumps({"prompt": prompt, "session_id": "x"}), env=env)
        return json.loads(out.stdout)["hookSpecificOutput"]

    def test_hook_attaches_slip(self):
        ctx = self.context("这段 Go 代码在高并发下会死锁")
        self.assertEqual(ctx["hookEventName"], "UserPromptSubmit")
        text = ctx["additionalContext"]
        self.assertIn("<triage-slip>", text)
        self.assertIn('"agent": "claude-triage:triage-t7-code"', text)
        self.assertIn("--category <category-id>", text)
        self.assertIn('"footer": "— 💻 软件开发 › 并发、竞态、死锁 · Claude Opus 5.5 · effort max"', text)

    def test_hook_skips_slash_commands_and_bad_input(self):
        for stdin in (json.dumps({"prompt": "/help"}), "not json", json.dumps({"prompt": "  "})):
            out = run("--hook", stdin=stdin)
            self.assertEqual((out.returncode, out.stdout), (0, ""), stdin)

    def test_hook_skips_background_agent_results(self):
        # Claude Code feeds a finished background agent back to the desk as a prompt; it is not a request.
        note = "<task-notification>\n<status>completed</status>\n<summary>Agent finished</summary>\n</task-notification>"
        out = run("--hook", stdin=json.dumps({"prompt": note}))
        self.assertEqual((out.returncode, out.stdout), (0, ""))

    def test_footer_omits_effort_for_models_without_one(self):
        r = triage("Translate to French: see you on Thursday", RULES, TAX, PROVIDERS)
        self.assertEqual(r["footer"], "— 🌐 Language › Everyday translation · Claude Haiku 4.5")

    def test_hook_can_be_switched_off(self):
        out = run("--hook", stdin=json.dumps({"prompt": "hi"}), env={**ENV, "CLAUDE_TRIAGE": "off"})
        self.assertEqual(out.stdout, "")

    def test_hook_uses_detected_provider(self):
        ctx = self.context("你好", env={**ENV, "ANTHROPIC_BASE_URL": "https://api.deepseek.com/anthropic"})
        self.assertIn('"agent": "triage-t1-read-deepseek"', ctx["additionalContext"])


if __name__ == "__main__":
    unittest.main()
