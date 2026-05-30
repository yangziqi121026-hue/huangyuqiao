# TradingAgents 接入研究报告

> 研究对象：[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents)
> 输出日期：2026-05-30
> 性质：**研究报告**，不改代码、不接 live、不接真实下单、不覆盖现有 5/2 旧版交易系统、不与 D3 只读旁路页面合并。

---

## 一、项目概览

TauricResearch/TradingAgents 是一个 **基于 LangGraph 的多智能体金融分析框架**，自我定位是 "mirrors the dynamics of real-world trading firms"。

- 协议：**Apache-2.0**
- 安装：`pip install .`（也提供 `Dockerfile` + `docker-compose.yml`）
- 入口：
  - CLI：`tradingagents` 或 `python -m cli.main`
  - SDK：`from tradingagents.graph.trading_graph import TradingAgentsGraph`
- 调用形态：
  ```python
  ta = TradingAgentsGraph(debug=True, config=config)
  _, decision = ta.propagate("NVDA", "2024-05-10")
  print(decision)
  ```
- 输入：**Ticker + 日期字符串**；输出：**文本型的决策建议**（BUY / SELL / HOLD + 各 Agent 报告）。
- **明确声明**：
  > "designed for research purposes. ... not intended as financial, investment, or trading advice."
- **不内置任何真实券商连接**，也没有 live order execution。订单只发送到 "simulated exchange"（即 paper trading / 回放）。

> 结论先放在前面：它**本身就是一个旁路型 AI 分析框架**，不是自动交易系统。从安全和合规角度，它适合作为"分析模块"被接入，不适合也无法直接拿来下单。

---

## 二、项目结构

```
TradingAgents/
├── assets/
├── cli/                       # CLI 入口
├── scripts/
├── tests/
├── tradingagents/             # 主 Python 包
│   ├── agents/                # 所有 Agent 实现（analysts / researchers / trader / risk）
│   ├── dataflows/             # 数据源封装（Alpha Vantage / yfinance / Reddit / StockTwits / 新闻 等）
│   ├── graph/                 # LangGraph 协调层（trading_graph.py 是主入口）
│   ├── llm_clients/           # 多家 LLM 客户端封装
│   └── default_config.py      # 默认配置
├── .env.example
├── .env.enterprise.example
├── Dockerfile
├── docker-compose.yml
├── main.py                    # 示例入口
├── pyproject.toml
├── requirements.txt
└── LICENSE                    # Apache-2.0
```

关键点：

- 整套系统的**协调中枢**在 `tradingagents/graph/trading_graph.py`，用 LangGraph 把所有 Agent 串成一个有向图。
- **数据层**只在 `dataflows/` 里，Agent 不直接抓数据，而是通过 dataflows 暴露的 "tools" 间接调用。
- `default_config.py` 控制：使用哪个 LLM、debate 轮数、并发数、缓存目录、benchmark 等。

---

## 三、Agent 角色清单

| 阶段 | Agent | 职责 |
|------|-------|------|
| 分析师团队 | Fundamentals Analyst | 财报、估值、内在价值、红旗信号 |
| 分析师团队 | Sentiment Analyst | StockTwits / Reddit / 社媒情绪汇总 |
| 分析师团队 | News Analyst | 宏观与全球新闻、事件影响 |
| 分析师团队 | Technical Analyst | MACD / RSI 等技术指标 |
| 研究员团队 | Bull Researcher | 多方观点，挑战分析师结论 |
| 研究员团队 | Bear Researcher | 空方观点，挑战分析师结论 |
| 决策层 | Trader | 综合 analyst+researcher 报告，给出交易计划 |
| 风控层 | Risk Manager / Portfolio Manager | 评估组合风险，批准 / 否决交易方案 |

辩论轮数由 `max_debate_rounds` 和 `max_risk_discuss_rounds` 控制（默认 1）。

> 角色设计上**与我们本地 `tradingagents_multi_market_clone/src/agents/` 已有的 8 个 Agent 完全对齐**（fundamental / news / sentiment / technical / bull / bear / research_manager / trader / risk_manager）——也就是说官方框架的设计哲学我们已经复刻并落到 A 股。

