# Benchmark / 评测

Two things live here:

| File | What it checks | Calls models? |
|---|---|---|
| `triage-cases.jsonl` + `eval_rules.py` | Does the rule engine send each request to the expected clinic? (routing regression) | No |
| `tasks.py` + `run_bench.py` | Does routing keep quality while cutting cost? (quality vs. cost) | Yes, or mock |

## Quality vs. cost

30 single-turn tasks, each with an automatic grader and a known-good reference answer:

| Difficulty | Examples | Graded by |
|---|---|---|
| easy (10) | translation, facts, typo fix, JSON, regex | exact match, keywords, JSON equality, regex behaviour |
| medium (10) | functions with edge cases, bug fix, LRU cache, IPv4 validation | hidden unit tests |
| hard (10) | O(n) / O(n log n) algorithms, expression parser, async concurrency limit, number theory, a production bug, system design | unit tests with time limits, final answer, keywords, LLM judge with a rubric |

Strategies per provider: one per clinic, `<provider>:quick | standard | deep | deep-max | frontier` (always that clinic's exact model and effort, e.g. `claude:deep-max` = Claude Opus 5.5 at max), plus `<provider>:triage` (the rule engine picks the clinic per task; when it is not confident, the desk model gives a second opinion, as in Claude Code). Each provider is compared with always using its own strongest clinic. Identical requests (two clinics with the same model and settings) are generated once.

```bash
# prove every grader and test is right: all references must pass (no API calls)
python3 benchmark/run_bench.py --check-references

# offline dry run with fake answers, to check the pipeline (no API calls)
python3 benchmark/run_bench.py --backend mock --providers claude,deepseek,kimi,zhipu,xiaomi --run-id mock

# real run: set the keys for the providers you test
export ANTHROPIC_API_KEY=...  DEEPSEEK_API_KEY=...  MOONSHOT_API_KEY=...  ZHIPU_API_KEY=...  MIMO_API_KEY=...
pip install anthropic          # only needed for Claude
python3 benchmark/run_bench.py --backend live --providers deepseek,kimi --judge deepseek/deep --run-id first --yes
```

Useful flags: `--strategies claude:deep,claude:triage`, `--difficulty hard`, `--tasks id1,id2`, `--repeats 3` (variance), `--region intl` (moonshot.ai / z.ai endpoints), `--no-second-opinion`, `--judge <provider>/<clinic>` (the one judge-graded task defaults to `claude/deep`). Runs are cached in `benchmark/results/<run-id>/`; re-running the same id resumes. The report is `summary.md` + `summary.json`.

Things to know:

- **Model-written code is executed** by the unit-test graders, in a subprocess with a timeout in a temp directory. That is not a security sandbox; run it where executing model output is acceptable.
- Every strategy gets the same neutral system prompt, so differences come from the model and the routing only. Escalation (`TRIAGE_ESCALATE`) is not modelled yet.
- Claude clinics send `output_config.effort` with the clinic's effort (Sonnet 5 medium, Opus 5.5 medium / max, Fable 5.1 max). Third-party clinics express depth through `extra_body` in `skills/triage/providers.json` (e.g. DeepSeek `thinking` + `reasoning_effort`), because their parameters differ.
- Cost is only reported for models with `pricing` in `providers.json` (Claude for now); others show "—".
- 30 tasks is small. Treat differences of one or two tasks as noise, and use `--repeats` before drawing conclusions.

---

## 中文速览

- `run_bench.py --check-references`：先验证所有标准答案都能通过打分器，保证题目本身没错。
- `--backend mock`：离线假数据，只用来检查流程，**数字没有任何意义**。
- `--backend live --yes`：真实调用 API，需要对应厂商的 key；可用 `--judge deepseek/deep` 把评委换成非 Claude 模型。
- 每家厂商都和“全部走自己最强的科室”比，看分诊能省多少、质量掉多少；每一行都标明精确型号和思考深度。
- 单元测试会执行模型写的代码，只有超时和临时目录隔离，不是安全沙箱。
