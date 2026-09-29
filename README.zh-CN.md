<div align="center">

# 🏥 claude-triage

### 别再用 Opus 的价钱去改一个变量名。

**Claude Code 的 AI 导诊台。** 由一个便宜的导诊模型读每条请求，从 120 个细类里认出它是哪类需求，再交给这类需求需要的模型和思考深度，并附一张讲清楚“为什么”的挂号单。

[English](README.md) | 简体中文

[![tests](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml/badge.svg)](https://github.com/xlhl1116/claude-triage/actions/workflows/test.yml)
[![license: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
![version](https://img.shields.io/badge/version-0.1.0-orange.svg)
![python](https://img.shields.io/badge/python-3.9%2B-blue.svg)
![no extra API key](https://img.shields.io/badge/extra%20API%20key-none-brightgreen.svg)

</div>

<!-- TODO: 替换为真实演示 GIF（docs/assets/demo.gif） -->
> 🎬 *演示 GIF 制作中。* 先看看效果：

```text
> 这段 Go 代码在高并发下会死锁，线上已经出现两次，帮我分析原因并修复

🏥 分诊挂号单
────────────────────────────
类别      💻 软件开发 › 并发、竞态、死锁
模型      Claude Opus 5.5（claude-opus-5-5，Anthropic Claude）
思考深度  max
理由      命中 “并发”、“死锁”
置信度    高
预估成本  ≈ $0.252（全部用最强配置 ≈ $0.830，省 70%）
改挂      在消息里加 @haiku / @sonnet / @opus / @opus-max / @fable 可直接指定模型

……Claude Opus 5.5（effort max）给出的回答……
— 软件开发 › 并发、竞态、死锁 · Claude Opus 5.5 · effort max
```

## 为什么需要它

- **所有请求用同一个模型，怎么选都亏。** 一直开 Opus，改个错别字也按架构评审的价钱算；一直开 Haiku，线上死锁只能得到一个浅显的回答。
- **你不该自己来判断。** 没人能提前知道一个问题该挂普通号还是专家号，导诊台根据你问的内容来判断。
- **每个决定都看得见。** 每个回答都附一张挂号单：类别、命中的关键词、型号、思考深度和预估节省。加一个词（`@opus-max`）就能推翻它。

> 🧪 **早期版本（v0.1）。** 规则引擎、49 个测试和分诊回归检查全部通过，但插件在 Claude Code 里的实际使用还很少。非常欢迎提交分错科的例子和 bug。

## 安装

```text
/plugin marketplace add xlhl1116/claude-triage
/plugin install claude-triage@claude-triage
```

需要 Claude Code 2.1.284 或更高版本（从这一版起支持 Claude Sonnet 5.5）。

重启 Claude Code 后，**主会话就是导诊台**，像平时一样提问即可。

**想先看看分诊效果？** 规则引擎是纯 Python，没有任何依赖：

```bash
git clone https://github.com/xlhl1116/claude-triage && cd claude-triage
echo "这段 Go 代码在高并发下会死锁，线上已经出现两次" | python3 skills/triage/scripts/triage.py --format slip
```

## 工作原理

```
你的消息 ──► hook：规则引擎识别类别，附上 <triage-slip> 挂号单   （不调用模型）
                  │
                  ▼
           导诊台（Claude Haiku 4.5，主会话）
           · 自己从不回答问题
           · 每张挂号单都复核类别，分错了就改挂
           · 展示挂号单
                  │  用 Agent 工具派单
                  ▼
   执行 agent = 精确型号 + 思考深度 + 工具权限，例如
   Claude Haiku 4.5 · Claude Sonnet 5.5 low / medium / high · Claude Opus 5.5 medium / high / max · Claude Fable 5.1 max
                  │  回答（或 TRIAGE_ESCALATE → 转给更强的模型）
                  ▼
           导诊台转给你，并注明类别、型号和思考深度
```

1. **识别需求类型，而不是让你选档位。** 大多数人分不清自己的问题该挂普通号还是专家号，所以没人需要做这个选择。hook 会把每条消息和 **17 个大类、120 个细类**对照：从“改个变量名”到“分布式架构”，从“合同审查”到“用药咨询”，然后附上挂号单。这一步不调用模型，不花 token。
2. **类别决定模型。** 每个细类都有默认的型号、思考深度和工具权限。日常翻译交给 Claude Haiku 4.5，跨模块的大型重构交给 Claude Opus 5.5 · max。健康、法律、金融类设了最低配置，不会落到便宜模型上，并附带专属指令，比如健康类会提醒就医。
3. **后台微调。** 涉及整个仓库、生产环境或支付、需求模糊、输入很长、有复杂度约束时自动上调；给了明确步骤时下调。最强的 Claude Fable 5.1 只有在多个信号叠加时才会用到。
4. **导诊台只用一个便宜模型**（Claude Haiku 4.5），自己从不答题。它会复核每条请求的类别，不只是规则拿不准的那些，发现规则分错了就改挂。
5. **执行 agent 可以转诊**：发现任务比预想的难，会转给更强的模型。

想自己指定模型，在消息里加 `@haiku`、`@sonnet`、`@opus`、`@opus-max` 或 `@fable` 即可。旧的 `@quick`、`@deep` 口令仍然有效。

## 分类表

<details>
<summary><b>17 个大类，120 个细类</b>（点击展开）</summary>

| 大类 | 细类数 | 示例 → 默认模型 |
|---|---:|---|
| 💻 软件开发 | 40 | 改名 / 格式化 → Haiku 4.5 · UI 组件 → Sonnet 5.5 medium · 跨模块功能 → Opus 5.5 medium · 框架迁移 → Opus 5.5 high · 大型重构、偶发 bug、并发、安全审计、分布式架构 → Opus 5.5 max |
| 📊 数据与数学 | 8 | 计算 → Haiku 4.5 · Excel 公式 → Sonnet 5.5 low · 统计分析 → Opus 5.5 medium · 数学证明 → Opus 5.5 max |
| ✍️ 写作 | 10 | 润色、邮件、摘要 → Sonnet 5.5 low · 公文报告、小说 → Opus 5.5 medium · 学术论文 → Opus 5.5 high |
| 🌐 语言 | 4 | 日常翻译、语法 → Haiku 4.5 · 法律 / 医学 / 长文翻译 → Opus 5.5 medium |
| 🔎 信息查询 | 5 | 常识 → Haiku 4.5 · 产品比较 → Sonnet 5.5 medium · 深度调研报告 → Opus 5.5 high |
| 🎓 教育学习 | 4 | 概念讲解、作业辅导 → Sonnet 5.5 medium |
| 🧭 实用建议 | 4 | 设备设置、办事流程、家居维修 → Sonnet 5.5 low |
| 🩺 健康 | 6 | 症状、心理健康 → Opus 5.5 medium · 用药、检查报告 → Opus 5.5 high（最低 Opus 5.5 medium） |
| ⚖️ 法律 | 4 | 法律咨询、合同起草 → Opus 5.5 medium · 合同审查、合规 → Opus 5.5 high（最低 Opus 5.5 medium） |
| 💰 金融财务 | 4 | 个人理财 → Sonnet 5.5 medium · 投资分析、财务建模 → Opus 5.5 high（最低 Opus 5.5 medium） |
| 💼 职场与商业 | 8 | 会议纪要 → Sonnet 5.5 low · 简历、面试 → Sonnet 5.5 medium · 商业计划 → Opus 5.5 high |
| 🔬 科研 | 5 | 文献综述、实验设计 → Opus 5.5 high · 理论推导 → Opus 5.5 max |
| 🎨 设计与多媒体 | 5 | 生图提示词 → Haiku 4.5 · UX、品牌、视频脚本 → Sonnet 5.5 medium |
| 💡 创意与娱乐 | 4 | 起名、角色扮演 → Sonnet 5.5 low · 头脑风暴、诗词 → Sonnet 5.5 medium |
| 🏠 生活 | 4 | 菜谱 → Haiku 4.5 · 旅行、育儿 → Sonnet 5.5 medium |
| 💬 闲聊与情感 | 3 | 寒暄 → Haiku 4.5 · 情感关系 → Sonnet 5.5 medium |
| 🗂️ 其他 | 2 | 询问分诊本身（导诊台直接回答） · 需求不清 |

</details>

大类的划分参考了公开的真实使用研究：OpenAI / NBER《How People Use ChatGPT》（2025）、Anthropic 的 Clio 和 Economic Index（2024–2026）、Microsoft《Copilot Usage Report 2025》。软件开发是 Claude 最主要的用途，也是 Claude Code 的核心场景，所以分得最细。

**全部 120 个细类**及其型号、思考深度、工具权限和最低配置，见 **[`docs/taxonomy.md`](docs/taxonomy.md)**。这份文档由 [`skills/triage/taxonomy.json`](skills/triage/taxonomy.json)（类别和关键词）、[`rules.json`](skills/triage/rules.json)（后台微调和改挂口令）、[`providers.json`](skills/triage/providers.json)（精确型号）自动生成。发现漏了哪类需求？往 `taxonomy.json` 里加一个细类，提个 PR 就行。

不想让导诊台当主会话？在 `~/.claude/settings.json` 里设置你自己的 `"agent"`（用户设置优先于插件），设 `CLAUDE_TRIAGE=off` 关掉 hook，需要时再用 `/claude-triage:triage <请求>` 单次分诊。

## 第三方厂商：DeepSeek、Kimi、智谱 GLM、小米 MiMo

Claude Code 同一时间只连一家的 Anthropic 兼容接口。切换到其他厂商时，导诊台和执行 agent 会按该厂商的精确模型 ID 重新生成：

| Claude | DeepSeek | 月之暗面 Kimi | 智谱 GLM | 小米 MiMo |
|---|---|---|---|---|
| Claude Haiku 4.5（导诊台） | DeepSeek V4.1 Flash `deepseek-flash` | Kimi K2.7 Code HighSpeed `kimi-k2.7-code-highspeed` | GLM-5.3-Flash `glm-5.3-flash` | MiMo V2.5 `mimo-v2.5` |
| Claude Sonnet 5.5 | DeepSeek V4.1 Flash `deepseek-flash` | Kimi K2.6 / K2.7 Code | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |
| Claude Opus 5.5 | DeepSeek V4 Pro `deepseek-v4-pro` | Kimi K3 `kimi-k3` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |
| Claude Fable 5.1 | DeepSeek V4 Pro `deepseek-v4-pro` | Kimi K3 `kimi-k3` | GLM-5.3 `glm-5.3` | MiMo V2.6 Pro `mimo-v2.6-pro` |

每一档的精确思考深度见 [`docs/taxonomy.md`](docs/taxonomy.md) 的“模型阶梯”一节。思考深度会传给厂商接口，但各家是否真的支持**尚未验证**，挂号单上会注明。

```bash
python3 skills/triage/scripts/use_provider.py deepseek                            # 预览
python3 skills/triage/scripts/use_provider.py deepseek --write ~/.claude/settings.json
python3 skills/triage/scripts/use_provider.py zhipu --intl --write ~/.claude/settings.json   # z.ai 国际站
python3 skills/triage/scripts/use_provider.py claude --write ~/.claude/settings.json          # 切回 Claude
```

`--write` 会写入接口地址和 key，把该厂商的导诊台和执行 agent 写到 `~/.claude/agents/`，并把该厂商的导诊台设为主会话。部分厂商的官方教程会设置 `CLAUDE_CODE_SUBAGENT_MODEL`，它会把所有执行 agent 强制成同一个模型，脚本会把它清掉。模型 ID 于 2026-09-28 对照各家文档核对过，个别未能完全确认的列在 `providers.json` 的 `unverified` 字段里。

## 与同类方案对比

| | **claude-triage** | OpenRouter Auto | RouteLLM | `opusplan`（Claude Code 内置） |
|---|---|---|---|---|
| 运行位置 | Claude Code 插件 | 托管 API 网关 | 自建服务 / 库 | Claude Code 内 |
| 决策粒度 | 每个请求，按 120 个细类 | 每个请求 | 每个请求 | 按模式（规划用 Opus，执行用 Sonnet） |
| 选择思考深度 | ✅ | ❌ | ❌ | ❌ |
| 解释决策 | ✅ 类别、命中信号、微调原因 | ❌ | ❌ | 不适用 |
| 执行前预估成本 | ✅ | ❌ | ❌ | ❌ |
| 领域护栏 | ✅ 健康、法律、金融设最低配置和专属指令 | ❌ | ❌ | ❌ |
| 一键手动推翻 | ✅ `@opus-max` | 指定 model 参数 | 调阈值 | 手动切模型 |
| 规则可读可改 | ✅ JSON + 测试 | ❌ | 训练出的路由器 | ❌ |
| 非 Anthropic 模型 | ✅ DeepSeek、Kimi、智谱、小米 MiMo（一次用一家） | ✅ | ✅ | ❌ |
| 额外 API key / 基础设施 | 无 | OpenRouter 账号 | 自己部署 | 无 |

*对比基于 2026-09 的公开文档，如有出入欢迎指正。*

## 单独试用规则引擎

```bash
echo "线上服务偶发 502，本地复现不了，帮我找根因" | python3 skills/triage/scripts/triage.py --format slip
python3 skills/triage/scripts/triage.py --format json --provider kimi --text "帮我审查这份租房合同有没有坑"
python3 skills/triage/scripts/triage.py --list-categories
```

运行测试和分诊回归检查：

```bash
python3 -m unittest discover -s tests
python3 benchmark/eval_rules.py
```

> ⚠️ 分诊回归检查（每个细类的示例 + 64 条人工标注的请求，目前全部通过）是和关键词一起写的，只能当回归检查，不代表真实流量下的准确率。最有价值的贡献是真实的“分错科”例子。

## Benchmark：质量与成本

`benchmark/run_bench.py` 用 30 道自动评分的题（简单 / 中等 / 困难各 10 道），分别测“固定用某个模型”和“按分诊路由”的表现，任何厂商都能测，并和“全部用最强模型”对比通过率与成本。用法见 [`benchmark/README.md`](benchmark/README.md)，真实跑分结果即将公布。

## 路线图

- [x] 规则引擎、可解释挂号单、成本预估
- [x] 导诊台固定用一个便宜模型并作为主会话；每个执行 agent 有精确型号 + 思考深度；逐级转诊
- [x] 基于公开使用研究的 120 类分类表；后台微调；健康、法律、金融设最低配置
- [x] 第三方厂商：DeepSeek、Kimi、智谱 GLM、小米 MiMo
- [x] Benchmark 框架：30 道自动评分题、按厂商分策略、离线 mock 模式
- [ ] **Benchmark 结果**：公布真实跑分并出图；按大类补题
- [ ] 验证各厂商是否支持 Claude Code 的 effort 设置
- [ ] **从反馈中学习**：记录改挂、导诊台复核和转诊，自动建议调整关键词和默认配置
- [ ] **混合路由**：同一会话里不同类别用不同厂商；接入 GPT、Gemini、本地模型

## 参与贡献

欢迎 issue 和 PR，尤其是“分错科”的例子：把提示词和你期望的类别加进 `benchmark/triage-cases.jsonl`，调整 `taxonomy.json` 里的关键词，然后运行：

```bash
python3 skills/triage/scripts/gen_agents.py   # 改了型号、档位或工具权限时
python3 skills/triage/scripts/gen_docs.py     # 刷新 docs/taxonomy.md
python3 -m unittest discover -s tests
```

---

如果 claude-triage 帮你省了 token，或者比你自己选得更准，点个 ⭐ 能让更多 Claude Code 用户看到它。

## 许可证

[MIT](LICENSE)
