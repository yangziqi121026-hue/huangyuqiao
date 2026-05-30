"""锁定 analysis.metadata 的纯函数行为：来源摘要、最新交易日、财报期。

这些函数从 market_data dict 抽取展示用字段，被 report_generator
和 base_agent._header 共用，是头部"数据可追溯性"的基石。

纯标准库 unittest，不联网、不调 LLM、不依赖 akshare 与 pandas
（用最小 stub mock history）。
"""

from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.analysis.metadata import (  # noqa: E402
    get_financial_period,
    get_latest_trade_day,
    summarize_sources,
)


class _FakeDF:
    """最小 history mock，仅满足 metadata.get_latest_trade_day 调用契约。"""

    def __init__(self, dates, source=None):
        self.empty = len(dates) == 0
        self.columns = ["date"] if dates else []
        self._dates = dates
        self.attrs = {"source": source} if source else {}

    def __getitem__(self, key):
        if key == "date":
            return _FakeSeries(self._dates)
        raise KeyError(key)


class _FakeSeries:
    def __init__(self, dates):
        self._dates = dates
        self.iloc = self  # 简化：self[-1] 直接取列表末尾

    def __getitem__(self, idx):
        return self._dates[idx]


class TestSummarizeSources(unittest.TestCase):
    def test_collect_from_all_dimensions_and_dedup(self):
        md = {
            "info": {"_sources": [
                "stock_info_a_code_name（新浪）",
                "stock_individual_info_em（东财）",
            ]},
            "financials": {"_sources": ["stock_financial_abstract（新浪）"]},
            "capital_flow": {"_sources": ["stock_individual_fund_flow（东财）"]},
            "history": _FakeDF(["2026-05-29"], source="stock_zh_a_hist（东财）"),
            "news": [{"is_mock": False, "title": "x"}],
        }
        out = summarize_sources(md)
        self.assertIn("AKShare 接口聚合", out)
        # 新浪 与 东财 都应被收录且不重复
        self.assertIn("新浪", out)
        self.assertIn("东财", out)
        # 不应有重复
        self.assertEqual(out.count("新浪"), 1)
        self.assertEqual(out.count("东财"), 1)

    def test_strips_comma_suffix(self):
        # '东财，新闻' 这种逗号后缀应只取'东财'，避免重复机构名
        md = {
            "info": {"_sources": ["stock_individual_info_em（东财）"]},
            "news": [{"is_mock": False, "title": "x"}],
        }
        out = summarize_sources(md)
        self.assertIn("东财", out)
        self.assertEqual(out.count("东财"), 1)
        self.assertNotIn("东财，新闻", out)

    def test_all_mock_falls_back_to_warning(self):
        md = {
            "info": {"_sources": []},
            "financials": {"_sources": []},
            "capital_flow": {"_sources": []},
            "history": None,
            "news": [{"is_mock": True, "title": "x"}],
        }
        out = summarize_sources(md)
        self.assertIn("无可识别真实数据源", out)

    def test_empty_market_data(self):
        # 完全空 dict 不应崩，返回 mock 提示
        out = summarize_sources({})
        self.assertIn("无可识别真实数据源", out)

    def test_news_all_mock_excluded(self):
        # 新闻全 mock 时不应加入"东财（新闻）"机构
        md = {
            "info": {"_sources": ["stock_info_a_code_name（新浪）"]},
            "news": [{"is_mock": True, "title": "x"}],
        }
        out = summarize_sources(md)
        self.assertIn("新浪", out)
        # 东财不应被新闻 mock 引入（其它维度也没东财）
        self.assertNotIn("东财", out)


class TestGetLatestTradeDay(unittest.TestCase):
    def test_pick_last_date_from_history(self):
        md = {"history": _FakeDF(["2026-05-27", "2026-05-28", "2026-05-29"])}
        self.assertEqual(get_latest_trade_day(md), "2026-05-29")

    def test_truncate_to_10_chars(self):
        # 'YYYY-MM-DD HH:MM:SS' 形式应只取日期部分
        md = {"history": _FakeDF(["2026-05-29 15:00:00"])}
        self.assertEqual(get_latest_trade_day(md), "2026-05-29")

    def test_empty_history_returns_empty(self):
        self.assertEqual(get_latest_trade_day({"history": _FakeDF([])}), "")

    def test_none_history_returns_empty(self):
        self.assertEqual(get_latest_trade_day({"history": None}), "")

    def test_missing_history_returns_empty(self):
        self.assertEqual(get_latest_trade_day({}), "")


class TestGetFinancialPeriod(unittest.TestCase):
    def test_extract_period(self):
        md = {"financials": {"latest_period": "2026Q1"}}
        self.assertEqual(get_financial_period(md), "2026Q1")

    def test_missing_returns_empty(self):
        self.assertEqual(get_financial_period({"financials": {}}), "")
        self.assertEqual(get_financial_period({}), "")

    def test_none_returns_empty(self):
        self.assertEqual(get_financial_period({"financials": {"latest_period": None}}), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
