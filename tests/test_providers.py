import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "skills" / "triage" / "scripts"
sys.path.insert(0, str(SCRIPTS))

from gen_agents import generate  # noqa: E402
from triage import DEFAULT_RULES, clinic_ids, detect_provider, load_providers, load_rules, render_slip, triage  # noqa: E402

PROVIDERS = load_providers()
RULES = load_rules(DEFAULT_RULES)
EFFORTS = {"low", "medium", "high", "xhigh", "max"}


def parse_agent(text):
    _, fm, body = text.split("---", 2)
    fields = dict(line.split(": ", 1) for line in fm.strip().splitlines())
    return fields, body


class Registry(unittest.TestCase):
    def test_expected_providers(self):
        self.assertEqual(set(PROVIDERS), {"claude", "deepseek", "kimi", "zhipu", "xiaomi"})

    def test_every_model_is_exact(self):
        for name, p in PROVIDERS.items():
            for cid in clinic_ids(RULES):
                m = p["models"][cid]
                with self.subTest(f"{name}/{cid}"):
                    self.assertTrue(m["id"] and m["name"])
                    self.assertNotIn(m["id"], ("haiku", "sonnet", "opus", "fable", "inherit"))
                    if m.get("effort") is not None:
                        self.assertIn(m["effort"], EFFORTS)

    def test_claude_roster(self):
        got = {cid: (m["id"], m.get("effort")) for cid, m in PROVIDERS["claude"]["models"].items()}
        self.assertEqual(got, {
            "quick": ("claude-haiku-4-5", None),
            "standard": ("claude-sonnet-5", "medium"),
            "deep": ("claude-opus-5-5", "medium"),
            "deep-max": ("claude-opus-5-5", "max"),
            "frontier": ("claude-fable-5-1", "max"),
        })


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
            "https://notdeepseek.com.evil.io": "claude",
        }
        for url, expected in cases.items():
            with self.subTest(url):
                self.assertEqual(detect_provider(PROVIDERS, url), expected)


class Slip(unittest.TestCase):
    def test_third_party_slip(self):
        r = triage("帮我设计一个分布式任务调度系统，处理并发和一致性", RULES, PROVIDERS, "deepseek")
        self.assertEqual((r["clinic"], r["model_id"], r["agent"]), ("deep-max", "deepseek-v4-pro", "triage-deep-max-deepseek"))
        slip = render_slip(r, RULES, "zh")
        self.assertIn("DeepSeek V4 Pro（deepseek-v4-pro", slip)
        self.assertIn("未验证", slip)
        self.assertIn("未配置", slip)


class Agents(unittest.TestCase):
    def test_plugin_agents_are_up_to_date(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "gen_agents.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_generated_agents_use_exact_models(self):
        for provider, p in PROVIDERS.items():
            files = generate(provider, RULES, PROVIDERS)
            self.assertEqual(len(files), len(RULES["clinics"]) + 1)
            for cid in clinic_ids(RULES):
                suffix = "" if provider == "claude" else f"-{provider}"
                fields, _ = parse_agent(files[f"triage-{cid}{suffix}.md"])
                with self.subTest(f"{provider}/{cid}"):
                    self.assertEqual(fields["model"], p["models"][cid]["id"])
                    self.assertEqual(fields.get("effort"), p["models"][cid].get("effort"))

    def test_desk_only_routes(self):
        fields, body = parse_agent(generate("claude", RULES, PROVIDERS)["triage-desk.md"])
        self.assertEqual(fields["model"], "claude-haiku-4-5")
        self.assertEqual(fields["tools"], "Agent, Skill, Bash")
        for cid in clinic_ids(RULES):
            self.assertIn(f"claude-triage:triage-{cid}", body)
        self.assertIn("Never answer the request yourself", body)

    def test_plugin_runs_desk_as_main_thread(self):
        self.assertEqual(json.loads((ROOT / "settings.json").read_text())["agent"], "triage-desk")
        hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text())["hooks"]["UserPromptSubmit"]
        self.assertIn("--hook", hooks[0]["hooks"][0]["command"])


class UseProvider(unittest.TestCase):
    def run_script(self, *args, **kw):
        return subprocess.run([sys.executable, str(SCRIPTS / "use_provider.py"), *args], capture_output=True,
                              text=True, encoding="utf-8", **kw)

    def test_print_mode(self):
        cfg = json.loads(self.run_script("kimi", check=True).stdout)
        self.assertEqual(cfg["agent"], "triage-desk-kimi")
        self.assertEqual(cfg["env"]["ANTHROPIC_BASE_URL"], "https://api.moonshot.cn/anthropic")
        self.assertEqual(cfg["env"]["ANTHROPIC_DEFAULT_HAIKU_MODEL"], "kimi-k2.7-code-highspeed")

    def test_intl_endpoint(self):
        cfg = json.loads(self.run_script("zhipu", "--intl", check=True).stdout)
        self.assertEqual(cfg["env"]["ANTHROPIC_BASE_URL"], "https://api.z.ai/api/anthropic")

    def test_write_and_switch_back(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp, "settings.json")
            path.write_text(json.dumps({"model": "opus", "env": {
                "CLAUDE_CODE_SUBAGENT_MODEL": "x", "ANTHROPIC_MODEL": "y", "KEEP_ME": "1"}}))
            self.run_script("xiaomi", "--write", str(path), check=True)
            settings = json.loads(path.read_text())
            agents = sorted(p.name for p in Path(tmp, "agents").glob("*.md"))
            desk = Path(tmp, "agents", "triage-desk-xiaomi.md").read_text()

            self.run_script("claude", "--write", str(path), check=True)
            back = json.loads(path.read_text())

        self.assertEqual(settings["agent"], "triage-desk-xiaomi")
        self.assertEqual(settings["model"], "opus")
        self.assertNotIn("CLAUDE_CODE_SUBAGENT_MODEL", settings["env"])
        self.assertNotIn("ANTHROPIC_MODEL", settings["env"])
        self.assertEqual(settings["env"]["KEEP_ME"], "1")
        self.assertEqual(len(agents), len(RULES["clinics"]) + 1)
        self.assertIn("model: mimo-v2.5", desk)
        self.assertNotIn("agent", back)
        self.assertEqual(back["env"], {"KEEP_ME": "1"})
        self.assertEqual(back["model"], "opus")


if __name__ == "__main__":
    unittest.main()
