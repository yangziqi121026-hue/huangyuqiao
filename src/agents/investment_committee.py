"""E. 投资委员会（替代"交易员"角色）。

关键差异：本角色绝不输出"买入/卖出"指令。
最终结论只能从以下四个非交易标签中选一个：
观察 / 谨慎关注 / 暂不参与 / 高风险。
当基本面与技术面冲突，必须保留分歧，不得强行给唯一方向。
"""

from typing import Dict

from .base_agent import BaseAgent

SYSTEM_PROMPT = (
    "你是 Investment Committee 投资委员会主持人。你汇总看多/看空研究员与四位分析师的结论，"
    "输出一份只读研究结论。严禁任何买卖指令；最终结论只能是以下四选一："
    "观察 / 谨慎关注 / 暂不参与 / 高风险。"
    "若基本面与技术面方向冲突，必须保留分歧，不得强行统一为单一方向。"
)


class InvestmentCommittee(BaseAgent):
    name = "investment_committee"
    role = "投资委员会"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, market_data: Dict, prev_outputs: Dict) -> str:
        conflict = prev_outputs.get("_conflict", {}) or {}
        dq = prev_outputs.get("_dq", {}) or {}
        conflict_note = conflict.get("message", "")
        insufficient = dq.get("insufficient") or []
        insufficient_note = (
            "；".join(insufficient) if insufficient else "无明显缺失"
        )
        return (
            "请基于以下材料给出投资委员会结论（Markdown，标题 **投资委员会结论**）。\n\n"
            f"【看多理由】\n{prev_outputs.get('bull_researcher', '（无）')}\n\n"
            f"【看空理由】\n{prev_outputs.get('bear_researcher', '（无）')}\n\n"
            f"【基本面 vs 技术面冲突检测】{conflict_note}\n"
            f"【数据缺失维度】{insufficient_note}\n\n"
            "请严格按以下字段输出（每行一个字段，字段名后用中文冒号）：\n"
            "- 看多理由：（凝练 1-3 条）\n"
            "- 看空理由：（凝练 1-3 条）\n"
            "- 分歧点：（若基本面与技术面冲突，必须在此明确指出，不得回避）\n"
            "- 风险等级：（低 / 中 / 高 / 不足以判断）\n"
            "- 观察价位：（给支撑/压力参考区间，不是买卖点）\n"
            "- 不确定因素：（列出仍待确认的关键变量）\n"
            "- 最终结论：（只能从 观察 / 谨慎关注 / 暂不参与 / 高风险 四选一）\n"
            "注意：最终结论字段绝不能是买入/卖出/加减仓等交易动作。"
        )
