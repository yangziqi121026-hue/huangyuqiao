"""CLI 入口：A股只读投研分析。

单股用法：
    python run.py 600519
    python run.py 600519 --depth 深度 --period 周线 --no-save
    python run.py 000001 --start 2024-06-01 --end 2025-05-30

批量用法：
    python run.py --pool pool.txt
    python run.py --pool pool.txt --depth 快速 --no-cache

说明：
- 只读分析，不下单、不接 live。
- 没有 OPENAI_API_KEY 时自动进入 mock 模式（仍可跑通全流程）。
- 单股和批量互斥：要么传 symbol，要么传 --pool。
"""

from __future__ import annotations

import argparse
import sys

from src import config
from src.batch import run_batch
from src.pool import read_pool_file
from src.report_generator import save_report_to_file
from src.snapshot import save_snapshot
from src.workflow import run_analysis


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A股只读投研分析 Agent")
    # symbol 可选：批量模式 (--pool) 时不传
    parser.add_argument("symbol", nargs="?", default=None,
                        help="A股 6 位代码，如 600519（批量模式 --pool 时不传）")
    parser.add_argument("--pool", default="",
                        help="批量模式：从文件读 6 位代码（一行一个，# 之后为注释）")
    parser.add_argument("--depth", default="标准", choices=config.ANALYSIS_DEPTHS)
    parser.add_argument("--period", default="日线", choices=list(config.PERIOD_MAP.keys()))
    parser.add_argument("--adjust", default="前复权", choices=list(config.ADJUST_MAP.keys()))
    parser.add_argument("--start", default="", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", default="", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--no-save", action="store_true", help="不落地 reports/")
    parser.add_argument("--no-snapshot", action="store_true",
                        help="不落 market_data 快照 JSON（默认会落，用于复现 / A-B 对比）")
    parser.add_argument("--no-cache", action="store_true",
                        help="禁用 AKShare 缓存（强制重抓 info/financials/news）")
    parser.add_argument("--quiet-cache", action="store_true",
                        help="不打 [cache] 命中/未命中日志（批量跑可能 noisy）")
    return parser


def _print_config_line():
    s = config.get_settings_summary()
    print(f"[配置] model={s['model']} mock_mode={s['mock_mode']} 只读={s['only_readonly']} "
          f"下单={s['enable_trading']} live={s['enable_live']} 市场={s['only_market']} "
          f"cache={s['cache_enabled']}")
    if s["mock_mode"]:
        print("[提示] 当前为 mock 模式（无 API Key 或未联网），结论仅用于流程验证。")


def _run_single(args) -> int:
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
        return 1

    print("\n" + "=" * 60)
    print(result["final_report"])
    print("=" * 60)
    print(f"[结论] {result['conclusion']}　[风险等级] {result['risk_level']}")

    if not args.no_save:
        path = save_report_to_file(args.symbol, result["final_report"])
        print(f"[已保存] {path}")
        if not args.no_snapshot:
            try:
                sp = save_snapshot(args.symbol, result.get("market_data") or {})
                print(f"[快照] {sp.name}（可用于复现 / A-B 模型对比）")
            except Exception as e:
                print(f"[快照] 落地失败：{e}（不影响报告，已忽略）")
    return 0


def _run_pool(args) -> int:
    symbols = read_pool_file(args.pool)
    if not symbols:
        print(f"[失败] pool 文件读不到合法代码：{args.pool}")
        print("  - 文件不存在 / 全是注释空行 / 全部非法代码（非 0/3/6 开头的 6 位数字）")
        return 1

    print(f"[批量] 共 {len(symbols)} 只标的：{', '.join(symbols)}")
    print(f"[开始] 批量分析（依次串行，单只失败不影响整批）...")

    def on_progress(idx, total, symbol, item):
        if item.get("ok"):
            print(f"  [{idx}/{total}] {symbol} {item.get('name', '')} "
                  f"→ {item.get('conclusion', '')}（风险 {item.get('risk_level', '')}, "
                  f"{item.get('duration_sec', 0):.1f}s）")
        else:
            print(f"  [{idx}/{total}] {symbol} ✗ 失败：{item.get('error', '')}")

    out = run_batch(
        symbols,
        start_date=args.start,
        end_date=args.end,
        period_zh=args.period,
        adjust_zh=args.adjust,
        depth=args.depth,
        save_individual=not args.no_save,
        save_summary=not args.no_save,
        save_snapshots=not args.no_save and not args.no_snapshot,
        on_progress=on_progress,
    )

    ok_count = sum(1 for r in out["results"] if r.get("ok"))
    fail_count = len(out["results"]) - ok_count
    print("\n" + "=" * 60)
    print(f"[批量完成] 成功 {ok_count} / 失败 {fail_count}（总耗时 "
          f"{out['duration_sec']:.1f}s ≈ {out['duration_sec']/60:.1f}min）")
    if out.get("summary_path"):
        print(f"[汇总已保存] {out['summary_path']}")
    return 0 if ok_count > 0 else 1


def main():
    args = _build_parser().parse_args()

    # 互斥校验：必须二选一
    if bool(args.symbol) == bool(args.pool):
        print("[错误] 必须二选一：传单只代码（如 `run.py 600519`）或 `--pool pool.txt`")
        sys.exit(2)

    if args.no_cache:
        # 仅本次进程禁用，不写 .env
        config.CACHE_ENABLED = False
    if args.quiet_cache:
        config.CACHE_VERBOSE = False

    _print_config_line()

    if args.pool:
        sys.exit(_run_pool(args))
    else:
        sys.exit(_run_single(args))


if __name__ == "__main__":
    main()
