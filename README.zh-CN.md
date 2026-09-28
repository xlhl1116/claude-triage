<div align="center">

# 🏥 claude-triage

**Claude Code 的 AI 导诊台：由一个便宜的导诊模型读每条请求，挂到它需要的精确型号和思考深度，并附一张讲清楚“为什么”的挂号单。**

[English](README.md) | 简体中文

[![tests](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml/badge.svg)](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

<!-- TODO: 替换为真实演示 GIF（docs/assets/demo.gif） -->
> 🎬 *演示 GIF 制作中。* 先看看效果：

```text
> 帮我设计一个分布式任务调度系统，处理并发和一致性

🏥 分诊挂号单
────────────────────────────
科室      特需门诊
模型      Claude Opus 5.5（claude-opus-5-5，Anthropic Claude）
思考深度  max
置信度    中（得分 9；standard≥2，deep≥5，deep-max≥8，frontier≥12）
依据      + 架构/系统设计 (+5)  + 并发/分布式 (+4)
预估成本  ≈ $0.252（全部走最高档 ≈ $0.830，省 70%）
改挂      在请求里加 @quick / @standard / @deep / @deep-max / @frontier 即可推翻本次分诊

……Claude Opus 5.5（effort max）给出的回答……
— 特需门诊 · Claude Opus 5.5 · effort max
```

## 安装

```text
/plugin marketplace add xlhl1116/claude-triage
/plugin install claude-triage@claude-triage
```

重启 Claude Code 后，**主会话就是导诊台**，像平时一样提问即可。

## 工作原理

```
你的消息 ──► hook：规则引擎打分，附上 <triage-slip> 挂号单
                  │
                  ▼
           导诊台（Claude Haiku 4.5，主会话）
           · 自己从不回答问题
           · 规则拿不准时，由它复核
           · 展示挂号单
                  │  用 Agent 工具派单
                  ▼
   ┌───────────┬───────────┬────────────┬─────────────┬─────────────┐
   │ 快速门诊  │ 普通门诊  │ 专家门诊   │ 特需门诊    │ 名医会诊    │
   │ Haiku 4.5 │ Sonnet 5  │ Opus 5.5   │ Opus 5.5    │ Fable 5.1   │
   │  默认     │  medium   │  medium    │   max       │    max      │
   └───────────┴───────────┴────────────┴─────────────┴─────────────┘
                  │  回答（或 TRIAGE_ESCALATE → 转上一级）
                  ▼
           导诊台转给你，并注明型号和思考深度
```

1. **hook 初筛每条消息**：用一张公开透明的规则表打分（任务类型、长度、是否含代码、是否涉及架构 / 并发 / 证明 / 疑难排查），附上挂号单。这一步不调用模型，不花 token。
2. **导诊台只用一个便宜模型**（Claude Haiku 4.5）：它从不自己答题；规则拿不准时，由它来决定挂哪个科。
3. **每个科室固定一个精确型号 + 思考深度**，写在 agent 配置里，例如 `model: claude-opus-5-5` + `effort: max`。不用 opus 这类别名，挂号单上写的就是实际运行的版本。
4. **专科可以转诊**：发现病情比预想的重，会转到上一级科室。

随时可以推翻分诊：在消息里加 `@quick`、`@standard`、`@deep`、`@deep-max` 或 `@frontier`（也可以用 `@haiku`、`@sonnet`、`@opus`、`@opus-max`、`@fable`）。

## 科室

| 科室 | 模型（精确版本） | 思考深度 | 得分 | 典型请求 |
|---|---|---|---|---|
| 导诊台 | Claude Haiku 4.5 `claude-haiku-4-5` | — | — | 给每条消息分诊，从不答题 |
| 快速门诊 `quick` | Claude Haiku 4.5 `claude-haiku-4-5` | 默认¹ | < 2 | 寒暄、翻译润色、错别字、重命名、简单问答 |
| 普通门诊 `standard` | Claude Sonnet 5 `claude-sonnet-5` | medium | 2–4 | 写函数、修明确的 bug、补测试、重构单个模块、审 PR |
| 专家门诊 `deep` | Claude Opus 5.5 `claude-opus-5-5` | medium | 5–7 | 单个疑难点：架构设计、方案权衡、证明、偶发 bug、跨模块迁移 |
| 特需门诊 `deep-max` | Claude Opus 5.5 `claude-opus-5-5` | max | 8–11 | 多个疑难点叠加：分布式/并发架构、并发 bug、全仓库安全审计 |
| 名医会诊 `frontier` | Claude Fable 5.1 `claude-fable-5-1` | max | ≥ 12 | 疑难信号大量叠加的超难问题 |

¹ Claude Haiku 4.5 没有 effort 参数。

科室名单在 [`skills/triage/rules.json`](skills/triage/rules.json)（科室、分数段、改挂口令），每个科室对应的精确型号在 [`skills/triage/providers.json`](skills/triage/providers.json)。改完运行 `python3 skills/triage/scripts/gen_agents.py`，agent 配置会自动重新生成。完整规则表见 [`docs/triage-rules.md`](docs/triage-rules.md)。

不想让导诊台当主会话？在 `~/.claude/settings.json` 里设置你自己的 `"agent"`（用户设置优先于插件），设 `CLAUDE_TRIAGE=off` 关掉 hook，需要时再用 `/claude-triage:triage <请求>` 单次分诊。

## 第三方厂商：DeepSeek、Kimi、智谱 GLM、小米 MiMo

Claude Code 同一时间只连一家的 Anthropic 兼容接口。切换到其他厂商时，导诊台和各科室会按该厂商的精确模型 ID 重新生成：

| 科室 | DeepSeek | 月之暗面 Kimi | 智谱 GLM | 小米 MiMo |
|---|---|---|---|---|
| 导诊台 / 快速门诊 | DeepSeek V4.1 Flash `deepseek-flash` | Kimi K2.7 Code HighSpeed `kimi-k2.7-code-highspeed` | GLM-5.3-Flash `glm-5.3-flash` | MiMo V2.5 `mimo-v2.5` |
| 普通门诊 | DeepSeek V4.1 Flash `deepseek-flash` | Kimi K2.6 `kimi-k2.6` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |
| 专家门诊 | DeepSeek V4 Pro `deepseek-v4-pro` | Kimi K3 `kimi-k3` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |
| 特需门诊 / 名医会诊 | DeepSeek V4 Pro `deepseek-v4-pro` | Kimi K3 `kimi-k3` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |

各科室的思考深度（low → max）会传给厂商接口，但各家是否真的支持**尚未验证**，挂号单上会注明。

```bash
python3 skills/triage/scripts/use_provider.py deepseek                            # 预览
python3 skills/triage/scripts/use_provider.py deepseek --write ~/.claude/settings.json
python3 skills/triage/scripts/use_provider.py zhipu --intl --write ~/.claude/settings.json   # z.ai 国际站
python3 skills/triage/scripts/use_provider.py claude --write ~/.claude/settings.json          # 切回 Claude
```

`--write` 会写入接口地址和 key，把该厂商的导诊台和科室 agent 写到 `~/.claude/agents/`，并把该厂商的导诊台设为主会话。部分厂商的官方教程会设置 `CLAUDE_CODE_SUBAGENT_MODEL`，它会把所有科室强制成同一个模型，脚本会把它清掉。模型 ID 于 2026-09-28 对照各家文档核对过，个别未能完全确认的列在 `providers.json` 的 `unverified` 字段里。

## 与同类方案对比

| | **claude-triage** | OpenRouter Auto | RouteLLM | `opusplan`（Claude Code 内置） |
|---|---|---|---|---|
| 运行位置 | Claude Code 插件 | 托管 API 网关 | 自建服务 / 库 | Claude Code 内 |
| 决策粒度 | 每个请求 | 每个请求 | 每个请求 | 按模式（规划用 Opus，执行用 Sonnet） |
| 选择思考深度 | ✅ | ❌ | ❌ | ❌ |
| 解释决策 | ✅ 挂号单列出信号和得分 | ❌ | ❌ | 不适用 |
| 执行前预估成本 | ✅ | ❌ | ❌ | ❌ |
| 一键手动推翻 | ✅ `@deep-max` | 指定 model 参数 | 调阈值 | 手动切模型 |
| 规则可读可改 | ✅ JSON + 测试 | ❌ | 训练出的路由器 | ❌ |
| 非 Anthropic 模型 | ✅ DeepSeek、Kimi、智谱、小米 MiMo（一次用一家） | ✅ | ✅ | ❌ |
| 额外 API key / 基础设施 | 无 | OpenRouter 账号 | 自己部署 | 无 |

*对比基于 2026-09 的公开文档，如有出入欢迎指正。*

## 单独试用规则引擎

```bash
echo "帮我设计一个分布式任务调度系统" | python3 skills/triage/scripts/triage.py --format slip
python3 skills/triage/scripts/triage.py --format json --provider kimi --text "把这句话翻译成英文：明天见"
```

运行测试和分诊回归用例：

```bash
python3 -m unittest discover -s tests
python3 benchmark/eval_rules.py
```

> ⚠️ `benchmark/triage-cases.jsonl` 里的 47 条种子用例是和规则一起写的，100% 准确率只是回归检查，不代表真实效果。

## Benchmark：质量与成本

`benchmark/run_bench.py` 用 30 道自动评分的题（简单 / 中等 / 困难各 10 道），分别测“固定用某个科室”和“按分诊路由”的表现，任何厂商都能测，并和“全部走最强科室”对比通过率与成本。用法见 [`benchmark/README.md`](benchmark/README.md)，真实跑分结果即将公布。

## 路线图

- [x] 分诊规则表、规则引擎、可解释挂号单、成本预估
- [x] 导诊台固定用一个便宜模型并作为主会话；五个科室各有精确型号 + 思考深度；逐级转诊
- [x] 第三方厂商：DeepSeek、Kimi、智谱 GLM、小米 MiMo
- [x] Benchmark 框架：30 道自动评分题、按厂商分策略、离线 mock 模式
- [ ] **Benchmark 结果**：公布真实跑分并出图
- [ ] 验证各厂商是否支持 Claude Code 的 effort 设置
- [ ] **从反馈中学习**：记录改挂和转诊，自动建议调整权重
- [ ] **混合路由**：同一会话里不同科室用不同厂商；接入 GPT、Gemini、本地模型

## 参与贡献

欢迎 issue 和 PR，尤其是“分错科”的例子：把提示词和你期望的科室加进 `benchmark/triage-cases.jsonl`，调整 `rules.json`；如果改了科室或型号，运行 `python3 skills/triage/scripts/gen_agents.py`；确保 `python3 -m unittest discover -s tests` 通过即可。

## 许可证

[MIT](LICENSE)
