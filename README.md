<div align="center">

# 🏥 claude-triage

**A triage desk for Claude Code: every request gets the right model and thinking effort — and a slip that explains why.**

English | [简体中文](README.zh-CN.md)

[![tests](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml/badge.svg)](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

<!-- TODO: replace with a real demo GIF (docs/assets/demo.gif) -->
> 🎬 *Demo GIF coming soon.* Until then, this is what you see:

```text
> /claude-triage:triage Our Node service leaks memory, but only after ~3 days in production

🏥 Triage slip
────────────────────────────
Clinic      Specialist clinic · triage-deep
Model       opus · effort high
Confidence  medium (score 5; standard≥2, deep≥5)
Why         + Hard-to-reproduce bug (+5)
Est. cost   ≈ $0.215 (always-opus ≈ $0.215, saves 0%)
Override    add @quick / @standard / @deep to your request
```

## Install

```text
/plugin marketplace add xlhl1116/claude-triage
/plugin install claude-triage@claude-triage
```

Then: `/claude-triage:triage <your request>`

## Why

Most requests don't need your most expensive model. Some really do. Picking by hand every time is tedious, and "always Opus" burns quota on "translate this sentence" while "always Sonnet" under-thinks the one bug that matters.

claude-triage sits in front of your request like a hospital triage desk:

1. **Screens** it with a transparent rule table (task type, length, code, architecture / concurrency / proof / hard-debug signals).
2. **Asks a nurse** (Haiku) for a cheap second opinion only when the rules aren't sure.
3. **Prints a slip**: chosen model + effort, the signals behind it, and an estimated cost vs. always-Opus.
4. **Dispatches** to one of three clinic subagents, and **escalates** automatically if the clinic finds the case harder than it looked.

You can always overrule it: add `@quick`, `@standard` or `@deep` to the request.

## Clinics

| Clinic | Subagent | Model · effort | Typical requests |
|---|---|---|---|
| Quick | `triage-quick` | haiku · — | chit-chat, translation, typos, renames, short lookups |
| Standard | `triage-standard` | sonnet · medium | write a function, fix a clear bug, add tests, refactor a module, review a PR |
| Specialist | `triage-deep` | opus · high | architecture, trade-offs, proofs, concurrency, production-only bugs, security audits, repo-wide migrations |
| *(nurse)* | `triage-nurse` | haiku | second opinion on low-confidence cases; never does the task |

The full rule table lives in [`docs/triage-rules.md`](docs/triage-rules.md); the source of truth is [`skills/triage/rules.json`](skills/triage/rules.json).

## How it compares

| | **claude-triage** | OpenRouter Auto | RouteLLM | `opusplan` (built into Claude Code) |
|---|---|---|---|---|
| Where it runs | Inside Claude Code, as a plugin | Hosted API gateway | Self-hosted server / library | Inside Claude Code |
| Decides per… | request | request | request | mode (Opus to plan, Sonnet to execute) |
| Picks thinking effort | ✅ | ❌ | ❌ | ❌ |
| Explains the decision | ✅ slip with signals and scores | ❌ | ❌ | n/a |
| Cost estimate before running | ✅ | ❌ | ❌ | ❌ |
| One-word manual override | ✅ `@quick` / `@deep` | model param | threshold param | switch model |
| Editable, readable rules | ✅ JSON + tests | ❌ | trained router | ❌ |
| Non-Anthropic models | ✅ DeepSeek, Kimi, GLM, MiMo (one provider at a time) | ✅ | ✅ | ❌ |
| Extra API key / infra | none | OpenRouter account | your own deployment | none |

*Comparison reflects public docs as of 2026-09; corrections welcome.*

## Other providers: DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo

Claude Code talks to one Anthropic-compatible endpoint at a time, and the clinics use the `haiku` / `sonnet` / `opus` aliases. Switching provider means remapping those aliases to that provider's fast / general / strongest model:

| Provider | Quick | Standard | Specialist |
|---|---|---|---|
| Claude | claude-haiku-4-5 | claude-sonnet-5 | claude-opus-5 |
| DeepSeek | deepseek-flash | deepseek-flash | deepseek-v4-pro |
| Moonshot Kimi | kimi-k2.7-code-highspeed | kimi-k2.6 | kimi-k3 |
| Zhipu GLM | glm-5.3-flash | glm-5.3 | glm-5.3 |
| Xiaomi MiMo | mimo-v2.5 | mimo-v2.6-pro | mimo-v2.6-pro |

```bash
python3 skills/triage/scripts/use_provider.py deepseek          # print the settings.json "env" block
python3 skills/triage/scripts/use_provider.py zhipu --intl      # z.ai instead of bigmodel.cn
python3 skills/triage/scripts/use_provider.py kimi --write ~/.claude/settings.json
```

The slip detects the provider from `ANTHROPIC_BASE_URL` and shows the real model name. Some vendor setup guides also set `CLAUDE_CODE_SUBAGENT_MODEL`, which forces every subagent onto one model and silently disables triage, so the script removes it. Model IDs were checked against each vendor's docs on 2026-09-28; the few that could not be fully confirmed are listed under `unverified` in [`providers.json`](skills/triage/providers.json).

## Try the rule engine on its own

The engine is a single standard-library Python file:

```bash
echo "Prove this lock-free queue is linearizable" | python3 skills/triage/scripts/triage.py --format slip
python3 skills/triage/scripts/triage.py --format json --text "Translate 'see you' into French"
```

Run the tests and the seed benchmark:

```bash
python3 -m unittest discover -s tests
python3 benchmark/eval_rules.py
```

> ⚠️ The 41 seed cases in `benchmark/triage-cases.jsonl` were written alongside the rules, so their 100% accuracy is a regression check, not a quality claim.

## Benchmark: quality vs. cost

`benchmark/run_bench.py` runs 30 auto-graded tasks (10 easy / 10 medium / 10 hard: translation, facts, coding with unit tests, algorithms, math, debugging, system design) under each strategy: every fixed tier, plus triage routing. Any provider above can be benchmarked, and they can be compared side by side. See [`benchmark/README.md`](benchmark/README.md). Published results are coming soon.

## Roadmap

- [x] Rule table, rule engine, explainable slip, cost estimate
- [x] Three clinic subagents + nurse, manual override, automatic escalation
- [x] Providers: DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo
- [x] Benchmark harness: 30 graded tasks, per-provider strategies, offline mock mode
- [ ] **Benchmark results**: publish real runs, with charts
- [ ] **Learn from feedback**: record overrides and escalations, suggest weight changes
- [ ] Hook mode: triage every prompt automatically, not only via the slash command
- [ ] **Mixed routing**: different providers per clinic in one session (e.g. DeepSeek for quick, Opus for deep); GPT, Gemini, local models

## Contributing

Issues and PRs welcome — especially misrouted examples. Add the prompt to `benchmark/triage-cases.jsonl` with the tier you expected, tweak `rules.json`, and make sure `python3 -m unittest discover -s tests` passes.

## License

[MIT](LICENSE)
