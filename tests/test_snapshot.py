"""锁定 src/snapshot.py 的序列化与 roundtrip 行为。

依赖 pandas（DataFrame.to_json），不联网、不调 LLM、不依赖 akshare。
落盘测试用 tempfile 隔离，不污染真实 reports/。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pandas as pd  # noqa: E402

from src import snapshot as snap_module  # noqa: E402
from src.snapshot import (  # noqa: E402
    SNAPSHOT_VERSION,
    load_snapshot,
    market_data_to_jsonable,
    save_snapshot,
)


def _sample_history() -> pd.DataFrame:
    df = pd.DataFrame({
        "date": ["2026-05-27", "2026-05-28", "2026-05-29"],
        "open": [100.0, 101.5, 102.0],
        "high": [103.0, 104.5, 103.5],
        "low": [99.0, 100.5, 101.0],
        "close": [102.5, 103.5, 102.8],
        "volume": [1000000, 1100000, 950000],
    })
    df.attrs["source"] = "stock_zh_a_hist（东财）"
    df.attrs["is_mock"] = False
    return df


def _sample_market_data() -> dict:
    return {
        "market": "A股",
        "symbol": "600519",
        "name": "贵州茅台",
        "currency": "CNY",
        "current_price": 1680.5,
        "fetched_at": "2026-05-31 12:00:00",
        "info": {
            "industry": "白酒",
            "pe": 25.6,
            "_sources": ["stock_info_a_code_name（新浪）"],
        },
        "history": _sample_history(),
        "financials": {"latest_period": "20260331", "_sources": ["x"]},
        "capital_flow": {"_sources": ["y"]},
        "news": [{"date": "2026-05-30", "title": "测试新闻", "is_mock": False}],
        "indicators": {"trend": "震荡偏强", "ma20": 1650.0},
        "data_quality": {"price_data": "ok"},
        "errors": [],
    }


class TestMarketDataToJsonable(unittest.TestCase):
    def test_history_dataframe_converted_to_records(self):
        md = _sample_market_data()
        out = market_data_to_jsonable(md)
        self.assertIn("history", out)
        self.assertIsInstance(out["history"], dict)
        recs = out["history"]["records"]
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[0]["date"], "2026-05-27")
        self.assertEqual(recs[2]["close"], 102.8)

    def test_history_attrs_preserved(self):
        md = _sample_market_data()
        out = market_data_to_jsonable(md)
        attrs = out["history"]["attrs"]
        self.assertEqual(attrs["source"], "stock_zh_a_hist（东财）")
        self.assertFalse(attrs["is_mock"])

    def test_nan_in_history_becomes_null(self):
        df = _sample_history()
        df.loc[1, "volume"] = pd.NA
        md = {"history": df}
        out = market_data_to_jsonable(md)
        # NaN 应被序列化为 None（pandas to_json 自动转 null，json.loads 后是 None）
        self.assertIsNone(out["history"]["records"][1]["volume"])

    def test_other_fields_passthrough(self):
        md = _sample_market_data()
        out = market_data_to_jsonable(md)
        self.assertEqual(out["symbol"], "600519")
        self.assertEqual(out["info"]["pe"], 25.6)
        self.assertEqual(out["financials"]["latest_period"], "20260331")
        self.assertEqual(len(out["news"]), 1)

    def test_empty_history_returns_empty_records(self):
        md = {"history": pd.DataFrame()}
        out = market_data_to_jsonable(md)
        self.assertEqual(out["history"]["records"], [])

    def test_none_history_returns_empty_records(self):
        md = {"history": None}
        out = market_data_to_jsonable(md)
        self.assertEqual(out["history"]["records"], [])

    def test_no_history_field(self):
        md = {"symbol": "600519", "name": "x"}
        out = market_data_to_jsonable(md)
        self.assertEqual(out["symbol"], "600519")
        self.assertNotIn("history", out)


class TestSaveLoadRoundtrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_reports = snap_module.REPORTS_DIR
        snap_module.REPORTS_DIR = Path(self.tmp)

    def tearDown(self):
        snap_module.REPORTS_DIR = self._orig_reports
        # 清理临时文件
        for f in Path(self.tmp).iterdir():
            try:
                f.unlink()
            except Exception:
                pass
        try:
            os.rmdir(self.tmp)
        except Exception:
            pass

    def test_save_creates_file_with_expected_name(self):
        md = _sample_market_data()
        path = save_snapshot("600519", md)
        self.assertTrue(path.exists())
        self.assertTrue(path.name.startswith("A股_600519_"))
        self.assertTrue(path.name.endswith(".snapshot.json"))

    def test_payload_envelope_fields(self):
        md = _sample_market_data()
        path = save_snapshot("600519", md)
        payload = load_snapshot(path)
        self.assertEqual(payload["version"], SNAPSHOT_VERSION)
        self.assertEqual(payload["symbol"], "600519")
        self.assertIn("saved_at", payload)
        self.assertIn("market_data", payload)

    def test_roundtrip_preserves_history_records(self):
        md = _sample_market_data()
        path = save_snapshot("600519", md)
        payload = load_snapshot(path)
        recs = payload["market_data"]["history"]["records"]
        self.assertEqual(len(recs), 3)
        self.assertEqual(recs[-1]["close"], 102.8)
        self.assertEqual(recs[0]["date"], "2026-05-27")

    def test_roundtrip_preserves_metadata(self):
        md = _sample_market_data()
        path = save_snapshot("600519", md)
        payload = load_snapshot(path)
        self.assertEqual(payload["market_data"]["info"]["pe"], 25.6)
        self.assertEqual(payload["market_data"]["financials"]["latest_period"],
                         "20260331")
        self.assertEqual(payload["market_data"]["fetched_at"],
                         "2026-05-31 12:00:00")

    def test_unsafe_symbol_chars_sanitized(self):
        # 非字母数字字符在文件名里被替换为下划线
        path = save_snapshot("600/519*?", {"symbol": "x"})
        self.assertTrue(path.exists())
        self.assertNotIn("/", path.name)
        self.assertNotIn("*", path.name)
        self.assertNotIn("?", path.name)

    def test_datetime_object_handled_by_default(self):
        # market_data 里塞一个 datetime 对象不应让 save 崩
        md = {"symbol": "600519", "some_dt": datetime(2026, 5, 31, 12, 0, 0)}
        path = save_snapshot("600519", md)
        payload = load_snapshot(path)
        # datetime → isoformat 字符串
        self.assertIn("2026-05-31T12:00:00", payload["market_data"]["some_dt"])


class TestUtf8Encoding(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self._orig_reports = snap_module.REPORTS_DIR
        snap_module.REPORTS_DIR = Path(self.tmp)

    def tearDown(self):
        snap_module.REPORTS_DIR = self._orig_reports
        for f in Path(self.tmp).iterdir():
            try:
                f.unlink()
            except Exception:
                pass
        try:
            os.rmdir(self.tmp)
        except Exception:
            pass

    def test_chinese_chars_not_escaped(self):
        md = _sample_market_data()
        path = save_snapshot("600519", md)
        raw = path.read_text(encoding="utf-8")
        # 中文应原样保留（ensure_ascii=False），不是 \uXXXX
        self.assertIn("贵州茅台", raw)
        self.assertIn("白酒", raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