---

## 四、需要的 API Key

> 来源：`.env.example` 与 `default_config.py`。**不需要全部配齐**，按 `llm_provider` 与 `data_vendors` 选择即可。

**LLM 相关（任选其一）：**

- `OPENAI_API_KEY`（GPT 系列）
- `ANTHROPIC_API_KEY`（Claude）
- `GOOGLE_API_KEY`（Gemini）
- `XAI_API_KEY`（Grok）
- `DEEPSEEK_API_KEY`
- `DASHSCOPE_API_KEY` / `DASHSCOPE_CN_API_KEY`（Qwen 国际 / 国内）
- `ZHIPU_API_KEY` / `ZHIPU_CN_API_KEY`（GLM 国际 / 国内）
- `MINIMAX_API_KEY` / `MINIMAX_CN_API_KEY`
- `OPENROUTER_API_KEY`
- `OLLAMA_BASE_URL`（本地模型）

**数据相关：**

- `ALPHA_VANTAGE_API_KEY`（美股财务、宏观）
- 默认还会用到 yfinance / Finnhub（不强制 Key，但有速率限制）
- Reddit / StockTwits / Google News（情绪、新闻）

**系统相关（可选）：**

- `TRADINGAGENTS_MEMORY_LOG_PATH`
- `TRADINGAGENTS_CACHE_DIR`

> ⚠️ **它完全不需要任何券商 API Key**（不需要 IBKR / 富途 / OKX / Binance / 老虎 等）。这是它**作为旁路分析模块的天然优势**——它从设计上就不能下单。

---

## 五、支持的模型

按 `default_config.py`：

- `deep_think_llm`（深思模型，默认 `gpt-5.4`）
- `quick_think_llm`（轻量模型，默认 `gpt-5.4-mini`）

支持的 provider：

- OpenAI（GPT 5.x）
- Anthropic（Claude 4.x）
- Google（Gemini 3.x）
- xAI（Grok 4.x）
- DeepSeek
- Qwen（DashScope 国际 / 国内）
- GLM（智谱 国际 / 国内）
- MiniMax
- OpenRouter
- Ollama（本地模型）
- Azure OpenAI（企业版）

每个 provider 还可以传 `*_reasoning_effort` / `*_thinking_level` 参数控制推理深度。

> 对接策略建议：**优先用 OpenAI 兼容协议**（DeepSeek / Qwen / 智谱大多兼容），可以一套客户端跑多家，跟我们本地 clone 的 `llm_client.py` 思路一致。

---

## 六、它输入什么市场数据

`dataflows/` 模块当前确认存在的文件：`alpha_vantage*.py`、`y_finance.py`、`yfinance_news.py`、`reddit.py`、`stocktwits.py`、`stockstats_utils.py`（无 `akshare.py` / `tushare.py` / 东方财富相关文件）。

| 类别 | 数据源 |
|------|--------|
| 行情 / K线 | yfinance、Alpha Vantage |
| 财务 | yfinance、Finnhub、Alpha Vantage |
| 全球新闻 | Google News、自带宏观主题列表 |
| 社媒情绪 | Reddit、StockTwits |
| 技术指标 | MACD、RSI 等（`stockstats_utils.py` 内部计算） |
| Benchmark | 通过 `benchmark_map` 按交易所后缀映射 |

数据源**是可换的**，由 `default_config.py` 的 `data_vendors` dict 控制（每一类都能独立换源）：

```python
"data_vendors": {
    "core_stock_apis": "yfinance",
    "technical_indicators": "yfinance",
    "fundamental_data": "yfinance",
    "news_data": "yfinance",
},
```

这意味着**理论上**可以新增一个 `akshare` provider 注册进 `data_vendors`，但**本次报告范围内不做此事**——我们的 A 股工作交给独立的 `tradingagents_multi_market_clone/` 和 `ashare_research_agent/`，不去 fork 官方包。

