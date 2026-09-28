"""Automatic graders for benchmark tasks.

Every grader returns {"passed": bool, "score": float in [0, 1], "detail": str}.
The `judge` grader needs a model call and is handled by run_bench.py, which
passes a `judge` callable in.

python_tests runs model-written code in a subprocess with a timeout inside a
temporary directory. That is isolation from the benchmark process, not a
security sandbox: only run the benchmark on machines where executing model
output is acceptable.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

FENCE_RE = re.compile(r"```[ \t]*([\w+-]*)[^\n]*\n(.*?)```", re.DOTALL)
NUMBER_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")


def result(passed: bool, detail: str = "", score: float | None = None) -> dict:
    return {"passed": passed, "score": float(passed) if score is None else score, "detail": detail[:500]}


def code_blocks(text: str) -> list[tuple[str, str]]:
    return [(lang.lower(), body) for lang, body in FENCE_RE.findall(text)]


def extract_code(text: str, lang: str = "python") -> str:
    blocks = code_blocks(text)
    if not blocks:
        return text.strip()
    tagged = [b for l, b in blocks if l in (lang, "py", "python3")]
    return max(tagged or [b for _, b in blocks], key=len)


def strip_answer(text: str) -> str:
    """Drop code fences, surrounding quotes/backticks and markdown emphasis."""
    blocks = code_blocks(text)
    if blocks:
        text = blocks[0][1]
    return text.strip().strip("`*\"'“”").strip()


def last_line(text: str) -> str:
    lines = [l for l in text.strip().splitlines() if l.strip()]
    return lines[-1] if lines else ""


# --------------------------------------------------------------------------- graders

def grade_exact(answer: str, spec: dict) -> dict:
    norm = lambda s: re.sub(r"\s+", " ", s).strip().rstrip(".。").lower()
    got = strip_answer(answer)
    return result(norm(got) == norm(spec["answer"]), f"got {got[:80]!r}")


def grade_keywords(answer: str, spec: dict) -> dict:
    low = answer.lower()
    missing = [g for g in spec["groups"] if not any(k.lower() in low for k in g)]
    hit = len(spec["groups"]) - len(missing)
    return result(not missing, f"missing one of {missing}" if missing else "all groups present",
                  hit / len(spec["groups"]))


def grade_regex(answer: str, spec: dict) -> dict:
    return result(bool(re.search(spec["pattern"], answer, re.IGNORECASE)), f"pattern {spec['pattern']}")


def grade_final_regex(answer: str, spec: dict) -> dict:
    line = last_line(answer)
    return result(bool(re.search(spec["pattern"], line, re.IGNORECASE)), f"last line {line[:80]!r}")


def grade_final_number(answer: str, spec: dict) -> dict:
    nums = NUMBER_RE.findall(last_line(answer))
    if not nums:
        return result(False, "no number on last line")
    got = float(nums[-1].replace(",", ""))
    return result(abs(got - spec["answer"]) < 1e-9, f"got {got:g}")


def grade_json_equals(answer: str, spec: dict) -> dict:
    raw = strip_answer(answer)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        return result(False, f"invalid JSON: {e}")
    return result(value == spec["value"], f"got {value!r}"[:200])


def grade_regex_tests(answer: str, spec: dict) -> dict:
    pattern = strip_answer(answer)
    if len(pattern) > 2 and pattern.startswith("/") and pattern.rstrip("gimsuy").endswith("/"):
        pattern = pattern[1:pattern.rstrip("gimsuy").rfind("/")]
    try:
        rx = re.compile(pattern)
    except re.error as e:
        return result(False, f"invalid regex {pattern!r}: {e}")
    wrong = [s for s in spec["match"] if not rx.fullmatch(s)] + \
            [s for s in spec["no_match"] if rx.fullmatch(s)]
    return result(not wrong, f"regex {pattern!r}, wrong on {wrong}" if wrong else f"regex {pattern!r}")


def grade_python_tests(answer: str, spec: dict) -> dict:
    code = extract_code(answer)
    for s in spec.get("must_contain", []):
        if s not in code:
            return result(False, f"code must contain {s!r}")
    for s in spec.get("must_not_contain", []):
        if s in code:
            return result(False, f"code must not contain {s!r}")
    with tempfile.TemporaryDirectory(prefix="triage-bench-") as tmp:
        Path(tmp, "solution.py").write_text(code, encoding="utf-8")
        Path(tmp, "test_solution.py").write_text(spec["tests"], encoding="utf-8")
        try:
            proc = subprocess.run([sys.executable, "test_solution.py"], cwd=tmp, capture_output=True,
                                  text=True, encoding="utf-8", timeout=spec.get("timeout", 10))
        except subprocess.TimeoutExpired:
            return result(False, "timeout")
    if proc.returncode == 0:
        return result(True, "tests passed")
    err = (proc.stderr or proc.stdout).strip().splitlines()
    return result(False, err[-1] if err else f"exit {proc.returncode}")


def grade_judge(answer: str, spec: dict, judge=None, prompt: str = "") -> dict:
    if judge is None:
        return result(False, "no judge configured")
    verdict = judge(prompt, answer, spec["rubric"])
    met = verdict.get("met", [])
    score = sum(bool(x) for x in met) / len(spec["rubric"]) if met else 0.0
    return result(score >= spec.get("pass_ratio", 0.8), verdict.get("reason", ""), score)


GRADERS = {
    "exact": grade_exact,
    "keywords": grade_keywords,
    "regex": grade_regex,
    "final_regex": grade_final_regex,
    "final_number": grade_final_number,
    "json_equals": grade_json_equals,
    "regex_tests": grade_regex_tests,
    "python_tests": grade_python_tests,
}


def grade(task: dict, answer: str, judge=None) -> dict:
    spec = task["grader"]
    if spec["type"] == "judge":
        return grade_judge(answer, spec, judge, task["prompt"])
    return GRADERS[spec["type"]](answer, spec)
