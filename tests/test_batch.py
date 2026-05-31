"""锁定 src/batch.py 的编排行为：

- run_analysis 用 mock 替换（不联网、不调 LLM、不依赖 akshare）
- 部分股票失败不影响整批
- _extract_batch_item 字段抽取正确
- on_progress 回调按顺序触发
- save_individual / save_summary 行为
"""

from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.batch import _extract_batch_item, run_batch  # noqa: E402


def _fake_ok_result(symbol: str, conclusion: str, name: str = "",
                    fund="偏强", tech="中性", conflict=False) -> dict:
    """伪造 run_analysis 的 ok=True 返回。"""
    return {
        "ok": True,
        "error": None,
        "market_data": {
            "symbol": symbol,
            "name": name or f"测试-{symbol}",
            "history": None,  # get_latest_trade_day 应安全降级
        },
        "agent_outputs": {},
        "conflict": {
            "conflict": conflict,
            "insufficient": False,
            "fundamental_bias": fund,
            "technical_bias": tech,
            "message": "",
        },
        "data_quality": {},
        "final_report": f"# Mock 报告 {symbol}\n\n本报告仅供研究学习。\n",
        "conclusion": conclusion,
        "risk_level": "中",
        "depth": "标准",
    }


def _fake_fail_result(error: str = "akshare 异常") -> dict:
    return {"ok": False, "error": error, "market_data": {}, "agent_outputs": {},
            "conflict": {}, "data_quality": {}, "final_report": "",
            "conclusion": "", "risk_level": "", "depth": "标准"}


class TestExtractBatchItem(unittest.TestCase):
    def test_ok_result_extracted_fully(self):
        res = _fake_ok_result("600519", "谨慎关注", name="贵州茅台",
                              fund="偏强", tech="偏空", conflict=True)
        item = _extract_batch_item("600519", res, duration=12.3,
                                   report_path="/abs/path.md")
        self.assertTrue(item["ok"])
        self.assertEqual(item["symbol"], "600519")
        self.assertEqual(item["name"], "贵州茅台")
        self.assertEqual(item["conclusion"], "谨慎关注")
        self.assertEqual(item["risk_level"], "中")
        self.assertEqual(item["fundamental_bias"], "偏强")
        self.assertEqual(item["technical_bias"], "偏空")
        self.assertTrue(item["conflict"])
        self.assertFalse(item["insufficient"])
        self.assertEqual(item["report_path"], "/abs/path.md")
        self.assertAlmostEqual(item["duration_sec"], 12.3)

    def test_fail_result_minimal_shape(self):
        res = _fake_fail_result("代码非法")
        item = _extract_batch_item("999999", res, duration=0.5)
        self.assertFalse(item["ok"])
        self.assertEqual(item["symbol"], "999999")
        self.assertEqual(item["error"], "代码非法")
        # 失败 item 不应包含 ok=True 才有的字段
        self.assertNotIn("conclusion", item)
        self.assertNotIn("name", item)

    def test_no_history_safe_default(self):
        # market_data 没有 history 时，latest_trade_day 应降级为"不足以判断"
        res = _fake_ok_result("600519", "观察")
        item = _extract_batch_item("600519", res, duration=1.0)
        self.assertEqual(item["latest_trade_day"], "不足以判断")


class TestRunBatchOrchestration(unittest.TestCase):
    def test_mixed_success_and_failure(self):
        def fake_run_analysis(symbol, **kwargs):
            if symbol == "999999":
                return _fake_fail_result("代码非法")
            return _fake_ok_result(symbol, "谨慎关注")

        with patch("src.batch.run_analysis", side_effect=fake_run_analysis):
            out = run_batch(
                ["600519", "999999", "000001"],
                save_individual=False, save_summary=False,
            )

        self.assertTrue(out["ok"])
        self.assertEqual(len(out["results"]), 3)
        # 顺序保留
        self.assertEqual([r["symbol"] for r in out["results"]],
                         ["600519", "999999", "000001"])
        # 失败标的 ok=False，error 字段在
        fail = next(r for r in out["results"] if r["symbol"] == "999999")
        self.assertFalse(fail["ok"])
        self.assertIn("代码非法", fail["error"])
        # 成功标的 ok=True
        for sym in ("600519", "000001"):
            it = next(r for r in out["results"] if r["symbol"] == sym)
            self.assertTrue(it["ok"])

    def test_uncaught_exception_inside_run_analysis_caught(self):
        # 即使 run_analysis 自己抛了（按理 run_analysis 内部 catch 了，但兜底）
        def boom(symbol, **kwargs):
            raise RuntimeError(f"模拟内部崩 {symbol}")

        with patch("src.batch.run_analysis", side_effect=boom):
            out = run_batch(["600519", "000001"],
                            save_individual=False, save_summary=False)
        self.assertEqual(len(out["results"]), 2)
        for r in out["results"]:
            self.assertFalse(r["ok"])
            self.assertIn("未捕获异常", r["error"])

    def test_on_progress_called_in_order(self):
        calls = []

        def fake_run_analysis(symbol, **kwargs):
            return _fake_ok_result(symbol, "观察")

        def progress(idx, total, symbol, item):
            calls.append((idx, total, symbol, item.get("ok")))

        with patch("src.batch.run_analysis", side_effect=fake_run_analysis):
            run_batch(["600519", "000001", "300750"],
                      save_individual=False, save_summary=False,
                      on_progress=progress)

        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], (1, 3, "600519", True))
        self.assertEqual(calls[1], (2, 3, "000001", True))
        self.assertEqual(calls[2], (3, 3, "300750", True))

    def test_summary_md_generated(self):
        def fake_run_analysis(symbol, **kwargs):
            return _fake_ok_result(symbol, "高风险")

        with patch("src.batch.run_analysis", side_effect=fake_run_analysis):
            out = run_batch(["600519", "000001"],
                            save_individual=False, save_summary=False)
        # 汇总 md 必须包含两只代码 + 高风险结论 + 元信息
        self.assertIn("600519", out["summary_md"])
        self.assertIn("000001", out["summary_md"])
        self.assertIn("高风险", out["summary_md"])
        self.assertIn("分析模型", out["summary_md"])
        self.assertIn("启动时间", out["summary_md"])
        self.assertIn("总耗时", out["summary_md"])

    def test_empty_symbols_returns_valid_summary(self):
        with patch("src.batch.run_analysis"):
            out = run_batch([], save_individual=False, save_summary=False)
        self.assertTrue(out["ok"])
        self.assertEqual(out["results"], [])
        self.assertIn("标的数量：0", out["summary_md"])

    def test_progress_callback_exception_does_not_kill_batch(self):
        def fake_run_analysis(symbol, **kwargs):
            return _fake_ok_result(symbol, "观察")

        def bad_progress(*args, **kwargs):
            raise RuntimeError("回调挂了")

        with patch("src.batch.run_analysis", side_effect=fake_run_analysis):
            out = run_batch(["600519", "000001"],
                            save_individual=False, save_summary=False,
                            on_progress=bad_progress)
        self.assertEqual(len(out["results"]), 2)
        self.assertTrue(all(r["ok"] for r in out["results"]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