默认的全球新闻主题（`global_news_queries`）也是**全美式宏观**：

```python
[
    "Federal Reserve interest rates inflation",
    "S&P 500 earnings GDP economic outlook",
    "geopolitical risk trade war sanctions",
    "ECB Bank of England BOJ central bank policy",
    "oil commodities supply chain energy",
]
```

`benchmark_map` 支持的市场后缀：

| 后缀 | 基准 |
|------|------|
| `.NS` / `.BO` | 印度 NIFTY / SENSEX |
| `.T` | 日经 225 |
| `.HK` | 恒生指数 |
| `.L` | FTSE 100 |
| `.TO` | 加拿大 TSX |
| `.AX` | 澳洲 ASX 200 |
| 默认（无后缀） | SPY |

> ⚠️ **完全没有 A 股**：
> - 没有 AKShare / Tushare / 东方财富
> - 没有北向资金、龙虎榜、同花顺、Wind
> - `benchmark_map` 里**没有** `.SS` / `.SZ`（沪/深），也就是说哪怕用 yfinance 的 `600519.SS` 强抓，它也找不到沪深 300 / 创业板指作为对标
> - 默认新闻主题里**没有一条**与中国市场相关
>
> 如果直接拿来分析 A 股，会得到 yfinance 上的 `600519.SS` 等**滞后、缺主力资金、缺政策面、无北向、benchmark 缺失**的数据，**不适合中国市场实战分析**。

---

## 七、它输出什么"交易建议"

主入口：

```python
state, decision = ta.propagate(ticker, date)
```

- `decision` 是**自然语言 + 离散信号**（BUY / SELL / HOLD），是 Trader Agent + Risk Manager 协商后的文本结论。
- `state` 是完整的中间状态，包含每个 analyst / researcher 的报告（Markdown 文本）。
- **存在结构化输出（Pydantic schemas）**，见 `tradingagents/agents/schemas.py`：

  | Schema | 字段 |
  |--------|------|
  | `ResearchPlan`（Research Manager） | `recommendation: PortfolioRating(Buy/Overweight/Hold/Underweight/Sell)`、`rationale: str`、`strategic_actions: str` |
  | `TraderProposal`（Trader） | `action: TraderAction(Buy/Hold/Sell)`、`reasoning: str`、`entry_price: Optional[float]`、`stop_loss: Optional[float]`、`position_sizing: Optional[str]` |
  | `PortfolioDecision`（Portfolio Manager） | `rating: PortfolioRating`、`executive_summary: str`、`investment_thesis: str`、`price_target: Optional[float]`、`time_horizon: Optional[str]` |

  ⚠️ **这正是必须警惕的地方**：官方框架原生就会吐出 `entry_price / stop_loss / position_sizing / price_target` 这样的具体价位与仓位字段，如果直接展示给用户，**词面上会接近"投顾意见"**。在我们的旁路接入里，这些字段要么**不渲染**，要么**降级为"参考价位 ± 区间，仅作研究"**，绝不允许出现"建议入场价 X 元、止损 Y 元、仓位 Z%"这种确定性表述。

- 没有自动下单，没有 webhook，没有 broker call（schema 字段是文本/数字，不会被任何代码送去执行）。
- 有 `reflect_and_remember(returns)` 用于**事后**学习真实收益（写入 memory log），但**它本身不会去查真实收益**——需要外部喂。

> 这意味着它的输出**仍然适合作为只读"AI 研究意见"展示**，不会产生副作用；但**渲染层必须自己屏蔽 entry_price / stop_loss / position_sizing 这三个字段**，或将其口径软化为"参考观察价位"。

---

## 八、是否能只作为"AI 分析模块"旁路接入

**结论：可以，且只能这样接。**

它的设计就是：

1. **无状态调用**：`propagate(ticker, date)` 是纯函数式调用，输入 ticker，输出报告，没有持久副作用（除了缓存和 memory log，都是本地文件）。
2. **没有 broker 接口**：源码里没有任何下单、撤单、查持仓的代码路径。
3. **没有 live 订阅**：没有 websocket、没有实时推送、不会被动触发。

