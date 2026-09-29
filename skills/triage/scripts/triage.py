#!/usr/bin/env python3
"""claude-triage rule engine: classify a request into a fine-grained category, then pick
the exact model and effort for it.

    category (taxonomy.json)  ->  default tier  ->  background adjustments  ->  model + effort (providers.json)

Tiers are internal: the user only sees the category, the model and the reason. Reads the
request from stdin (or --text) and prints JSON and/or a triage slip. Standard library only.

    echo "线上服务偶发 502，帮我找根因" | python3 triage.py --format slip
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_RULES = SKILL_DIR / "rules.json"
DEFAULT_TAXONOMY = SKILL_DIR / "taxonomy.json"
DEFAULT_PROVIDERS = SKILL_DIR / "providers.json"

# re.ASCII keeps \b meaningful next to CJK characters ("这个bug" still matches \bbug\b).
FLAGS = re.IGNORECASE | re.ASCII | re.MULTILINE
LIST_ITEM_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)、])\s+\S", re.MULTILINE)
CJK_RE = re.compile(r"[㐀-鿿豈-﫿]")


# --------------------------------------------------------------------------- loading

def load_rules(path: Path = DEFAULT_RULES) -> dict:
    with open(path, encoding="utf-8") as f:
        rules = json.load(f)
    for m in rules["modifiers"]:
        m["_compiled"] = [re.compile(p, FLAGS) for p in m["patterns"]]
    rules["_tier_ids"] = [t["id"] for t in rules["tiers"]]
    return rules


def load_taxonomy(path: Path = DEFAULT_TAXONOMY) -> dict:
    with open(path, encoding="utf-8") as f:
        tax = json.load(f)
    tax["_by_id"] = {}
    for d in tax["domains"]:
        for c in d["categories"]:
            c["_domain"] = d
            c["_compiled"] = [re.compile(p, FLAGS) for p in c["keywords"]]
            tax["_by_id"][c["id"]] = c
    tax["_fallback"] = next(c for c in tax["_by_id"].values() if c.get("fallback"))
    return tax


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
    """role is 'desk' or '<tier>-<toolset>' (e.g. 't7-code'). Claude agents ship inside the
    plugin, so they are namespaced; other providers' agents are generated as user agents."""
    if provider == "claude":
        return f"claude-triage:triage-{role}" if namespaced else f"triage-{role}"
    return f"triage-{role}-{provider}"


def category_label(c: dict, lang: str) -> str:
    d = c["_domain"]
    if lang == "zh":
        return f"{d['emoji']} {d['label_zh']} › {c['label_zh']}"
    return f"{d['emoji']} {d['label_en']} › {c['label_en']}"


# --------------------------------------------------------------------------- classification

def classify(text: str, tax: dict, rules: dict) -> dict:
    """Score every category by the keywords it matches. The best one wins; ties go to the
    category with the longer (more specific) matches. Confidence says whether the desk
    should take a second look."""
    scored = []
    for c in tax["_by_id"].values():
        hits = []
        for rx in c["_compiled"]:
            m = rx.search(text)
            if m and m.group(0).strip():
                hits.append(m.group(0).strip())
        if hits:
            scored.append((len(hits) * c.get("weight", 1.0), sum(len(h) for h in hits), c, hits))
    scored.sort(key=lambda s: (s[0], s[1]), reverse=True)

    cfg = rules["classification"]
    if not scored:
        return {"category": tax["_fallback"], "hits": [], "confidence": "low", "candidates": []}
    top, second = scored[0][0], (scored[1][0] if len(scored) > 1 else 0)
    if top >= cfg["high_min_score"] and top - second >= cfg["min_margin"]:
        conf = "high"
    elif top - second >= cfg["min_margin"]:
        conf = "medium"
    else:
        conf = "low"
    candidates = [{"id": s[2]["id"], "label_zh": s[2]["label_zh"], "label_en": s[2]["label_en"], "score": s[0]}
                  for s in scored[:3]]
    return {"category": scored[0][2], "hits": scored[0][3], "confidence": conf, "candidates": candidates}


