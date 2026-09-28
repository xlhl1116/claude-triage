#!/usr/bin/env python3
"""Print (or write) the Claude Code settings that point it at another provider.

Claude Code talks to one Anthropic-compatible endpoint at a time. The triage
clinics use the model aliases haiku / sonnet / opus, and Claude Code lets you
remap those aliases with ANTHROPIC_DEFAULT_{HAIKU,SONNET,OPUS}_MODEL. So
switching provider = new base URL + key + mapping each clinic to that
provider's quick / standard / deep model. The triage slip then detects the
provider from ANTHROPIC_BASE_URL and shows the real model names.

    python3 use_provider.py deepseek                 # print a settings.json "env" block
    python3 use_provider.py kimi --shell             # print export lines instead
    python3 use_provider.py zhipu --intl             # international endpoint, if any
    python3 use_provider.py xiaomi --write ~/.claude/settings.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from triage import load_providers  # noqa: E402

ALIAS_VARS = {"quick": "ANTHROPIC_DEFAULT_HAIKU_MODEL",
              "standard": "ANTHROPIC_DEFAULT_SONNET_MODEL",
              "deep": "ANTHROPIC_DEFAULT_OPUS_MODEL"}
CLEARED = ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
           "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
           "API_TIMEOUT_MS", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
           # Some vendor guides set these; they would force every subagent onto one model / effort
           # and silently defeat the triage clinics, so switching provider always removes them.
           "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL"]


def pick_base_url(cc: dict, intl: bool, token_plan: bool) -> str:
    if token_plan and cc.get("base_url_token_plan"):
        return cc["base_url_token_plan"]
    if intl and cc.get("base_url_intl"):
        return cc["base_url_intl"]
    return cc["base_url"]


def build_env(provider: dict, intl: bool, token_plan: bool = False) -> dict:
    cc = provider["claude_code"]
    base = pick_base_url(cc, intl, token_plan)
    env = {"ANTHROPIC_BASE_URL": base, cc.get("token_var", "ANTHROPIC_AUTH_TOKEN"): f"${provider['key_env']}"}
    for tier, var in ALIAS_VARS.items():
        env[var] = cc.get("models", {}).get(tier) or provider["models"][tier]["id"]
    env.update(cc.get("env", {}))
    return env


def main(argv: list[str] | None = None) -> int:
    providers = load_providers()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("provider", choices=sorted(providers))
    ap.add_argument("--intl", action="store_true", help="use the international endpoint if the provider has one")
    ap.add_argument("--token-plan", action="store_true", help="use the token-plan endpoint if the provider has one")
    ap.add_argument("--shell", action="store_true", help="print shell export lines")
    ap.add_argument("--write", type=Path, metavar="SETTINGS_JSON",
                    help="merge into this settings file (the key is copied from the provider's env var if set)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = providers[args.provider]
    if args.provider == "claude":
        print("Claude is the default: remove these keys from the \"env\" block of your settings "
              "(and unset them in your shell) to go back to Anthropic:\n  " + "\n  ".join(CLEARED))
        return 0
    if not p.get("claude_code"):
        print(f"{p['label_en']} has no Anthropic-compatible endpoint configured, so Claude Code cannot use it "
              "directly. It is still available in the benchmark.", file=sys.stderr)
        return 1

    env = build_env(p, args.intl, args.token_plan)
    key_var = p["claude_code"].get("token_var", "ANTHROPIC_AUTH_TOKEN")
    for note in p.get("unverified", []):
        print(f"# note: unverified — {note}; check {p['docs']}", file=sys.stderr)
    print("# note: remove CLAUDE_CODE_SUBAGENT_MODEL / CLAUDE_CODE_EFFORT_LEVEL if your shell sets them; "
          "they override the triage clinics.", file=sys.stderr)

    if args.shell:
        for k, v in env.items():
            print(f'export {k}="{v}"')
        return 0

    if args.write:
        import os
        key = os.environ.get(p["key_env"])
        env[key_var] = key or f"<your {p['label_en']} API key>"
        settings = json.loads(args.write.read_text(encoding="utf-8")) if args.write.exists() else {}
        old = settings.get("env", {})
        settings["env"] = {k: v for k, v in old.items() if k not in CLEARED} | env
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {args.write}" + ("" if key else f"  (set {key_var} yourself: ${p['key_env']} was not set)"))
        print("Restart Claude Code for the change to take effect.")
        return 0

    env[key_var] = f"<your {p['label_en']} API key>"
    print(json.dumps({"env": env}, indent=2, ensure_ascii=False))
    print(f"\n# Paste into ~/.claude/settings.json (or .claude/settings.local.json), then restart Claude Code.\n"
          f"# Docs: {p['docs']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
