"""批量分析编排（只读）。

入口：run_batch(symbols, ...)

每只股票独立 try/except，单只失败不会中断整批；失败标的在汇总的「失败标的」段
显式列出。本流程不包含任何下单 / 交易 / live 调用。
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Callable, Dict, List, Optional

from . import config
from .analysis.metadata import get_latest_trade_day
from .report_generator import (
    build_batch_summary,
    save_batch_summary_to_file,
    save_report_to_file,
)
from .snapshot import save_snapshot
from .workflow import run_analysis


def _extract_batch_item(
    symbol: str, result: Dict, duration: float, report_path: str = ""
) -> Dict:
    """从 run_analysis 的 result 抽取批量汇总所需字段。"""
    if not result.get("ok"):
        return {
            "symbol": symbol,
            "ok": False,
            "error": result.get("error", "未知错误"),
            "duration_sec": duration,
        }
    md = result.get("market_data") or {}
    cf = result.get("conflict") or {}
    return {
        "symbol": symbol,
        "name": md.get("name", ""),
        "ok": True,
        "conclusion": result.get("conclusion", "观察"),
        "risk_level": result.get("risk_level", "不足以判断"),
        "fundamental_bias": cf.get("fundamental_bias", "不足以判断"),
        "technical_bias": cf.get("technical_bias", "不足以判断"),
        "conflict": bool(cf.get("conflict")),
        "insufficient": bool(cf.get("insufficient")),
        "latest_trade_day": get_latest_trade_day(md) or "不足以判断",
        "report_path": report_path,
        "duration_sec": duration,
    }


def run_batch(
    symbols: List[str],
    *,
    start_date: str = "",
    end_date: str = "",
    period_zh: str = "日线",
    adjust_zh: str = "前复权",
    depth: str = "标准",
    save_individual: bool = True,
    save_summary: bool = True,
    save_snapshots: bool = True,
    on_progress: Optional[Callable[[int, int, str, Dict], None]] = None,
) -> Dict:
    """跑一批股票，返回汇总字典。

    返回：
        {
          "ok": True,
          "started_at": "YYYY-MM-DD HH:MM:SS",
          "finished_at": "YYYY-MM-DD HH:MM:SS",
          "duration_sec": float,
          "results": [batch_item, ...],  # 与 build_batch_summary 输入兼容
          "summary_md": str,
          "summary_path": str,  # 若 save_summary=True
        }
    """
    started_dt = datetime.now()
    started_at = started_dt.strftime("%Y-%m-%d %H:%M:%S")
    results: List[Dict] = []
    total = len(symbols)

    for idx, symbol in enumerate(symbols, start=1):
        t0 = time.time()
        report_path = ""
        try:
            res = run_analysis(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                period_zh=period_zh,
                adjust_zh=adjust_zh,
                depth=depth,
            )
            if res.get("ok") and save_individual:
                try:
                    p = save_report_to_file(symbol, res["final_report"])
                    report_path = str(p)
                except Exception:
                    pass  # 落盘失败不影响汇总
            if res.get("ok") and save_snapshots:
                try:
                    save_snapshot(symbol, res.get("market_data") or {})
                except Exception:
                    pass  # 快照失败不影响汇总
        except Exception as e:
            res = {"ok": False, "error": f"未捕获异常：{e}"}
        item = _extract_batch_item(symbol, res, time.time() - t0, report_path)
        results.append(item)
        if on_progress is not None:
            try:
                on_progress(idx, total, symbol, item)
            except Exception:
                pass

    finished_dt = datetime.now()
    finished_at = finished_dt.strftime("%Y-%m-%d %H:%M:%S")
    duration = (finished_dt - started_dt).total_seconds()

    summary_md = build_batch_summary(
        results=results,
        started_at=started_at,
        finished_at=finished_at,
        duration_sec=duration,
        cache_enabled=config.CACHE_ENABLED,
    )

    summary_path = ""
    if save_summary:
        try:
            sp = save_batch_summary_to_file(summary_md)
            summary_path = str(sp)
        except Exception:
            pass

    return {
        "ok": True,
        "started_at": started_at,
        "finished_at": finished_at,
        "duration_sec": duration,
        "results": results,
        "summary_md": summary_md,
        "summary_path": summary_path,
    }
