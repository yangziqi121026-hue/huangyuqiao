"""数据质量评估。

核心要求：数据缺失时必须显式标注"不足以判断"，不得用占位结论掩盖缺失。
"""

from __future__ import annotations

import math
from typing import Dict, List

MISSING = "不足以判断"


def missing_label(value, suffix: str = "") -> str:
    """缺失值统一渲染为 不足以判断；否则带单位返回。"""
    if value is None:
        return MISSING
    if isinstance(value, float) and math.isnan(value):
        return MISSING
    if isinstance(value, str) and value.strip() in ("", "--", "nan", "None"):
        return MISSING
    return f"{value}{suffix}"


def assess_data_quality(market_data: Dict) -> Dict:
    """返回每个维度是否足以判断，并汇总整体可信度提示。"""
    dq = market_data.get("data_quality") or {}
    ind = market_data.get("indicators") or {}
    fin = market_data.get("financials") or {}
    cap = market_data.get("capital_flow") or {}

    flags = {
        "price": dq.get("price_data") == "ok" and ind.get("bars", 0) >= 20,
        "fundamental": bool(fin.get("snapshot") or fin.get("indicators_latest")),
        "capital": bool(cap.get("_sources")),
        "news": dq.get("news_data") in ("ok",),
    }

    insufficient: List[str] = []
    if not flags["price"]:
        insufficient.append("技术面（行情样本不足或为 mock）")
    if not flags["fundamental"]:
        insufficient.append("基本面（财务数据缺失）")
    if not flags["capital"]:
        insufficient.append("资金面（主力/北向资金不可得）")
    if not flags["news"]:
        insufficient.append("消息面（新闻缺失或为 mock）")

    overall = "充分" if not insufficient else (
        "部分缺失" if len(insufficient) < 3 else "严重不足"
    )

    return {
        "flags": flags,
        "insufficient": insufficient,
        "overall": overall,
    }
