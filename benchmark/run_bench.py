#!/usr/bin/env python3
"""Quality-vs-cost benchmark: fixed models vs. triage routing, for each provider.

    # 1. prove every grader and test is correct (no API calls)
    python3 benchmark/run_bench.py --check-references

    # 2. offline pipeline check with fake answers (no API calls)
    python3 benchmark/run_bench.py --backend mock --providers claude,deepseek --run-id mock

    # 3. what a real run would cost, where prices are configured (no API calls)
    python3 benchmark/run_bench.py --estimate --providers claude

    # 4. run for real. Claude needs ANTHROPIC_API_KEY and `pip install anthropic`;
    #    other providers need the key env var named in skills/triage/providers.json.
    python3 benchmark/run_bench.py --backend live --providers claude,deepseek --run-id first --yes

Strategies are '<provider>:<tier>' (always that tier's exact model and effort, e.g.
'claude:t7' = Claude Opus 5.5 at max; tiers are internal, see rules.json) and
'<provider>:triage' (the rule engine classifies each task into a category, which sets
the model; when it is not confident, the desk model gives a second opinion). Every
unique (model, effort, task, repeat) is generated once and shared, so a triage
strategy's quality and cost differ from the fixed models only through routing
(plus second-opinion calls).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "skills" / "triage" / "scripts"))

import graders  # noqa: E402
from tasks import TASKS  # noqa: E402
from triage import estimate_tokens, load_providers, load_rules, load_taxonomy, triage  # noqa: E402

CONFIG_PATH = HERE / "models.json"
RESULTS_DIR = HERE / "results"
RULES = load_rules()
TAXONOMY = load_taxonomy()
TIERS = RULES["_tier_ids"]
DEFAULT_FIXED = ["t1", "t3", "t5", "t7", "t8"]
SECOND_OPINION_PROMPT = """You are a triage desk. You do not solve the request; you only decide which category it belongs to.

Categories:
""" + "\n".join(f"- `{c['id']}`: {c['label_en']}" for c in TAXONOMY["_by_id"].values() if c.get("handler") != "desk") + """

