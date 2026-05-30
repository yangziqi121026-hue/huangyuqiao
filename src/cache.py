"""AKShare 抓取结果的 SQLite 缓存（按日失效）。

设计：
- Key = (symbol, dimension, fetch_date_YYYY-MM-DD)，隔天自动失效（无需手动 TTL）。
- Payload 用 JSON 序列化；遇到不可序列化对象（如 pandas Timestamp / numpy 标量）
  自动 fallback 为字符串。
- 只缓存"变化慢"的维度（info / financials / news）；history / capital_flow 不进缓存。
- 全 stdlib，无第三方依赖；支持 `:memory:` 便于测试。

只读分析专用：缓存里只有 AKShare 公开数据，绝不存储任何 API Key、用户态、订单。
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

_SCHEMA = """
CREATE TABLE IF NOT EXISTS akshare_cache (
    symbol     TEXT NOT NULL,
    dimension  TEXT NOT NULL,
    fetch_date TEXT NOT NULL,
    payload    TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (symbol, dimension, fetch_date)
)
"""


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class AkshareCache:
    """线程安全的 SQLite 缓存。

    用法：
        cache = AkshareCache("data/cache.db")
        if (hit := cache.get("600519", "info")) is not None:
            return hit
        result = expensive_akshare_call(...)
        cache.put("600519", "info", result)
    """

    def __init__(self, db_path: Union[str, Path] = ":memory:"):
        self.db_path = str(db_path)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def get(
        self,
        symbol: str,
        dimension: str,
        fetch_date: Optional[str] = None,
    ) -> Optional[Any]:
        fd = fetch_date or _today()
        with self._lock:
            row = self._conn.execute(
                "SELECT payload FROM akshare_cache WHERE symbol=? AND dimension=? AND fetch_date=?",
                (symbol, dimension, fd),
            ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except json.JSONDecodeError:
            return None

    def put(
        self,
        symbol: str,
        dimension: str,
        payload: Any,
        fetch_date: Optional[str] = None,
    ) -> None:
        fd = fetch_date or _today()
        # default=str 兜底不可序列化对象（pandas Timestamp / numpy 标量 / Decimal 等）
        # 注：调用方应确保 payload 是 dict / list / 标量；DataFrame 等大对象不应入缓存。
        blob = json.dumps(payload, ensure_ascii=False, default=str)
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO akshare_cache "
                "(symbol, dimension, fetch_date, payload, created_at) VALUES (?, ?, ?, ?, ?)",
                (symbol, dimension, fd, blob, _now_iso()),
            )
            self._conn.commit()

    def clear(
        self,
        symbol: Optional[str] = None,
        dimension: Optional[str] = None,
    ) -> int:
        """删条件匹配的缓存条目；不传任何参数即清空。返回删除条数。"""
        conds, args = [], []
        if symbol is not None:
            conds.append("symbol=?")
            args.append(symbol)
        if dimension is not None:
            conds.append("dimension=?")
            args.append(dimension)
        where = (" WHERE " + " AND ".join(conds)) if conds else ""
        with self._lock:
            cur = self._conn.execute(f"DELETE FROM akshare_cache{where}", args)
            self._conn.commit()
            return cur.rowcount

    def stats(self) -> dict:
        """返回简单统计：总条数 / 各维度计数 / 各日期计数。"""
        with self._lock:
            total = self._conn.execute("SELECT COUNT(*) FROM akshare_cache").fetchone()[0]
            by_dim = dict(self._conn.execute(
                "SELECT dimension, COUNT(*) FROM akshare_cache GROUP BY dimension"
            ).fetchall())
            by_date = dict(self._conn.execute(
                "SELECT fetch_date, COUNT(*) FROM akshare_cache GROUP BY fetch_date"
            ).fetchall())
        return {"total": total, "by_dimension": by_dim, "by_date": by_date}

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# 进程级单例（按 db 路径区分）
_cache_instances: dict[str, AkshareCache] = {}
_singleton_lock = threading.Lock()


def get_cache(db_path: Union[str, Path]) -> AkshareCache:
    """按路径返回单例缓存实例。同进程内同路径共享同一个连接。"""
    key = str(db_path)
    with _singleton_lock:
        if key not in _cache_instances:
            _cache_instances[key] = AkshareCache(key)
        return _cache_instances[key]