def find_override(text: str, rules: dict) -> tuple[str | None, str | None]:
    """Longest matching token wins, so '@opus-max' is not read as '@opus'."""
    lowered = text.lower()
    best = None
    for tier, tokens in rules["overrides"].items():
        for token in tokens:
            if token.lower() in lowered and (best is None or len(token) > len(best[1])):
                best = (tier, token)
    return best or (None, None)


def modifiers(text: str, rules: dict) -> list[dict]:
    found = []
    for m in rules["modifiers"]:
        for rx in m["_compiled"]:
            hit = rx.search(text)
            if hit:
                found.append({"id": m["id"], "label_zh": m["label_zh"], "label_en": m["label_en"],
                              "delta": m["delta"], "match": hit.group(0).strip()})
                break
    comp = rules["computed_modifiers"]

    def add(key: str) -> None:
        c = comp[key]
        found.append({"id": key, "label_zh": c["label_zh"], "label_en": c["label_en"], "delta": c["delta"], "match": None})

    if len(text.strip()) >= comp["long_input"]["min_chars"]:
        add("long_input")
    if len(LIST_ITEM_RE.findall(text)) >= comp["many_requirements"]["min_items"]:
        add("many_requirements")
    return found


def adjust_tier(default: str, delta: int, category: dict, rules: dict) -> str:
    """Apply the background adjustment within the category's floor / ceiling. The top tier is
    only reached by stacking: at least +2 from a default of t6 or above."""
    tiers = rules["_tier_ids"]
    adj = rules["adjustment"]
    delta = max(-adj["max_down"], min(adj["max_up"], delta))
    base = tiers.index(default)
    idx = max(0, min(len(tiers) - 1, base + delta))
    if idx == len(tiers) - 1 and base < len(tiers) - 1:
        need = adj["top_tier_needs"]
        if delta < need["min_up"] or base < tiers.index(need["min_default"]):
            idx -= 1
    if category.get("floor"):
        idx = max(idx, tiers.index(category["floor"]))
    if category.get("ceiling"):
        idx = min(idx, tiers.index(category["ceiling"]))
    return tiers[idx]


def cost_usd(pricing: dict | None, in_tok: int, out_tok: int) -> float | None:
    if not pricing:
        return None
    return (in_tok * pricing["input"] + out_tok * pricing["output"]) / 1_000_000


# --------------------------------------------------------------------------- triage

def triage(text: str, rules: dict, tax: dict, providers: dict | None = None, provider: str = "claude",
           category: str | None = None) -> dict:
    """Route one request. `category` forces the category (the desk's second opinion)."""
    cls = classify(text, tax, rules)
    if category:
        cls = {**cls, "category": tax["_by_id"][category], "confidence": "desk", "hits": []}
    c = cls["category"]
    mods = modifiers(text, rules)
    override, token = find_override(text, rules)
    delta = sum(m["delta"] for m in mods)
    if c.get("handler") == "desk":
        tier = None
    elif override:
        tier = override
    else:
        tier = adjust_tier(c["tier"], delta, c, rules)
    guidance = " ".join(g for g in (c["_domain"].get("guidance_en"), c.get("guidance_en")) if g) or None

    result = {
        "category": c["id"],
        "category_zh": category_label(c, "zh"),
        "category_en": category_label(c, "en"),
        "confidence": "manual" if override else cls["confidence"],
        "needs_second_opinion": cls["confidence"] == "low" and not override,
        "candidates": cls["candidates"],
        "keywords": cls["hits"],
        "default_tier": c["tier"],
        "tier": tier,
        "modifiers": mods,
        "override": token,
        "toolset": c["tools"],
        "handler": c.get("handler", "clinic"),
        "guidance": guidance,
        "lang": detect_lang(text),
    }
    if tier is None or providers is None:
        return result

    p = providers[provider]
    m = p["models"][tier]
    top_tier = rules["_tier_ids"][-1]
    in_tok = estimate_tokens(text) + rules["base_context_tokens"]
    out = rules["expected_output_tokens"]
    est = cost_usd(m.get("pricing"), in_tok, out[tier])
    top = cost_usd(p["models"][top_tier].get("pricing"), in_tok, out[top_tier])
    result.update({
        "provider": provider,
        "provider_label": p["label_en"],
        "provider_label_zh": p["label_zh"],
        "agent": agent_name(provider, f"{tier}-{c['tools']}"),
        "model_id": m["id"],
        "model_name": m.get("name", m["id"]),
        "effort": m.get("effort"),
        "effort_verified": p.get("effort_verified", False),
        "estimate": {
            "input_tokens": in_tok,
            "output_tokens": out[tier],
            "cost_usd": None if est is None else round(est, 4),
            "strongest_cost_usd": None if top is None else round(top, 4),
            "saving_pct": round(100 * (1 - est / top)) if est is not None and top else None,
        },
    })
    result["footer"] = footer(result)
    return result


