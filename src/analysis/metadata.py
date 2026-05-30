"""报告元信息辅助：数据来源摘要、行情最新交易日、财报期。

这些是纯函数，从 market_data dict 中读取字段，不依赖 LLM / akshare / 网络。
报告头部（report_generator）和各 agent 的 prompt 头部（base_agent._header）共用。
"""

from __future__ import annotations

import re
from typing import Dict


def summarize_sources(market_data: Dict) -> str:
    """从各维度 _sources 中提取上游机构名（去重），作为 prompt / 报告头部摘要。

    输入示例：
        info._sources = ['stock_info_a_code_name（新浪）', 'stock_individual_info_em（东财）']
        financials._sources = ['stock_financial_abstract（新浪）']
        history.attrs.source = 'stock_zh_a_hist（东财）'
    输出示例：
        'AKShare 接口聚合（新浪 / 东财）'

    全 mock / 空数据时返回明确提示，避免 LLM 误以为有真实数据。
    """
    raw: list[str] = []
    for key in ("info", "financials", "capital_flow"):
        raw += (market_data.get(key) or {}).get("_sources", []) or []
    hist = market_data.get("history")
    if hist is not None:
        try:
            hs = getattr(hist, "attrs", {}).get("source", "")
            if hs:
                raw.append(hs)
        except Exception:
            pass
    news = market_data.get("news") or []
    if news and not all(n.get("is_mock") for n in news):
        raw.append("stock_news_em（东财，新闻）")

    institutions: list[str] = []
    for s in raw:
        m = re.search(r"（([^）]+)）", s)
        if m:
            # 把"东财，新闻"这种逗号分隔的取第一段；去掉前后空白
            inst = m.group(1).split("，")[0].split(",")[0].strip()
            if inst:
                institutions.append(inst)

    seen, uniq = set(), []
    for i in institutions:
        if i not in seen:
            seen.add(i)
            uniq.append(i)

    if not uniq:
        return "无可识别真实数据源（可能处于 mock 模式或网络异常）"
    return "AKShare 接口聚合（" + " / ".join(uniq) + "）"


def get_latest_trade_day(market_data: Dict) -> str:
    """从 history DataFrame 抽取最新交易日字符串（YYYY-MM-DD）。

    history 为空或无 date 列时返回空串，由调用方决定显示"不足以判断"。
    """
    hist = market_data.get("history")
    if hist is None:
        return ""
    try:
        if hasattr(hist, "empty") and hist.empty:
            return ""
        if hasattr(hist, "columns") and "date" in hist.columns:
            val = hist["date"].iloc[-1]
            return str(val)[:10]
        if hasattr(hist, "index") and len(hist.index) > 0:
            return str(hist.index[-1])[:10]
    except Exception:
        return ""
    return ""


def get_financial_period(market_data: Dict) -> str:
    """从 financials 抽取最新财报期，格式化为 YYYY-MM-DD。

    AKShare 的 latest_period 一般是 8 位数字（'20260331' / int 20260331），
    转成 '2026-03-31' 提升可读性。若已是带横线日期、季度标记（'2026Q1'）
    或其它格式，原样返回；缺失返回空串。
    """
    fin = market_data.get("financials") or {}
    val = fin.get("latest_period")
    if val is None or val == "":
        return ""
    s = str(val).strip()
    if re.fullmatch(r"\d{8}", s):
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    return s
