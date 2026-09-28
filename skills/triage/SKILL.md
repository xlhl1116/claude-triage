---
name: triage
description: Triage desk — pick the clinic (exact model version + thinking effort, e.g. Claude Opus 5.5 at max) for a request, show an explainable triage slip, then dispatch the request to that clinic's subagent. Use when the user runs /claude-triage:triage, asks to "triage", "route", "分诊" or "挂号" a request, or when the triage desk has no <triage-slip> for a message.
argument-hint: "[@quick|@standard|@deep|@deep-max|@frontier] <your request>"
allowed-tools: Bash(python3 *) Bash(python *)
---

# Triage desk / 分诊台

The request to triage is:

<request>
$ARGUMENTS
</request>

If the request above is empty, ask the user what they want triaged and stop. Do not answer the request yourself at any point: this skill only routes it.

## 1. Rule-based screening / 规则初筛

Run the rule engine on the request **verbatim**, on stdin through a quoted heredoc so nothing in it is interpreted by the shell:

```bash
python3 "${CLAUDE_SKILL_DIR}/scripts/triage.py" --format both <<'CLAUDE_TRIAGE_EOF'
<the request, verbatim>
CLAUDE_TRIAGE_EOF
```

If `python3` is missing, try `python`. The JSON gives the `clinic`, the `agent` to dispatch to, the exact `model_id` / `model_name` and `effort`, the `score`, the `confidence`, any manual `override`, and the matched `signals`; the slip below it is the same result rendered for the user.

The provider (Claude, DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo) is detected from `ANTHROPIC_BASE_URL`; add `--provider <name>` if the user reaches a provider through their own proxy.

## 2. Second opinion when unsure / 拿不准时复核

Only when `confidence` is `low`: decide the clinic yourself. Rerun the script with `--text "@<clinic> "` prepended to the request if you need the slip for another clinic, or read the clinics from `${CLAUDE_SKILL_DIR}/rules.json`. Pick the cheapest clinic that can clearly do the job well; go higher only when a wrong answer would be costly. Never change a `manual` slip.

## 3. Show the slip / 出挂号单

Show the slip to the user before any work starts. If you changed the clinic, show the slip for the new clinic and add a line `复核 / Review: <one-sentence reason>`.

## 4. Dispatch / 派发

Dispatch with the Agent tool to the slip's `agent` (for Claude: `claude-triage:triage-<clinic>`):

- Pass the user's request verbatim, minus any `@clinic` override token.
- Add the context the clinic cannot see: relevant earlier turns, file paths, what was already tried, decisions already made. Clinics do not see this conversation.

## 5. Hand back / 回诊

- Relay the clinic's answer faithfully and completely.
- If it starts with `TRIAGE_ESCALATE:`, tell the user in one line and dispatch once to the next clinic up (quick → standard → deep → deep-max → frontier), at most two transfers.
- End with one line naming who handled it, e.g. `— 特需门诊 · Claude Opus 5.5 · effort max`.
