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
TIER_ORDER = ["quick", "standard", "deep"]

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


def find_override(text: str, rules: dict) -> tuple[str | None, str | None]:
    lowered = text.lower()
    for tier in TIER_ORDER:
        for token in rules["overrides"][tier]:
            if token.lower() in lowered:
                return tier, token
    return None, None


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


def tier_for(total: int, rules: dict) -> str:
    th = rules["thresholds"]
    if total >= th["deep"]:
        return "deep"
    if total >= th["standard"]:
        return "standard"
    return "quick"


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
    if any(abs(total - t) <= 1 for t in rules["thresholds"].values()):
        return "medium"
    return "high"


def cost_usd(pricing: dict | None, in_tok: int, out_tok: int) -> float | None:
    if not pricing:
        return None
    return (in_tok * pricing["input"] + out_tok * pricing["output"]) / 1_000_000


def triage(text: str, rules: dict, providers: dict | None = None, provider: str = "claude") -> dict:
    total, hits = score(text, rules)
    override, token = find_override(text, rules)
    tier = override or tier_for(total, rules)
    conf = "manual" if override else confidence_for(total, hits, rules)

    t = rules["tiers"][tier]
    result = {
        "tier": tier,
        "agent": t["agent"],
        "model": t["model"],
        "effort": t["effort"],
        "score": total,
        "thresholds": rules["thresholds"],
        "confidence": conf,
        "needs_nurse": conf == "low",
        "override": token,
        "signals": hits,
        "lang": detect_lang(text),
    }
    if providers is None:
        return result

    p = providers[provider]
    m = p["models"][tier]
    deep = p["models"]["deep"]
    in_tok = estimate_tokens(text) + rules["base_context_tokens"]
    est = cost_usd(m.get("pricing"), in_tok, t["expected_output_tokens"])
    baseline = cost_usd(deep.get("pricing"), in_tok, rules["tiers"]["deep"]["expected_output_tokens"])
    result.update({
        "provider": provider,
        "provider_label": p["label_en"],
        "provider_label_zh": p["label_zh"],
        "model_id": m["id"],
        "estimate": {
            "input_tokens": in_tok,
            "output_tokens": t["expected_output_tokens"],
            "cost_usd": None if est is None else round(est, 4),
            "always_deep_cost_usd": None if baseline is None else round(baseline, 4),
            "saving_pct": round(100 * (1 - est / baseline)) if est is not None and baseline else None,
        },
    })
    return result


CONF_LABEL = {
    "zh": {"high": "高", "medium": "中", "low": "低（建议复核）", "manual": "手动指定"},
    "en": {"high": "high", "medium": "medium", "low": "low (second opinion advised)", "manual": "manual"},
}


def render_slip(r: dict, rules: dict, lang: str) -> str:
    t = rules["tiers"][r["tier"]]
    zh = lang == "zh"
    label = t["label_zh"] if zh else t["label_en"]
    if r["signals"]:
        reasons = "  ".join(
            f"{'+' if s['weight'] > 0 else '−'} {s['label_zh'] if zh else s['label_en']} ({s['weight']:+d})"
            for s in r["signals"])
    else:
        reasons = "（无明显信号）" if zh else "(no clear signals)"
    th = r["thresholds"]
    e = r.get("estimate", {})
    effort = "" if t["effort"] in (None, "n/a") else f" · effort {t['effort']}"
    provider = r.get("provider", "claude")
    if provider == "claude":
        model = f"{t['model']}{effort}"
    else:
        vendor = r["provider_label_zh"] if zh else r["provider_label"]
        model = f"{r['model_id']}（{vendor} · {t['model']} 档）" if zh else f"{r['model_id']} ({vendor}, {t['model']} slot)"
    deep_name = "opus" if provider == "claude" else r.get("provider_label", provider)

    if e.get("cost_usd") is None:
        cost_zh = f"—（未配置 {r.get('provider_label_zh', provider)} 的价格）"
        cost_en = f"— (no pricing configured for {r.get('provider_label', provider)})"
    else:
        cost_zh = f"≈ ${e['cost_usd']:.3f}（全程用最强档 ≈ ${e['always_deep_cost_usd']:.3f}，省 {e['saving_pct']}%）"
        cost_en = f"≈ ${e['cost_usd']:.3f} (always-strongest ≈ ${e['always_deep_cost_usd']:.3f}, saves {e['saving_pct']}%)"

    if zh:
        lines = [
            "🏥 分诊挂号单",
            "────────────────────────────",
            f"科室      {label} · {t['agent']}",
            f"模型      {model}",
            f"置信度    {CONF_LABEL['zh'][r['confidence']]}（得分 {r['score']}；standard≥{th['standard']}，deep≥{th['deep']}）",
            f"依据      {reasons}",
            f"预估成本  {cost_zh}",
            "改挂      在请求里加 @quick / @standard / @deep 即可推翻本次分诊",
        ]
        if r["override"]:
            lines.insert(5, f"手动指定  检测到 “{r['override']}”")
    else:
        lines = [
            "🏥 Triage slip",
            "────────────────────────────",
            f"Clinic      {label} · {t['agent']}",
            f"Model       {model}",
            f"Confidence  {CONF_LABEL['en'][r['confidence']]} (score {r['score']}; standard≥{th['standard']}, deep≥{th['deep']})",
            f"Why         {reasons}",
            f"Est. cost   {cost_en}",
            "Override    add @quick / @standard / @deep to your request",
        ]
        if r["override"]:
            lines.insert(5, f"Manual      found \"{r['override']}\"")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--text", help="request text (default: read stdin)")
    ap.add_argument("--format", choices=["json", "slip", "both"], default="json")
    ap.add_argument("--lang", choices=["auto", "zh", "en"], default="auto")
    ap.add_argument("--provider", default="auto",
                    help="claude, deepseek, kimi, zhipu, xiaomi … (default: detect from ANTHROPIC_BASE_URL)")
    ap.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    ap.add_argument("--providers", type=Path, default=DEFAULT_PROVIDERS)
    args = ap.parse_args(argv)

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
