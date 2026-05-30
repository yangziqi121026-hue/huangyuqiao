"""智能体基类。

约定：
- 每个智能体只读取 workflow 传入的 market_data + prev_outputs。
- 任何智能体都不能直接调用 AKShare 等数据源。
- 任何智能体都不得输出"买入/卖出"等交易指令；只做研究判断。
"""

from __future__ import annotations

from typing import Dict, Optional

from ..analysis.data_quality import missing_label
from ..llm_client import LLMClient

# 所有 agent 共享的硬性口径，注入到 system prompt 末尾
GUARDRAIL = (
    "【硬性约束】这是只读投研分析，严禁输出任何交易指令。"
    "不得出现'买入/卖出/加仓/减仓/满仓/清仓/必须买/必须卖'等字样。"
    "数据缺失时必须写'不足以判断'，不得编造数据。"
)


class BaseAgent:
    name: str = "base"
    role: str = "base"
    system_prompt: str = ""

    DEFAULT_TEMPERATURE = 0.4
    DEFAULT_MAX_TOKENS = 1400

    def __init__(self, llm: Optional[LLMClient] = None):
        self.llm = llm or LLMClient()

    def build_user_prompt(self, market_data: Dict, prev_outputs: Dict) -> str:
        raise NotImplementedError

    def run(self, market_data: Dict, prev_outputs: Dict) -> str:
        user_prompt = self.build_user_prompt(market_data, prev_outputs)
        return self.llm.chat(
            system_prompt=self.system_prompt + " " + GUARDRAIL,
            user_prompt=user_prompt,
            temperature=self.DEFAULT_TEMPERATURE,
            max_tokens=self.DEFAULT_MAX_TOKENS,
        )

    # ---------- 共享格式化 ----------

    @staticmethod
    def _header(market_data: Dict) -> str:
        info = market_data.get("info") or {}
        return (
            f"市场：{market_data.get('market', '')}\n"
            f"代码：{market_data.get('symbol', '')}\n"
            f"名称：{market_data.get('name', '')}\n"
            f"行业：{missing_label(info.get('industry'))}\n"
            f"主营业务：{missing_label(info.get('main_business'))}\n"
            f"当前价：{missing_label(market_data.get('current_price'))}\n"
            f"数据抓取时间：{market_data.get('fetched_at', '')}"
        )

    @staticmethod
    def _fmt_fundamentals(market_data: Dict) -> str:
        info = market_data.get("info") or {}
        fin = market_data.get("financials") or {}
        ind = fin.get("indicators_latest") or {}
        growth = fin.get("growth") or {}
        snap = fin.get("snapshot") or {}
        lines = [
            f"- 总市值：{missing_label(info.get('market_cap'))}",
            f"- 流通市值：{missing_label(info.get('circulating_market_cap'))}",
            f"- PE：{missing_label(info.get('pe'))}",
            f"- PB：{missing_label(info.get('pb'))}",
            f"- ROE(净资产收益率%)：{missing_label(ind.get('净资产收益率(%)'))}",
            f"- 销售净利率(%)：{missing_label(ind.get('销售净利率(%)'))}",
            f"- 资产负债率(%)：{missing_label(ind.get('资产负债率(%)'))}",
            f"- 营收增长率(%)：{missing_label(growth.get('营收增长率(%)'))}",
            f"- 净利润增长率(%)：{missing_label(growth.get('净利润增长率(%)'))}",
        ]
        if fin.get("latest_period"):
            lines.append(f"- 财报期：{fin['latest_period']}")
        for k in ("经营活动产生的现金流量净额", "归母净利润", "营业总收入"):
            if k in snap:
                lines.append(f"- {k}：{missing_label(snap.get(k))}")
        srcs = fin.get("_sources") or []
        if srcs:
            lines.append(f"- 财务数据来源：{', '.join(srcs)}")
        return "\n".join(lines)

    @staticmethod
    def _fmt_indicators(market_data: Dict) -> str:
        ind = market_data.get("indicators") or {}
        return "\n".join([
            f"- 趋势：{ind.get('trend', '不足以判断')}（样本 {ind.get('bars', 0)} 根 K 线）",
            f"- MA5/10/20/60：{missing_label(ind.get('ma5'))} / {missing_label(ind.get('ma10'))} / "
            f"{missing_label(ind.get('ma20'))} / {missing_label(ind.get('ma60'))}",
            f"- RSI14：{missing_label(ind.get('rsi14'))}",
            f"- MACD/Signal/Hist：{missing_label(ind.get('macd'))} / "
            f"{missing_label(ind.get('macd_signal'))} / {missing_label(ind.get('macd_hist'))}",
            f"- 近20日涨跌幅(%)：{missing_label(ind.get('pct_20d'))}",
            f"- 成交量变化(5d vs 20d, %)：{missing_label(ind.get('volume_change'))}",
            f"- 支撑位 / 压力位：{missing_label(ind.get('support'))} / {missing_label(ind.get('resistance'))}",
        ])

    @staticmethod
    def _fmt_capital(market_data: Dict) -> str:
        cap = market_data.get("capital_flow") or {}
        amt = cap.get("amount_latest")
        amt_disp = f"{round(amt / 1e8, 2)}亿元" if isinstance(amt, (int, float)) else "不足以判断"
        lines = [
            f"- 近5日主力净流入合计：{missing_label(cap.get('main_fund_5d_sum'))}",
            f"- 最新成交额：{amt_disp}",
            f"- 最新换手率(%)：{missing_label(cap.get('turnover_rate_latest'))}",
        ]
        recent = cap.get("main_fund_recent") or []
        if recent:
            seq = ", ".join(
                f"{r.get('date', '')}:{missing_label(r.get('main_net'))}" for r in recent
            )
            lines.append(f"- 主力净流入(近几日)：{seq}")
        nb = cap.get("northbound")
        lines.append(f"- 北向资金：{'见市场级汇总（个股实时已停披露）' if nb else '不足以判断'}")
        srcs = cap.get("_sources") or []
        if srcs:
            lines.append(f"- 资金面数据来源：{', '.join(srcs)}")
        return "\n".join(lines)

    @staticmethod
    def _fmt_news(market_data: Dict) -> str:
        news = market_data.get("news") or []
        if not news:
            return "（无可用新闻，消息面不足以判断）"
        lines = []
        for n in news[:10]:
            mark = "[mock] " if n.get("is_mock") else ""
            lines.append(f"- {mark}{n.get('date', '')} | {n.get('title', '')} | {n.get('summary', '')}")
        return "\n".join(lines)
