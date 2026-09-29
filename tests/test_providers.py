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
from triage import detect_provider, load_providers, load_rules, load_taxonomy, render_slip, triage  # noqa: E402

PROVIDERS = load_providers()
RULES = load_rules()
TAX = load_taxonomy()
TIERS = RULES["_tier_ids"]
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
            for cid in TIERS:
                m = p["models"][cid]
                with self.subTest(f"{name}/{cid}"):
                    self.assertTrue(m["id"] and m["name"])
                    self.assertNotIn(m["id"], ("haiku", "sonnet", "opus", "fable", "inherit"))
                    if m.get("effort") is not None:
                        self.assertIn(m["effort"], EFFORTS)

    def test_claude_ladder(self):
        got = {t: (m["id"], m.get("effort")) for t, m in PROVIDERS["claude"]["models"].items()}
        self.assertEqual(got, {
            "t1": ("claude-haiku-4-5", None),
            "t2": ("claude-sonnet-5-5", "low"),
            "t3": ("claude-sonnet-5-5", "medium"),
            "t4": ("claude-sonnet-5-5", "high"),
            "t5": ("claude-opus-5-5", "medium"),
            "t6": ("claude-opus-5-5", "high"),
            "t7": ("claude-opus-5-5", "max"),
            "t8": ("claude-fable-5-1", "max"),
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
        r = triage("这段 Go 代码在高并发下会死锁，帮我分析原因", RULES, TAX, PROVIDERS, "deepseek")
        self.assertEqual((r["category"], r["model_id"], r["agent"]),
                         ("software.concurrency-bug", "deepseek-v4-pro", "triage-t7-code-deepseek"))
        slip = render_slip(r, RULES, "zh")
        self.assertIn("DeepSeek V4 Pro（deepseek-v4-pro", slip)
        self.assertIn("未验证", slip)
        self.assertIn("未配置", slip)


class Agents(unittest.TestCase):
    def test_plugin_agents_are_up_to_date(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "gen_agents.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_docs_are_up_to_date(self):
        out = subprocess.run([sys.executable, str(SCRIPTS / "gen_docs.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(out.returncode, 0, out.stdout)

    def test_every_routed_agent_exists(self):
        for provider in PROVIDERS:
            files = generate(provider, RULES, TAX, PROVIDERS)
            names = {f[:-3] for f in files}
            for c in TAX["_by_id"].values():
                if c.get("handler") == "desk":
                    continue
                for text in filter(None, (c.get("example"), "整个项目 生产环境 " + (c.get("example") or ""), "@fable x", "@haiku x")):
                    r = triage(text, RULES, TAX, PROVIDERS, provider, c["id"])
                    self.assertIn(r["agent"].split(":")[-1], names, f"{provider} {c['id']} {r['agent']}")

    def test_executors_use_exact_models(self):
        for provider, p in PROVIDERS.items():
            files = generate(provider, RULES, TAX, PROVIDERS)
            suffix = "" if provider == "claude" else f"-{provider}"
            for tier in TIERS:
                for ts, spec in RULES["toolsets"].items():
                    fields, _ = parse_agent(files[f"triage-{tier}-{ts}{suffix}.md"])
                    with self.subTest(f"{provider}/{tier}/{ts}"):
                        self.assertEqual(fields["model"], p["models"][tier]["id"])
                        self.assertEqual(fields.get("effort"), p["models"][tier].get("effort"))
                        self.assertEqual(fields.get("tools"), spec["tools"])

    def test_desk_only_routes(self):
        fields, body = parse_agent(generate("claude", RULES, TAX, PROVIDERS)["triage-desk.md"])
        self.assertEqual(fields["model"], "claude-haiku-4-5")
        self.assertEqual(fields["tools"], "Agent, Skill, Bash, Glob")
        self.assertIn("never answer", body.lower())
        for cid in TAX["_by_id"]:
            self.assertIn(f"`{cid}`", body)

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
        self.assertEqual(cfg["env"]["ANTHROPIC_DEFAULT_OPUS_MODEL"], "kimi-k3")

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
        self.assertEqual(len(agents), len(TIERS) * len(RULES["toolsets"]) + 1)
        self.assertIn("model: mimo-v2.5", desk)
        self.assertNotIn("agent", back)
        self.assertEqual(back["env"], {"KEEP_ME": "1"})
        self.assertEqual(back["model"], "opus")


if __name__ == "__main__":
    unittest.main()
