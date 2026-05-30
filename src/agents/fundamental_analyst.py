"""A. 公司基本面分析师。"""

from typing import Dict

from .base_agent import BaseAgent

SYSTEM_PROMPT = (
    "你是 Fundamental Analyst 基本面分析师。你只分析公司基本面："
    "主营业务、所属行业、市值、PE/PB、ROE、营收增长、净利润增长、现金流、负债情况。"
    "不要给交易建议，只输出基本面判断；数据缺失必须写'不足以判断'。"
)


class FundamentalAnalyst(BaseAgent):
    name = "fundamental_analyst"
    role = "基本面分析师"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, market_data: Dict, prev_outputs: Dict) -> str:
        dq = market_data.get("data_quality", {})
        return (
            "请基于以下数据完成基本面分析，输出 Markdown，标题为 **基本面分析**。\n\n"
            f"{self._header(market_data)}\n\n"
            "【基本面数据】\n"
            f"{self._fmt_fundamentals(market_data)}\n\n"
            f"【财务数据质量】{dq.get('financial_data', 'unknown')}\n\n"
            "请逐条输出：\n"
            "1. 主营业务与所属行业\n"
            "2. 市值与估值（PE/PB）\n"
            "3. 盈利能力（ROE / 净利率）\n"
            "4. 成长性（营收增长 / 净利润增长）\n"
            "5. 现金流与负债情况\n"
            "6. 基本面方向（偏多 / 中性 / 偏空 / 不足以判断）及理由\n"
            "7. 数据完整性说明（缺失项请明确标注'不足以判断'）"
        )
