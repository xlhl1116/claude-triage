<div align="center">

# 🏥 claude-triage

**A triage desk for Claude Code: a cheap desk model reads every request and sends it to the exact model and thinking effort it needs, with a slip that explains why.**

English | [简体中文](README.zh-CN.md)

[![tests](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml/badge.svg)](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

<!-- TODO: replace with a real demo GIF (docs/assets/demo.gif) -->
> 🎬 *Demo GIF coming soon.* Until then, this is what you see:

```text
> Design a distributed job scheduler for 1M QPS and handle concurrency and consistency

🏥 Triage slip
────────────────────────────
Clinic      Senior specialist
Model       Claude Opus 5.5 (claude-opus-5-5, Anthropic Claude)
Effort      max
Confidence  medium (score 9; standard≥2, deep≥5, deep-max≥8, frontier≥12)
Why         + Architecture / system design (+5)  + Concurrency / distributed (+4)
Est. cost   ≈ $0.252 (top clinic ≈ $0.830, saves 70%)
Override    add @quick / @standard / @deep / @deep-max / @frontier to your request

…the answer from Claude Opus 5.5 at max effort…
— Senior specialist · Claude Opus 5.5 · effort max
```

## Install

```text
/plugin marketplace add xlhl1116/claude-triage
/plugin install claude-triage@claude-triage
```

Restart Claude Code. From then on the **triage desk is your main conversation**: just type as usual.

## How it works

```
your message ──► hook: rule engine scores it, attaches a <triage-slip>
                     │
                     ▼
              Triage desk (Claude Haiku 4.5, main thread)
              · never answers anything itself
              · low confidence → gives a second opinion
              · shows the slip
                     │  dispatches with the Agent tool
                     ▼
     ┌───────────┬───────────┬────────────┬─────────────┬─────────────┐
     │  quick    │ standard  │   deep     │  deep-max   │  frontier   │
     │ Haiku 4.5 │ Sonnet 5  │ Opus 5.5   │ Opus 5.5    │ Fable 5.1   │
     │  default  │  medium   │  medium    │   max       │    max      │
     └───────────┴───────────┴────────────┴─────────────┴─────────────┘
                     │  answer (or TRIAGE_ESCALATE → next clinic up)
                     ▼
              desk relays it to you, naming model + effort
```

1. **A hook screens every message** with a transparent rule table (task type, length, code, architecture / concurrency / proof / hard-debug signals) and attaches a slip. No model call, no tokens.
2. **The desk runs on one cheap model** (Claude Haiku 4.5). It never answers; when the rules aren't confident it decides the clinic itself.
3. **Each clinic is one exact model + effort**, set in its agent's frontmatter, e.g. `model: claude-opus-5-5` + `effort: max`. No aliases: the slip names the version that will actually run.
4. **Clinics escalate** to the next one up if the case turns out harder than it looked.

Overrule any decision by adding `@quick`, `@standard`, `@deep`, `@deep-max` or `@frontier` (or `@haiku`, `@sonnet`, `@opus`, `@opus-max`, `@fable`) to a message.

## Clinics

| Clinic | Model (exact version) | Effort | Score | Typical requests |
|---|---|---|---|---|
| Triage desk | Claude Haiku 4.5 `claude-haiku-4-5` | — | — | routes every message; never answers |
| `quick` | Claude Haiku 4.5 `claude-haiku-4-5` | default¹ | < 2 | chit-chat, translation, typos, renames, short lookups |
| `standard` | Claude Sonnet 5 `claude-sonnet-5` | medium | 2–4 | write a function, fix a clear bug, add tests, refactor a module, review a PR |
| `deep` | Claude Opus 5.5 `claude-opus-5-5` | medium | 5–7 | one hard problem: a design question, a trade-off, a proof, an intermittent bug, a migration |
| `deep-max` | Claude Opus 5.5 `claude-opus-5-5` | max | 8–11 | several hard aspects at once: distributed architecture, concurrency bugs, repo-wide security audits |
| `frontier` | Claude Fable 5.1 `claude-fable-5-1` | max | ≥ 12 | the hardest problems, where many hard signals stack up |

¹ Claude Haiku 4.5 has no effort setting.

The roster lives in [`skills/triage/rules.json`](skills/triage/rules.json) (clinics, score bands, overrides) and [`skills/triage/providers.json`](skills/triage/providers.json) (which exact model serves each clinic). Change either, run `python3 skills/triage/scripts/gen_agents.py`, and the agents are regenerated to match. The full rule table is in [`docs/triage-rules.md`](docs/triage-rules.md).

Don't want the desk as your main thread? Set your own `"agent"` in `~/.claude/settings.json` (user settings override the plugin), set `CLAUDE_TRIAGE=off` to silence the hook, and use `/claude-triage:triage <request>` when you want a single request triaged.

## Other providers: DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo

Claude Code talks to one Anthropic-compatible endpoint at a time. For another provider, the desk and clinics are generated with that provider's exact model IDs:

| Clinic | DeepSeek | Moonshot Kimi | Zhipu GLM | Xiaomi MiMo |
|---|---|---|---|---|
| desk / `quick` | DeepSeek V4.1 Flash `deepseek-flash` | Kimi K2.7 Code HighSpeed `kimi-k2.7-code-highspeed` | GLM-5.3-Flash `glm-5.3-flash` | MiMo V2.5 `mimo-v2.5` |
| `standard` | DeepSeek V4.1 Flash `deepseek-flash` | Kimi K2.6 `kimi-k2.6` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |
| `deep` | DeepSeek V4 Pro `deepseek-v4-pro` | Kimi K3 `kimi-k3` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |
| `deep-max` / `frontier` | DeepSeek V4 Pro `deepseek-v4-pro` | Kimi K3 `kimi-k3` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |

Clinic effort levels (low → max) are passed through to the provider's endpoint; whether each provider honours them is **not verified yet**, and the slip says so.

```bash
python3 skills/triage/scripts/use_provider.py deepseek                            # preview
python3 skills/triage/scripts/use_provider.py deepseek --write ~/.claude/settings.json
python3 skills/triage/scripts/use_provider.py zhipu --intl --write ~/.claude/settings.json   # z.ai
python3 skills/triage/scripts/use_provider.py claude --write ~/.claude/settings.json          # back to Claude
```

`--write` sets the endpoint and key, writes the provider's desk + clinic agents to `~/.claude/agents/`, and makes that desk your main thread. Some vendor setup guides set `CLAUDE_CODE_SUBAGENT_MODEL`, which would force every clinic onto one model; the script removes it. Model IDs were checked against each vendor's docs on 2026-09-28; the few not fully confirmed are listed under `unverified` in `providers.json`.

## How it compares

| | **claude-triage** | OpenRouter Auto | RouteLLM | `opusplan` (built into Claude Code) |
|---|---|---|---|---|
| Where it runs | Inside Claude Code, as a plugin | Hosted API gateway | Self-hosted server / library | Inside Claude Code |
| Decides per… | request | request | request | mode (Opus to plan, Sonnet to execute) |
| Picks thinking effort | ✅ | ❌ | ❌ | ❌ |
| Explains the decision | ✅ slip with signals and scores | ❌ | ❌ | n/a |
| Cost estimate before running | ✅ | ❌ | ❌ | ❌ |
| One-word manual override | ✅ `@deep-max` | model param | threshold param | switch model |
| Editable, readable rules | ✅ JSON + tests | ❌ | trained router | ❌ |
| Non-Anthropic models | ✅ DeepSeek, Kimi, GLM, MiMo (one provider at a time) | ✅ | ✅ | ❌ |
| Extra API key / infra | none | OpenRouter account | your own deployment | none |

*Comparison reflects public docs as of 2026-09; corrections welcome.*

## Try the rule engine on its own

```bash
echo "Prove this lock-free queue is linearizable" | python3 skills/triage/scripts/triage.py --format slip
python3 skills/triage/scripts/triage.py --format json --provider kimi --text "Translate 'see you' into French"
```

Tests and the routing regression set:

```bash
python3 -m unittest discover -s tests
python3 benchmark/eval_rules.py
```

> ⚠️ The 47 seed cases in `benchmark/triage-cases.jsonl` were written alongside the rules, so their 100% accuracy is a regression check, not a quality claim.

## Benchmark: quality vs. cost

`benchmark/run_bench.py` runs 30 auto-graded tasks (10 easy / 10 medium / 10 hard) under every fixed clinic and under triage routing, for any provider, and reports pass rate and cost against always using the strongest clinic. See [`benchmark/README.md`](benchmark/README.md). Published results are coming soon.

## Roadmap

- [x] Rule table, rule engine, explainable slip, cost estimate
- [x] Triage desk on one cheap model as the main thread; five clinics with exact model + effort; escalation
- [x] Providers: DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo
- [x] Benchmark harness: 30 graded tasks, per-provider strategies, offline mock mode
- [ ] **Benchmark results**: publish real runs, with charts
- [ ] Verify which providers honour Claude Code's effort setting
- [ ] **Learn from feedback**: record overrides and escalations, suggest weight changes
- [ ] **Mixed routing**: different providers per clinic in one session; GPT, Gemini, local models

## Contributing

Issues and PRs welcome, especially misrouted examples. Add the prompt to `benchmark/triage-cases.jsonl` with the clinic you expected, tweak `rules.json`, run `python3 skills/triage/scripts/gen_agents.py` if you changed clinics or models, and make sure `python3 -m unittest discover -s tests` passes.

## License

[MIT](LICENSE)