旁路接入的标准姿势：

```
┌──────────────────────────────┐
│ 我们的 5/2 旧版交易系统       │  ← 完全不动
│ （trading-platform / backend）│
└─────────────┬────────────────┘
              │ 不连接
              ▼
┌──────────────────────────────┐
│ 旁路 AI 分析进程（独立）       │
│  - 自己的 venv                │
│  - 自己的 .env                │
│  - 自己的端口                 │
│  - 只读 ticker，不读持仓       │
│  - 只输出 Markdown / JSON     │
└──────────────────────────────┘
              │ 输出
              ▼
        Markdown 报告 / SQLite 历史
```

**严禁的接入方式：**

- ❌ 把 TradingAgents 的 decision 直接喂给我们 backend 的下单接口。
- ❌ 让 TradingAgents 订阅我们的 live 行情流。
- ❌ 把 TradingAgents 的进程嵌进 trading-platform 服务里共享端口 / 共享 DB。
- ❌ 复用我们的券商 API Key。
- ❌ 改 App.jsx 引用它的输出做自动操作。

---

## 九、和"D3 只读旁路页面"如何结合

**前提：D3 只读旁路页面是只读的，必须继续保持只读。**

可行的最轻量结合方式（仅做研究，**本次不实施**）：

1. AI 分析模块作为**独立后台脚本**跑（CLI 或定时任务），把每次输出的报告写到一个单独目录，比如 `ai_reports/{symbol}/{date}.md`。
2. D3 只读页面**不调用** AI 模块进程，只**读取**那个目录的 Markdown / JSON 文件，渲染一栏"AI 研究意见"。
3. 该栏明确标注"研究观点 / Not investment advice"，**不允许出现"下单"、"一键执行"、"跟单"按钮**。

要点：

- D3 页面和 AI 模块之间**只走文件 / 只读 API**，单向（AI → 页面）。
- AI 模块**不读取** D3 页面任何用户态、持仓、订单数据。
- 两个进程互不感知彼此存活与否，AI 挂掉不影响 D3。

> ⚠️ 但根据用户的明确禁令"不要把它和 D3 旁路页合并"，**本次只做研究备案，不实施任何 D3 页面的改动**。本节仅作为后续可选方案存档。

---

## 十、和我们 5/2 旧版交易系统的适配评估

| 维度 | TauricResearch/TradingAgents | 我们 5/2 旧版交易系统 | 适配结论 |
|------|------------------------------|--------------------|----------|
| 主要市场 | 美股为主 | 我们目前主线（按用户描述）| ⚠️ A 股市场需要自建 provider，**不能直接复用** |
| 数据源 | yfinance / Alpha Vantage / Reddit / StockTwits | 用户场景需要 AKShare | ⚠️ 需要替换 / 增配 |
| 下单 | **无** | 已有 | ✅ 互不冲突，旁路即可 |
| Live 行情 | **无** | 可能有 | ✅ 互不冲突，旁路即可 |
| LLM | 多家可选 | / | ✅ 独立 .env |
| 部署 | Docker / pip | 独立服务 | ✅ 独立进程 |
| 安全风险 | 无 broker key | / | ✅ 无新增攻击面 |

适配判断：

- **能旁路并存** ✅：作为独立的"AI 研究意见生成器"，不进入下单链路。
- **不能直接覆盖** ❌：它对 A 股、港股的数据支持为零，直接用会给出错误结论。
- **不能合并代码库** ❌：它依赖 LangGraph、特定版本的多家 SDK，会污染现有 backend 依赖树。

---

## 十一、可以借鉴的功能

> 这些设计可以**借鉴思想，落到我们自己的 A 股 Agent**（即 `tradingagents_multi_market_clone`），不需要 import 它的代码。

