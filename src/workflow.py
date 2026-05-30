"""分析流程编排（只读）。

入口：run_analysis(symbol, ...)

流程：
6位A股代码 → AKShare 抓数据 → 指标计算 → 冲突/质量评估
→ 基本面 → 技术面 → 资金面 → 消息面（4 分析师）
→ 看多 / 看空研究员
→ 投资委员会结论（只输出 观察/谨慎关注/暂不参与/高风险）
→ 最终 Markdown 报告

本流程不包含任何下单 / 交易 / live 调用。
"""

from __future__ import annotations

import re
import traceback
from datetime import datetime, timedelta
from typing import Callable, Dict, Optional

from . import config
from . import akshare_provider as provider
from .indicators import compute_indicators
from .llm_client import LLMClient
from .analysis import (
    assess_data_quality,
    detect_fundamental_technical_conflict,
    reconcile_conflict,
)
from .report_generator import build_final_report, extract_conclusion, extract_risk_level
from .agents import (
    FundamentalAnalyst,
    TechnicalAnalyst,
    CapitalFlowAnalyst,
    NewsAnalyst,
    BullResearcher,
    BearResearcher,
    InvestmentCommittee,
)

STAGES = [
    ("data_fetch", "数据获取中"),
    ("fundamental_analyst", "基本面分析师分析中"),
    ("technical_analyst", "技术分析师分析中"),
    ("capital_flow_analyst", "资金面分析师分析中"),
    ("news_analyst", "消息面分析师分析中"),
    ("bull_researcher", "看多研究员分析中"),
    ("bear_researcher", "看空研究员分析中"),
    ("investment_committee", "投资委员会汇总中"),
    ("final_report", "最终报告生成中"),
]


def _default_dates() -> Dict[str, str]:
    end = datetime.now().date()
    start = end - timedelta(days=365)
    return {"start_date": start.strftime("%Y-%m-%d"), "end_date": end.strftime("%Y-%m-%d")}


def run_analysis(
    symbol: str,
    start_date: str = "",
    end_date: str = "",
    period_zh: str = "日线",
    adjust_zh: str = "前复权",
    depth: str = "标准",
    on_stage: Optional[Callable[[str, str, Dict], None]] = None,
) -> Dict:
    out: Dict = {
        "ok": False,
        "error": None,
        "market_data": {},
        "agent_outputs": {},
        "conflict": {},
        "data_quality": {},
        "final_report": "",
        "conclusion": "",
        "risk_level": "",
        "depth": depth,
    }

    symbol = (symbol or "").strip()
    if not re.match(r"^\d{6}$", symbol):
        out["error"] = "请输入正确的 A 股 6 位股票代码（仅 6/0/3 开头的沪深 A 股）"
        return out
    if not provider.validate_symbol(symbol):
        out["error"] = f"该代码非沪深 A 股或暂不支持（如北交所）：{symbol}"
        return out

    dates = _default_dates()
    start_date = start_date or dates["start_date"]
    end_date = end_date or dates["end_date"]
    period = config.PERIOD_MAP.get(period_zh, "daily")
    adjust = config.ADJUST_MAP.get(adjust_zh, "")

    def _emit(stage_id: str, ctx: Optional[Dict] = None):
        if on_stage is None:
            return
        try:
            on_stage(stage_id, dict(STAGES).get(stage_id, stage_id), ctx or {})
        except Exception:
            pass

    # 1) 抓数据
    _emit("data_fetch")
    try:
        market_data = provider.fetch_market_data(
            symbol=symbol, start_date=start_date, end_date=end_date,
            period=period, adjust=adjust,
        )
    except Exception as e:
        out["error"] = f"获取数据失败：{e}"
        out["market_data"] = {"errors": [str(e), traceback.format_exc()]}
        return out

    # 2) 指标
    history = market_data.get("history")
    indicators = compute_indicators(history) if history is not None else {}
    indicators.pop("df_with_indicators", None)
    market_data["indicators"] = indicators

    # 3) 冲突 + 数据质量评估
    conflict = detect_fundamental_technical_conflict(market_data)
    dq_assessment = assess_data_quality(market_data)

    # 4) 智能体串行
    llm = LLMClient()
    pipeline = [
        ("fundamental_analyst", FundamentalAnalyst(llm)),
        ("technical_analyst", TechnicalAnalyst(llm)),
        ("capital_flow_analyst", CapitalFlowAnalyst(llm)),
        ("news_analyst", NewsAnalyst(llm)),
        ("bull_researcher", BullResearcher(llm)),
        ("bear_researcher", BearResearcher(llm)),
        ("investment_committee", InvestmentCommittee(llm)),
    ]
    depth_cfg = {
        "快速": {"max_tokens": 700, "temperature": 0.3},
        "标准": {"max_tokens": 1300, "temperature": 0.4},
        "深度": {"max_tokens": 1900, "temperature": 0.5},
    }.get(depth, {"max_tokens": 1300, "temperature": 0.4})

    agent_outputs: Dict[str, str] = {
        "_conflict": conflict,        # 供投资委员会读取
        "_dq": dq_assessment,
    }
    for stage_id, agent in pipeline:
        _emit(stage_id)
        agent.DEFAULT_MAX_TOKENS = depth_cfg["max_tokens"]
        agent.DEFAULT_TEMPERATURE = depth_cfg["temperature"]
        try:
            text = agent.run(market_data, agent_outputs)
        except Exception as e:
            text = f"> {agent.role} 执行失败：{e}"
        agent_outputs[stage_id] = text or ""

    # 4.5) 用各分析师(LLM)的定性方向重算冲突判定（LLM 优先、确定性指标兜底），
    #      保证最终"综合摘要"的方向/冲突与正文一致，不再两层口径打架。
    conflict = reconcile_conflict(
        conflict,
        agent_outputs.get("fundamental_analyst", ""),
        agent_outputs.get("technical_analyst", ""),
    )

    # 5) 报告
    _emit("final_report")
    final_report = build_final_report(
        market_data=market_data,
        agent_outputs=agent_outputs,
        conflict=conflict,
        dq_assessment=dq_assessment,
        period_zh=period_zh,
        adjust_zh=adjust_zh,
    )

    out["ok"] = True
    out["market_data"] = market_data
    out["agent_outputs"] = {k: v for k, v in agent_outputs.items() if not k.startswith("_")}
    out["conflict"] = conflict
    out["data_quality"] = dq_assessment
    out["final_report"] = final_report
    out["conclusion"] = extract_conclusion(agent_outputs.get("investment_committee", ""))
    out["risk_level"] = extract_risk_level(agent_outputs.get("investment_committee", ""))
    return out