def footer(r: dict) -> str:
    """The closing line the desk copies verbatim, so it never has to recall model or effort itself."""
    label = r["category_zh"] if r["lang"] == "zh" else r["category_en"]
    effort = f" · effort {r['effort']}" if r.get("effort") else ""
    return f"— {label} · {r['model_name']}{effort}"


CONF_LABEL = {
    "zh": {"high": "高", "medium": "中", "low": "低（导诊台会复核）", "manual": "手动指定", "desk": "导诊台判定"},
    "en": {"high": "high", "medium": "medium", "low": "low (the desk will take a second look)", "manual": "manual",
           "desk": "set by the desk"},
}


def render_slip(r: dict, rules: dict, lang: str) -> str:
    zh = lang == "zh"
    lines = ["🏥 分诊挂号单" if zh else "🏥 Triage slip", "────────────────────────────"]

    def add(k_zh: str, k_en: str, v: str) -> None:
        lines.append(f"{k_zh}  {v}" if zh else f"{k_en:<11} {v}")

    add("类别    ", "Category", r["category_zh"] if zh else r["category_en"])
    if r["handler"] == "desk":
        add("处理    ", "Handled by", "导诊台直接回答" if zh else "the desk answers directly")
        return "\n".join(lines)

    if "model_id" in r:
        effort = r["effort"]
        if not effort:
            depth = "默认（该模型不支持 effort）" if zh else "default (model has no effort setting)"
        elif r.get("effort_verified", True):
            depth = effort
        else:
            depth = f"{effort}（已传给厂商，是否生效未验证）" if zh else f"{effort} (passed to the provider; support unverified)"
        vendor = r["provider_label_zh"] if zh else r["provider_label"]
        add("模型    ", "Model",
            f"{r['model_name']}（{r['model_id']}，{vendor}）" if zh else f"{r['model_name']} ({r['model_id']}, {vendor})")
        add("思考深度", "Effort", depth)

    reasons = []
    if r["override"]:
        reasons.append(f"手动指定“{r['override']}”" if zh else f"manual override \"{r['override']}\"")
    elif r["keywords"]:
        if zh:
            reasons.append("命中 " + "、".join(f"“{k}”" for k in r["keywords"][:4]))
        else:
            reasons.append("matched " + ", ".join(f"\"{k}\"" for k in r["keywords"][:4]))
    elif r["confidence"] == "desk":
        reasons.append("导诊台复核" if zh else "desk review")
    for m in r["modifiers"]:
        reasons.append(f"{'+' if m['delta'] > 0 else '−'}{abs(m['delta'])} {m['label_zh'] if zh else m['label_en']}")
    if not reasons:
        reasons.append("没有明显信号" if zh else "no clear signals")
    add("理由    ", "Why", "；".join(reasons) if zh else "; ".join(reasons))

    conf = CONF_LABEL["zh" if zh else "en"][r["confidence"]]
    if r["confidence"] == "low" and r["candidates"]:
        cands = " / ".join(c["label_zh" if zh else "label_en"] for c in r["candidates"])
        conf += f"；候选：{cands}" if zh else f"; candidates: {cands}"
    add("置信度  ", "Confidence", conf)

    e = r.get("estimate")
    if e:
        if e["cost_usd"] is None:
            cost = f"—（未配置 {r['provider_label_zh']} 的价格）" if zh else f"— (no pricing configured for {r['provider_label']})"
        elif zh:
            cost = f"≈ ${e['cost_usd']:.3f}（全部用最强配置 ≈ ${e['strongest_cost_usd']:.3f}，省 {e['saving_pct']}%）"
        else:
            cost = f"≈ ${e['cost_usd']:.3f} (strongest model ≈ ${e['strongest_cost_usd']:.3f}, saves {e['saving_pct']}%)"
        add("预估成本", "Est. cost", cost)
    tokens = " / ".join(t[0] for t in rules["overrides"].values())
    add("改挂    ", "Override", f"在消息里加 {tokens} 可直接指定模型" if zh else f"add {tokens} to pick the model yourself")
    return "\n".join(lines)


