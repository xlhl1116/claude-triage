# 分诊规则表 / Triage rules

> 规则的来源是 [`skills/triage/rules.json`](../skills/triage/rules.json)（科室、分数段、信号、改挂口令）和 [`skills/triage/providers.json`](../skills/triage/providers.json)（每个科室用哪个精确型号）。本页是它们的可读版本。改完规则跑 `python3 benchmark/eval_rules.py` 看效果；改了科室或型号再跑 `python3 skills/triage/scripts/gen_agents.py` 重新生成 agent。
>
> Sources of truth: `rules.json` (clinics, score bands, signals, overrides) and `providers.json` (exact model per clinic). This page is the readable version.

## 流程 / Pipeline

```
用户消息 ──► ① UserPromptSubmit hook：规则引擎打分，附上 <triage-slip>（不调用模型）
                │
                ▼
             ② 导诊台（主会话，固定用 Claude Haiku 4.5，从不答题）
                │  置信度低 → 导诊台自己复核
                ▼
             ③ 展示挂号单 ──► ④ 派发给对应科室 agent（精确型号 + effort）
                                     │
                                     ▼
                              ⑤ 回诊；需要时逐级转诊（最多两次）
```

## 科室 / Clinics（Claude）

每个请求挂到得分能达到的**最高**科室：

| 科室 | 得分 | 模型（精确版本） | 思考深度 | 适合 | 改挂口令 |
|---|---|---|---|---|---|
| 快速门诊 `quick` | < 2 | Claude Haiku 4.5 `claude-haiku-4-5` | 默认（无 effort 参数） | 寒暄、翻译润色、错别字、重命名、简单问答 | `@quick` `--quick` `@haiku` `用haiku` `用 haiku` `快速回答` |
| 普通门诊 `standard` | 2–4 | Claude Sonnet 5 `claude-sonnet-5` | medium | 写函数/脚本、常规 bug、写测试、单模块重构、代码审查 | `@standard` `--standard` `@sonnet` `用sonnet` `用 sonnet` |
| 专家门诊 `deep` | 5–7 | Claude Opus 5.5 `claude-opus-5-5` | medium | 单个疑难点：架构设计、方案权衡、证明、偶发 bug、跨模块迁移 | `@deep` `--deep` `@opus` `用opus` `用 opus` `深度思考` `think hard` |
| 特需门诊 `deep-max` | 8–11 | Claude Opus 5.5 `claude-opus-5-5` | max | 多个疑难点叠加：分布式/并发架构、并发 bug 排查、全仓库安全审计 | `@deep-max` `--deep-max` `@opus-max` `ultrathink` |
| 名医会诊 `frontier` | ≥ 12 | Claude Fable 5.1 `claude-fable-5-1` | max | 疑难信号大量叠加的超难问题 | `@frontier` `--frontier` `@fable` `用fable` `用 fable` |

导诊台本身用 Claude Haiku 4.5 `claude-haiku-4-5`。

## 打分 / Scoring

每个信号在一条请求里最多计一次，得分相加。

### 关键词信号 / Keyword signals

