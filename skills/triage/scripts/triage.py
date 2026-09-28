#!/usr/bin/env python3
"""claude-triage rule engine: score a request and pick a tier (quick / standard / deep).

Reads the request text from stdin (or --text) and prints either JSON or a
human-readable triage slip. Standard library only, so it runs anywhere
Claude Code runs.

    echo "帮我设计一个分布式任务调度系统" | python3 triage.py --format slip
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "rules.json"
DEFAULT_PROVIDERS = Path(__file__).resolve().parent.parent / "providers.json"

# re.ASCII keeps \b meaningful next to CJK characters ("这个bug" still matches \bbug\b).
FLAGS = re.IGNORECASE | re.ASCII | re.MULTILINE
CODE_RE = re.compile(
    r"```|^\s*(def |class |import |from \S+ import |function |const |let |#include|public |package )|[{};]\s*$",
    FLAGS,
)
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)、])\s+\S", re.MULTILINE)
CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")


def load_rules(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        rules = json.load(f)
    for sig in rules["signals"]:
        sig["_compiled"] = [re.compile(p, FLAGS) for p in sig["patterns"]]
    return rules


def load_providers(path: Path = DEFAULT_PROVIDERS) -> dict:
    with open(path, encoding="utf-8") as f:
        return {k: v for k, v in json.load(f).items() if not k.startswith("_")}


def detect_provider(providers: dict, base_url: str | None = None) -> str:
    """Which provider Claude Code is pointed at, judged from ANTHROPIC_BASE_URL."""
    base_url = base_url if base_url is not None else os.environ.get("ANTHROPIC_BASE_URL", "")
    host = (urlparse(base_url).hostname or "").lower()
    if host:
        for name, p in providers.items():
            if any(host == d or host.endswith("." + d) for d in p.get("detect_hosts", [])):
                return name
    return "claude"


def estimate_tokens(text: str) -> int:
    cjk = len(CJK_RE.findall(text))
    return max(1, round(cjk + (len(text) - cjk) / 4))


def detect_lang(text: str) -> str:
    return "zh" if CJK_RE.search(text) else "en"


def agent_name(provider: str, role: str, namespaced: bool = True) -> str:
    """Claude agents ship inside the plugin (so they are namespaced); other providers'
    agents are generated as user/project agents with the provider in the name."""
    if provider == "claude":
        return f"claude-triage:triage-{role}" if namespaced else f"triage-{role}"
    return f"triage-{role}-{provider}"


def clinic_ids(rules: dict) -> list[str]:
    return [c["id"] for c in rules["clinics"]]


def clinic(rules: dict, clinic_id: str) -> dict:
    return next(c for c in rules["clinics"] if c["id"] == clinic_id)


def find_override(text: str, rules: dict) -> tuple[str | None, str | None]:
    """Longest matching token wins, so '@opus-max' is not read as '@opus'."""
    lowered = text.lower()
    best = None
    for c in rules["clinics"]:
        for token in c.get("overrides", []):
            if token.lower() in lowered and (best is None or len(token) > len(best[1])):
                best = (c["id"], token)
    return best or (None, None)


def score(text: str, rules: dict) -> tuple[int, list[dict]]:
    hits: list[dict] = []
    for sig in rules["signals"]:
        for rx in sig["_compiled"]:
            m = rx.search(text)
            if m:
                hits.append({"id": sig["id"], "label_zh": sig["label_zh"], "label_en": sig["label_en"],
                             "weight": sig["weight"], "match": m.group(0).strip()})
                break

    comp = rules["computed"]
    stripped = text.strip()
    has_code = bool(CODE_RE.search(text))

    def add(key: str) -> None:
        c = comp[key]
        hits.append({"id": key, "label_zh": c["label_zh"], "label_en": c["label_en"],
                     "weight": c["weight"], "match": None})

    has_positive = any(h["weight"] > 0 for h in hits)
    if len(stripped) <= comp["short_prompt"]["max_chars"] and not has_code and not has_positive:
        add("short_prompt")
    if has_code:
        add("has_code")
    if len(stripped) >= comp["very_long_input"]["min_chars"]:
        add("very_long_input")
    elif len(stripped) >= comp["long_input"]["min_chars"]:
        add("long_input")
    if len(LIST_ITEM_RE.findall(text)) >= comp["many_requirements"]["min_items"]:
        add("many_requirements")

    return sum(h["weight"] for h in hits), hits


def boundaries(rules: dict) -> list[int]:
    return [c["min_score"] for c in rules["clinics"] if c["min_score"] is not None]


def clinic_for(total: int, rules: dict) -> str:
    """The strongest clinic whose min_score the request reaches."""
    chosen = rules["clinics"][0]["id"]
    for c in rules["clinics"]:
        if c["min_score"] is None or total >= c["min_score"]:
            chosen = c["id"]
    return chosen


def confidence_for(total: int, hits: list[dict], rules: dict) -> str:
    """low = let the triage nurse (Haiku) take a second look.

    low:    no keyword signal matched (only length heuristics), or the request
            mixes "trivial" and "hard" signals that pull in opposite directions
    medium: score within 1 point of a tier boundary
    high:   everything else
    """
    keyword = [h for h in hits if h["match"] is not None]
    if not keyword:
        return "low"
    if any(h["weight"] < 0 for h in keyword) and any(h["weight"] >= 3 for h in keyword):
        return "low"
    if any(abs(total - t) <= 1 for t in boundaries(rules)):
        return "medium"
    return "high"


def cost_usd(pricing: dict | None, in_tok: int, out_tok: int) -> float | None:
    if not pricing:
        return None
    return (in_tok * pricing["input"] + out_tok * pricing["output"]) / 1_000_000


def triage(text: str, rules: dict, providers: dict | None = None, provider: str = "claude") -> dict:
    total, hits = score(text, rules)
    override, token = find_override(text, rules)
    cid = override or clinic_for(total, rules)
    conf = "manual" if override else confidence_for(total, hits, rules)

    c = clinic(rules, cid)
    result = {
        "clinic": cid,
        "agent": agent_name(provider if providers is not None else "claude", cid),
        "effort": c["effort"],
        "score": total,
        "boundaries": {x["id"]: x["min_score"] for x in rules["clinics"] if x["min_score"] is not None},
        "confidence": conf,
        "needs_second_opinion": conf == "low",
        "override": token,
        "signals": hits,
        "lang": detect_lang(text),
    }
    if providers is None:
        return result

    p = providers[provider]
    m = p["models"][cid]
    top_id = rules["clinics"][-1]["id"]
    top = p["models"][top_id]
    in_tok = estimate_tokens(text) + rules["base_context_tokens"]
    est = cost_usd(m.get("pricing"), in_tok, c["expected_output_tokens"])
    baseline = cost_usd(top.get("pricing"), in_tok, clinic(rules, top_id)["expected_output_tokens"])
    result.update({
        "provider": provider,
        "provider_label": p["label_en"],
        "provider_label_zh": p["label_zh"],
        "model_id": m["id"],
        "model_name": m.get("name", m["id"]),
        "effort": m.get("effort"),
        "effort_verified": p.get("effort_verified", False),
        "estimate": {
            "input_tokens": in_tok,
            "output_tokens": c["expected_output_tokens"],
            "cost_usd": None if est is None else round(est, 4),
            "strongest_cost_usd": None if baseline is None else round(baseline, 4),
            "saving_pct": round(100 * (1 - est / baseline)) if est is not None and baseline else None,
        },
    })
    return result


CONF_LABEL = {
    "zh": {"high": "高", "medium": "中", "low": "低（建议复核）", "manual": "手动指定"},
    "en": {"high": "high", "medium": "medium", "low": "low (second opinion advised)", "manual": "manual"},
}


def render_slip(r: dict, rules: dict, lang: str) -> str:
    c = clinic(rules, r["clinic"])
    zh = lang == "zh"
    label = c["label_zh"] if zh else c["label_en"]
    if r["signals"]:
        reasons = "  ".join(
            f"{'+' if s['weight'] > 0 else '−'} {s['label_zh'] if zh else s['label_en']} ({s['weight']:+d})"
            for s in r["signals"])
    else:
        reasons = "（无明显信号）" if zh else "(no clear signals)"
    bands = "，".join(f"{k}≥{v}" for k, v in r["boundaries"].items()) if zh else \
        ", ".join(f"{k}≥{v}" for k, v in r["boundaries"].items())
    effort = r["effort"]
    if "model_id" in r:
        vendor = r["provider_label_zh"] if zh else r["provider_label"]
        model = f"{r['model_name']}（{r['model_id']}，{vendor}）" if zh else f"{r['model_name']} ({r['model_id']}, {vendor})"
    else:
        model = "—"
    if not effort:
        depth = "默认（该模型不支持 effort）" if zh else "default (model has no effort setting)"
    elif r.get("effort_verified", True):
        depth = effort
    else:
        depth = f"{effort}（已传给厂商，是否生效未验证）" if zh else f"{effort} (passed to the provider; support unverified)"
    e = r.get("estimate", {})
    if e.get("cost_usd") is None:
        cost_zh = f"—（未配置 {r.get('provider_label_zh', '')} 的价格）"
        cost_en = f"— (no pricing configured for {r.get('provider_label', '')})"
    else:
        cost_zh = f"≈ ${e['cost_usd']:.3f}（全部走最高档 ≈ ${e['strongest_cost_usd']:.3f}，省 {e['saving_pct']}%）"
        cost_en = f"≈ ${e['cost_usd']:.3f} (top clinic ≈ ${e['strongest_cost_usd']:.3f}, saves {e['saving_pct']}%)"
    ids = " / ".join("@" + x for x in clinic_ids(rules))

    if zh:
        lines = [
            "🏥 分诊挂号单",
            "────────────────────────────",
            f"科室      {label}",
            f"模型      {model}",
            f"思考深度  {depth}",
            f"置信度    {CONF_LABEL['zh'][r['confidence']]}（得分 {r['score']}；{bands}）",
            f"依据      {reasons}",
            f"预估成本  {cost_zh}",
            f"改挂      在请求里加 {ids} 即可推翻本次分诊",
        ]
        if r["override"]:
            lines.insert(6, f"手动指定  检测到 “{r['override']}”")
    else:
        lines = [
            "🏥 Triage slip",
            "────────────────────────────",
            f"Clinic      {label}",
            f"Model       {model}",
            f"Effort      {depth}",
            f"Confidence  {CONF_LABEL['en'][r['confidence']]} (score {r['score']}; {bands})",
            f"Why         {reasons}",
            f"Est. cost   {cost_en}",
            f"Override    add {ids} to your request",
        ]
        if r["override"]:
            lines.insert(6, f"Manual      found \"{r['override']}\"")
    return "\n".join(lines)


def hook_main(rules_path: Path, providers_path: Path) -> int:
    """UserPromptSubmit hook: attach a <triage-slip> for the triage desk to every prompt.

    Never blocks the prompt: any problem means no slip, and the desk falls back to the skill.
    """
    try:
        if os.environ.get("CLAUDE_TRIAGE", "").lower() in ("0", "off", "false", "no"):
            return 0
        prompt = json.loads(sys.stdin.read() or "{}").get("prompt", "")
        if not prompt.strip() or prompt.lstrip().startswith("/"):
            return 0
        rules = load_rules(rules_path)
        providers = load_providers(providers_path)
        provider = os.environ.get("CLAUDE_TRIAGE_PROVIDER") or detect_provider(providers)
        r = triage(prompt, rules, providers, provider if provider in providers else "claude")
        brief = {k: r[k] for k in ("clinic", "agent", "model_id", "model_name", "effort", "confidence",
                                   "score", "override", "provider")}
        context = ("<triage-slip>\n"
                   "Computed by the claude-triage rule engine for the triage desk; other agents can ignore it.\n"
                   f"{json.dumps(brief, ensure_ascii=False)}\n\n{render_slip(r, rules, r['lang'])}\n"
                   "</triage-slip>")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": context}}, ensure_ascii=False))
    except Exception:
        pass
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--text", help="request text (default: read stdin)")
    ap.add_argument("--format", choices=["json", "slip", "both"], default="json")
    ap.add_argument("--lang", choices=["auto", "zh", "en"], default="auto")
    ap.add_argument("--provider", default="auto",
                    help="claude, deepseek, kimi, zhipu, xiaomi … (default: detect from ANTHROPIC_BASE_URL)")
    ap.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    ap.add_argument("--providers", type=Path, default=DEFAULT_PROVIDERS)
    ap.add_argument("--hook", action="store_true", help="run as a Claude Code UserPromptSubmit hook")
    args = ap.parse_args(argv)
    if args.hook:
        return hook_main(args.rules, args.providers)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    text = args.text if args.text is not None else sys.stdin.read()
    if not text.strip():
        print("error: empty request", file=sys.stderr)
        return 2

    rules = load_rules(args.rules)
    providers = load_providers(args.providers)
    provider = detect_provider(providers) if args.provider == "auto" else args.provider
    if provider not in providers:
        print(f"error: unknown provider {provider!r}; known: {', '.join(providers)}", file=sys.stderr)
        return 2
    result = triage(text, rules, providers, provider)
    lang = result["lang"] if args.lang == "auto" else args.lang

    if args.format in ("json", "both"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.format in ("slip", "both"):
        print(render_slip(result, rules, lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
