"""基本面 vs 技术面冲突检测。

要求：当基本面与技术面方向相反时必须显式提示冲突，
报告不得强行给出唯一结论，应在投资委员会环节保留分歧。
"""

from __future__ import annotations

import math
import re
from typing import Dict, Optional


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not (isinstance(v, float) and math.isnan(v))


def _fundamental_bias(market_data: Dict) -> Optional[str]:
    """根据财务指标粗判基本面方向：偏多 / 偏空 / 中性 / None(不足以判断)。"""
    fin = market_data.get("financials") or {}
    ind = fin.get("indicators_latest") or {}
    growth = fin.get("growth") or {}

    score = 0
    seen = 0

    roe = ind.get("净资产收益率(%)")
    if _is_num(roe):
        seen += 1
        score += 1 if roe >= 10 else (-1 if roe < 5 else 0)

    debt = ind.get("资产负债率(%)")
    if _is_num(debt):
        seen += 1
        score += 1 if debt < 50 else (-1 if debt > 70 else 0)

    rev_g = growth.get("营收增长率(%)")
    if _is_num(rev_g):
        seen += 1
        score += 1 if rev_g > 10 else (-1 if rev_g < 0 else 0)

    profit_g = growth.get("净利润增长率(%)")
    if _is_num(profit_g):
        seen += 1
        score += 1 if profit_g > 10 else (-1 if profit_g < 0 else 0)

    if seen < 2:
        return None  # 不足以判断
    if score >= 1:
        return "偏多"
    if score <= -1:
        return "偏空"
    return "中性"


def _technical_bias(market_data: Dict) -> Optional[str]:
    ind = market_data.get("indicators") or {}
    if ind.get("bars", 0) < 20:
        return None
    trend = ind.get("trend", "")
    bull = any(k in trend for k in ("上升", "多头", "反弹", "偏强"))
    bear = any(k in trend for k in ("下降", "空头", "回调", "偏弱"))
    # 例如 "短期回调，中期偏强" 同时含多空信号 → 视为中性，避免误判方向
    if bull and not bear:
        return "偏多"
    if bear and not bull:
        return "偏空"
    if bull and bear:
        return "中性"
    if "震荡" in trend:
        return "中性"
    return None


def detect_fundamental_technical_conflict(market_data: Dict) -> Dict:
    """返回冲突判定结果。"""
    f = _fundamental_bias(market_data)
    t = _technical_bias(market_data)

    if f is None or t is None:
        return {
            "conflict": False,
            "insufficient": True,
            "fundamental_bias": f or "不足以判断",
            "technical_bias": t or "不足以判断",
            "message": "基本面或技术面数据不足，无法可靠比较方向，相关结论标注为不足以判断。",
        }

    conflict = {"偏多", "偏空"} == {f, t}
    return {
        "conflict": conflict,
        "insufficient": False,
        "fundamental_bias": f,
        "technical_bias": t,
        "message": (
            f"⚠️ 基本面（{f}）与技术面（{t}）方向冲突，本报告保留分歧、不给出唯一结论。"
            if conflict else
            f"基本面（{f}）与技术面（{t}）方向不冲突。"
        ),
    }


# =====================================================
# LLM 定性结论解析 + 与确定性指标的对齐（LLM 优先，指标兜底）
# =====================================================

_DIR_LABELS = ("偏多", "偏空", "中性", "不足以判断")


def parse_analyst_direction(text: str, key: str) -> Optional[str]:
    """从分析师 Markdown 输出里解析方向结论。

    key 为 "基本面方向" 或 "技术面方向"。返回 偏多/偏空/中性/不足以判断，解析不到返回 None。
    思路：先剔除标题里形如"（偏多 / 中性 / 偏空 / 不足以判断）"的选项枚举（含斜杠的括号），
    再在标题之后的小窗口里取最先出现的方向词。
    """
    if not text:
        return None
    s = text.replace("*", "").replace("`", "").replace("　", " ")
    # 剔除含斜杠的括号（即选项枚举），避免把题面当成答案
    s = re.sub(r"[（(][^（()）]*[/／][^（()）]*[)）]", "", s)
    idx = s.find(key)
    if idx == -1:
        return None
    window = s[idx + len(key): idx + len(key) + 200]
    best_pos, best_label = None, None
    for label in _DIR_LABELS:
        p = window.find(label)
        if p != -1 and (best_pos is None or p < best_pos):
            best_pos, best_label = p, label
    return best_label


def _bias_or_none(v) -> Optional[str]:
    return v if v in ("偏多", "偏空", "中性") else None


def reconcile_conflict(det_conflict: Dict, fundamental_text: str, technical_text: str) -> Dict:
    """以分析师(LLM)定性方向为准、确定性指标兜底，重算冲突判定。

    保证最终报告"综合摘要"里的方向/冲突与正文各分析师结论一致，消除两层口径打架。
    """
    f_llm = parse_analyst_direction(fundamental_text, "基本面方向")
    t_llm = parse_analyst_direction(technical_text, "技术面方向")

    f = f_llm or _bias_or_none(det_conflict.get("fundamental_bias"))
    t = t_llm or _bias_or_none(det_conflict.get("technical_bias"))

    f_disp = f or "不足以判断"
    t_disp = t or "不足以判断"
    fn = _bias_or_none(f)
    tn = _bias_or_none(t)

    if fn is None or tn is None:
        return {
            "conflict": False,
            "insufficient": True,
            "fundamental_bias": f_disp,
            "technical_bias": t_disp,
            "message": "基本面或技术面方向存在缺失（以各分析师定性结论为准），未做强制冲突判定。",
            "basis": "llm_priority",
        }

    conflict = {"偏多", "偏空"} == {fn, tn}
    return {
        "conflict": conflict,
        "insufficient": False,
        "fundamental_bias": f_disp,
        "technical_bias": t_disp,
        "message": (
            f"⚠️ 基本面（{fn}）与技术面（{tn}）方向冲突，本报告保留分歧、不给出唯一结论。"
            if conflict else
            f"基本面（{fn}）与技术面（{tn}）方向不冲突。"
        ),
        "basis": "llm_priority",
    }
