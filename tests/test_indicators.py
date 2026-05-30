"""锁定技术指标计算（indicators.compute_indicators）的单元测试。

纯标准库 unittest + pandas/numpy，无需网络 / akshare / LLM。
运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import math
import os
import sys
import unittest

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.indicators import compute_indicators  # noqa: E402


def _mkdf(closes, highs=None, lows=None, volumes=None):
    n = len(closes)
    highs = highs if highs is not None else closes
    lows = lows if lows is not None else closes
    volumes = volumes if volumes is not None else [1000.0] * n
    dates = pd.date_range("2025-01-01", periods=n, freq="B").strftime("%Y-%m-%d")
    return pd.DataFrame({
        "date": dates,
        "open": closes,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": volumes,
    })


class TestComputeIndicatorsDefaults(unittest.TestCase):
    def test_empty_df(self):
        r = compute_indicators(pd.DataFrame())
        self.assertEqual(r["bars"], 0)
        self.assertEqual(r["trend"], "不足以判断")
        self.assertTrue(math.isnan(r["ma5"]))

    def test_missing_required_columns(self):
        df = pd.DataFrame({"date": ["2025-01-01"], "close": [10.0]})
        r = compute_indicators(df)
        self.assertEqual(r["bars"], 0)
        self.assertEqual(r["trend"], "不足以判断")

    def test_none_input(self):
        r = compute_indicators(None)
        self.assertEqual(r["bars"], 0)


class TestComputeIndicatorsTrend(unittest.TestCase):
    def test_uptrend_is_bull(self):
        df = _mkdf([float(i) for i in range(1, 81)])  # 单调上升
        r = compute_indicators(df)
        self.assertEqual(r["bars"], 80)
        self.assertEqual(r["trend"], "多头排列（上升趋势）")
        self.assertTrue(r["ma5"] > r["ma20"] > r["ma60"])

    def test_downtrend_is_bear(self):
        df = _mkdf([float(i) for i in range(80, 0, -1)])  # 单调下降
        r = compute_indicators(df)
        self.assertEqual(r["trend"], "空头排列（下降趋势）")
        self.assertTrue(r["ma5"] < r["ma20"] < r["ma60"])

    def test_flat_is_consolidation(self):
        df = _mkdf([50.0] * 80)  # 横盘
        r = compute_indicators(df)
        self.assertEqual(r["trend"], "震荡")
        self.assertEqual(r["ma5"], 50.0)
        self.assertEqual(r["ma20"], 50.0)
        self.assertEqual(r["ma60"], 50.0)
        # 无涨跌 → RSI 回退到中性 50
        self.assertEqual(r["rsi14"], 50.0)


class TestComputeIndicatorsValues(unittest.TestCase):
    def test_support_resistance(self):
        closes = [10.0] * 30
        highs = [c + 2 for c in closes]
        lows = [c - 3 for c in closes]
        highs[15] = 20.0  # 最高
        lows[10] = 4.0     # 最低
        df = _mkdf(closes, highs=highs, lows=lows)
        r = compute_indicators(df)
        self.assertEqual(r["resistance"], 20.0)
        self.assertEqual(r["support"], 4.0)

    def test_pct_20d_and_volume_change(self):
        closes = [float(i) for i in range(1, 81)]  # close[-21]=60, last=80
        df = _mkdf(closes)  # 成交量恒定
        r = compute_indicators(df)
        self.assertAlmostEqual(r["pct_20d"], round((80 - 60) / 60 * 100, 2), places=2)
        self.assertEqual(r["volume_change"], 0.0)  # 量恒定 → 0%

    def test_bars_count(self):
        df = _mkdf([float(i) for i in range(1, 26)])
        self.assertEqual(compute_indicators(df)["bars"], 25)


if __name__ == "__main__":
    unittest.main(verbosity=2)
