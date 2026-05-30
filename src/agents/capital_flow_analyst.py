"""C. 资金面分析师。"""

from typing import Dict

from .base_agent import BaseAgent

SYSTEM_PROMPT = (
    "你是 Capital Flow Analyst 资金面分析师。你只分析资金面："
    "主力资金流入流出、北向资金（如可获取）、成交额变化、换手率。"
    "不要给交易建议，只输出资金面判断；数据缺失必须写'不足以判断'。"
)


class CapitalFlowAnalyst(BaseAgent):
    name = "capital_flow_analyst"
    role = "资金面分析师"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, market_data: Dict, prev_outputs: Dict) -> str:
        dq = market_data.get("data_quality", {})
        return (
            "请基于以下资金数据完成资金面分析，输出 Markdown，标题为 **资金面分析**。\n\n"
            f"{self._header(market_data)}\n\n"
            "【资金面数据】\n"
            f"{self._fmt_capital(market_data)}\n\n"
            f"【资金数据质量】{dq.get('capital_data', 'unknown')}\n\n"
            "请逐条输出：\n"
            "1. 主力资金流入流出趋势\n"
            "2. 北向资金（如不可获取，写'不足以判断'，不要编造个股北向数据）\n"
            "3. 成交额 / 换手率变化\n"
            "4. 资金面方向（流入 / 中性 / 流出 / 不足以判断）及理由"
        )
