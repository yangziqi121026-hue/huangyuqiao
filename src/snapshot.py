"""市场数据快照存档（JSON），便于复现与 A/B 模型对比。

落地路径：`reports/A股_{symbol}_{ts}.snapshot.json`

用途：
- **复现**：同一份 snapshot 重跑 LLM 部分，不重抓 AKShare
- **A/B 对比**：同一份 snapshot 喂给不同 LLM（DeepSeek / Qwen / GPT），对比结论差异
- **审计**：保留每次跑使用的真实数据切片，方便事后回溯

JSON-safe 序列化策略：
- `history`（pd.DataFrame）→ {records: list of dict, attrs: dict}；NaN → null；Timestamp → ISO
- 其它维度（info / financials / capital_flow / news / indicators / data_quality）都是
  dict / list / scalar，用 `json.dumps(default=_default)` 兜底 numpy 标量 / datetime
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Union

from .config import REPORTS_DIR

SNAPSHOT_VERSION = 1


def _df_to_records(df) -> list:
    """DataFrame → list of dict。NaN → null，Timestamp → ISO 字符串。"""
    if df is None:
        return []
    try:
        if hasattr(df, "empty") and df.empty:
            return []
        # pandas 自带的 to_json 处理 NaN / Timestamp 最稳，再 loads 回 Python list
        s = df.to_json(orient="records", date_format="iso", default_handler=str)
        return json.loads(s)
    except Exception:
        return []


def _df_attrs(df) -> dict:
    """提取 DataFrame.attrs（含 source / is_mock / mock_reason 等可追溯字段）。"""
    if df is None:
        return {}
    try:
        return dict(getattr(df, "attrs", {}) or {})
    except Exception:
        return {}


def market_data_to_jsonable(md: Dict) -> Dict:
    """把 market_data 转成可 JSON 序列化的 dict。

    `history` 单独处理为 {records, attrs}；其它键透传（依赖 _default 兜底）。
    """
    md = md or {}
    out: Dict[str, Any] = {}
    for k, v in md.items():
        if k == "history":
            out["history"] = {"records": _df_to_records(v), "attrs": _df_attrs(v)}
        else:
            out[k] = v
    return out


def _default(o: Any) -> Any:
    """JSON 序列化兜底：numpy 标量 / datetime / pandas NaT 等转合理表示。"""
    if hasattr(o, "isoformat"):
        return o.isoformat()
    if hasattr(o, "item"):
        try:
            return o.item()
        except Exception:
            pass
    return str(o)


def _safe_symbol(symbol: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in (symbol or "symbol"))


def save_snapshot(symbol: str, market_data: Dict) -> Path:
    """落地 market_data 快照到 `reports/A股_{symbol}_{ts}.snapshot.json`。

    payload 结构：
        {
          "version": 1,
          "saved_at": "YYYY-MM-DD HH:MM:SS",
          "symbol": "600519",
          "market_data": { ...JSON-safe... }
        }
    """
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = REPORTS_DIR / f"A股_{_safe_symbol(symbol)}_{ts}.snapshot.json"
    payload = {
        "version": SNAPSHOT_VERSION,
        "saved_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "symbol": symbol,
        "market_data": market_data_to_jsonable(market_data),
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=_default),
        encoding="utf-8",
    )
    return path


def load_snapshot(path: Union[str, Path]) -> Dict:
    """读 snapshot.json 返回完整 payload dict。"""
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_market_data_from_snapshot(path: Union[str, Path]):
    """从 snapshot.json 还原 market_data dict（含 DataFrame）+ payload 元信息。

    返回 (market_data, payload)：
    - market_data["history"] 从 {records, attrs} 还原为 pd.DataFrame，attrs 写回
    - 其它字段透传
    - payload 含 version / saved_at / symbol 等元信息

    用于 `run.py --replay`：不重抓 AKShare、直接喂给 LLM 流程。
    """
    import pandas as pd  # 延迟 import，模块基础功能不强依赖 pandas

    payload = load_snapshot(path)
    md = dict(payload.get("market_data") or {})
    history_blob = md.get("history")
    if isinstance(history_blob, dict) and "records" in history_blob:
        records = history_blob.get("records") or []
        df = pd.DataFrame(records)
        attrs = history_blob.get("attrs") or {}
        # DataFrame.attrs 必须逐字段赋（不能 df.attrs = dict）
        for k, v in (attrs or {}).items():
            df.attrs[k] = v
        md["history"] = df
    elif history_blob is None or (isinstance(history_blob, dict) and not history_blob):
        md["history"] = pd.DataFrame()
    return md, payload
