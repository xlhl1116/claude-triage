#!/usr/bin/env python3
"""Routing-only eval of the triage desk: which executor does it dispatch each request to?

    python3 benchmark/desk_eval/run.py <plugin dir> <cases.jsonl> <out.jsonl> [workers]
    python3 benchmark/desk_eval/score.py <out.jsonl>

Runs `claude -p` with the plugin once per case. A PreToolUse hook (log_agent.py) records the desk's
Agent call and denies it, so executors never run: about $0.03 and 20 s per case. Set SAVE_DIR to keep
each case's stream-json transcript. Resumes: cases already in <out.jsonl> are skipped.
"""
import json, os, subprocess, sys, tempfile, time, shutil
from concurrent.futures import ThreadPoolExecutor
HERE = os.path.dirname(os.path.abspath(__file__))
repo, cases_path, out_path = sys.argv[1:4]
workers = int(sys.argv[4]) if len(sys.argv) > 4 else 6
sys.path.insert(0, os.path.join(repo, "skills/triage/scripts"))
import triage as T
R, TX, P = T.load_rules(), T.load_taxonomy(), T.load_providers()
settings = json.dumps({"hooks": {"PreToolUse": [{"matcher": "Agent|Task", "hooks": [{"type": "command", "command": f"python3 {HERE}/log_agent.py"}]}]}})
env0 = {k: v for k, v in os.environ.items() if not (k.startswith("CLAUDE_") or k == "CLAUDECODE")}
env0["IS_SANDBOX"] = "1"
done = set()
if os.path.exists(out_path):
    done = {json.loads(l)["id"] for l in open(out_path)}
cases = [json.loads(l) for l in open(cases_path) if l.strip()]
def one(c):
    wd = tempfile.mkdtemp()
    log = os.path.join(wd, "agent.log")
    env = dict(env0, DESK_LOG=log)
    t = time.time()
    try:
        p = subprocess.run(["claude", "-p", c["prompt"], "--plugin-dir", repo, "--settings", settings,
                            "--output-format", "stream-json", "--verbose", "--permission-mode", "bypassPermissions",
                            "--max-turns", "6"], cwd=wd, env=env, capture_output=True, text=True, timeout=240)
        out = p.stdout
    except subprocess.TimeoutExpired as ex:
        out = ex.stdout or ""
        out = out.decode() if isinstance(out, bytes) else out
    if os.environ.get("SAVE_DIR"):
        open(os.path.join(os.environ["SAVE_DIR"], c["id"] + ".jsonl"), "w").write(out)
    cost = None; cats = []; model = None
    for line in out.splitlines():
        try: e = json.loads(line)
        except ValueError: continue
        if e.get("type") == "result": cost = e.get("total_cost_usd")
        if e.get("type") == "system" and e.get("subtype") == "init": model = e.get("model")
        if e.get("type") == "assistant":
            for b in e["message"].get("content", []):
                if b.get("type") == "tool_use" and b["name"] == "Bash":
                    cmd = b["input"].get("command", "")
                    if "--category" in cmd:
                        cats.append(cmd.split("--category")[1].split()[0])
    calls = [json.loads(l) for l in open(log)] if os.path.exists(log) else []
    agents = [x["agent"] for x in calls if x["agent"]]
    rule = T.triage(c["prompt"], R, TX, P, "claude")
    exp = T.triage(c["prompt"], R, TX, P, "claude", c["expected_category"])
    shutil.rmtree(wd, ignore_errors=True)
    return {"id": c["id"], "prompt": c["prompt"], "expected": c["expected_category"],
            "rule_category": rule["category"], "rule_confidence": rule["confidence"],
            "expected_agent": exp.get("agent", "desk"), "desk_categories": cats,
            "desk_agent": agents[0] if agents else None, "malformed": sum(1 for x in calls if not x["agent"]), "cost": cost, "secs": round(time.time() - t), "model": model}
todo = [c for c in cases if c["id"] not in done]
with ThreadPoolExecutor(workers) as ex, open(out_path, "a") as f:
    for r in ex.map(one, todo):
        f.write(json.dumps(r, ensure_ascii=False) + "\n"); f.flush()
        print(r["id"], r["expected_agent"], r["desk_agent"], r["cost"], r["secs"], flush=True)
