"""CLI 入口：A股只读投研分析。

用法：
    python run.py 600519
    python run.py 600519 --depth 深度 --period 周线 --no-save
    python run.py 000001 --start 2024-06-01 --end 2025-05-30

说明：
- 只读分析，不下单、不接 live。
- 没有 OPENAI_API_KEY 时自动进入 mock 模式（仍可跑通全流程）。
"""

from __future__ import annotations

import argparse
import sys

from src import config
from src.workflow import run_analysis
from src.report_generator import save_report_to_file


def main():
    parser = argparse.ArgumentParser(description="A股只读投研分析 Agent")
    parser.add_argument("symbol", help="A股 6 位代码，如 600519")
    parser.add_argument("--depth", default="标准", choices=config.ANALYSIS_DEPTHS)
    parser.add_argument("--period", default="日线", choices=list(config.PERIOD_MAP.keys()))
    parser.add_argument("--adjust", default="前复权", choices=list(config.ADJUST_MAP.keys()))
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--no-save", action="store_true", help="不落地 reports/")
    parser.add_argument("--no-cache", action="store_true",
                        help="禁用 AKShare 缓存（强制重抓 info/financials/news）")
    args = parser.parse_args()

    if args.no_cache:
        # 仅本次进程禁用，不写 .env
        config.CACHE_ENABLED = False

    s = config.get_settings_summary()
    print(f"[配置] model={s['model']} mock_mode={s['mock_mode']} 只读={s['only_readonly']} "
          f"下单={s['enable_trading']} live={s['enable_live']} 市场={s['only_market']} "
          f"cache={s['cache_enabled']}")
    if s["mock_mode"]:
        print("[提示] 当前为 mock 模式（无 API Key 或未联网），结论仅用于流程验证。")

    print(f"[开始] 分析 {args.symbol} ...")

    def on_stage(stage_id, stage_zh, ctx):
        print(f"  - {stage_zh}")

    result = run_analysis(
        symbol=args.symbol,
        start_date=args.start,
        end_date=args.end,
        period_zh=args.period,
        adjust_zh=args.adjust,
        depth=args.depth,
        on_stage=on_stage,
    )

    if not result["ok"]:
        print(f"[失败] {result['error']}")
        sys.exit(1)

    print("\n" + "=" * 60)
    print(result["final_report"])
    print("=" * 60)
    print(f"[结论] {result['conclusion']}　[风险等级] {result['risk_level']}")

    if not args.no_save:
        path = save_report_to_file(args.symbol, result["final_report"])
        print(f"[已保存] {path}")


if __name__ == "__main__":
    main()
