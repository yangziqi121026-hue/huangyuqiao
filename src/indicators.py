"""技术指标计算（技术面输入）。

输入统一为 pandas DataFrame，要求包含列：date, open, high, low, close, volume。
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

REQUIRED_COLS = ("date", "open", "high", "low", "close", "volume")


def _safe_last(series: pd.Series) -> float:
    if series is None or len(series) == 0:
        return float("nan")
    try:
        return float(series.iloc[-1])
    except (TypeError, ValueError):
        return float("nan")


def _round(v: float, n: int = 2) -> float:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return float("nan")
    return float(round(v, n))


def calc_ma(df: pd.DataFrame, n: int) -> pd.Series:
    return df["close"].rolling(window=n, min_periods=1).mean()


def calc_rsi(df: pd.DataFrame, n: int = 14) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=n, min_periods=1).mean()
    avg_loss = loss.rolling(window=n, min_periods=1).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)


def calc_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = df["close"].ewm(span=fast, adjust=False).mean()
    ema_slow = df["close"].ewm(span=slow, adjust=False).mean()
    macd = ema_fast - ema_slow
    sig = macd.ewm(span=signal, adjust=False).mean()
    return macd, sig, macd - sig


def compute_indicators(df: pd.DataFrame) -> Dict:
    result: Dict = {
        "ma5": float("nan"), "ma10": float("nan"), "ma20": float("nan"), "ma60": float("nan"),
        "rsi14": float("nan"),
        "macd": float("nan"), "macd_signal": float("nan"), "macd_hist": float("nan"),
        "high_52w": float("nan"), "low_52w": float("nan"),
        "pct_20d": float("nan"), "volume_change": float("nan"),
        "support": float("nan"), "resistance": float("nan"),
        "trend": "不足以判断",
        "bars": 0,
        "df_with_indicators": df,
    }

    if df is None or df.empty:
        return result
    if [c for c in REQUIRED_COLS if c not in df.columns]:
        return result

    df = df.copy().sort_values("date").reset_index(drop=True)
    result["bars"] = len(df)

    df["MA5"] = calc_ma(df, 5)
    df["MA10"] = calc_ma(df, 10)
    df["MA20"] = calc_ma(df, 20)
    df["MA60"] = calc_ma(df, 60)
    df["RSI14"] = calc_rsi(df, 14)
    macd, sig, hist = calc_macd(df)
    df["MACD"], df["MACD_SIGNAL"], df["MACD_HIST"] = macd, sig, hist

    last_close = _safe_last(df["close"])
    result["ma5"] = _round(_safe_last(df["MA5"]))
    result["ma10"] = _round(_safe_last(df["MA10"]))
    result["ma20"] = _round(_safe_last(df["MA20"]))
    result["ma60"] = _round(_safe_last(df["MA60"]))
    result["rsi14"] = _round(_safe_last(df["RSI14"]))
    result["macd"] = _round(_safe_last(df["MACD"]), 4)
    result["macd_signal"] = _round(_safe_last(df["MACD_SIGNAL"]), 4)
    result["macd_hist"] = _round(_safe_last(df["MACD_HIST"]), 4)

    lookback = df.tail(252) if len(df) >= 252 else df
    result["high_52w"] = _round(float(lookback["high"].max()))
    result["low_52w"] = _round(float(lookback["low"].min()))

    if len(df) >= 21:
        prev = float(df["close"].iloc[-21])
        if prev > 0:
            result["pct_20d"] = _round((last_close - prev) / prev * 100)
    elif len(df) >= 2:
        prev = float(df["close"].iloc[0])
        if prev > 0:
            result["pct_20d"] = _round((last_close - prev) / prev * 100)

    if len(df) >= 20:
        v5 = float(df["volume"].tail(5).mean())
        v20 = float(df["volume"].tail(20).mean())
        if v20 > 0:
            result["volume_change"] = _round((v5 - v20) / v20 * 100)

    recent = df.tail(60) if len(df) >= 60 else df
    result["support"] = _round(float(recent["low"].min()))
    result["resistance"] = _round(float(recent["high"].max()))

    ma5, ma20, ma60 = result["ma5"], result["ma20"], result["ma60"]
    if not any(np.isnan(x) for x in (ma5, ma20, ma60)):
        if ma5 > ma20 > ma60:
            result["trend"] = "多头排列（上升趋势）"
        elif ma5 < ma20 < ma60:
            result["trend"] = "空头排列（下降趋势）"
        elif ma5 > ma20 and ma20 < ma60:
            result["trend"] = "短期反弹，中期偏弱"
        elif ma5 < ma20 and ma20 > ma60:
            result["trend"] = "短期回调，中期偏强"
        else:
            result["trend"] = "震荡"

    result["df_with_indicators"] = df
    return result
