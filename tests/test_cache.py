"""锁定 AKShare SQLite 缓存（src/cache.py）行为。

纯标准库 unittest + sqlite3 ':memory:'，不联网、不依赖 akshare。
"""

from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime, timedelta

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.cache import AkshareCache  # noqa: E402


def _yesterday() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class TestBasicGetPut(unittest.TestCase):
    def setUp(self):
        self.cache = AkshareCache(":memory:")

    def test_put_then_get_roundtrip(self):
        payload = {"name": "贵州茅台", "industry": "白酒", "pe": 25.6}
        self.cache.put("600519", "info", payload)
        got = self.cache.get("600519", "info")
        self.assertEqual(got, payload)

    def test_get_miss_returns_none(self):
        self.assertIsNone(self.cache.get("600519", "info"))

    def test_list_payload(self):
        # news 是 list[dict]，必须可序列化
        payload = [{"date": "2026-05-29", "title": "x"}, {"date": "2026-05-30", "title": "y"}]
        self.cache.put("600519", "news", payload)
        self.assertEqual(self.cache.get("600519", "news"), payload)

    def test_nested_dict(self):
        payload = {"snapshot": {"营收": 100.0}, "_sources": ["a", "b"], "_fetched_at": "2026-05-30 21:00:00"}
        self.cache.put("600519", "financials", payload)
        self.assertEqual(self.cache.get("600519", "financials"), payload)


class TestKeyIsolation(unittest.TestCase):
    def setUp(self):
        self.cache = AkshareCache(":memory:")

    def test_different_symbol_isolated(self):
        self.cache.put("600519", "info", {"a": 1})
        self.cache.put("000001", "info", {"a": 2})
        self.assertEqual(self.cache.get("600519", "info"), {"a": 1})
        self.assertEqual(self.cache.get("000001", "info"), {"a": 2})

    def test_different_dimension_isolated(self):
        self.cache.put("600519", "info", {"x": "info"})
        self.cache.put("600519", "financials", {"x": "fin"})
        self.cache.put("600519", "news", [{"x": "news"}])
        self.assertEqual(self.cache.get("600519", "info"), {"x": "info"})
        self.assertEqual(self.cache.get("600519", "financials"), {"x": "fin"})
        self.assertEqual(self.cache.get("600519", "news"), [{"x": "news"}])

    def test_different_date_isolated(self):
        # 同 symbol + 同 dimension + 不同日期 应分开存
        self.cache.put("600519", "info", {"v": "old"}, fetch_date=_yesterday())
        self.cache.put("600519", "info", {"v": "new"}, fetch_date=_today())
        self.assertEqual(self.cache.get("600519", "info", fetch_date=_yesterday()), {"v": "old"})
        self.assertEqual(self.cache.get("600519", "info", fetch_date=_today()), {"v": "new"})

    def test_yesterday_data_does_not_serve_today(self):
        # 昨天的缓存不会被今天的请求命中（按日 key 天然失效）
        self.cache.put("600519", "info", {"v": "old"}, fetch_date=_yesterday())
        self.assertIsNone(self.cache.get("600519", "info"))  # 默认 fetch_date=today


class TestUpsertAndClear(unittest.TestCase):
    def setUp(self):
        self.cache = AkshareCache(":memory:")

    def test_put_same_key_overwrites(self):
        self.cache.put("600519", "info", {"v": 1})
        self.cache.put("600519", "info", {"v": 2})
        self.assertEqual(self.cache.get("600519", "info"), {"v": 2})

    def test_clear_all(self):
        self.cache.put("600519", "info", {"a": 1})
        self.cache.put("000001", "news", [{"x": "y"}])
        deleted = self.cache.clear()
        self.assertEqual(deleted, 2)
        self.assertIsNone(self.cache.get("600519", "info"))
        self.assertIsNone(self.cache.get("000001", "news"))

    def test_clear_by_symbol(self):
        self.cache.put("600519", "info", {"a": 1})
        self.cache.put("600519", "news", [{"x": "y"}])
        self.cache.put("000001", "info", {"a": 2})
        deleted = self.cache.clear(symbol="600519")
        self.assertEqual(deleted, 2)
        self.assertIsNone(self.cache.get("600519", "info"))
        self.assertEqual(self.cache.get("000001", "info"), {"a": 2})

    def test_clear_by_dimension(self):
        self.cache.put("600519", "info", {"a": 1})
        self.cache.put("600519", "news", [{"x": "y"}])
        self.cache.put("000001", "info", {"a": 2})
        deleted = self.cache.clear(dimension="info")
        self.assertEqual(deleted, 2)
        self.assertIsNone(self.cache.get("600519", "info"))
        self.assertIsNone(self.cache.get("000001", "info"))
        self.assertIsNotNone(self.cache.get("600519", "news"))


class TestSerializationSafety(unittest.TestCase):
    """payload 含不可直接 JSON 序列化对象时应 fallback 为字符串，不应抛异常。"""

    def setUp(self):
        self.cache = AkshareCache(":memory:")

    def test_datetime_falls_back_to_str(self):
        payload = {"date": datetime(2026, 5, 30, 21, 0, 0), "name": "x"}
        # put 不应抛
        self.cache.put("600519", "info", payload)
        got = self.cache.get("600519", "info")
        self.assertEqual(got["name"], "x")
        # datetime 被 str 化
        self.assertEqual(got["date"], "2026-05-30 21:00:00")


class TestStats(unittest.TestCase):
    def test_empty_stats(self):
        cache = AkshareCache(":memory:")
        s = cache.stats()
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["by_dimension"], {})

    def test_populated_stats(self):
        cache = AkshareCache(":memory:")
        cache.put("600519", "info", {"a": 1})
        cache.put("600519", "news", [{"x": "y"}])
        cache.put("000001", "info", {"a": 2})
        s = cache.stats()
        self.assertEqual(s["total"], 3)
        self.assertEqual(s["by_dimension"], {"info": 2, "news": 1})


if __name__ == "__main__":
    unittest.main(verbosity=2)