# --------------------------------------------------------------------------- entry points

DISPATCH_TOOLS = ("Agent", "Task")


def is_desk(event: dict) -> bool:
    return str(event.get("agent_type", "")).split(":")[-1] == "triage-desk"


def last_request(transcript: Path) -> tuple[str | None, bool]:
    """The user's latest request in a transcript, and whether the desk dispatched it since."""
    prompt, dispatched = None, False
    with open(transcript, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            content = (e.get("message") or {}).get("content")
            if e.get("type") == "user" and not e.get("isMeta") and isinstance(content, str) \
                    and not content.lstrip().startswith(("<", "/")):
                prompt, dispatched = content, False
            elif e.get("type") == "assistant" and isinstance(content, list):
                dispatched = dispatched or any(c.get("type") == "tool_use" and c.get("name") in DISPATCH_TOOLS
                                               for c in content)
    return prompt, dispatched


def hook_prompt(event: dict, rules: dict, tax: dict, providers: dict, provider: str) -> dict | None:
    """UserPromptSubmit: attach a <triage-slip> for the triage desk to every prompt."""
    prompt = event.get("prompt", "")
    # Slash commands, and background-agent results that Claude Code feeds back as a prompt.
    if not prompt.strip() or prompt.lstrip().startswith(("/", "<task-notification>")):
        return None
    r = triage(prompt, rules, tax, providers, provider)
    brief = {k: r.get(k) for k in ("category", "confidence", "candidates", "handler", "agent", "model_id",
                                   "model_name", "effort", "tier", "guidance", "provider", "footer")}
    rerun = (f"python3 \"{Path(__file__).resolve()}\" --provider {provider} --category <category-id> "
             "--format both <<'CLAUDE_TRIAGE_EOF' (the user's message on stdin, then CLAUDE_TRIAGE_EOF)")
    context = ("<triage-slip>\n"
               "Computed by the claude-triage rule engine for the triage desk; other agents can ignore it.\n"
               f"{json.dumps(brief, ensure_ascii=False)}\n\n{render_slip(r, rules, r['lang'])}\n\n"
               f"To route under a different category: {rerun}\n"
               "</triage-slip>")
    return {"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}


def hook_bash(event: dict) -> dict | None:
    """PreToolUse on Bash: the desk may only run the triage script; looking into the repo is the executor's job."""
    command = str((event.get("tool_input") or {}).get("command", "")).replace("\\", "/")
    if not is_desk(event) or "scripts/triage.py" in command:
        return None
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse", "permissionDecision": "deny",
        "permissionDecisionReason": "The triage desk only runs the triage script. Dispatch the request to the "
                                    "slip's executor with the Agent tool; it can read and search the repo."}}