1. **多 Agent + 多空辩论**：Analyst → Bull/Bear → Trader → Risk Manager 的 pipeline 是好抽象。我们本地 clone 已经落了这套结构。
2. **deep_think_llm vs quick_think_llm 分层**：复杂决策用强模型，工具调用用快模型，省 token。
3. **dataflows 与 agents 解耦**：Agent 只看统一字段，数据源可换。我们的 `BaseDataProvider` 已经是这套。
4. **`reflect_and_remember(returns)` 记忆机制**：每次决策事后写回真实收益，用于下次决策时检索类似案例，是研究价值高的部分。
5. **debate 轮数可配置**：在快速调试 / 深度研究之间切换。
6. **benchmark_map 按交易所映射**：A 股可以默认对标沪深 300、创业板指等。
7. **checkpoint 与 memory log 落盘**：长跑任务可恢复。
8. **多 LLM provider 抽象**：一套 client 跑多家，方便国内外切换。

---

## 十二、不能直接接入的功能

> 这些**禁止照搬**，要么是合规问题，要么是技术不适配。

| 不能照搬 | 原因 |
|---------|------|
| Trader Agent 的"下单"语义 | 它说的"下单"是模拟，但**词面**会误导，必须改成"建议" |
| Risk Manager 的"approve transaction" | 同上，必须改成"风险等级标注"，不得视为指令 |
| 它的 dataflows（yfinance / Alpha Vantage / Reddit / StockTwits） | 对 A 股**几乎没有覆盖**，会误导 |
| 它对 ticker 的解析（NVDA / AAPL 风格） | A 股是 6 位数字，符号体系不同 |
| Reddit / StockTwits 情绪 | 国内监管 + 数据可得性问题 |
| benchmark 默认（SPX / NDX） | 必须改为沪深 300 / 创业板指 |
| 直接把 decision 接到 webhook / broker | **绝对禁止** |
| live 订阅 | **绝对禁止** |
| copy trading | **绝对禁止** |
| 复用我们生产的 API Key | **绝对禁止** |

---

## 十三、风险点专项

| 风险 | 严重性 | 我们的对策（本次只做规约） |
|------|--------|----------------------------|
| 自动交易（auto trading） | 🔴 高 | AI 模块**完全不持有**任何下单接口；不引用 backend；不调用 broker SDK |
| Copy trading / 跟单 | 🔴 高 | AI 输出只写文件，不发 webhook；UI 不允许"一键跟单"按钮 |
| API Key 泄漏 | 🟡 中 | AI 模块用独立 `.env`，不读取生产 `.env`；只放 LLM 与公开数据源 Key；不放券商 Key |
| Live Trading 误启 | 🔴 高 | 入口函数禁用任何 "live" / "realtime" / "websocket" 参数；只接受历史日期 |
| LLM 幻觉给出错误价位 | 🟡 中 | 报告必须标注"研究观点，非投资建议"；不输出"必须买入 / 必须卖出"；冲突时必须提示冲突 |
| 数据滞后 / 缺失 | 🟡 中 | 报告必须打印**数据来源 + 抓取时间**；缺数据必须标注"不足以判断" |
| 用户误以为是实盘策略 | 🟡 中 | 报告头部固定免责声明；不显示"模拟净值曲线"等暗示盈利的可视化 |

---

## 十四、A 股投研 Agent —— 项目结构与最小可运行版本计划

> 用户要求：先**只输出项目结构 + MVP 计划**，不写完整系统代码。
>
> 已有事实：用户本地 `tradingagents_multi_market_clone/` 目录其实**已经初步实现**了这套架构（含 `src/agents`、`src/data_providers`、`workflow.py`、`report_generator.py`、`pages/01_📊_Dashboard.py`、`requirements.txt`、`pool.txt`、`reports/`、`data/`）。
>
> 因此本节定位为：**确认 MVP 范围 + 标注需要补齐的最小项**，不重新设计目录。

### 14.1 目标定位（再强调）

- ✅ 输入：A 股代码（6 位数字）
- ✅ 输出：完整 Markdown 投研报告
- ✅ 数据：AKShare（行情、财务、北向、资金流、新闻）
- ❌ 不接美股、不接 OKX、不接券商
- ❌ 不自动下单
- ❌ 不出"必须买入 / 必须卖出"指令
- ✅ 报告必须含**数据来源 + 抓取时间**
- ✅ 基本面 vs 技术面冲突时**显式标注冲突**
- ✅ 数据缺失时**显式标注"不足以判断"**

