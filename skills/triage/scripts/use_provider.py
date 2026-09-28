#!/usr/bin/env python3
"""Point Claude Code (and the triage desk) at another provider.

Claude Code talks to one Anthropic-compatible endpoint at a time. Switching
provider means: new base URL + key, the haiku / sonnet / opus aliases remapped
to that provider's models (Claude Code uses them internally), and a desk plus
clinic agents whose `model:` fields name that provider's exact model IDs.

    python3 use_provider.py deepseek                      # print what would change
    python3 use_provider.py deepseek --write ~/.claude/settings.json
    python3 use_provider.py zhipu --intl --write .claude/settings.local.json
    python3 use_provider.py claude --write ~/.claude/settings.json   # back to Anthropic

--write merges the env block into the settings file, writes the provider's agents
into the `agents/` folder next to it (~/.claude/agents or .claude/agents), and
sets "agent" so the provider's triage desk runs as the main thread.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gen_agents import generate  # noqa: E402
from triage import DEFAULT_RULES, agent_name, load_providers, load_rules  # noqa: E402

ALIAS_CLINICS = {"ANTHROPIC_DEFAULT_HAIKU_MODEL": "quick",
                 "ANTHROPIC_DEFAULT_SONNET_MODEL": "standard",
                 "ANTHROPIC_DEFAULT_OPUS_MODEL": "deep-max"}
CLEARED = ["ANTHROPIC_BASE_URL", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_MODEL", "ANTHROPIC_SMALL_FAST_MODEL",
           "ANTHROPIC_DEFAULT_HAIKU_MODEL", "ANTHROPIC_DEFAULT_SONNET_MODEL", "ANTHROPIC_DEFAULT_OPUS_MODEL",
           "API_TIMEOUT_MS", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
           # Some vendor guides set these; they force every subagent onto one model / effort
           # and silently defeat the clinics, so switching provider always removes them.
           "CLAUDE_CODE_SUBAGENT_MODEL", "CLAUDE_CODE_EFFORT_LEVEL"]


def pick_base_url(cc: dict, intl: bool, token_plan: bool) -> str:
    if token_plan and cc.get("base_url_token_plan"):
        return cc["base_url_token_plan"]
    if intl and cc.get("base_url_intl"):
        return cc["base_url_intl"]
    return cc["base_url"]


def build_env(provider: dict, intl: bool, token_plan: bool = False) -> dict:
    cc = provider["claude_code"]
    env = {"ANTHROPIC_BASE_URL": pick_base_url(cc, intl, token_plan),
           cc.get("token_var", "ANTHROPIC_AUTH_TOKEN"): f"<your {provider['label_en']} API key>"}
    for var, cid in ALIAS_CLINICS.items():
        env[var] = provider["models"][cid]["id"]
    env.update(cc.get("env", {}))
    return env


def is_triage_desk(agent: str | None) -> bool:
    return bool(agent) and agent.startswith("triage-desk")


def main(argv: list[str] | None = None) -> int:
    providers = load_providers()
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("provider", choices=sorted(providers))
    ap.add_argument("--intl", action="store_true", help="use the international endpoint if the provider has one")
    ap.add_argument("--token-plan", action="store_true", help="use the token-plan endpoint if the provider has one")
    ap.add_argument("--write", type=Path, metavar="SETTINGS_JSON", help="apply to this settings file")
    ap.add_argument("--agents-dir", type=Path, help="where to write agents (default: agents/ next to the settings file)")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    p = providers[args.provider]
    rules = load_rules(DEFAULT_RULES)

    if args.provider == "claude":
        if not args.write:
            print("Back to Anthropic: remove these env keys from your settings (and your shell):\n  "
                  + "\n  ".join(CLEARED)
                  + "\nand remove an \"agent\": \"triage-desk-<provider>\" entry, so the plugin's own desk applies.")
            return 0
        path = args.write.expanduser()
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        settings["env"] = {k: v for k, v in settings.get("env", {}).items() if k not in CLEARED}
        if not settings["env"]:
            settings.pop("env")
        if is_triage_desk(settings.get("agent")):
            settings.pop("agent")
        path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {path}: provider settings removed; the plugin's Claude desk applies. Restart Claude Code.")
        return 0

    if not p.get("claude_code"):
        print(f"{p['label_en']} has no Anthropic-compatible endpoint configured.", file=sys.stderr)
        return 1
    for note in p.get("unverified", []):
        print(f"note: unverified — {note}; check {p['docs']}", file=sys.stderr)
    if not p.get("effort_verified", False):
        print(f"note: clinic effort levels are passed to {p['label_en']}; whether it honours them is unverified.",
              file=sys.stderr)

    env = build_env(p, args.intl, args.token_plan)
    key_var = p["claude_code"].get("token_var", "ANTHROPIC_AUTH_TOKEN")
    desk = agent_name(args.provider, "desk")
    agents = generate(args.provider, rules, providers)

    if not args.write:
        print(json.dumps({"agent": desk, "env": env}, indent=2, ensure_ascii=False))
        print(f"\nplus these agents (generated with gen_agents.py --provider {args.provider} --out ~/.claude/agents):\n  "
              + "\n  ".join(agents) + f"\nDocs: {p['docs']}", file=sys.stderr)
        return 0

    path = args.write.expanduser()
    key = os.environ.get(p["key_env"])
    if key:
        env[key_var] = key
    settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    settings["env"] = {k: v for k, v in settings.get("env", {}).items() if k not in CLEARED} | env
    settings["agent"] = desk
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    agents_dir = (args.agents_dir or path.parent / "agents").expanduser()
    agents_dir.mkdir(parents=True, exist_ok=True)
    for f, text in agents.items():
        (agents_dir / f).write_text(text, encoding="utf-8")

    print(f"wrote {path} (main agent: {desk})" + ("" if key else f"; set {key_var} yourself: ${p['key_env']} was not set"))
    print(f"wrote {len(agents)} agents to {agents_dir}")
    print("Restart Claude Code for the change to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