def hook_stop(event: dict, rules: dict, tax: dict, providers: dict, provider: str) -> dict | None:
    """Stop: the desk may not end a turn that answered a request without dispatching it."""
    if not is_desk(event) or event.get("stop_hook_active") or not event.get("transcript_path"):
        return None
    prompt, dispatched = last_request(Path(event["transcript_path"]))
    if prompt is None or dispatched:
        return None
    r = triage(prompt, rules, tax, providers, provider)
    if r["handler"] == "desk" or "agent" not in r:
        return None
    return {"decision": "block",
            "reason": f"The triage desk never answers a request itself, not even to ask what the user means. "
                      f"Dispatch the user's latest request to `{r['agent']}` (or the executor of the category "
                      "you re-routed to) with the Agent tool, run_in_background: false, then relay its answer "
                      "and end with the slip's footer."}


def hook_main(rules_path: Path, taxonomy_path: Path, providers_path: Path) -> int:
    """Claude Code hooks for the triage desk (UserPromptSubmit, PreToolUse on Bash, Stop).

    Never breaks the session: any problem means no output, and Claude Code carries on as usual.
    """
    try:
        if os.environ.get("CLAUDE_TRIAGE", "").lower() in ("0", "off", "false", "no"):
            return 0
        event = json.loads(sys.stdin.read() or "{}")
        name = event.get("hook_event_name", "UserPromptSubmit")
        if name == "PreToolUse":
            out = hook_bash(event)
        else:
            rules, tax, providers = load_rules(rules_path), load_taxonomy(taxonomy_path), load_providers(providers_path)
            provider = os.environ.get("CLAUDE_TRIAGE_PROVIDER") or detect_provider(providers)
            provider = provider if provider in providers else "claude"
            handler = hook_stop if name == "Stop" else hook_prompt
            out = handler(event, rules, tax, providers, provider)
        if out:
            print(json.dumps(out, ensure_ascii=False))
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
    ap.add_argument("--category", help="force a category id (e.g. software.hard-debug): the desk's second opinion")
    ap.add_argument("--list-categories", action="store_true", help="print all category ids and exit")
    ap.add_argument("--rules", type=Path, default=DEFAULT_RULES)
    ap.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    ap.add_argument("--providers", type=Path, default=DEFAULT_PROVIDERS)
    ap.add_argument("--hook", action="store_true", help="run as a Claude Code hook (UserPromptSubmit, PreToolUse, Stop)")
    args = ap.parse_args(argv)
    if args.hook:
        return hook_main(args.rules, args.taxonomy, args.providers)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rules, tax, providers = load_rules(args.rules), load_taxonomy(args.taxonomy), load_providers(args.providers)
    if args.list_categories:
        for c in tax["_by_id"].values():
            print(f"{c['id']}\t{category_label(c, 'zh')}")
        return 0

    text = args.text if args.text is not None else sys.stdin.read()
    if not text.strip():
        print("error: empty request", file=sys.stderr)
        return 2
    provider = detect_provider(providers) if args.provider == "auto" else args.provider
    if provider not in providers:
        print(f"error: unknown provider {provider!r}; known: {', '.join(providers)}", file=sys.stderr)
        return 2
    if args.category and args.category not in tax["_by_id"]:
        print(f"error: unknown category {args.category!r}; see --list-categories", file=sys.stderr)
        return 2
    result = triage(text, rules, tax, providers, provider, args.category)
    lang = result["lang"] if args.lang == "auto" else args.lang

    if args.format in ("json", "both"):
        print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.format in ("slip", "both"):
        print(render_slip(result, rules, lang))
    return 0


if __name__ == "__main__":
    sys.exit(main())