### 14.2 推荐的项目结构（基于已有 clone 微调）

```
tradingagents_multi_market_clone/         # 已有，独立进程，不进 trading-platform
├── app.py                                # Streamlit 入口（已有）
├── pages/
│   ├── 01_📊_Dashboard.py                # 已有
│   └── 02_📄_Stock_Report.py             # 【MVP 新增】输入 ticker → 出报告
├── src/
│   ├── config.py                         # 已有
│   ├── llm_client.py                     # 已有；OpenAI 兼容协议
│   ├── workflow.py                       # 已有；编排 8 个 Agent
│   ├── report_generator.py               # 已有；Markdown 模板
│   ├── database.py                       # 已有；SQLite 历史
│   ├── holdings.py                       # 已有
│   ├── indicators.py                     # 已有；MA/MACD/RSI/支撑压力
│   ├── data_providers/
│   │   ├── base_provider.py              # 已有
│   │   ├── a_share_provider.py           # 已有；AKShare
│   │   ├── us_stock_provider.py          # 预留，本次不动
│   │   └── hk_stock_provider.py          # 预留，本次不动
│   └── agents/
│       ├── base_agent.py                 # 已有
│       ├── fundamental_analyst.py        # 已有
│       ├── technical_analyst.py          # 已有
│       ├── sentiment_analyst.py          # 已有
│       ├── news_analyst.py               # 已有
│       ├── bull_researcher.py            # 已有
│       ├── bear_researcher.py            # 已有
│       ├── research_manager.py           # 已有
│       ├── trader.py                     # 已有（注意：必须改语义为"建议"）
│       └── risk_manager.py               # 已有（注意：必须改语义为"风险等级"）
├── data/                                 # 已有；AKShare 缓存
├── reports/                              # 已有；输出 Markdown
├── requirements.txt                      # 已有
└── .env.example                          # 【需补】明确只放 LLM Key
```

### 14.3 MVP 范围（最小可运行）

只跑通一条主链路：

1. 输入 6 位 A 股代码 → `AShareProvider.fetch_market_data(symbol)` 返回统一 `market_data`。
2. `indicators.py` 计算 MA5/10/20/60、MACD、RSI、成交量变化、支撑压力。
3. 依次跑：基本面 → 新闻 → 情绪 → 技术 4 个 Analyst（mock 模式可跑通）。
4. 跑 Bull / Bear 1 轮辩论 → Research Manager 汇总。
5. Trader 输出**研究建议**（不是订单），Risk Manager 输出**风险等级**。
6. `report_generator.py` 渲染固定 Markdown 模板：
   - A. 公司基本面（主营 / 行业 / 市值 / PE / PB / ROE / 营收增长 / 净利润增长 / 现金流 / 负债）
   - B. 技术面（趋势 / MA / MACD / RSI / 量 / 支撑压力）
   - C. 资金面（主力流入流出 / 北向资金 / 成交额 / 换手率）
   - D. 消息面（近期新闻 / 政策 / 行业事件 / 风险事件）
   - E. 投资委员会结论（看多 / 看空 / 分歧点 / 风险等级 / 观察价位 / 不确定因素 / 最终结论：观察 / 谨慎关注 / 暂不参与 / 高风险）
7. 报告头部固定打印：
   ```
   > 数据来源：AKShare（行情、财务、资金流、新闻）
   > 抓取时间：YYYY-MM-DD HH:MM:SS（北京时间）
   > 本报告为研究观点，不构成投资建议，不保证收益，不执行真实交易。
   ```
8. 落 SQLite，留历史可查。

### 14.4 MVP 显式不做的事

