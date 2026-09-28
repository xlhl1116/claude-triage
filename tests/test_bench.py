import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "benchmark"))

import graders  # noqa: E402
import run_bench  # noqa: E402
from tasks import TASKS  # noqa: E402


class References(unittest.TestCase):
    def test_every_reference_passes_its_grader(self):
        for t in TASKS:
            if t["grader"]["type"] == "judge":
                continue
            with self.subTest(t["id"]):
                self.assertTrue(graders.grade(t, t["reference"])["passed"])

    def test_wrong_answers_fail(self):
        by_id = {t["id"]: t for t in TASKS}
        self.assertFalse(graders.grade(by_id["easy-https-port"], "80")["passed"])
        self.assertFalse(graders.grade(by_id["hard-automorphic"], "The answer is\n10491")["passed"])
        self.assertFalse(graders.grade(by_id["med-lru"], "```python\nclass LRUCache: pass\n```")["passed"])


class Strategies(unittest.TestCase):
    def setUp(self):
        self.config = run_bench.load_config()

    def test_exact_model_and_effort(self):
        r = lambda name, row=None: run_bench.resolve_strategy(self.config, name, row)
        self.assertEqual(r("claude:t5"), ("claude/t5", "medium"))
        self.assertEqual(r("claude:t7"), ("claude/t7", "max"))
        self.assertEqual(r("claude:t1"), ("claude/t1", None))
        self.assertEqual(r("claude:triage", {"tier": "t8"}), ("claude/t8", "max"))
        self.assertEqual(self.config["targets"]["claude/t8"]["id"], "claude-fable-5-1")
        # third-party depth goes through extra_body, not a Claude effort value
        self.assertEqual(r("deepseek:t7"), ("deepseek/t7", None))
        self.assertEqual(self.config["targets"]["deepseek/t7"]["extra"]["reasoning_effort"], "max")

    def test_identical_requests_share_a_generation(self):
        k = lambda target, effort: run_bench.gen_key(self.config, target, effort, "t", 0)
        self.assertEqual(k("deepseek/t7", None), k("deepseek/t8", None))
        self.assertNotEqual(k("claude/t5", "medium"), k("claude/t7", "max"))

    def test_routing_uses_the_taxonomy(self):
        task = next(t for t in TASKS if t["id"] == "hard-shared-default-bug")
        rec = run_bench.route("claude", task, run_bench.MockBackend(self.config), self.config)
        self.assertEqual((rec["category"], rec["tier"]), ("software.hard-debug", "t7"))

    def test_intl_region_switches_bench_endpoint(self):
        intl = run_bench.load_config(region="intl")
        self.assertEqual(intl["targets"]["kimi/t7"]["base_url"], "https://api.moonshot.ai/v1")
        self.assertEqual(self.config["targets"]["kimi/t7"]["base_url"], "https://api.moonshot.cn/v1")


class FakeChat(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeChat.seen.append((self.path, self.headers["Authorization"], body))
        reply = {"choices": [{"message": {"content": "443"}, "finish_reason": "stop"}],
                 "usage": {"prompt_tokens": 12, "completion_tokens": 3}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class OpenAICompat(unittest.TestCase):
    def test_request_shape_and_parsing(self):
        server = HTTPServer(("127.0.0.1", 0), FakeChat)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            config = run_bench.load_config()
            target = dict(config["targets"]["deepseek/t7"], base_url=f"http://127.0.0.1:{server.server_port}")
            with mock.patch.dict("os.environ", {"DEEPSEEK_API_KEY": "sk-test", "NO_PROXY": "127.0.0.1"}):
                out = run_bench.call_openai_compat(target, None, "sys", "What port?", 100)
        finally:
            server.shutdown()
            server.server_close()
        path, auth, body = FakeChat.seen[-1]
        self.assertEqual(path, "/chat/completions")
        self.assertEqual(auth, "Bearer sk-test")
        self.assertEqual(body["model"], "deepseek-v4-pro")
        self.assertEqual(body["thinking"], {"type": "enabled"})
        self.assertEqual(body["messages"][0], {"role": "system", "content": "sys"})
        self.assertEqual(out["text"], "443")
        self.assertEqual(out["usage"], {"input_tokens": 12, "output_tokens": 3})

    def test_missing_key_is_a_clear_error(self):
        config = run_bench.load_config()
        with mock.patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "MIMO_API_KEY"):
                run_bench.call_openai_compat(config["targets"]["xiaomi/t7"], None, "s", "p", 10)


class MockRun(unittest.TestCase):
    def test_mock_run_end_to_end(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(run_bench, "RESULTS_DIR", Path(tmp)):
            rc = run_bench.main(["--backend", "mock", "--providers", "claude,kimi", "--run-id", "t",
                                 "--difficulty", "easy,hard"])
            summary = json.loads(Path(tmp, "t", "summary.json").read_text(encoding="utf-8"))
        self.assertEqual(rc, 0)
        self.assertEqual(summary["strategies"]["kimi:t8"]["pass_rate"], 1.0)
        self.assertIn("kimi", summary["routing_confusion"])


if __name__ == "__main__":
    unittest.main()
