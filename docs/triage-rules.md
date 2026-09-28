# 分诊规则表 / Triage rules

> 规则的唯一来源是 [`skills/triage/rules.json`](../skills/triage/rules.json)，本页是它的可读版本。改规则请改 JSON，再跑 `python3 benchmark/eval_rules.py` 看效果。
>
> The single source of truth is [`skills/triage/rules.json`](../skills/triage/rules.json); this page is the readable version. Edit the JSON, then run `python3 benchmark/eval_rules.py`.

## 流程 / Pipeline

```
请求 ──► ① 手动改挂？(@quick/@standard/@deep …) ──是──► 直接挂号
            │否
            ▼
         ② 关键词 + 长度打分 ──► 得分 → 科室
            │
            ▼
         ③ 置信度低？──是──► 分诊护士（Haiku）复核
            │否
            ▼
         ④ 出挂号单 ──► ⑤ 派发给对应专科 agent ──► 需要时逐级转诊
```

## 科室 / Clinics

| 科室 | Agent | 模型 | effort | 适合 |
|---|---|---|---|---|
| 快速门诊 Quick | `triage-quick` | haiku | —（Haiku 4.5 无 effort 参数） | 寒暄、翻译润色、错别字、重命名、简单问答 |
| 普通门诊 Standard | `triage-standard` | sonnet | medium | 写函数/脚本、常规 bug、写测试、单模块重构、代码审查 |
| 专家门诊 Specialist | `triage-deep` | opus | high | 架构设计、方案权衡、证明/算法、并发分布式、疑难杂症、安全审计、全仓库改动 |

## 打分 / Scoring

每个信号在一条请求里最多计一次，得分相加：

- 得分 **< 2** → 快速门诊
- **2 ≤ 得分 < 5** → 普通门诊
- 得分 **≥ 5** → 专家门诊

### 关键词信号 / Keyword signals

| 信号 | 权重 | 示例关键词 |
|---|---:|---|
| 寒暄/闲聊 | −3 | 你好、谢谢、hi、thanks（整句只有这些） |
| 翻译/润色 | −2 | 翻译、译成、润色、translate、proofread |
| 琐碎修改 | −2 | 错别字、重命名、格式化、加注释、typo、rename |
| 简单问答 | −1 | 什么是…、…是什么意思、what is、define |
| 解释代码 | +1 | 解释这段代码、explain this code |
| 总结归纳 | +1 | 总结、摘要、summarize、tl;dr |
| 多步骤任务 | +1 | 首先…然后、第一步、step by step |
| 编写代码 | +2 | 写一个函数/脚本、实现、implement、write a … script |
| 排查/修复 bug | +2 | bug、报错、异常、traceback、fix、修复 |
| 编写测试 | +2 | 单元测试、测试用例、unit tests |
| 重构 | +2 | 重构、refactor、clean up |
| 代码审查 | +2 | 代码审查、code review |
| 方案权衡 | +2 | 权衡、优缺点、利弊、trade-off、pros and cons |
| 算法/复杂度 | +2 | 时间复杂度、最优解、动态规划、complexity |
| 性能优化 | +2 | 性能、瓶颈、延迟、latency、profiling |
| 迁移/重写 | +2 | 迁移、重写、migrate、rewrite |
| 跨文件/全仓库 | +3 | 整个项目、全仓库、多个文件、entire codebase |
| 并发/分布式 | +4 | 并发、竞态、死锁、分布式、一致性、race condition |
| 安全审计 | +4 | 安全审计、漏洞、威胁建模、vulnerability |
| 架构/系统设计 | +5 | 架构、系统设计、技术选型、微服务、system design |
| 疑难杂症排查 | +5 | 偶发、间歇、根因、内存泄漏、只在线上、flaky、leak、root cause |
| 证明/推导 | +5 | 证明、推导、prove、proof、linearizable |

### 计算信号 / Computed signals

| 信号 | 权重 | 条件 |
|---|---:|---|
| 请求很短 | −1 | ≤ 40 字符、不含代码、且没有命中任何加分信号 |
| 包含代码 | +1 | 有代码块或典型代码行 |
| 输入较长 | +1 | ≥ 2,000 字符 |
| 输入很长 | +2 | ≥ 8,000 字符（替代上一条） |
| 需求条目多 | +1 | ≥ 5 条列表项 |

## 置信度 / Confidence

| 置信度 | 条件 | 处理 |
|---|---|---|
| 手动指定 | 命中改挂口令 | 直接按指定科室 |
| 低 | 没命中任何关键词（只有长度信号）；或同时出现“琐碎”与“疑难”信号（如“把这份架构文档翻译成英文”） | 交给分诊护士（Haiku）复核 |
| 中 | 得分离某个分界线 ≤ 1 分 | 照常派发，挂号单上注明 |
| 高 | 其余情况 | 照常派发 |

## 改挂口令 / Manual overrides

| 科室 | 口令 |
|---|---|
| 快速门诊 | `@quick` `--quick` `@haiku` `用haiku` `快速回答` |
| 普通门诊 | `@standard` `--standard` `@sonnet` `用sonnet` |
| 专家门诊 | `@deep` `--deep` `@opus` `用opus` `深度思考` `ultrathink` `think hard` |

## 预估成本 / Cost estimate

`预估成本 = (请求 token + 3,000 上下文) × 输入单价 + 该科室典型输出 token × 输出单价`

典型输出：quick 600 / standard 2,500 / deep 8,000 token。单价见 `rules.json` 的 `pricing_usd_per_mtok`（默认按 Anthropic API 2026-06 标价：Haiku 4.5 $1/$5，Sonnet 5 $2/$10，Opus 5 $5/$25 每百万 token）。这只是数量级参考；订阅用户看的是额度而不是账单，但比例一样有意义。

## 转诊 / Escalation

专科 agent 发现任务比预想的难时，会回复 `TRIAGE_ESCALATE: <原因>`，分诊台自动转到上一级科室（quick → standard → deep），最多转两次。
