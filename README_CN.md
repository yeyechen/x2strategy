<div align="center">

<img src="assets/alagent_logo.png" alt="ALAGENT Logo" width="120">

# X2Strategy

**任意研究输入 → 策略规格 → 可执行代码 → 回测 → 诊断报告**

---

*将量化金融研究——论文、草稿、研报或策略想法——自动转化为经过验证的可执行交易策略。*

</div>

## 亮点

- **🔬 多格式输入** — PDF 论文、Markdown 草稿、DOCX 研报、纯文本。自动检测格式。
UPSA 示例位于 `examples/upsa/`。可复现实验输入已放在 `examples/upsa/input/`，生成的实现文件为 `examples/upsa/universal_portfolio_shrinkage_approximation.py`。
- **🧠 5 层 LLM 提取** — 多策略检测 → 指标提取 → 信号逻辑 → 执行计划 → 风控规则。
- **✅ 可验证的代码生成** — AST 语法校验 + Backtrader 结构检查 + 指标注册表核查，而非"生成然后祈祷"。
- **📊 自动化回测** — 自动执行回测、提取指标，并与论文报告的结果进行对照诊断。
- **🤖 Agent 原生** — 作为 [Agent Skill](https://agentskills.io/) (`/x2strategy`) 运行在 VS Code Copilot、Claude Code 或任何兼容的 Agent 平台。
- **💰 每篇论文约 ¥0.7** — 推荐使用 DeepSeek，支持任意 [LiteLLM 兼容模型](https://docs.litellm.ai/docs/providers)。

## 工作原理

```
                        ┌──────────────────────────────────────────────────────────────┐
                        │                    X2Strategy                              │
                        │                                                              │
  PDF / MD / DOCX / TXT │   ┌─────────┐   ┌───────────┐   ┌──────────┐   ┌─────────┐ │
  ─────────────────────►│   │  解析    ├──►│  提取      ├──►│  生成    ├──►│  回测   │ │
                        │   │(parser) │   │(L0 → L4)  │   │ (code)   │   │+ 诊断   ││
                        │   └─────────┘   └───────────┘   └──────────┘   └─────────┘ │
                        │        ▼              ▼               ▼             ▼        │
                        │   PaperContent   StrategySpec   Backtrader.py   Report.md   │
                        └──────────────────────────────────────────────────────────────┘
```

| 阶段 | 输入 | 输出 | 说明 |
|:------|:-----|:-----|:-----|
| **解析** | 任意文档 | `PaperContent` | 格式自适应提取（PyMuPDF / 直读 / python-docx） |
| **提取** | PaperContent | `StrategySpec[]` | 5 层 LLM：检测策略 → 提取指标、逻辑、执行、风控 |
| **生成** | StrategySpec | `strategy.py` | 数据模块 → 信号模块 → 回测模块 → 整合 |
| **验证** | strategy.py | 通过 / 失败 | AST 语法 + Backtrader 结构 + 指标存在性检查 |
| **回测** | strategy.py | 绩效指标 | 子进程执行，超时控制，指标提取 |
| **诊断** | 绩效指标 | `report.md` | 与论文报告结果对比，标记偏差 |

## 快速开始

### 作为 Agent Skill

[Agent Skills](https://agentskills.io/) 是开放标准。Clone 到 Agent 的 skill 目录后，Agent 自动发现 `SKILL.md` 并注册 `/x2strategy` 斜杠命令。

#### OpenClaw用户 / 安装到OpenClaw

OpenClaw 用户可以直接从 ClawHub 安装：

```bash
openclaw skills install patrick-lew/x2strategy
```

也可以使用 ClawHub CLI：

```bash
npx clawhub@latest install x2strategy
```

如果需要远程或引导式安装，可以将下面的提示词粘贴到 OpenClaw：

```text
Install the skill "X2strategy" (patrick-lew/x2strategy) from ClawHub.
Skill page: https://clawhub.ai/patrick-lew/x2strategy
Keep the work scoped to this skill only.
After install, inspect the skill metadata and help me finish setup.
Use only the metadata you can verify from ClawHub; do not invent missing requirements.
Ask before making any broader environment changes.
```

#### Claude Code/Codex/Copilot 用户 可以将技能直接 clone 到本地 Agent 的技能目录：

<table>
<tr><td><b>GitHub Copilot</b></td><td>

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git ~/.copilot/skills/x2strategy
```

</td></tr>
<tr><td><b>Claude Code</b></td><td>

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git ~/.claude/skills/x2strategy
```

</td></tr>
<tr><td><b>项目级共享</b></td><td>

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git .github/skills/x2strategy
```

</td></tr>
</table>

然后安装依赖。安装成功后，Agent 在初始化时可能会自动完成，但手动安装仍是最稳妥的方式：

```bash
cd ~/.copilot/skills/x2strategy   # 或你 clone 到的路径
# 如果没有安装uv，请执行 pip install uv
uv sync --all-extras
```

<details>
<summary>手动安装依赖的可选方式</summary>

```bash
# Skill 运行所需的最小依赖
uv sync --extra agent --extra codegen

# 增加 DOCX 解析支持
uv sync --extra agent --extra codegen --extra docx

# 使用 pip 替代 uv
python -m venv .venv && source .venv/bin/activate
pip install -e ".[codegen,agent,docx,dev]"
```

</details>

> [!IMPORTANT]
> 目录名**必须**为 `x2strategy`（与 `SKILL.md` 中的 `name` 字段一致）。安装后，在对话中输入 `/x2strategy` 即可调用，或 Agent 在相关上下文中自动激活。

### Skill 快速上手

```bash
# 1. 配置 Skill 工作目录
cp .env.example .env          # 填入 API Key（推荐 DEEPSEEK_API_KEY）

# 2. 在 Agent 中启动 Skill
# /x2strategy
```

然后直接用自然语言提出任务，例如：

> *"分析这篇论文并实现其中的主要策略"* + 附上 PDF 文件

Skill 会自动完成解析、提取、代码生成、验证、回测和诊断。
在开始提取前，它应先询问你是否要补充自定义 instruction、实现约束、已知 pitfalls，或额外的参考文件。
在完成提取并确定目标 strategy/plan 之后，它必须先读取 [references/extraction_quality.md](references/extraction_quality.md)，然后才能进入 repair、代码生成或确定性本地实现。
当你需要从搜索结果里选论文、补充修复阶段的 pitfall/clarification、确认推断默认值，或处理 compare/repair 暴露出的 `needs_human_review` 问题时，也应继续使用同样的交互式流程。
在代码生成和诊断之后，它也应继续给出交互式的下一步动作菜单，而不是默认流程已经结束。

默认生成文件应写入 `PAPER2SPEC_LIBRARY_PATH/<slug>/`，例如 `content.json`、`spec.json`、生成的实现文件以及 `results/metrics.json`。如果引用了已有的 Copilot、VS Code 或其他 Agent 日志路径，但该路径为空或缺少必要文件，应从原始论文、说明文件和数据重新生成，而不是依赖日志摘要。

Spec2Code 输出应在适用时至少包含 Sharpe ratio、maximum drawdown、total return，以及 return value / final portfolio value。

这里的“自定义 instruction”就是你额外告诉 skill 的提取要求，不是代码命令。

- 你可以指定它必须保留哪些规则或假设。
- 你可以说明哪些常见误读或坑要避免。
- 你也可以补充论文里没写清、但你已经确认过的背景信息。

例如：
"只实现文中的主策略，不要把附录里的扩展版本一起做进去。"
"如果权重计算有歧义，优先按 equal weight 处理。"
"这篇论文里的 rebalance frequency 以月频为准，不要猜成周频。"

如果提取、对比或修复阶段留下了 `needs_human_review` 问题，它应在生成代码前通过交互式对话继续确认。在 VS Code Copilot 中，如果 `vscode_askQuestions` 可用，就应优先使用该对话框，而不是只用普通文本描述问题。如果验证或诊断之后仍有未决判断，也应再次交互确认，而不是静默重试或直接结束。

## 支持的输入格式

| 格式 | 扩展名 | 解析器 | 说明 |
|:-----|:-------|:-------|:-----|
| **PDF** | `.pdf` | PyMuPDF → Mode A（直接）或 Mode B（FAISS） | 完整支持，覆盖 95%+ 论文 |
| **Markdown** | `.md` `.markdown` | 直接文本读取 | 适合策略草稿、笔记 |
| **Word** | `.docx` | python-docx（`uv sync --extra docx`） | 适合内部研究报告 |
| **纯文本** | `.txt` | 直接读取 | 原始策略描述 |

格式根据文件扩展名自动检测，无需额外配置。

## 示例

[`examples/`](examples/) 目录中的主示例已切换为 UPSA paper2code，由 Copilot GPT-5.4 生成：

| 论文 | 检测到的策略 | 产物 |
|:-----|:------------|:-----|
| **Universal Portfolio Shrinkage Approximation** (Kelly, Malamud, Pourmohammadi & Trojani 2025) | 1 — UPSA ridge-ensemble portfolio | content + spec + paper2code contract |

可复现实验输入已放在 `examples/input/`，生成的实现文件为 `examples/universal_portfolio_shrinkage_approximation.py`。

<details>
<summary>输出目录结构示例</summary>

```
examples/upsa/
├── README.md
├── upsa_content.json
├── upsa_content.md
├── upsa_spec.json
├── upsa_spec.md
├── upsa_operator_pitfall_context.md
├── upsa_review_and_diagnosis.md
├── upsa_metadata.json
├── universal_portfolio_shrinkage_approximation.py
└── input/
    ├── P10_Kelly_Malamud_Pourmohammadi_Trojani_2025_NBER.pdf
    ├── sample_instruction.md
    ├── jkp_factors_wide.csv
    ├── jkp_factors_long.csv
    └── upsa_weights.csv
```

</details>

⚠️ 不是所有由 skill 提取出的策略都适合直接连接 broker 做 paper trading。很多研究策略的输入本身就是因子收益、合成组合、排序面板或其他不可直接交易的数据；也有一些策略本质上是组合构造、SDF 或资产定价流程，而不是实时下单规则。开源 skill 侧重有依据的提取、代码生成、验证和研究回测。若策略和数据契约适合实盘/模拟盘，ALAGENT 网站可以生成连接 broker 的策略。

## 项目结构

```
x2strategy/
├── paper2spec/                 # 阶段 1：文档 → 结构化规格
│   ├── config.py               #   环境变量与 library 路径配置
│   ├── parser.py               #   多格式解析器（PDF / MD / DOCX / TXT）
│   ├── pdf_utils.py            #   PDF 提取辅助函数
│   ├── extractor.py            #   PaperContent → ExtractionResult (L0-L4)
│   ├── models.py               #   数据模型（PaperContent, StrategySpec 等）
│   ├── prompts.py              #   5 层提取 prompt 模板
│   ├── llm.py                  #   LiteLLM 统一接口
│   ├── render.py               #   JSON → Markdown 渲染
│   └── search.py               #   arXiv + SSRN 论文搜索
│
├── spec2code/                  # 阶段 2：规格 → 代码 → 回测 → 诊断
│   ├── validator.py            #   AST + 结构 + 指标验证
│   ├── config.py               #   代码生成与回测配置
│   └── models.py               #   CodeModules, ValidationResult
│
├── references/                 # 经过验证的领域知识（非 LLM 幻觉）
│   ├── backtrader_patterns.md  #   源码验证的 Backtrader 模式
│   ├── indicator_cookbook.md    #   官方指标参数参考（来自 bt 源码）
│   ├── data_sources.md         #   yfinance + akshare API 文档
│   ├── paper2spec.md           #   Paper2Spec 深入指南
│   ├── spec2code.md            #   Spec2Code 深入指南
│   └── skill-internals.md      #   Skill 配置与环境细节
│
├── scripts/                    # CLI 入口
│   ├── analyze.py              #   完整 paper2spec 管线
│   ├── extract.py              #   从解析内容提取规格
│   ├── parse.py                #   将文档解析为 PaperContent
│   ├── search.py               #   搜索论文
│   ├── generate_schemas.py     #   生成 JSON Schema
│   ├── run_full_tests.sh       #   测试运行辅助脚本
│   └── validate_strategy.py    #   独立策略验证
├── schemas/                    # JSON Schema 定义
├── examples/                   # 预生成的参考输出
├── tests/                      # 180+ 单元测试和集成测试
├── SKILL.md                    # Agent Skill 入口
└── pyproject.toml              # 项目配置与依赖
```

## 核心设计决策

### 为什么用 Reference Docs 而非 Prompts？

LLM 经常在 Backtrader API 细节上产生幻觉：
- SMA 默认 `period` 是 `30`，而非 `20`
- RSI 内部使用 `SmoothedMovingAverage`，而非 EMA
- BollingerBands 的 line 名是 `.top/.mid/.bot`，而非 `.upper/.lower`

我们的 `references/` 目录包含**经过源码验证**的知识。Agent 按需读取这些文档，而不是依赖不稳定的 API 记忆。

### 为什么用结构化规格作为中间产物？

直接从论文生成代码会丢失可审计性。`StrategySpec` 中间层的价值：
- **可审计** — 人工可以在代码生成前审阅规格
- **可复用** — 同一规格可以适配不同回测引擎
- **可测试** — 规格提取和代码生成可以独立验证

### 有依据的提取与修复

`paper2spec` 支持在提取阶段加入 instruction 或 clarification 上下文。
当论文把关键公式放在附录、缺少常数、仓位分配表述含糊，或你希望自定义提取要求时，应该开启这类 grounding。

- 当输入存在歧义时，skill 应在提取前主动询问你是否要补充 instruction 文件、clarification 或参考资料。
- [references/extraction_quality.md](references/extraction_quality.md) 是人工审计与修复的基准参考。
- 如果要做 repair-style RAG，只能使用从 [paper2spec/resources/operator_pitfall_index.md](paper2spec/resources/operator_pitfall_index.md) 检索出的相关 pitfalls，不能把整个索引直接交给模型自由挑选。
- 最终依据仍然是论文、selected plan、用户澄清信息和已确认的自定义要求；pitfall index 只是审计辅助材料。

## 配置

| 环境变量 | 默认值 | 说明 |
|:---------|:-------|:-----|
| `PAPER2SPEC_LIBRARY_PATH` | `./library` | 输出根目录 |
| `PAPER2SPEC_MODEL` | `openai/gpt-4o-mini` | LLM 模型（[LiteLLM 格式](https://docs.litellm.ai/docs/providers)） |
| `SPEC2CODE_BACKTEST_TIMEOUT` | `300` | 回测超时（秒） |
| `DEEPSEEK_API_KEY` | — | DeepSeek（推荐：最佳性价比） |
| `OPENROUTER_API_KEY` | — | OpenRouter（一个 Key 访问所有模型） |
| `OPENAI_API_KEY` | — | OpenAI 直连 |

所有脚本支持 `--model` 参数覆盖 `PAPER2SPEC_MODEL`。

## 文档

| 资源 | 说明 |
|:-----|:-----|
| [SKILL.md](SKILL.md) | Agent Skill 指令——配置、单一 workflow、HITL review、输出路径 |
| [references/paper2spec.md](references/paper2spec.md) | Paper → Spec 提取深入指南 |
| [references/spec2code.md](references/spec2code.md) | Spec → Code 生成深入指南 |
| [references/backtrader_patterns.md](references/backtrader_patterns.md) | 源码验证的 Backtrader 模式 |
| [references/indicator_cookbook.md](references/indicator_cookbook.md) | 官方指标参数参考 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 管线架构 |

## 测试

```bash
pytest tests/ -v              # 180+ 确定性测试
pytest tests/ -v --run-real   # + 真实 API 测试（需要 DEEPSEEK_API_KEY）
```

## 参与贡献

欢迎贡献！请参阅[架构文档](docs/ARCHITECTURE.md)了解代码库。

```bash
git clone https://github.com/ALAGENT-HKU/x2strategy.git && cd x2strategy
uv sync --all-extras
cp .env.example .env  # 填入 API Key
pytest tests/ -v      # 验证所有测试通过
```

## 许可证

[Apache-2.0](LICENSE) · 由 **[ALAGENT AI 优彦智能](http://home.alagent.cloud)** 构建 — 可验证、可信赖的金融 AI

---

<div align="center">

## 💬 加入社区

<a href="https://home.alagent.cloud">🌐 官网</a> &nbsp;·&nbsp; <a href="https://github.com/ALAGENT-HKU">GitHub</a> &nbsp;·&nbsp; <a href="mailto:contact@alagent.cloud">📧 contact@alagent.cloud</a>

<br>

<img src="assets/wechat_QR.jpg" alt="微信交流群二维码" width="260">

**扫码加入 ALAGENT 开源交流群**

</div>