| 信号 | 权重 | 示例关键词 |
|---|---:|---|
| 寒暄/闲聊 | -3 | （见 rules.json） |
| 翻译/润色 | -2 | 翻译、译成、润色 |
| 琐碎修改 | -2 | 拼写、错别字、改个名、格式化 |
| 简单问答 | -1 | （见 rules.json） |
| 解释代码 | +1 | 这段代码 |
| 总结归纳 | +1 | 总结、概括、摘要 |
| 多步骤任务 | +1 | 第一步、分步 |
| 编写代码 | +2 | （见 rules.json） |
| 排查/修复 bug | +2 | 报错、异常、traceback、修复 |
| 编写测试 | +2 | 单元测试、测试用例 |
| 重构 | +2 | 重构 |
| 代码审查 | +2 | 代码审查、审查 |
| 方案权衡 | +2 | 权衡、优缺点、利弊、方案对比 |
| 算法/复杂度 | +2 | 时间复杂度、空间复杂度、复杂度、算法设计 |
| 性能优化 | +2 | 性能、瓶颈、延迟 |
| 迁移/重写 | +2 | 迁移、重写、升级到 |
| 跨文件/全仓库 | +3 | 多个文件、所有文件 |
| 并发/分布式 | +4 | 并发、竞态、死锁、分布式 |
| 安全审计 | +4 | 安全审计、漏洞、威胁建模 |
| 架构/系统设计 | +5 | 架构、系统设计、技术选型、微服务 |
| 证明/推导 | +5 | 证明、推导 |
| 疑难杂症排查 | +5 | 偶发、间歇、偶尔、随机失败 |

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
| 手动指定 | 命中改挂口令（多个口令时取最长的，`@opus-max` 不会被当成 `@opus`） | 直接按指定科室 |
| 低 | 没命中任何关键词（只有长度信号）；或同时出现“琐碎”与“疑难”信号（如“把这份架构文档翻译成英文”） | 导诊台自己复核 |
| 中 | 得分离某条分数线 ≤ 1 分 | 照常派发，挂号单上注明 |
| 高 | 其余情况 | 照常派发 |

## 预估成本 / Cost estimate

`预估成本 = (请求 token + 3,000 上下文) × 输入单价 + 该科室典型输出 token × 输出单价`，对比“全部走最高科室”。

典型输出：quick 600 / standard 2,500 / deep 6,000 / deep-max 12,000 / frontier 16,000 token。单价见 `providers.json` 各模型的 `pricing`（Claude 按 Anthropic API 标价：Haiku 4.5 $1/$5，Sonnet 5 $2/$10，Opus 5.5 $4/$20，Fable 5.1 $10/$50 每百万 token；第三方暂未配置，显示“—”）。这只是数量级参考；订阅用户看的是额度而不是账单，但比例一样有意义。

## 第三方厂商 / Other providers

切换厂商后（`use_provider.py <厂商> --write …`），导诊台和科室按该厂商的精确型号重新生成，导诊台用该厂商“快速门诊”那一档的模型：

| 厂商 | 快速门诊 | 普通门诊 | 专家门诊 | 特需门诊 | 名医会诊 |
|---|---|---|---|---|---|
| DeepSeek 深度求索 | DeepSeek V4.1 Flash `deepseek-flash` · low | DeepSeek V4.1 Flash `deepseek-flash` · medium | DeepSeek V4 Pro `deepseek-v4-pro` · high | DeepSeek V4 Pro `deepseek-v4-pro` · max | DeepSeek V4 Pro `deepseek-v4-pro` · max |
| 月之暗面 Kimi | Kimi K2.7 Code HighSpeed `kimi-k2.7-code-highspeed` · low | Kimi K2.6 `kimi-k2.6` · medium | Kimi K3 `kimi-k3` · high | Kimi K3 `kimi-k3` · max | Kimi K3 `kimi-k3` · max |
| 智谱 GLM | GLM-5.3-Flash `glm-5.3-flash` · low | GLM-5.3 `glm-5.3` · medium | GLM-5.3 `glm-5.3` · high | GLM-5.3 `glm-5.3` · max | GLM-5.3 `glm-5.3` · max |
| 小米 MiMo | MiMo V2.5 `mimo-v2.5` · low | MiMo V2.6 Pro `mimo-v2.6-pro` · medium | MiMo V2.6 Pro `mimo-v2.6-pro` · high | MiMo V2.6 Pro `mimo-v2.6-pro` · max | MiMo V2.6 Pro `mimo-v2.6-pro` · max |

第三方科室的 effort 会写进 agent 配置并传给厂商接口，但各家是否支持**尚未验证**，挂号单上会注明。benchmark 直连 API 时，则按各家自己的参数设置思考深度（见 `providers.json` 的 `extra_body` / `api_effort`）。

## 转诊 / Escalation

科室发现任务明显超出能力时，回复 `TRIAGE_ESCALATE: <原因>`，导诊台转到下一个更高的科室，最多转两次。