- ❌ 不接美股 / 港股 provider（保留接口但不实现）
- ❌ 不接任何券商 / 不接 OKX
- ❌ 不接 live / websocket / 实时推送
- ❌ 不接 copy trading
- ❌ 不接收任何"下单触发"参数
- ❌ 不在报告里写"必须买入"、"必须卖出"、"建议满仓"
- ❌ 不与 trading-platform / backend / App.jsx / D3 只读页**合并代码或共享进程**
- ❌ 不把它 clone 到 trading-platform 仓库里

### 14.5 完成 MVP 还差什么（最小补齐项）

基于现有目录扫描，下面这些**在已有的 clone 中可能还需要确认或补齐**——本次只罗列，不动代码：

1. `.env.example` 是否明确**只列 LLM Key**、不列任何券商 Key？需确认。
2. `trader.py` 与 `risk_manager.py` 的 prompt 是否**已经把"order / transaction"改成"建议 / 风险等级"**？需确认。
3. `report_generator.py` 是否在报告**头部强制注入数据来源与抓取时间**？需确认。
4. 是否对**基本面 vs 技术面冲突**有显式分支？需确认。
5. 是否对**数据缺失**有显式 "不足以判断" 模板？需确认。
6. AKShare 抓取层是否带缓存与限频保护？需确认。
7. 是否禁掉了任何 `live=True` / `realtime=True` 参数？需确认。

> 上述 7 项是 MVP 验收前要逐一过的清单。**本次不修改代码**，留待后续单独任务。

---

## 十五、最终结论

1. **TauricResearch/TradingAgents 是研究型框架，不是交易系统**：天然适合作为旁路 AI 分析模块。
2. **但不适合直接接入我们的 5/2 旧版交易系统**：
   - 不能合并代码库
   - 不能复用券商 Key
   - 数据源对 A 股几乎无覆盖
3. **正确的姿势是借鉴架构、不引用代码**：
   - 我们本地 `tradingagents_multi_market_clone/` 已经把官方多 Agent 架构落到 A 股
   - 继续完善它即可，不要去 import 官方包
4. **D3 只读页 / trading-platform / backend / App.jsx 本次都不动**。
5. **A 股 Agent 的 MVP** 就是把现有 clone 沿着 14.5 的补齐清单收口，输出 Markdown 报告，落 SQLite，纯只读、纯研究。
6. **所有报告必须**：标数据源、标抓取时间、冲突显式、缺失显式、不出强制指令、写免责声明。

---

> 报告完。下一步建议：先**只过一遍 14.5 的 7 项补齐清单**，确认我们 A 股 clone 已经符合所有"只读、只研究"约束，再考虑是否生成第一份样例报告。

---

## 附录：本次刷新校核记录（2026-05-30）

本次重新对照 GitHub 上的当前仓库做了实地拉取（WebFetch `README.md` / `default_config.py` / `agents/schemas.py` / `agents/trader/trader.py` / `dataflows/` / `agents/` 目录），订正与补充了：

- **第六节**：补 `dataflows/` 当前实际文件清单（`alpha_vantage*` / `y_finance` / `yfinance_news` / `reddit` / `stocktwits` / `stockstats_utils`，**无 akshare/tushare**）；补可换源的 `data_vendors` dict；补默认 `global_news_queries` 全是美式宏观主题；补 `benchmark_map` 详细映射、明确指出**不含 `.SS` / `.SZ`**。
- **第七节**：**订正**——以前写的"没有结构化字段"已过时。当前 `schemas.py` 明确定义了 `ResearchPlan` / `TraderProposal` / `PortfolioDecision`，其中 `TraderProposal` 含 `entry_price / stop_loss / position_sizing`、`PortfolioDecision` 含 `price_target / time_horizon`。这些字段**词面接近投顾意见**，旁路渲染层必须屏蔽或软化口径。
- 其它章节复核后保持原样：协议（Apache-2.0）、安装方式、Agent 角色、API Key 清单、模型 provider 列表、风险条款、A 股 MVP 补齐清单——与当前仓库一致。
- 不变的硬约束（再次重申）：**不 clone 进现有项目、不覆盖 trading-platform / backend / App.jsx、不与 D3 只读旁路页合并、不接真实下单、不接 live、不复用券商 Key。**
