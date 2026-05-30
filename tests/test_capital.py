"""锁定资金面「成交额/换手率」从日K兜底的纯计算逻辑：

- 东财源（stock_zh_a_hist）：列名 turnover_rate，已是百分比 → 直接用。
- 新浪源（stock_zh_a_daily）：列名 turnover，是小数（成交量/流通股）→ ×100 转百分比。
- 空表 / 缺列 / None：安全返回 {amount_latest: None, turnover_rate_latest: None}，绝不抛异常。

纯标准库 unittest + pandas，无需网络 / akshare / LLM。
运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import sys
import unittest

import pandas as pd

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.akshare_provider import _capital_metrics_from_hist  # noqa: E402


class TestCapitalMetricsFromHist(unittest.TestCase):
    def test_eastmoney_turnover_rate_used_directly(self):
        # 东财源：turnover_rate 已是百分比，直接采用
        df = pd.DataFrame({
            "date": ["2025-01-01", "2025-01-02"],
            "amount": [1.0e8, 2.5e8],
            "turnover_rate": [0.50, 0.61],
        })
        m = _capital_metrics_from_hist(df)
        self.assertEqual(m["amount_latest"], 2.5e8)
        self.assertEqual(m["turnover_rate_latest"], 0.61)

    def test_sina_turnover_fraction_scaled_to_percent(self):
        # 新浪源：turnover 是小数 → ×100
        df = pd.DataFrame({
            "date": ["2025-01-01", "2025-01-02"],
            "amount": [1.0e8, 1.515692068e9],
            "turnover": [0.005, 0.007211154269443679],
        })
        m = _capital_metrics_from_hist(df)
        self.assertEqual(m["amount_latest"], 1.515692068e9)
        self.assertEqual(m["turnover_rate_latest"], round(0.007211154269443679 * 100, 4))

    def test_turnover_rate_preferred_over_turnover(self):
        # 两列都在时，优先用东财的 turnover_rate（百分比），不再 ×100
        df = pd.DataFrame({
            "amount": [3.0e8],
            "turnover_rate": [1.23],
            "turnover": [0.0123],
        })
        m = _capital_metrics_from_hist(df)
        self.assertEqual(m["turnover_rate_latest"], 1.23)

    def test_amount_only(self):
        df = pd.DataFrame({"amount": [9.9e8]})
        m = _capital_metrics_from_hist(df)
        self.assertEqual(m["amount_latest"], 9.9e8)
        self.assertIsNone(m["turnover_rate_latest"])

    def test_empty_df(self):
        m = _capital_metrics_from_hist(pd.DataFrame())
        self.assertIsNone(m["amount_latest"])
        self.assertIsNone(m["turnover_rate_latest"])

    def test_none_input(self):
        m = _capital_metrics_from_hist(None)
        self.assertIsNone(m["amount_latest"])
        self.assertIsNone(m["turnover_rate_latest"])

    def test_missing_columns(self):
        df = pd.DataFrame({"date": ["2025-01-01"], "close": [10.0]})
        m = _capital_metrics_from_hist(df)
        self.assertIsNone(m["amount_latest"])
        self.assertIsNone(m["turnover_rate_latest"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