Reply with exactly one JSON object and nothing else: {"category": "<id>", "reason": "<one short sentence>"}"""
JUDGE_SYSTEM = """You are a strict grader. You will see a task, a candidate answer, and a numbered rubric.
For each rubric item decide whether the answer clearly satisfies it. Be strict: vague mentions do not count.
Reply with exactly one JSON object: {"met": [true/false for each item, in order], "reason": "<one sentence>"}"""


# --------------------------------------------------------------------------- config

def load_config(path: Path = CONFIG_PATH, region: str = "cn") -> dict:
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    config["provider_defs"] = load_providers()
    config["targets"] = build_targets(config["provider_defs"], region)
    config["rules"] = RULES
    config["taxonomy"] = TAXONOMY
    return config


def build_targets(providers: dict, region: str = "cn") -> dict:
    """'<provider>/<tier>' -> everything needed to call that model."""
    targets = {}
    for pname, p in providers.items():
        bench = dict(p["bench"])
        if region == "intl" and bench.get("base_url_intl"):
            bench["base_url"] = bench["base_url_intl"]
        for tier in TIERS:
            m = p["models"][tier]
            targets[f"{pname}/{tier}"] = {
                "provider": pname, "tier": tier, "id": m["id"], "name": m.get("name", m["id"]),
                "api": bench["api"], "base_url": bench["base_url"], "key_env": p["key_env"],
                "effort": m.get("effort") if m.get("supports_effort") else None,
                "extra": m.get("extra_body", {}), "pricing": m.get("pricing"),
                "label": m.get("name", m["id"]) + (
                    f" · {m['effort']}" if m.get("supports_effort") and m.get("effort")
                    else f" · {m['api_effort']}" if m.get("api_effort") else ""),
            }
    return targets


def strategy_names(config: dict, providers: list[str]) -> list[str]:
    return [f"{p}:{t}" for p in providers for t in DEFAULT_FIXED + ["triage"]]


def resolve_strategy(config: dict, name: str, routing_row: dict | None) -> tuple[str, str | None]:
    """Strategy name -> (target key, effort) for one task. Third-party models express depth
    through extra_body in providers.json, so they carry no Claude effort value."""
    provider, kind = name.split(":")
    tier = routing_row["tier"] if kind == "triage" else kind
    target = f"{provider}/{tier}"
    return target, config["targets"][target]["effort"]


def cost_of(usage: dict, pricing: dict | None) -> float | None:
    if not pricing:
        return None
    return (usage.get("input_tokens", 0) * pricing["input"]
            + usage.get("output_tokens", 0) * pricing["output"]
            + usage.get("cache_creation_input_tokens", 0) * pricing.get("cache_write", pricing["input"])
            + usage.get("cache_read_input_tokens", 0) * pricing.get("cache_read", pricing["input"])) / 1_000_000


def parse_json_object(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


# --------------------------------------------------------------------------- backends

def call_anthropic(target: dict, effort: str | None, system: str, prompt: str, max_tokens: int) -> dict:
    try:
        import anthropic
    except ImportError:
        raise RuntimeError("pip install anthropic   # required for Anthropic-API targets")
    key = os.environ.get(target["key_env"])
    if not key:
        raise RuntimeError(f"{target['key_env']} is not set")
    client = anthropic.Anthropic(api_key=key, base_url=target["base_url"], max_retries=4)
    kwargs = {"model": target["id"], "max_tokens": max_tokens, "system": system,
              "messages": [{"role": "user", "content": prompt}]}
    if effort:
        kwargs["output_config"] = {"effort": effort}
    kwargs.update(target["extra"])
    with client.messages.stream(**kwargs) as stream:
        msg = stream.get_final_message()
    u = msg.usage
    usage = {"input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
             "cache_creation_input_tokens": getattr(u, "cache_creation_input_tokens", 0) or 0,
             "cache_read_input_tokens": getattr(u, "cache_read_input_tokens", 0) or 0}
    text = "".join(b.text for b in msg.content if b.type == "text")
    return {"text": text, "usage": usage, "stop_reason": msg.stop_reason}


def call_openai_compat(target: dict, effort: str | None, system: str, prompt: str, max_tokens: int) -> dict:
    """POST /chat/completions with the standard library, so no extra dependency is needed."""
    key = os.environ.get(target["key_env"])
    if not key:
        raise RuntimeError(f"{target['key_env']} is not set")
    body = {"model": target["id"], "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
    body.update(target["extra"])
    req = urllib.request.Request(
        target["base_url"].rstrip("/") + "/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, method="POST")
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=900) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(2 ** (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
    choice = data["choices"][0]
    u = data.get("usage") or {}
    usage = {"input_tokens": u.get("prompt_tokens", 0), "output_tokens": u.get("completion_tokens", 0)}
    return {"text": choice["message"].get("content") or "", "usage": usage,
            "stop_reason": choice.get("finish_reason")}


class LiveBackend:
    name = "live"
    APIS = {"anthropic": call_anthropic, "openai": call_openai_compat}

    def __init__(self, config: dict):
        self.config = config

    def call(self, target_key: str, effort: str | None, system: str, prompt: str, task: dict | None = None,
             max_tokens: int | None = None) -> dict:
        target = self.config["targets"][target_key]
        t0 = time.time()
        out = self.APIS[target["api"]](target, effort, system, prompt, max_tokens or self.config["max_tokens"])
        out["latency_s"] = round(time.time() - t0, 2)
        return out


class MockBackend:
    """Deterministic fake answers for testing the pipeline offline. NOT real model output."""

    name = "mock"
    STRENGTH = {"t1": 1, "t2": 2, "t3": 2, "t4": 2, "t5": 3, "t6": 3, "t7": 3, "t8": 3}
    DIFFICULTY = {"easy": 1, "medium": 2, "hard": 3}
    OUTPUT = {"t1": 300, "t2": 600, "t3": 900, "t4": 1500, "t5": 2400, "t6": 3500, "t7": 5000, "t8": 7000}

    def __init__(self, config: dict):
        self.config = config

    def call(self, target_key: str, effort: str | None, system: str, prompt: str, task: dict | None = None,
             max_tokens: int | None = None) -> dict:
        tier = self.config["targets"][target_key]["tier"]
        usage = {"input_tokens": estimate_tokens(system + prompt), "output_tokens": self.OUTPUT[tier]}
        if system == SECOND_OPINION_PROMPT:
            top = triage(task["prompt"], RULES, TAXONOMY)["category"]  # the mock desk agrees with the rules
            text = json.dumps({"category": top, "reason": "mock"})
            usage["output_tokens"] = 40
        elif system == JUDGE_SYSTEM:
            text = json.dumps({"met": [task["reference"] in prompt] * len(task["grader"]["rubric"]), "reason": "mock"})
            usage["output_tokens"] = 60
        elif self.STRENGTH[tier] >= self.DIFFICULTY[task["difficulty"]]:
            text = task["reference"]
        else:
            text = "I'm not sure."
        return {"text": text, "usage": usage, "latency_s": 0.0, "stop_reason": "end_turn"}


BACKENDS = {"live": LiveBackend, "mock": MockBackend}


# --------------------------------------------------------------------------- routing

def route(provider: str, task: dict, backend, config: dict, use_second_opinion: bool = True) -> dict:
    """Rule engine first; when it is not confident, the desk model (the provider's desk tier,
    as in Claude Code) picks the category, and the category sets the model."""
    rules, tax = config["rules"], config["taxonomy"]
    r = triage(task["prompt"], rules, tax)
    record = {"key": f"{provider}|{task['id']}", "provider": provider, "task_id": task["id"],
              "difficulty": task["difficulty"], "rule_category": r["category"], "category": r["category"],
              "confidence": r["confidence"], "tier": r["tier"] or TIERS[0], "second_opinion": None,
              "second_opinion_cost_usd": 0.0}
    if use_second_opinion and r["needs_second_opinion"]:
        desk = f"{provider}/{rules['desk']['tier']}"
        try:
            out = backend.call(desk, None, SECOND_OPINION_PROMPT, task["prompt"], task=task, max_tokens=300)
            record["second_opinion_cost_usd"] = cost_of(out["usage"], config["targets"][desk]["pricing"])
            verdict = parse_json_object(out["text"])
            if verdict.get("category") in tax["_by_id"]:
                r2 = triage(task["prompt"], rules, tax, category=verdict["category"])
                record.update(category=r2["category"], tier=r2["tier"] or TIERS[0])
            record["second_opinion"] = verdict
        except Exception as e:  # keep the rule verdict
            record["second_opinion"] = {"error": str(e)[:300]}
    return record


def gen_key(config: dict, target: str, effort: str | None, task_id: str, repeat: int) -> str:
    """Identical requests share one generation, e.g. two tiers that use the same
    model with the same settings."""
    t = config["targets"][target]
    extra = json.dumps(t["extra"], sort_keys=True) if t["extra"] else "-"
    return f"{t['provider']}|{t['id']}|{effort or '-'}|{extra}|{task_id}|{repeat}"


# --------------------------------------------------------------------------- run

class JsonlStore:
    def __init__(self, path: Path, key: str = "key"):
        self.path, self.key, self.lock = path, key, threading.Lock()
        self.rows = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    self.rows[row[key]] = row

    def add(self, row: dict) -> None:
        with self.lock:
            self.rows[row[self.key]] = row
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")


def make_judge(backend, config: dict, task: dict, costs: list):
    def judge(prompt: str, answer: str, rubric: list[str]) -> dict:
        items = "\n".join(f"{i + 1}. {r}" for i, r in enumerate(rubric))
        msg = f"<task>\n{prompt}\n</task>\n\n<answer>\n{answer}\n</answer>\n\n<rubric>\n{items}\n</rubric>"
        j = config["judge"]
        out = backend.call(j["target"], j.get("effort"), JUDGE_SYSTEM, msg, task=task, max_tokens=2000)
        costs.append(cost_of(out["usage"], config["targets"][j["target"]]["pricing"]) or 0.0)
        try:
            return parse_json_object(out["text"])
        except ValueError as e:
            return {"met": [], "reason": f"judge reply unparseable: {e}"}
    return judge


def run(args, config: dict, tasks: list[dict]) -> Path:
    backend = BACKENDS[args.backend](config)
    run_dir = RESULTS_DIR / args.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    used_targets = sorted({k for k in config["targets"] if k.split("/")[0] in args.providers} | {config["judge"]["target"]})
    meta = {"backend": args.backend, "providers": args.providers, "strategies": args.strategies,
            "repeats": args.repeats, "task_ids": [t["id"] for t in tasks],
            "models": {k: config["targets"][k]["id"] for k in used_targets},
            "judge": config["judge"], "second_opinion": not args.no_second_opinion,
            "region": args.region,
            "started": time.strftime("%Y-%m-%dT%H:%M:%S")}
    (run_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")

    routing = JsonlStore(run_dir / "routing.jsonl")
    gens = JsonlStore(run_dir / "generations.jsonl")

    for provider in {s.split(":")[0] for s in args.strategies if s.endswith(":triage")}:
        for t in tasks:
            if f"{provider}|{t['id']}" not in routing.rows:
                routing.add(route(provider, t, backend, config, use_second_opinion=not args.no_second_opinion))

    needed = {}
    for t in tasks:
        for rep in range(args.repeats):
            for name in args.strategies:
                row = routing.rows.get(f"{name.split(':')[0]}|{t['id']}")
                target, effort = resolve_strategy(config, name, row)
                needed[gen_key(config, target, effort, t["id"], rep)] = (target, effort, t, rep)

    todo = [v for k, v in needed.items() if k not in gens.rows]
    print(f"{len(needed)} unique generations, {len(needed) - len(todo)} cached, {len(todo)} to run")

    def work(target, effort, task, rep):
        try:
            out = backend.call(target, effort, config["system_prompt"], task["prompt"], task=task)
        except Exception as e:  # keep going; a failed call counts as a failed task
            out = {"text": "", "usage": {}, "latency_s": 0.0, "stop_reason": f"error: {e}"[:300]}
        judge_costs: list[float] = []
        grade = graders.grade(task, out["text"], judge=make_judge(backend, config, task, judge_costs))
        return {"key": gen_key(config, target, effort, task["id"], rep), "target": target,
                "model_id": config["targets"][target]["id"], "effort": effort,
                "task_id": task["id"], "difficulty": task["difficulty"], "repeat": rep,
                "cost_usd": cost_of(out["usage"], config["targets"][target]["pricing"]),
                "judge_cost_usd": sum(judge_costs), **out, "grade": grade}

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(work, *job) for job in todo]
        for i, fut in enumerate(as_completed(futures), 1):
            row = fut.result()
            gens.add(row)
            mark = "✓" if row["grade"]["passed"] else "✗"
            cost = "" if row["cost_usd"] is None else f"  ${row['cost_usd']:.4f}"
            print(f"[{i}/{len(todo)}] {mark} {row['key']}{cost}  {row['grade']['detail'][:70]}")

    return run_dir


# --------------------------------------------------------------------------- estimate / references

def estimate(config: dict, tasks: list[dict], strategies: list[str], repeats: int) -> None:
    rules = config["rules"]
    keys, total, unpriced = set(), 0.0, set()
    for t in tasks:
        tier = triage(t["prompt"], rules, config["taxonomy"])["tier"] or TIERS[0]
        for name in strategies:
            target, effort = resolve_strategy(config, name, {"tier": tier})
            for rep in range(repeats):
                k = gen_key(config, target, effort, t["id"], rep)
                if k in keys:
                    continue
                keys.add(k)
                usage = {"input_tokens": estimate_tokens(config["system_prompt"] + t["prompt"]),
                         "output_tokens": rules["expected_output_tokens"][target.split("/")[1]]}
                c = cost_of(usage, config["targets"][target]["pricing"])
                if c is None:
                    unpriced.add(target)
                else:
                    total += c
    by_id = {t["id"]: t for t in tasks}
    judged = sum(1 for k in keys if by_id[k.split("|")[-2]]["grader"]["type"] == "judge")
    jp = config["targets"][config["judge"]["target"]]["pricing"]
    judge_cost = judged * (cost_of({"input_tokens": 6000, "output_tokens": 1500}, jp) or 0.0)
    print(f"{len(tasks)} tasks × {repeats} repeat(s), strategies: {', '.join(strategies)}")
    print(f"unique generations: {len(keys)} (identical requests, including triage's, are shared)")
    print(f"estimated generation cost: ${total:.2f}")
    print(f"estimated judge cost:      ${judge_cost:.2f} ({judged} judged generations)")
    print(f"estimated total:           ${total + judge_cost:.2f}")
    if unpriced:
        print(f"not included (no pricing configured): {', '.join(sorted(unpriced))}")
    print("Rough estimate from typical output lengths; hard tasks at high effort can run several times longer.")


def check_references(tasks: list[dict]) -> int:
    failed = 0
    for t in tasks:
        if t["grader"]["type"] == "judge":
            print(f"  skip  {t['id']} (judge-graded)")
            continue
        g = graders.grade(t, t["reference"])
        failed += not g["passed"]
        print(f"  {'ok  ' if g['passed'] else 'FAIL'}  {t['id']}  {g['detail'][:80]}")
    print(f"{len(tasks) - failed}/{len(tasks)} references pass")
    return 1 if failed else 0


def select_tasks(args) -> list[dict]:
    tasks = TASKS
    if args.tasks:
        wanted = set(args.tasks.split(","))
        tasks = [t for t in tasks if t["id"] in wanted]
    if args.difficulty:
        tasks = [t for t in tasks if t["difficulty"] in args.difficulty.split(",")]
    if not tasks:
        sys.exit("no tasks selected")
    return tasks


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--backend", choices=sorted(BACKENDS), default="mock")
    ap.add_argument("--providers", help="comma-separated, e.g. claude,deepseek,kimi,zhipu,xiaomi")
    ap.add_argument("--strategies", help="override, e.g. claude:deep,claude:triage,deepseek:triage")
    ap.add_argument("--run-id", default=None, help="results/<run-id>/ (reruns resume from cache)")
    ap.add_argument("--tasks", help="comma-separated task ids")
    ap.add_argument("--difficulty", help="comma-separated: easy,medium,hard")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--concurrency", type=int, default=4)
    ap.add_argument("--no-second-opinion", action="store_true", help="route on rules alone")
    ap.add_argument("--estimate", action="store_true", help="print a cost estimate and exit")
    ap.add_argument("--check-references", action="store_true", help="grade reference answers and exit")
    ap.add_argument("--yes", action="store_true", help="confirm spending money with --backend live")
    ap.add_argument("--judge", help="judge model as '<provider>/<tier>' (default from models.json)")
    ap.add_argument("--region", choices=["cn", "intl"], default="cn",
                    help="which endpoint to use for providers that have both")
    ap.add_argument("--config", type=Path, default=CONFIG_PATH)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    config = load_config(args.config, args.region)
    if args.judge:
        if args.judge not in config["targets"]:
            sys.exit(f"unknown judge target {args.judge!r}; expected '<provider>/<tier>'")
        config["judge"] = {"target": args.judge, "effort": config["judge"].get("effort")}
    args.providers = args.providers.split(",") if args.providers else config["providers"]
    unknown = [p for p in args.providers if p not in config["provider_defs"]]
    if unknown:
        sys.exit(f"unknown providers: {unknown}; known: {', '.join(config['provider_defs'])}")
    args.strategies = args.strategies.split(",") if args.strategies else strategy_names(config, args.providers)
    for s in args.strategies:
        p, _, kind = s.partition(":")
        if p not in config["provider_defs"] or kind not in TIERS + ["triage"]:
            sys.exit(f"bad strategy {s!r}; expected '<provider>:<{'|'.join(TIERS)}|triage>'")
    args.providers = sorted({s.split(":")[0] for s in args.strategies})
    tasks = select_tasks(args)

    if args.check_references:
        return check_references(tasks)
    if args.estimate:
        estimate(config, tasks, args.strategies, args.repeats)
        return 0
    if args.backend == "live" and not args.yes:
        estimate(config, tasks, args.strategies, args.repeats)
        print("\nThis calls real model APIs and costs money. Re-run with --yes to proceed.")
        return 1

    args.run_id = args.run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{args.backend}"
    run_dir = run(args, config, tasks)

    import report
    report.write_report(run_dir, config)
    print(f"\nreport: {run_dir / 'summary.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
