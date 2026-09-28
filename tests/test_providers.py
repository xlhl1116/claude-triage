import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "triage" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from triage import DEFAULT_RULES, TIER_ORDER, detect_provider, load_providers, load_rules, render_slip, triage  # noqa: E402

PROVIDERS = load_providers()
RULES = load_rules(DEFAULT_RULES)


class Registry(unittest.TestCase):
    def test_expected_providers(self):
        self.assertEqual(set(PROVIDERS), {"claude", "deepseek", "kimi", "zhipu", "xiaomi"})

    def test_every_provider_is_complete(self):
        for name, p in PROVIDERS.items():
            with self.subTest(name):
                for key in ("label_en", "label_zh", "key_env", "detect_hosts", "docs", "bench", "models"):
                    self.assertIn(key, p)
                self.assertIn(p["bench"]["api"], ("anthropic", "openai"))
                for tier in TIER_ORDER:
                    self.assertTrue(p["models"][tier]["id"])
                if p["claude_code"]:
                    self.assertTrue(p["claude_code"]["base_url"].startswith("https://"))


class Detection(unittest.TestCase):
    def test_detect_from_base_url(self):
        cases = {
            "https://api.deepseek.com/anthropic": "deepseek",
            "https://api.moonshot.cn/anthropic": "kimi",
            "https://api.moonshot.ai/anthropic": "kimi",
            "https://open.bigmodel.cn/api/anthropic": "zhipu",
            "https://api.z.ai/api/anthropic": "zhipu",
            "https://api.xiaomimimo.com/anthropic": "xiaomi",
            "https://token-plan-cn.xiaomimimo.com/anthropic": "xiaomi",
            "https://api.anthropic.com": "claude",
            "": "claude",
            "https://my-proxy.example.com": "claude",
        }
        for url, expected in cases.items():
            with self.subTest(url):
                self.assertEqual(detect_provider(PROVIDERS, url), expected)

    def test_lookalike_host_is_not_matched(self):
        self.assertEqual(detect_provider(PROVIDERS, "https://notdeepseek.com.evil.io"), "claude")


class Slip(unittest.TestCase):
    def test_third_party_slip_shows_real_model_and_no_price(self):
        r = triage("帮我设计一个分布式任务调度系统的架构", RULES, PROVIDERS, "deepseek")
        self.assertEqual((r["tier"], r["model_id"]), ("deep", "deepseek-v4-pro"))
        self.assertIsNone(r["estimate"]["cost_usd"])
        slip = render_slip(r, RULES, "zh")
        self.assertIn("deepseek-v4-pro", slip)
        self.assertIn("未配置", slip)

    def test_claude_slip_keeps_cost(self):
        r = triage("Translate 'hello' into French", RULES, PROVIDERS, "claude")
        self.assertIsNotNone(r["estimate"]["cost_usd"])
        self.assertIn("haiku", render_slip(r, RULES, "en"))

    def test_cli_provider_flag(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "triage.py"), "--provider", "zhipu", "--format", "json"],
                             input="hi", capture_output=True, text=True, encoding="utf-8", check=True).stdout
        self.assertEqual(json.loads(out)["model_id"], "glm-5.3-flash")


class UseProvider(unittest.TestCase):
    def run_script(self, *args, **kw):
        return subprocess.run([sys.executable, str(SCRIPTS / "use_provider.py"), *args], capture_output=True,
                              text=True, encoding="utf-8", **kw)

    def test_prints_alias_mapping(self):
        env = json.loads(self.run_script("kimi", check=True).stdout)["env"]
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.moonshot.cn/anthropic")
        self.assertEqual(env["ANTHROPIC_DEFAULT_OPUS_MODEL"], "kimi-k3")
        self.assertIn("ANTHROPIC_AUTH_TOKEN", env)

    def test_intl_endpoint(self):
        env = json.loads(self.run_script("zhipu", "--intl", check=True).stdout)["env"]
        self.assertEqual(env["ANTHROPIC_BASE_URL"], "https://api.z.ai/api/anthropic")

    def test_write_merges_and_removes_overrides(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "settings.json")
            path.write_text(json.dumps({"model": "opus", "env": {
                "CLAUDE_CODE_SUBAGENT_MODEL": "x", "ANTHROPIC_MODEL": "y", "KEEP_ME": "1"}}))
            self.run_script("xiaomi", "--write", str(path), check=True)
            settings = json.loads(path.read_text())
        self.assertEqual(settings["model"], "opus")
        env = settings["env"]
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", env)
        self.assertNotIn("ANTHROPIC_MODEL", env)
        self.assertEqual(env["KEEP_ME"], "1")
        self.assertEqual(env["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "mimo-v2.5")


if __name__ == "__main__":
    unittest.main()
