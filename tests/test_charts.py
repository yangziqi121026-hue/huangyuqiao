"""锁定 src/charts.py 的图表生成行为。

不渲染、不联网；只验证 plotly Figure 结构（trace 数量、类型、x/y 数据正确）。
"""

from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import plotly.graph_objects as go  # noqa: E402

from src.charts import (  # noqa: E402
    make_capital_flow_chart,
    make_kline_chart,
    make_macd_chart,
)


def _fake_history(n: int = 60) -> pd.DataFrame:
    """构造 n 根日 K 的 mock 行情，含 OHLCV + amount + turnover。"""
    base = 100.0
    rng = np.random.default_rng(seed=42)
    closes = base + rng.normal(0, 1.0, n).cumsum()
    return pd.DataFrame({
        "date": [f"2026-{(i // 30) + 1:02d}-{(i % 30) + 1:02d}" for i in range(n)],
        "open": closes - 0.3,
        "high": closes + 0.8,
        "low": closes - 0.8,
        "close": closes,
        "volume": rng.integers(1_000_000, 3_000_000, n).astype(float),
        "amount": rng.uniform(2e8, 5e8, n),
        "turnover": rng.uniform(0.005, 0.02, n),  # 小数形式
    })


class TestKlineChart(unittest.TestCase):
    def test_returns_plotly_figure(self):
        fig = make_kline_chart(_fake_history(80))
        self.assertIsInstance(fig, go.Figure)

    def test_candlestick_trace_present(self):
        fig = make_kline_chart(_fake_history(80))
        types = [type(t).__name__ for t in fig.data]
        self.assertIn("Candlestick", types)

    def test_ma_lines_added_when_enough_bars(self):
        # n=80 时 MA5/10/20/60 都应能算
        fig = make_kline_chart(_fake_history(80))
        names = [t.name for t in fig.data]
        for label in ("MA5", "MA10", "MA20", "MA60"):
            self.assertIn(label, names)

    def test_ma60_skipped_when_few_bars(self):
        # 30 根 K 只能算 MA5/10/20，MA60 跳过
        fig = make_kline_chart(_fake_history(30))
        names = [t.name for t in fig.data]
        self.assertIn("MA5", names)
        self.assertIn("MA20", names)
        self.assertNotIn("MA60", names)

    def test_empty_df_returns_placeholder(self):
        fig = make_kline_chart(pd.DataFrame())
        self.assertIsInstance(fig, go.Figure)
        # 占位图无 candlestick，但有 annotation
        self.assertEqual(len(fig.data), 0)
        self.assertTrue(any("不足以判断" in (a.text or "") for a in fig.layout.annotations))

    def test_none_df_returns_placeholder(self):
        fig = make_kline_chart(None)
        self.assertIsInstance(fig, go.Figure)
        self.assertEqual(len(fig.data), 0)

    def test_missing_ohlc_column_safe(self):
        df = pd.DataFrame({"date": ["2026-05-30"], "close": [100.0]})
        fig = make_kline_chart(df)
        # 缺 open/high/low 视为不足，返回占位
        self.assertEqual(len(fig.data), 0)

    def test_title_includes_disclaimer(self):
        fig = make_kline_chart(_fake_history(80))
        self.assertIn("仅供研究学习", fig.layout.title.text)
        self.assertIn("不构成投资建议", fig.layout.title.text)


class TestMacdChart(unittest.TestCase):
    def test_returns_plotly_figure(self):
        fig = make_macd_chart(_fake_history(40))
        self.assertIsInstance(fig, go.Figure)

    def test_macd_signal_hist_traces_present(self):
        fig = make_macd_chart(_fake_history(40))
        names = [t.name for t in fig.data]
        self.assertIn("MACD", names)
        self.assertIn("Signal", names)
        self.assertIn("MACD Hist", names)

    def test_few_bars_returns_placeholder(self):
        fig = make_macd_chart(_fake_history(10))
        # < 26 根无法算 MACD，返回占位
        self.assertEqual(len(fig.data), 0)

    def test_empty_df_safe(self):
        fig = make_macd_chart(pd.DataFrame())
        self.assertIsInstance(fig, go.Figure)
        self.assertEqual(len(fig.data), 0)

    def test_none_df_safe(self):
        fig = make_macd_chart(None)
        self.assertIsInstance(fig, go.Figure)

    def test_title_includes_disclaimer(self):
        fig = make_macd_chart(_fake_history(40))
        self.assertIn("不构成投资建议", fig.layout.title.text)


class TestCapitalFlowChart(unittest.TestCase):
    def test_returns_plotly_figure(self):
        fig = make_capital_flow_chart(_fake_history(30))
        self.assertIsInstance(fig, go.Figure)

    def test_amount_bar_present(self):
        fig = make_capital_flow_chart(_fake_history(30))
        types = [type(t).__name__ for t in fig.data]
        self.assertIn("Bar", types)
        names = [t.name for t in fig.data]
        self.assertTrue(any("成交额" in n for n in names))

    def test_turnover_line_present(self):
        fig = make_capital_flow_chart(_fake_history(30))
        names = [t.name for t in fig.data]
        self.assertTrue(any("换手率" in n for n in names))

    def test_main_fund_added_when_provided(self):
        df = _fake_history(30)
        cf = {"main_fund_recent": [
            {"date": "2026-05-29", "main_net": 1e9},
            {"date": "2026-05-30", "main_net": -5e8},
        ]}
        fig = make_capital_flow_chart(df, capital_flow=cf)
        names = [t.name for t in fig.data]
        self.assertTrue(any("主力净流入" in n for n in names))

    def test_no_main_fund_when_missing(self):
        fig = make_capital_flow_chart(_fake_history(30), capital_flow={})
        names = [t.name for t in fig.data]
        self.assertFalse(any("主力净流入" in n for n in names))

    def test_empty_df_returns_placeholder(self):
        fig = make_capital_flow_chart(pd.DataFrame())
        self.assertIsInstance(fig, go.Figure)
        self.assertEqual(len(fig.data), 0)

    def test_none_df_returns_placeholder(self):
        fig = make_capital_flow_chart(None)
        self.assertIsInstance(fig, go.Figure)

    def test_df_without_amount_or_turnover_safe(self):
        # 只有 date 列也应不崩，只是没有 trace 数据
        df = pd.DataFrame({"date": ["2026-05-30", "2026-05-29"]})
        fig = make_capital_flow_chart(df)
        self.assertIsInstance(fig, go.Figure)


class TestSafetyMessaging(unittest.TestCase):
    def test_all_chart_titles_include_research_disclaimer(self):
        for fn in (make_kline_chart, make_macd_chart, make_capital_flow_chart):
            fig = fn(_fake_history(80))
            title = (fig.layout.title.text or "")
            self.assertIn("仅供研究学习", title,
                          f"{fn.__name__} 标题缺少研究免责字样")


if __name__ == "__main__":
    unittest.main(verbosity=2)
