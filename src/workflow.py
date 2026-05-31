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


def _empty_out(depth: str) -> Dict:
    return {
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


def _analyze_market_data(
    market_data: Dict,
    depth: str = "标准",
    period_zh: str = "日线",
    adjust_zh: str = "前复权",
    on_stage: Optional[Callable[[str, str, Dict], None]] = None,
) -> Dict:
    """已有 market_data → 算指标 → 跑 7 agent → 出报告。

    run_analysis（先抓数据）和 run_analysis_replay（从 snapshot 还原）都调这个，
    保证 LLM 链路完全一致，避免两条 codepath 走偏。
    """
    out = _empty_out(depth)

    def _emit(stage_id: str, ctx: Optional[Dict] = None):
        if on_stage is None:
            return
        try:
            on_stage(stage_id, dict(STAGES).get(stage_id, stage_id), ctx or {})
        except Exception:
            pass

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
        "_conflict": conflict,        # 供投资委员会读取（委员会前会用 LLM 定性方向重算并覆盖）
        "_dq": dq_assessment,
    }
    for stage_id, agent in pipeline:
        _emit(stage_id)
        # 4.5) 在投资委员会汇总「之前」，用已产出的基本面/技术面定性方向重算冲突判定
        #      （LLM 优先、确定性指标兜底）。这样委员会拿到的冲突口径与最终"综合摘要"
        #      完全一致，消除"委员会正文说方向冲突、综合摘要却说不冲突"的两层打架。
        if stage_id == "investment_committee":
            conflict = reconcile_conflict(
                conflict,
                agent_outputs.get("fundamental_analyst", ""),
                agent_outputs.get("technical_analyst", ""),
            )
            agent_outputs["_conflict"] = conflict
        agent.DEFAULT_MAX_TOKENS = depth_cfg["max_tokens"]
        agent.DEFAULT_TEMPERATURE = depth_cfg["temperature"]
        try:
            text = agent.run(market_data, agent_outputs)
        except Exception as e:
            text = f"> {agent.role} 执行失败：{e}"
        agent_outputs[stage_id] = text or ""

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


def run_analysis(
    symbol: str,
    start_date: str = "",
    end_date: str = "",
    period_zh: str = "日线",
    adjust_zh: str = "前复权",
    depth: str = "标准",
    on_stage: Optional[Callable[[str, str, Dict], None]] = None,
) -> Dict:
    out = _empty_out(depth)

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

    # 2-5) 共用流水线
    return _analyze_market_data(
        market_data, depth=depth, period_zh=period_zh,
        adjust_zh=adjust_zh, on_stage=on_stage,
    )


def run_analysis_replay(
    snapshot_path,
    period_zh: str = "日线",
    adjust_zh: str = "前复权",
    depth: str = "标准",
    on_stage: Optional[Callable[[str, str, Dict], None]] = None,
) -> Dict:
    """重放模式：从 snapshot.json 加载 market_data，跳过 AKShare 抓取，直接走 LLM 流水线。

    用途：
    - 复现历史报告（同 snapshot + 同模型 → 极相似结论）
    - 改了 prompt / 换了模型后快速验证（不烧 AKShare 配额、不等抓取时间）
    - A/B 模型对比的底层接口（同 snapshot 喂不同 LLM）

    报告头部会自动标注 "Replay 模式" + 原快照保存时间，避免误读为新跑。
    """
    from .snapshot import load_market_data_from_snapshot

    out = _empty_out(depth)
    try:
        market_data, payload = load_market_data_from_snapshot(snapshot_path)
    except Exception as e:
        out["error"] = f"加载快照失败：{e}"
        return out

    symbol = market_data.get("symbol", "")
    if not symbol:
        out["error"] = "快照缺少 symbol 字段，无法 replay"
        return out

    # 注入 replay 元信息，供 build_final_report 头部展示
    market_data["_replay_from"] = str(snapshot_path)
    market_data["_replay_saved_at"] = payload.get("saved_at", "")
    market_data["_replay_snapshot_version"] = payload.get("version", "?")

    return _analyze_market_data(
        market_data, depth=depth, period_zh=period_zh,
        adjust_zh=adjust_zh, on_stage=on_stage,
    )
