---
name: triage
description: Triage desk — pick the right model (Haiku / Sonnet / Opus) and thinking effort for a request, show an explainable triage slip with an estimated cost, then dispatch the request to the matching clinic subagent. Use when the user runs /claude-triage:triage, or asks to "triage", "route", "分诊" or "挂号" a request.
argument-hint: "[@quick|@standard|@deep] <your request>"
allowed-tools: Bash(python3 *) Bash(python *)
---

# Triage desk / 分诊台

The request to triage is:

<request>
$ARGUMENTS
</request>

If the request above is empty, ask the user what they want triaged and stop.

## 1. Rule-based screening / 规则初筛

Run the rule engine on the request **verbatim**. Pass it on stdin through a quoted heredoc so nothing in it is interpreted by the shell:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/triage.py" --format json <<'CLAUDE_TRIAGE_EOF'
<the request, verbatim>
CLAUDE_TRIAGE_EOF
```

If `python3` is missing, try `python`. If neither works, skip to step 2 and let the nurse decide.

The JSON gives `tier`, `agent`, `model`, `effort`, `score`, `confidence`, `needs_nurse`, `override`, the matched `signals`, the `provider` and real `model_id` behind the clinic, and a cost `estimate` (null when no pricing is configured for that provider).

The provider (Claude, DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo) is detected from `ANTHROPIC_BASE_URL`. If the user reaches a provider through their own proxy, add `--provider <name>`; `python3 "${CLAUDE_SKILL_DIR}/scripts/use_provider.py" <name>` prints the settings that point Claude Code at a provider.

## 2. Second opinion when unsure / 拿不准时请分诊护士

Only when `needs_nurse` is `true` (and there is no manual `override`): dispatch the request to the `claude-triage:triage-nurse` subagent and use the `tier` from its JSON reply. Add its `reason` to the slip as an extra line ("护士复核 / Nurse review"). Never call the nurse for a manual override.

## 3. Show the triage slip / 出挂号单

Show the slip to the user in their language before doing any work. To get it pre-rendered, re-run the script with `--format slip` (same heredoc). If the nurse changed the tier, adjust the clinic / model / effort lines to match. Keep the override hint at the bottom: adding `@quick`, `@standard` or `@deep` to the request forces a clinic.

## 4. Dispatch / 派发

Dispatch the request to the chosen clinic subagent: `claude-triage:triage-quick`, `claude-triage:triage-standard` or `claude-triage:triage-deep`.

- Pass the user's request verbatim, with any override token (`@quick`, `@deep`, `用 opus`, …) removed.
- Add the context the clinic needs that it cannot see: relevant file paths, what was already tried, and decisions made earlier in this conversation. Keep it short.
- Do not solve the task yourself; the point of the desk is that the chosen model does the work.

## 5. Hand back / 回诊

- Relay the clinic's answer to the user faithfully.
- If the reply starts with `TRIAGE_ESCALATE:`, tell the user in one line that the case was transferred and why, then dispatch once to the next clinic up (quick → standard → deep). Escalate at most twice.
- End with one line naming the clinic that handled it, e.g. `— 由 专家门诊 · opus 接诊` / `— handled by Specialist clinic · opus`.
