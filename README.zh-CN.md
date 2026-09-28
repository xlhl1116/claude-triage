<div align="center">

# 🏥 claude-triage

**Claude Code 的 AI 导诊台：每个请求自动挂到合适的模型和思考深度，还附一张讲清楚“为什么”的挂号单。**

[English](README.md) | 简体中文

[![tests](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml/badge.svg)](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

<!-- TODO: 替换为真实演示 GIF（docs/assets/demo.gif） -->
> 🎬 *演示 GIF 制作中。* 先看看效果：

```text
> /claude-triage:triage 线上服务偶发 502，只在生产环境出现，帮我找出根因

🏥 分诊挂号单
────────────────────────────
科室      专家门诊 · triage-deep
模型      opus · effort high
置信度    中（得分 5；standard≥2，deep≥5）
依据      + 疑难杂症排查 (+5)
预估成本  ≈ $0.215（全程用 opus ≈ $0.215，省 0%）
改挂      在请求里加 @quick / @standard / @deep 即可推翻本次分诊
```

## 安装

```text
/plugin marketplace add xlhl1116/claude-triage
/plugin install claude-triage@claude-triage
```

使用：`/claude-triage:triage <你的请求>`

## 为什么需要它

大多数请求用不着最贵的模型，但总有几个真的需要。每次手动切模型很烦；“永远 Opus”会把额度烧在“翻译一句话”上，“永远 Sonnet”又会在真正要命的 bug 上想得不够深。

claude-triage 像医院的分诊台一样站在请求前面：

1. **初筛**：用一张公开透明的规则表打分（任务类型、长度、是否含代码、是否涉及架构 / 并发 / 证明 / 疑难排查……）。
2. **护士复核**：只有规则拿不准时，才请 Haiku 便宜地再看一眼。
3. **出挂号单**：选中的模型 + effort、依据哪些信号、预估成本以及和“全程 Opus”相比省多少。
4. **派发接诊**：交给三个专科 subagent 之一；专科发现病情比预想的重，会**自动转诊**到上一级。

随时可以推翻分诊：在请求里加 `@quick`、`@standard` 或 `@deep`。

## 科室

| 科室 | Subagent | 模型 · effort | 典型请求 |
|---|---|---|---|
| 快速门诊 | `triage-quick` | haiku · — | 寒暄、翻译润色、错别字、重命名、简单问答 |
| 普通门诊 | `triage-standard` | sonnet · medium | 写函数、修明确的 bug、补测试、重构单个模块、审 PR |
| 专家门诊 | `triage-deep` | opus · high | 架构设计、方案权衡、证明、并发、只在线上出现的 bug、安全审计、全仓库迁移 |
| *（分诊护士）* | `triage-nurse` | haiku | 低置信度时给第二意见，从不亲自干活 |

完整规则表见 [`docs/triage-rules.md`](docs/triage-rules.md)，规则源文件是 [`skills/triage/rules.json`](skills/triage/rules.json)。

## 与同类方案对比

| | **claude-triage** | OpenRouter Auto | RouteLLM | `opusplan`（Claude Code 内置） |
|---|---|---|---|---|
| 运行位置 | Claude Code 插件 | 托管 API 网关 | 自建服务 / 库 | Claude Code 内 |
| 决策粒度 | 每个请求 | 每个请求 | 每个请求 | 按模式（规划用 Opus，执行用 Sonnet） |
| 选择思考深度 | ✅ | ❌ | ❌ | ❌ |
| 解释决策 | ✅ 挂号单列出信号和得分 | ❌ | ❌ | 不适用 |
| 执行前预估成本 | ✅ | ❌ | ❌ | ❌ |
| 一键手动推翻 | ✅ `@quick` / `@deep` | 指定 model 参数 | 调阈值 | 手动切模型 |
| 规则可读可改 | ✅ JSON + 测试 | ❌ | 训练出的路由器 | ❌ |
| 跨厂商模型 | ❌（规划中） | ✅ | ✅ | ❌ |
| 额外 API key / 基础设施 | 无 | OpenRouter 账号 | 自己部署 | 无 |

*对比基于 2026-09 的公开文档，如有出入欢迎指正。*

## 单独试用规则引擎

引擎是一个只依赖标准库的 Python 文件：

```bash
echo "帮我设计一个分布式任务调度系统" | python3 skills/triage/scripts/triage.py --format slip
python3 skills/triage/scripts/triage.py --format json --text "把这句话翻译成英文：明天见"
```

运行测试和种子基准：

```bash
python3 -m unittest discover -s tests
python3 benchmark/eval_rules.py
```

> ⚠️ `benchmark/triage-cases.jsonl` 里的 41 条种子用例是和规则一起写的，100% 准确率只是回归检查，不代表真实效果。真正的 benchmark 在路线图上——非常欢迎贡献真实的（脱敏后的）提示词。

## 路线图

- [x] 分诊规则表、规则引擎、可解释挂号单、成本预估
- [x] 三个专科 subagent + 分诊护士、手动改挂、自动转诊
- [ ] **Benchmark**：在公开任务集上对比“全程 Opus / 全程 Sonnet”的质量与成本，并出图
- [ ] **从反馈中学习**：记录改挂和转诊，自动建议调整权重
- [ ] Hook 模式：每条提示词自动分诊，不必手动敲命令
- [ ] **跨厂商路由**（第二阶段）：GPT、Gemini、本地模型共用同一张挂号单

## 参与贡献

欢迎 issue 和 PR，尤其是“分错科”的例子：把提示词和你期望的科室加进 `benchmark/triage-cases.jsonl`，调整 `rules.json`，确保 `python3 -m unittest discover -s tests` 通过即可。

## 许可证

[MIT](LICENSE)
