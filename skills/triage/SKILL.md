---
name: triage
description: Triage desk — classify a request into one of ~120 fine-grained categories (code, writing, research, health, law, finance, …), pick the exact model and thinking effort that category needs (e.g. Claude Opus 5.5 at max), show an explainable slip, then dispatch the request to that executor. Use when the user runs /claude-triage:triage, asks to "triage", "route", "分诊" or "挂号" a request, or when the triage desk has no <triage-slip> for a message.
argument-hint: "[@haiku|@sonnet|@opus|@opus-max|@fable] <your request>"
allowed-tools: Bash(sh *) Bash(python3 *) Bash(python *)
---

# Triage desk / 分诊台

The request to triage is:

<request>
$ARGUMENTS
</request>

If the request above is empty, ask the user what they want triaged and stop. Do not answer the request yourself at any point: this skill only routes it.

## 1. Classify / 识别类别

Run the rule engine on the request **verbatim**, on stdin through a quoted heredoc so nothing in it is interpreted by the shell:

```bash
sh "${CLAUDE_SKILL_DIR}/scripts/triage.sh" --format both <<'CLAUDE_TRIAGE_EOF'
<the request, verbatim>
CLAUDE_TRIAGE_EOF
```

`triage.sh` runs the engine with whichever Python 3.9+ it finds (`python3`, `python` or `py -3`). The JSON gives the `category`, the `confidence` and top `candidates`, the executor `agent` to dispatch to, the exact `model_id` / `model_name` and `effort`, any background `modifiers` (scope, risk, clarity, input size), any manual `override`, and category `guidance`; the slip below it is the same result rendered for the user. If `handler` is `desk`, the request is about the triage itself: answer it directly from the slip and stop.

The provider (Claude, DeepSeek, Kimi, Zhipu GLM, Xiaomi MiMo) is detected from `ANTHROPIC_BASE_URL`; add `--provider <name>` if the user reaches a provider through their own proxy.

## 2. Check the category / 复核类别

Always check the category, whatever the `confidence`: the rules match keywords and can be confidently wrong. Pick the category that fits what the user wants done; use the unclear fallback only when you cannot tell (a request about code or a document the user has not pasted is not unclear: route it by its task). `sh "${CLAUDE_SKILL_DIR}/scripts/triage.sh" --list-categories` prints them all. If yours differs from the slip's, rerun step 1 with `--category <id>` added. A `manual` slip means the user picked the model: never change its model; to correct only its category, rerun with the request **including** its override token.

## 3. Show the slip / 出挂号单

Show the slip to the user before any work starts. If you re-routed, show the new slip and add a line `复核 / Review: <one-sentence reason>`. Never mention internal tiers; talk about the category and the model.

## 4. Dispatch / 派发

Dispatch with the Agent tool to the slip's `agent` (for Claude: `claude-triage:triage-<tier>-<tools>`), in the foreground (`run_in_background: false`) so the answer comes back in this turn:

- Pass the user's request verbatim, minus any override token such as `@opus-max`.
- Include the slip's `guidance` if there is one.
- Add the context the executor cannot see: relevant earlier turns, file paths, what was already tried, decisions already made.

## 5. Hand back / 回诊

- Relay the executor's answer faithfully and completely: paste it verbatim, however long. The user cannot see the executor's output, only what you write, so never summarize it or refer to it as "above".
- If it starts with `TRIAGE_ESCALATE:`, tell the user in one line and dispatch once to the next stronger model with the same tool profile (the next tier up in the agent name), at most two transfers.
- End with the JSON's `footer` line from the run you dispatched with (the `--category` rerun if you re-routed), copied verbatim, e.g. `— 💻 软件开发 › 并发、竞态、死锁 · Claude Opus 5.5 · effort max`. Never write it yourself.
