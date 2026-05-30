"""B. 技术面分析师。"""

from typing import Dict

from .base_agent import BaseAgent

SYSTEM_PROMPT = (
    "你是 Technical Analyst 技术分析师。你只分析技术面："
    "K线趋势、MA5/10/20/60、MACD、RSI、成交量变化、支撑位/压力位。"
    "不要给交易建议，只输出技术面判断；样本不足必须写'不足以判断'。"
)


class TechnicalAnalyst(BaseAgent):
    name = "technical_analyst"
    role = "技术分析师"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, market_data: Dict, prev_outputs: Dict) -> str:
        dq = market_data.get("data_quality", {})
        return (
            "请基于以下指标完成技术面分析，输出 Markdown，标题为 **技术面分析**。\n\n"
            f"{self._header(market_data)}\n\n"
            "【技术指标】\n"
            f"{self._fmt_indicators(market_data)}\n\n"
            f"【行情数据质量】{dq.get('price_data', 'unknown')}\n\n"
            "请逐条输出：\n"
            "1. K线趋势（结合均线排列）\n"
            "2. 均线系统（MA5/10/20/60 的多空关系）\n"
            "3. MACD 动能\n"
            "4. RSI 强弱\n"
            "5. 成交量变化\n"
            "6. 支撑位 / 压力位\n"
            "7. 技术面方向（偏多 / 中性 / 偏空 / 不足以判断）及理由"
        )
