"""锁定 `_cached_safe_call` 的 verbose 日志行为：

- CACHE_VERBOSE=True 时每次命中/未命中打 `[cache] {dim} hit/miss → fetched ({symbol})`
- CACHE_VERBOSE=False 时不打任何 `[cache]` 日志

用 ':memory:' SQLite + 临时关闭限频 sleep，纯 stdlib 测试，不联网。
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src import config  # noqa: E402
from src import cache as cache_module  # noqa: E402
from src.akshare_provider import _cached_safe_call  # noqa: E402


class _ConfigPatch:
    """局部覆盖 config 字段并在 tearDown 恢复，避免污染其它测试。"""

    def __init__(self):
        self._orig: dict = {}

    def set(self, name: str, value):
        if name not in self._orig:
            self._orig[name] = getattr(config, name)
        setattr(config, name, value)

    def restore(self):
        for name, value in self._orig.items():
            setattr(config, name, value)
        self._orig.clear()


class _CacheVerboseBase(unittest.TestCase):
    def setUp(self):
        self.cp = _ConfigPatch()
        # 用 in-memory SQLite，独占进程级单例 slot
        self.cp.set("CACHE_DB_PATH", ":memory:")
        self.cp.set("CACHE_ENABLED", True)
        # 关掉限频 sleep 让测试秒级跑完
        self.cp.set("AKSHARE_FETCH_SLEEP_SEC", 0.0)
        # 清单例避免与其它测试共享 ":memory:" 实例
        cache_module._cache_instances.clear()

    def tearDown(self):
        self.cp.restore()
        cache_module._cache_instances.clear()

    @staticmethod
    def _capture(fn):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            result = fn()
        return buf.getvalue(), result


class TestVerboseOn(_CacheVerboseBase):
    def test_miss_then_hit_log_lines(self):
        self.cp.set("CACHE_VERBOSE", True)
        fake = lambda symbol: {"k": "v", "_sources": ["mock"]}

        out1, r1 = self._capture(
            lambda: _cached_safe_call(fake, "600519", "info", default={})
        )
        self.assertEqual(r1["k"], "v")
        self.assertIn("[cache] info miss → fetched (600519)", out1)
        self.assertNotIn("hit", out1)

        out2, r2 = self._capture(
            lambda: _cached_safe_call(fake, "600519", "info", default={})
        )
        self.assertEqual(r2["k"], "v")
        self.assertIn("[cache] info hit (600519)", out2)
        self.assertNotIn("miss", out2)

    def test_different_dimensions_logged_separately(self):
        self.cp.set("CACHE_VERBOSE", True)
        fake_info = lambda s: {"x": 1}
        fake_fin = lambda s: {"y": 2}
        out, _ = self._capture(lambda: (
            _cached_safe_call(fake_info, "600519", "info", default={}),
            _cached_safe_call(fake_fin, "600519", "financials", default={}),
        ))
        self.assertIn("[cache] info miss → fetched (600519)", out)
        self.assertIn("[cache] financials miss → fetched (600519)", out)

    def test_empty_result_marked_not_cached(self):
        # 返回 default 时既不入缓存，也明确打"not cached"标记
        self.cp.set("CACHE_VERBOSE", True)
        fake_empty = lambda s: {}  # 与 default={} 相等
        out, r = self._capture(
            lambda: _cached_safe_call(fake_empty, "600519", "info", default={})
        )
        self.assertEqual(r, {})
        self.assertIn("not cached", out)
        # 再次调用仍 miss（没有入库）
        out2, _ = self._capture(
            lambda: _cached_safe_call(fake_empty, "600519", "info", default={})
        )
        self.assertNotIn("hit", out2)


class TestVerboseOff(_CacheVerboseBase):
    def test_no_log_when_quiet(self):
        self.cp.set("CACHE_VERBOSE", False)
        fake = lambda s: {"k": "v"}
        # miss
        out1, _ = self._capture(
            lambda: _cached_safe_call(fake, "600519", "info", default={})
        )
        self.assertNotIn("[cache]", out1)
        # hit
        out2, _ = self._capture(
            lambda: _cached_safe_call(fake, "600519", "info", default={})
        )
        self.assertNotIn("[cache]", out2)


class TestCacheDisabled(_CacheVerboseBase):
    def test_no_log_when_cache_disabled(self):
        # CACHE_ENABLED=False 时整个缓存层旁路，也不应该打 [cache] 日志
        self.cp.set("CACHE_ENABLED", False)
        self.cp.set("CACHE_VERBOSE", True)
        fake = lambda s: {"k": "v"}
        out, r = self._capture(
            lambda: _cached_safe_call(fake, "600519", "info", default={})
        )
        self.assertEqual(r["k"], "v")
        self.assertNotIn("[cache]", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
