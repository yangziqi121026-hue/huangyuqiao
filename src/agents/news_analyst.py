"""D. 消息面分析师。"""

from typing import Dict

from .base_agent import BaseAgent

SYSTEM_PROMPT = (
    "你是 News Analyst 消息面分析师。你只分析消息面："
    "近期新闻、政策影响、行业事件、风险事件。"
    "不要给交易建议，只输出消息面判断；无新闻必须写'不足以判断'，不得编造新闻。"
)


class NewsAnalyst(BaseAgent):
    name = "news_analyst"
    role = "消息面分析师"
    system_prompt = SYSTEM_PROMPT

    def build_user_prompt(self, market_data: Dict, prev_outputs: Dict) -> str:
        dq = market_data.get("data_quality", {})
        return (
            "请基于以下新闻完成消息面分析，输出 Markdown，标题为 **消息面分析**。\n\n"
            f"{self._header(market_data)}\n\n"
            "【近期新闻】\n"
            f"{self._fmt_news(market_data)}\n\n"
            f"【新闻数据质量】{dq.get('news_data', 'unknown')}\n\n"
            "请逐条输出：\n"
            "1. 近期重要新闻摘要\n"
            "2. 政策影响\n"
            "3. 行业事件\n"
            "4. 风险事件\n"
            "5. 消息面方向（偏正面 / 中性 / 偏负面 / 不足以判断）及理由"
        )
