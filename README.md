# A股个股投研分析 Agent（只读 / 研究用途）

> 多智能体（TradingAgents 风格）A股个股投研分析系统。
> **只读分析，不接自动交易，不下单，不接 live，不接美股 / 港股 / OKX。**
> 本项目为独立目录，与 trading-platform / backend / D3 旁路页 **无任何耦合**。

---

## 一、它做什么

输入一个 A 股 6 位代码，输出一份完整的 Markdown 投研报告，包含五大模块：

| 模块 | 内容 |
|------|------|
| A. 公司基本面 | 主营业务 / 行业 / 市值 / PE / PB / ROE / 营收增长 / 净利润增长 / 现金流 / 负债 |
| B. 技术面 | K线趋势 / MA5·10·20·60 / MACD / RSI / 成交量变化 / 支撑位 / 压力位 |
| C. 资金面 | 主力资金流入流出 / 北向资金（如可获取）/ 成交额 / 换手率 |
| D. 消息面 | 近期新闻 / 政策影响 / 行业事件 / 风险事件 |
| E. 投资委员会结论 | 看多理由 / 看空理由 / 分歧点 / 风险等级 / 观察价位 / 不确定因素 / 最终结论 |

**最终结论只会是这四个研究分级之一**（绝不出现买入/卖出指令）：

> 观察 / 谨慎关注 / 暂不参与 / 高风险

---

## 二、硬性约束（写进代码，不可被参数覆盖）

- ✅ 数据来源使用 **AKShare**；只分析 A 股。
- ✅ 报告必含 **数据来源 + 抓取时间**。
- ✅ 基本面与技术面冲突时 **显式提示冲突，不强行给唯一结论**。
- ✅ 数据缺失时 **标注「不足以判断」**，不编造。
- ❌ 不自动下单；不生成「必须买入 / 必须卖出」指令（report 末尾有 forbidden-word 安全网）。
- ❌ 不接 live / 不接实时订阅；不接美股 / 港股 / OKX。
- ❌ 不需要任何券商 / 交易所 API Key。

---

## 三、Agent 角色

```
基本面分析师 ┐
技术面分析师 ├─→ 看多研究员 ┐
资金面分析师 ├─→ 看空研究员 ┴─→ 投资委员会（只出 观察/谨慎关注/暂不参与/高风险）
消息面分析师 ┘
```

---

## 四、目录结构

```
ashare_research_agent/
├── run.py                       # CLI 入口：python run.py 600519
├── run_tests.py                 # 一键跑单元测试（不联网/不调 LLM）
├── app.py                       # Streamlit 单页 UI（可选）
├── requirements.txt
├── .env.example                 # 只放 LLM Key，无券商 Key
├── reports/                     # 输出的 Markdown 报告
├── data/                        # AKShare 名称缓存
├── hooks/pre-commit             # 提交前自动跑测试的 git 钩子（core.hooksPath）
├── tests/                       # 单元测试（指标/冲突对齐/结论抽取/禁词安全网/资金面兜底）
└── src/
    ├── config.py                # 配置 + 只读安全约束
    ├── akshare_provider.py      # AKShare 数据（基本面/行情/财务/资金/北向/新闻）
    ├── indicators.py            # MA / MACD / RSI / 支撑压力 / 量
    ├── llm_client.py            # OpenAI 兼容 + mock 回退
    ├── analysis/
    │   ├── conflict.py          # 基本面 vs 技术面冲突检测
    │   └── data_quality.py      # 缺失 → 不足以判断
    ├── agents/                  # 7 个智能体
    └── report_generator.py      # A-E 报告 + 数据源/时间 + 免责声明
```

---

## 五、安装与运行

```bash
# 1. 创建虚拟环境（可选）
python -m venv .venv && .venv\Scripts\activate   # Windows PowerShell

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置（可选；不配则自动 mock）
copy .env.example .env   # 然后填 OPENAI_API_KEY

# 4. 跑 CLI
python run.py 600519
python run.py 000001 --depth 深度 --period 周线

# 5. 或跑 Web UI
streamlit run app.py
```

无 `OPENAI_API_KEY` 或未联网时自动进入 **mock 模式**，仍可跑通全流程（结论仅用于验证流程）。

---

## 五·五、测试

纯标准库 `unittest`，**无需安装 pytest，不联网、不调用 LLM、不依赖 akshare**——只验证只读分析的核心逻辑与安全约束。

```bash
# 方式一：一键脚本（推荐，带通过/失败汇总，退出码可接 CI）
python run_tests.py
python run_tests.py -q          # 安静模式

# 方式二：标准 unittest 发现
python -m unittest discover -s tests -v
```

覆盖范围（约 40 个用例）：

| 测试文件 | 守住的行为 |
|----------|-----------|
| `tests/test_indicators.py` | MA/RSI/MACD、支撑压力、趋势判定；空数据/缺列安全返回 |
| `tests/test_conflict.py` | 分析师方向解析、LLM 定性优先于确定性指标、冲突/缺失判定 |
| `tests/test_report.py` | 最终结论只落四档（非法值回退「观察」）、风险等级、禁词安全网 |
| `tests/test_capital.py` | 资金面成交额/换手率从日K兜底的纯计算（东财百分比直用、新浪小数×100、缺列安全） |

> 这些测试把「不出买卖指令、只用四档结论、数据缺失标『不足以判断』、基本面/技术面冲突要显式提示」这些**硬约束**钉死，改 prompt 或动逻辑后回归一遍即可发现破坏。

### 提交前自动回归（pre-commit 钩子）

仓库自带版本化钩子 `hooks/pre-commit`，每次 `git commit` 前自动跑上面全部用例，任一失败即**阻断提交**，守住硬约束不被悄悄改坏。

```bash
# 克隆后启用一次（钩子目录已纳入版本控制，无需手动拷贝到 .git/hooks）
git config core.hooksPath hooks

# 手动触发一次（不产生提交）
git hook run pre-commit

# 确需跳过（不推荐）
git commit --no-verify
```

> Windows 上钩子优先用 `py -3` 启动器，避开 Microsoft Store 的 python stub。

---

## 六、最小可运行版本（MVP）范围

- ✅ 一条主链路：6位代码 → 抓数据 → 指标 → 4分析师 → 多空 → 投资委员会 → Markdown 报告。
- ✅ mock 模式下离线可跑通。
- ✅ 真实数据走 AKShare（行情/财务/资金/新闻），北向为 best-effort。
- 🔒 不做：美股/港股 provider、自动交易、live、跟单、与外部系统合并。

---

## 七、免责声明

本项目为 AI 自动生成的只读研究材料，数据来自 AKShare 公开接口，可能滞后/缺失/错误。
不构成投资建议，不预测涨跌，不承诺收益。投资有风险，决策请独立判断并自担风险。
