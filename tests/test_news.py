"""锁定消息面新闻的「去重 + 时效过滤 + 按时间降序」纯逻辑：

- _parse_news_dt：多格式解析，解析不了返回 None（不误杀）。
- _dedup_and_filter_news：
    * 标题去重（去空白/大小写不敏感），保留最新一条；
    * 时效过滤（早于 cutoff 丢弃，无日期保留）；
    * 按时间降序（新在前、无日期排后）；
    * 截断到 limit；
    * 全部过期时退回全量（不让消息面整段空白）。

纯标准库 unittest，无需网络 / akshare / LLM。
运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.akshare_provider import (  # noqa: E402
    _parse_news_dt,
    _norm_title,
    _dedup_and_filter_news,
)

NOW = datetime(2026, 5, 30, 12, 0, 0)


def _n(title, date):
    return {"title": title, "date": date, "summary": title, "url": "", "is_mock": False}


class TestParseNewsDt(unittest.TestCase):
    def test_common_formats(self):
        self.assertEqual(_parse_news_dt("2026-05-29 10:30:00"), datetime(2026, 5, 29, 10, 30, 0))
        self.assertEqual(_parse_news_dt("2026-05-29 10:30"), datetime(2026, 5, 29, 10, 30))
        self.assertEqual(_parse_news_dt("2026-05-29"), datetime(2026, 5, 29))
        self.assertEqual(_parse_news_dt("2026/05/29 10:30:00"), datetime(2026, 5, 29, 10, 30, 0))

    def test_unparseable_returns_none(self):
        self.assertIsNone(_parse_news_dt(""))
        self.assertIsNone(_parse_news_dt(None))
        self.assertIsNone(_parse_news_dt("昨天"))


class TestNormTitle(unittest.TestCase):
    def test_whitespace_and_case(self):
        self.assertEqual(_norm_title("  Foo  Bar "), _norm_title("foo bar"))
        self.assertEqual(_norm_title("贵州 茅台 大涨"), _norm_title("贵州茅台大涨"))
        self.assertEqual(_norm_title(None), "")


class TestDedupAndFilterNews(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(_dedup_and_filter_news([], now=NOW), [])

    def test_dedup_by_title(self):
        items = [
            _n("贵州茅台发布年报", "2026-05-29 09:00:00"),
            _n("贵州茅台 发布年报", "2026-05-28 09:00:00"),  # 同标题（空白不同）→ 去重
            _n("行业政策点评", "2026-05-27 09:00:00"),
        ]
        out = _dedup_and_filter_news(items, now=NOW)
        titles = [_norm_title(x["title"]) for x in out]
        self.assertEqual(len(out), 2)
        # 去重保留最新一条（5-29 那条）
        self.assertEqual(out[0]["date"], "2026-05-29 09:00:00")
        self.assertIn(_norm_title("行业政策点评"), titles)

    def test_time_filter_drops_old(self):
        items = [
            _n("新消息", "2026-05-29"),
            _n("旧消息", "2026-01-01"),  # 距今约 5 个月 > 30 天 → 丢弃
        ]
        out = _dedup_and_filter_news(items, now=NOW, max_age_days=30)
        titles = [x["title"] for x in out]
        self.assertIn("新消息", titles)
        self.assertNotIn("旧消息", titles)

    def test_sorted_newest_first(self):
        items = [
            _n("中", "2026-05-20"),
            _n("新", "2026-05-29"),
            _n("旧", "2026-05-10"),
        ]
        out = _dedup_and_filter_news(items, now=NOW, max_age_days=365)
        self.assertEqual([x["title"] for x in out], ["新", "中", "旧"])

    def test_undated_kept_and_last(self):
        items = [
            _n("有日期", "2026-05-29"),
            _n("无日期", ""),  # 解析不了 → 保留，排在有日期之后
        ]
        out = _dedup_and_filter_news(items, now=NOW, max_age_days=30)
        self.assertEqual([x["title"] for x in out], ["有日期", "无日期"])

    def test_limit_respected(self):
        items = [_n(f"news-{i}", f"2026-05-{10 + i:02d}") for i in range(20)]
        out = _dedup_and_filter_news(items, now=NOW, max_age_days=3650, limit=5)
        self.assertEqual(len(out), 5)

    def test_all_old_falls_back_not_empty(self):
        # 全部过期：不应返回空，而是退回按时间降序的全量
        items = [
            _n("旧1", "2025-01-01"),
            _n("旧2", "2025-02-01"),
        ]
        out = _dedup_and_filter_news(items, now=NOW, max_age_days=30)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0]["title"], "旧2")  # 较新的在前


if __name__ == "__main__":
    unittest.main(verbosity=2)
