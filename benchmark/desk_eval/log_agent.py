#!/usr/bin/env python3
import json, os, sys
e = json.load(sys.stdin)
if e.get("tool_name") in ("Agent", "Task"):
    ti = e.get("tool_input") or {}
    with open(os.environ["DESK_LOG"], "a") as f:
        f.write(json.dumps({"agent": ti.get("subagent_type"), "named": ti.get("agent")}) + "\n")
    if ti.get("subagent_type"):
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
            "permissionDecisionReason": "Evaluation run: dispatch recorded, the executor will not run. Stop now."}}))
