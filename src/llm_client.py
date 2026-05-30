"""LLM 客户端封装

- 优先使用 OpenAI 兼容协议（OPENAI_API_KEY / OPENAI_BASE_URL / MODEL_NAME）。
- 没有 API Key 或 MOCK_MODE=true 时使用 mock 返回，保证全流程在无网络/无 key 时也可跑通。
- mock 输出严格遵守"只读、不下单、不给买卖指令"的口径。
"""

from __future__ import annotations

import time
from typing import Optional

from . import config


class LLMClient:
    def __init__(self):
        self.mock_mode = config.MOCK_MODE
        self.model = config.MODEL_NAME
        self._client = None
        self._init_error = ""
        if not self.mock_mode:
            try:
                from openai import OpenAI  # 延迟导入，mock 场景不强依赖

                self._client = OpenAI(
                    api_key=config.OPENAI_API_KEY,
                    base_url=config.OPENAI_BASE_URL or None,
                )
            except Exception as e:
                self._init_error = str(e)
                self.mock_mode = True

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.4,
        max_tokens: int = 1400,
        retries: int = 2,
    ) -> str:
        if self.mock_mode:
            return self._mock(system_prompt, user_prompt)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        last_err: Optional[Exception] = None
        for i in range(retries + 1):
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                content = resp.choices[0].message.content or ""
                return content.strip()
            except Exception as e:
                last_err = e
                time.sleep(0.8 * (i + 1))
        return (
            f"> LLM 调用失败（{type(last_err).__name__}），以下为 mock 回退结果：\n\n"
            + self._mock(system_prompt, user_prompt)
        )

    # ---------- mock ----------

    def _mock(self, system_prompt: str, user_prompt: str) -> str:
        role = _detect_role(system_prompt)
        hint = _extract_hint(user_prompt)

        if role == "fundamental":
            return (
                "**基本面分析（mock）**\n"
                f"- 标的：{hint}\n"
                "- 主营业务 / 行业：mock 模式下未接入真实数据，以下仅为占位结论。\n"
                "- 营收与净利润增长：缺乏真实财报，**不足以判断**。\n"
                "- 估值（PE/PB）：暂无法量化，需接入真实数据后复核。\n"
                "- ROE / 现金流 / 负债：数据缺失，可信度低。\n"
                "- 基本面结论：中性偏谨慎（占位）。"
            )
        if role == "technical":
            return (
                "**技术面分析（mock）**\n"
                f"- 指标快照：{hint}\n"
                "- 均线排列：参考 MA5/10/20/60 给出方向。\n"
                "- MACD / RSI：未到极端区域（占位）。\n"
                "- 量价：量能温和。\n"
                "- 支撑 / 压力：参考近 60 日高低点。\n"
                "- 技术面结论：以震荡看待，等待方向明确。"
            )
        if role == "capital":
            return (
                "**资金面分析（mock）**\n"
                "- 主力资金：mock 模式，无真实主力净流入数据，**不足以判断**。\n"
                "- 北向资金：如不可获取则不纳入结论。\n"
                "- 成交额 / 换手率：参考近期变化（占位）。\n"
                "- 资金面结论：中性。"
            )
        if role == "news":
            return (
                "**消息面分析（mock）**\n"
                "- 近期新闻：当前为占位/模拟数据，需接入真实新闻源后提高可信度。\n"
                "- 政策影响 / 行业事件：未识别明确方向。\n"
                "- 风险事件：暂未识别。\n"
                "- 消息面结论：中性。"
            )
        if role == "bull":
            return (
                "**看多理由（mock）**\n"
                "1. 若估值处合理偏下区间，向下空间相对有限。\n"
                "2. 若站稳关键均线，存在反弹动能。\n"
                "3. 行业长期需求仍在。\n"
                "（注：mock 数据，理由可信度低。）"
            )
        if role == "bear":
            return (
                "**看空理由（mock）**\n"
                "1. 宏观/政策不确定性仍在。\n"
                "2. 若跌破关键支撑可能加速下行。\n"
                "3. 财务/资金数据缺失影响判断锚定。\n"
                "（注：mock 数据，理由可信度低。）"
            )
        if role == "committee":
            return (
                "**投资委员会结论（mock）**\n"
                "- 看多理由：见看多研究员，可信度受 mock 数据限制。\n"
                "- 看空理由：见看空研究员，可信度受 mock 数据限制。\n"
                "- 分歧点：数据完整性 vs 价格趋势。\n"
                "- 风险等级：不足以判断\n"
                "- 观察价位：以近 60 日高低点为参考区间。\n"
                "- 不确定因素：财务、资金、新闻多为 mock，需接入真实数据复核。\n"
                "- 最终结论：观察\n"
                "- 说明：本结论为研究观点，不构成投资建议，不含任何买卖指令。"
            )
        return f"[mock 输出] role={role}\n上下文：{hint}"


def _detect_role(system_prompt: str) -> str:
    s = system_prompt or ""
    for sep in ("。", "."):
        if sep in s:
            s = s.split(sep, 1)[0]
            break
    head = s.lower()
    if "fundamental" in head or "基本面分析师" in head:
        return "fundamental"
    if "technical" in head or "技术分析师" in head:
        return "technical"
    if "capital" in head or "资金面分析师" in head:
        return "capital"
    if "news analyst" in head or "消息面分析师" in head or "新闻分析师" in head:
        return "news"
    if "bull" in head or "看多研究员" in head:
        return "bull"
    if "bear" in head or "看空研究员" in head:
        return "bear"
    if "committee" in head or "投资委员会" in head:
        return "committee"
    return "generic"


def _extract_hint(user_prompt: str, max_len: int = 160) -> str:
    if not user_prompt:
        return ""
    first_line = user_prompt.strip().splitlines()[0]
    return first_line[:max_len]
