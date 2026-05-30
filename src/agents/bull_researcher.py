"""看多研究员。"""

from typing import Dict

from .base_agent import BaseAgent

SYSTEM_PROMPT = (
    "你是 Bull Researcher 看多研究员。你的任务是在四位分析师结论基础上，"
    "尽力列出'看多理由'。但不得夸大、不得编造，不得给交易指令。"
    "如果支撑看多的证据不足，必须如实说明可信度低。"
)


class BullResearcher(BaseAgent):
    name = "bull_researcher"
    role = "看多研究员"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, market_data: Dict, prev_outputs: Dict) -> str:
        return (
            "请基于以下四位分析师的结论，列出看多理由（Markdown，标题 **看多理由**）。\n\n"
            f"【基本面】\n{prev_outputs.get('fundamental_analyst', '（无）')}\n\n"
            f"【技术面】\n{prev_outputs.get('technical_analyst', '（无）')}\n\n"
            f"【资金面】\n{prev_outputs.get('capital_flow_analyst', '（无）')}\n\n"
            f"【消息面】\n{prev_outputs.get('news_analyst', '（无）')}\n\n"
            "请输出 3-5 条看多理由，每条注明依据来自哪个维度，并标注可信度。"
        )
