# Benchmark / 评测

Two things live here:

| File | What it checks | Calls models? |
|---|---|---|
| `triage-cases.jsonl` + `eval_rules.py` | Does the rule engine put each request in the expected category? (routing regression) | No |
| `triage-heldout.jsonl`, `triage-heldout-2.jsonl` | Same check on requests the rules were not written for (`python3 benchmark/eval_rules.py benchmark/triage-heldout-2.jsonl`). `triage-heldout.jsonl` has since been used to tune the rules; `triage-heldout-2.jsonl` has not, so keep it that way and write a new set for the next honest check | No |
| `tasks.py` + `run_bench.py` | Does routing keep quality while cutting cost? (quality vs. cost) | Yes, or mock |

## Quality vs. cost

30 single-turn tasks, each with an automatic grader and a known-good reference answer:

| Difficulty | Examples | Graded by |
|---|---|---|
| easy (10) | translation, facts, typo fix, JSON, regex | exact match, keywords, JSON equality, regex behaviour |
| medium (10) | functions with edge cases, bug fix, LRU cache, IPv4 validation | hidden unit tests |
| hard (10) | O(n) / O(n log n) algorithms, expression parser, async concurrency limit, number theory, a production bug, system design | unit tests with time limits, final answer, keywords, LLM judge with a rubric |

Strategies per provider: fixed models `<provider>:t1 | t3 | t5 | t7 | t8` by default (e.g. `claude:t7` = Claude Opus 5.5 at max; the internal tiers t1–t8 are listed in [`docs/taxonomy.md`](../docs/taxonomy.md)), plus `<provider>:triage`: the rule engine puts each task in one of the 120 categories, which sets the model; when it is not confident, the desk model picks the category, as in Claude Code. Each provider is compared with always using its own strongest model. Identical requests (two tiers with the same model and settings) are generated once.

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

Useful flags: `--strategies claude:t5,claude:t7,claude:triage`, `--difficulty hard`, `--tasks id1,id2`, `--repeats 3` (variance), `--region intl` (moonshot.ai / z.ai endpoints), `--no-second-opinion`, `--judge <provider>/<tier>` (the one judge-graded task defaults to `claude/t5`, Claude Opus 5.5 medium). Runs are cached in `benchmark/results/<run-id>/`; re-running the same id resumes. The report is `summary.md` + `summary.json`.

Things to know:

- **Model-written code is executed** by the unit-test graders, in a subprocess with a timeout in a temp directory. That is not a security sandbox; run it where executing model output is acceptable.
- Every strategy gets the same neutral system prompt, so differences come from the model and the routing only. Escalation (`TRIAGE_ESCALATE`) is not modelled yet.
- Claude tiers send `output_config.effort` (Sonnet 5 low / medium / high, Opus 5.5 medium / high / max, Fable 5.1 max). Third-party tiers express depth through `extra_body` in `skills/triage/providers.json` (e.g. DeepSeek `thinking` + `reasoning_effort`), because their parameters differ.
- Routing keywords were partly tuned while looking at these 30 task prompts, so triage results on this set are optimistic; judge routing on prompts it has not seen.
- Cost is only reported for models with `pricing` in `providers.json` (Claude for now); others show "—".
- 30 tasks is small. Treat differences of one or two tasks as noise, and use `--repeats` before drawing conclusions.

---

## 中文速览

- `run_bench.py --check-references`：先验证所有标准答案都能通过打分器，保证题目本身没错。
- `--backend mock`：离线假数据，只用来检查流程，**数字没有任何意义**。
- `--backend live --yes`：真实调用 API，需要对应厂商的 key；可用 `--judge deepseek/deep` 把评委换成非 Claude 模型。
- 每家厂商都和“全部用自己最强的模型”比，看分诊能省多少、质量掉多少；每一行都标明精确型号和思考深度。
- 分诊关键词调整时参考过这 30 道题，所以分诊在这套题上的表现偏乐观，要用没见过的题来评估。
- 单元测试会执行模型写的代码，只有超时和临时目录隔离，不是安全沙箱。
