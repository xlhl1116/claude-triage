<div align="center">

# 🏥 claude-triage

### Stop paying Opus prices to rename a variable.

**A triage desk for Claude Code.** A cheap desk model reads every request, recognises which of 120 kinds it is, and sends it to the model and thinking effort that kind needs, with a slip that explains why.

English | [简体中文](README.zh-CN.md)

[![tests](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml/badge.svg)](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![version](https://img.shields.io/badge/version-0.1.0-orange.svg)
![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![no extra API key](https://img.shields.io/badge/extra%20API%20key-none-brightgreen.svg)

</div>

<!-- TODO: replace with a real demo GIF (docs/assets/demo.gif) -->
> 🎬 *Demo GIF coming soon.* Until then, this is what you see:

```text
> Our checkout service deadlocks under high concurrency in production. Find the cause and fix it.

🏥 Triage slip
────────────────────────────
Category    💻 Software development › Concurrency, race or deadlock bug
Model       Claude Opus 5.5 (claude-opus-5-5, Anthropic Claude)
Effort      max
Why         matched "deadlock", "concurrency"; +1 High stakes
Confidence  high
Est. cost   ≈ $0.252 (strongest model ≈ $0.830, saves 70%)
Override    add @haiku / @sonnet / @opus / @opus-max / @fable to pick the model yourself

…the answer from Claude Opus 5.5 at max effort…
— Software development › Concurrency, race or deadlock bug · Claude Opus 5.5 · effort max
```

## Why

- **One model for everything is the wrong trade.** Keep Opus on and a typo fix costs like an architecture review; keep Haiku on and a production deadlock gets a shallow answer.
- **You shouldn't have to decide.** Nobody knows in advance whether a question needs a "standard" or a "specialist" model. The desk works it out from what you asked.
- **You can see every decision.** Each answer comes with a slip: the category, the words that matched, the model, the effort and the estimated saving. One word (`@opus-max`) overrules it.

> 🧪 **Early release (v0.1).** The rule engine, 49 tests and the routing checks all pass, but the plugin has had little real-world use in Claude Code yet. Misrouted examples and bug reports are very welcome.

## Install

```text
/plugin marketplace add xlhl1116/claude-triage
/plugin install claude-triage@claude-triage
```

Needs Claude Code 2.1.284 or later (the first release that knows Claude Sonnet 5.5) and Python 3.9+ (`python3`, `python` or the Windows `py` launcher; the plugin finds whichever works). On Windows, install [Git for Windows](https://git-scm.com/download/win): Claude Code runs the plugin's hooks and the desk's Bash tool in Git Bash.

Restart Claude Code. From then on the **triage desk is your main conversation**: just type as usual.

### Where it works

| Where | Automatic triage of every message | `/claude-triage:triage <request>` |
|---|---|---|
| Claude Code CLI (terminal) | ✅ the desk is the main conversation | ✅ |
| Claude desktop app, Code tab | ❌ the app ignores a plugin's main-agent setting | ✅ |
| Claude desktop app, Cowork | ❌ same reason | ⚠️ should work (same plugin format), not tested yet |

In the desktop app, install from **+ → Plugins → Add plugin** and type `/claude-triage:triage` before a request you want routed; the slip, the exact model and effort, and the full answer work the same way. The hook stays silent there, so it costs your main model nothing. The executor always runs inside the same conversation as a sub-agent (shown as a collapsible step), and the desk passes its answer back to you in full.

**Just want to see the routing first?** The rule engine is plain Python with no dependencies:

```bash
git clone https://github.com/xlhl1116/claude-triage && cd claude-triage
echo "Our checkout service deadlocks under high concurrency in production" | python3 skills/triage/scripts/triage.py --format slip
```

## How it works

```
your message ──► hook: rule engine recognises the category, attaches a <triage-slip>   (no model call)
                     │
                     ▼
              Triage desk (Claude Haiku 4.5, main thread)
              · never answers anything itself
              · checks the category on every slip and re-routes when it's wrong
              · shows the slip
                     │  dispatches with the Agent tool
                     ▼
     executor = exact model + effort + tool access, e.g.
     Claude Haiku 4.5 · Claude Sonnet 5.5 low / medium / high · Claude Opus 5.5 medium / high / max · Claude Fable 5.1 max
                     │  answer (or TRIAGE_ESCALATE → a stronger model)
                     ▼
              desk relays it to you, naming the category, model and effort
```

1. **Recognise the request, not a difficulty level.** Most people can't tell whether their question needs a "standard" or a "specialist" model, so nobody has to choose. A hook matches every message against **120 categories in 17 domains** (from "rename a variable" to "distributed architecture", "contract review" or "medication question") and attaches a slip. No model call, no tokens.
2. **The category sets the model.** Each category has a default model, effort and tool access: a translation goes to Claude Haiku 4.5, a large cross-module refactor to Claude Opus 5.5 at max. Health, legal and finance categories have a floor, so they never drop to a cheap model, and carry category-specific instructions (for example, recommend seeing a doctor).
3. **Background adjustments.** Signals such as the whole repo, production or payments, an open-ended ask, very long input or hard complexity limits move the choice up; explicit step-by-step instructions move it down. The strongest model, Claude Fable 5.1, is only reached when several such signals stack up.
4. **The desk runs on one cheap model** (Claude Haiku 4.5). It never answers anything itself. It checks the rules' category on every request, not just the uncertain ones, and re-routes when the rules got it wrong.
5. **Executors escalate** to a stronger model if the task turns out harder than it looked.

Pick the model yourself any time by adding `@haiku`, `@sonnet`, `@opus`, `@opus-max` or `@fable` to a message (the old `@quick` / `@deep` tokens still work).

## Categories

<details>
<summary><b>17 domains, 120 categories</b> (click to expand)</summary>

| Domain | Categories | Examples → default model |
|---|---:|---|
| 💻 Software development | 40 | rename / format → Haiku 4.5 · UI component → Sonnet 5.5 medium · cross-module feature → Opus 5.5 medium · migration → Opus 5.5 high · large refactor, intermittent bug, concurrency, security audit, distributed architecture → Opus 5.5 max |
| 📊 Data and math | 8 | arithmetic → Haiku 4.5 · spreadsheet formulas → Sonnet 5.5 low · statistics → Opus 5.5 medium · proofs → Opus 5.5 max |
| ✍️ Writing | 10 | edit my text, emails, summaries → Sonnet 5.5 low · formal reports, fiction → Opus 5.5 medium · academic papers → Opus 5.5 high |
| 🌐 Language | 4 | everyday translation, grammar → Haiku 4.5 · legal / medical / long-form translation → Opus 5.5 medium |
| 🔎 Information lookup | 5 | facts → Haiku 4.5 · product comparison → Sonnet 5.5 medium · in-depth research report → Opus 5.5 high |
| 🎓 Education | 4 | concept explanations, homework → Sonnet 5.5 medium |
| 🧭 How-to guidance | 4 | device settings, paperwork, DIY → Sonnet 5.5 low |
| 🩺 Health | 6 | symptoms, mental health → Opus 5.5 medium · medication, test results → Opus 5.5 high (floor: Opus 5.5 medium) |
| ⚖️ Legal | 4 | legal questions, contract drafting → Opus 5.5 medium · contract review, compliance → Opus 5.5 high (floor: Opus 5.5 medium) |
| 💰 Finance | 4 | personal finance → Sonnet 5.5 medium · investing, modelling → Opus 5.5 high (floor: Opus 5.5 medium) |
| 💼 Work and business | 8 | meeting notes → Sonnet 5.5 low · resume, interview → Sonnet 5.5 medium · business plan → Opus 5.5 high |
| 🔬 Research | 5 | literature review, experiment design → Opus 5.5 high · theoretical derivation → Opus 5.5 max |
| 🎨 Design and media | 5 | image prompts → Haiku 4.5 · UX, branding, video scripts → Sonnet 5.5 medium |
| 💡 Creative and fun | 4 | naming, role play → Sonnet 5.5 low · brainstorming, poems → Sonnet 5.5 medium |
| 🏠 Everyday life | 4 | recipes → Haiku 4.5 · travel, parenting → Sonnet 5.5 medium |
| 💬 Chat and feelings | 3 | greetings → Haiku 4.5 · relationships → Sonnet 5.5 medium |
| 🗂️ Other | 2 | questions about the triage (answered by the desk) · unclear requests |

</details>

The domains are grounded in published studies of real usage: OpenAI / NBER *How People Use ChatGPT* (2025), Anthropic's Clio and Economic Index (2024–2026) and Microsoft's *Copilot Usage Report 2025*. Software development is split the finest because it is the biggest use of Claude and the core of Claude Code.

**The full table** of every category with its model, effort, tools and floor is in **[`docs/taxonomy.md`](docs/taxonomy.md)**. It is generated from [`skills/triage/taxonomy.json`](skills/triage/taxonomy.json) (categories and keywords), [`rules.json`](skills/triage/rules.json) (adjustments and overrides) and [`providers.json`](skills/triage/providers.json) (exact models). Missing a kind of request? Add a category to `taxonomy.json` and open a PR.

Don't want the desk as your main thread? Set your own `"agent"` in `~/.claude/settings.json` (user settings override the plugin), set `CLAUDE_TRIAGE=off` to silence the hook, and use `/claude-triage:triage <request>` when you want a single request triaged.

## Other providers: DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo

Claude Code talks to one Anthropic-compatible endpoint at a time. For another provider, the desk and executors are generated with that provider's exact model IDs:

| Claude | DeepSeek | Moonshot Kimi | Zhipu GLM | Xiaomi MiMo |
|---|---|---|---|---|
| Claude Haiku 4.5 (desk) | DeepSeek V4.1 Flash `deepseek-flash` | Kimi K2.7 Code HighSpeed `kimi-k2.7-code-highspeed` | GLM-5.3-Flash `glm-5.3-flash` | MiMo V2.5 `mimo-v2.5` |
| Claude Sonnet 5.5 | DeepSeek V4.1 Flash `deepseek-flash` | Kimi K2.6 / K2.7 Code | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |
| Claude Opus 5.5 | DeepSeek V4 Pro `deepseek-v4-pro` | Kimi K3 `kimi-k3` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |
| Claude Fable 5.1 | DeepSeek V4 Pro `deepseek-v4-pro` | Kimi K3 `kimi-k3` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |

The exact effort per step is in [`docs/taxonomy.md`](docs/taxonomy.md) (model ladder section). Effort levels are passed through to each provider's endpoint; whether they are honoured is **not verified yet**, and the slip says so.

```bash
python3 skills/triage/scripts/use_provider.py deepseek                            # preview
python3 skills/triage/scripts/use_provider.py deepseek --write ~/.claude/settings.json
python3 skills/triage/scripts/use_provider.py zhipu --intl --write ~/.claude/settings.json   # z.ai
python3 skills/triage/scripts/use_provider.py claude --write ~/.claude/settings.json          # back to Claude
```

`--write` sets the endpoint and key, writes the provider's desk and executors to `~/.claude/agents/`, and makes that desk your main thread. Some vendor setup guides set `CLAUDE_CODE_SUBAGENT_MODEL`, which would force every executor onto one model; the script removes it. Model IDs were checked against each vendor's docs on 2026-09-28; the few not fully confirmed are listed under `unverified` in `providers.json`.

## How it compares

| | **claude-triage** | OpenRouter Auto | RouteLLM | `opusplan` (built into Claude Code) |
|---|---|---|---|---|
| Where it runs | Inside Claude Code, as a plugin | Hosted API gateway | Self-hosted server / library | Inside Claude Code |
| Decides per… | request, by one of 120 categories | request | request | mode (Opus to plan, Sonnet to execute) |
| Picks thinking effort | ✅ | ❌ | ❌ | ❌ |
| Explains the decision | ✅ category, matched signals, adjustments | ❌ | ❌ | n/a |
| Cost estimate before running | ✅ | ❌ | ❌ | ❌ |
| Domain-specific guardrails | ✅ floors and instructions for health, legal, finance | ❌ | ❌ | ❌ |
| One-word manual override | ✅ `@opus-max` | model param | threshold param | switch model |
| Editable, readable rules | ✅ JSON + tests | ❌ | trained router | ❌ |
| Non-Anthropic models | ✅ DeepSeek, Kimi, GLM, MiMo (one provider at a time) | ✅ | ✅ | ❌ |
| Extra API key / infra | none | OpenRouter account | your own deployment | none |

*Comparison reflects public docs as of 2026-09; corrections welcome.*

## Try the rule engine on its own

```bash
echo "Prove this lock-free queue is linearizable" | python3 skills/triage/scripts/triage.py --format slip
python3 skills/triage/scripts/triage.py --format json --provider kimi --text "Review this rental contract for unfair clauses"
python3 skills/triage/scripts/triage.py --list-categories
```

Tests and the routing regression:

```bash
python3 -m unittest discover -s tests
python3 benchmark/eval_rules.py
```

> ⚠️ The routing checks (every category's example plus 64 labelled prompts, all passing) were written alongside the keywords, so they are regression checks, not an accuracy claim on real traffic. Misrouted real-world examples are the most useful contribution.

## Benchmark: quality vs. cost

`benchmark/run_bench.py` runs 30 auto-graded tasks (10 easy / 10 medium / 10 hard) with fixed models and with triage routing, for any provider, and reports pass rate and cost against always using the strongest model. See [`benchmark/README.md`](benchmark/README.md). Published results are coming soon.

## Roadmap

- [x] Rule engine, explainable slip, cost estimate
- [x] Triage desk on one cheap model as the main thread; exact model + effort per executor; escalation
- [x] 120-category taxonomy grounded in public usage studies; background adjustments; floors for health, legal, finance
- [x] Providers: DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo
- [x] Benchmark harness: 30 graded tasks, per-provider strategies, offline mock mode
- [ ] **Benchmark results**: publish real runs, with charts; more tasks per domain
- [ ] Verify which providers honour Claude Code's effort setting
- [ ] **Learn from feedback**: record overrides, desk re-routes and escalations; suggest keyword and default changes
- [ ] **Mixed routing**: different providers per category in one session; GPT, Gemini, local models

## Contributing

Issues and PRs welcome, especially misrouted examples: add the prompt to `benchmark/triage-cases.jsonl` with the category you expected, adjust keywords in `taxonomy.json`, then run

```bash
python3 skills/triage/scripts/gen_agents.py   # if you changed models, tiers or tool profiles
python3 skills/triage/scripts/gen_docs.py     # refresh docs/taxonomy.md
python3 -m unittest discover -s tests
```

---

If claude-triage saves you tokens or picks better than you would have, a ⭐ helps other Claude Code users find it.

## License

[MIT](LICENSE)
