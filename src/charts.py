"""Streamlit 图表（K 线 / MACD / 资金流）。

纯函数：接收 pandas DataFrame，返回 plotly Figure。
不依赖 streamlit / akshare / LLM，方便在测试里独立验证。

使用方：app.py 用 st.plotly_chart(make_xxx_chart(...), use_container_width=True)
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd
import plotly.graph_objects as go

from .indicators import calc_ma, calc_macd


_DISCLAIMER = "仅供研究学习，不构成投资建议"


def _empty_figure(message: str) -> go.Figure:
    """统一的空图占位（数据不足或缺失时）。"""
    fig = go.Figure()
    fig.update_layout(
        annotations=[dict(
            text=message, xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False, font=dict(size=16),
        )],
        margin=dict(l=10, r=10, t=40, b=10),
        height=400,
    )
    return fig


def _has_ohlc(df: Optional[pd.DataFrame]) -> bool:
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return False
    needed = {"date", "open", "high", "low", "close"}
    return needed.issubset(set(df.columns))


def make_kline_chart(
    df: Optional[pd.DataFrame],
    title: str = "K 线（含 MA5/10/20/60）",
) -> go.Figure:
    """K 线 + MA5/10/20/60 叠加。

    df 缺失或缺列时返回带 "数据不足" 提示的空图，不抛异常。
    """
    if not _has_ohlc(df):
        return _empty_figure("行情数据不足以判断（缺少 OHLC 列）")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=df["date"], open=df["open"], high=df["high"],
        low=df["low"], close=df["close"],
        name="K 线",
        increasing_line_color="#d62728",  # A 股习惯：红涨
        decreasing_line_color="#2ca02c",  # 绿跌
    ))
    # 叠加 4 条 MA
    for n, color in [(5, "#ff7f0e"), (10, "#1f77b4"),
                     (20, "#9467bd"), (60, "#8c564b")]:
        if len(df) >= n:
            fig.add_trace(go.Scatter(
                x=df["date"], y=calc_ma(df, n),
                name=f"MA{n}", mode="lines",
                line=dict(color=color, width=1.2),
            ))
    fig.update_layout(
        title=f"{title}　（{_DISCLAIMER}）",
        xaxis_title="日期", yaxis_title="价格",
        xaxis_rangeslider_visible=False,
        margin=dict(l=10, r=10, t=50, b=10),
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def make_macd_chart(
    df: Optional[pd.DataFrame],
    title: str = "MACD（12, 26, 9）",
) -> go.Figure:
    """MACD / Signal 折线 + Histogram 柱状（同图共享 x 轴）。"""
    if not _has_ohlc(df):
        return _empty_figure("行情数据不足以判断（无法计算 MACD）")
    if len(df) < 26:
        return _empty_figure(f"行情样本不足以判断（{len(df)} 根，需要 ≥26 根计算 MACD）")

    macd, signal, hist = calc_macd(df)
    fig = go.Figure()
    # Histogram 柱：正红负绿（与 A 股 K 线配色一致）
    colors = ["#d62728" if v >= 0 else "#2ca02c" for v in hist]
    fig.add_trace(go.Bar(
        x=df["date"], y=hist, name="MACD Hist",
        marker_color=colors, opacity=0.6,
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=macd, name="MACD", mode="lines",
        line=dict(color="#1f77b4", width=1.5),
    ))
    fig.add_trace(go.Scatter(
        x=df["date"], y=signal, name="Signal", mode="lines",
        line=dict(color="#ff7f0e", width=1.5),
    ))
    fig.update_layout(
        title=f"{title}　（{_DISCLAIMER}）",
        xaxis_title="日期", yaxis_title="MACD 值",
        margin=dict(l=10, r=10, t=50, b=10),
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        barmode="overlay",
    )
    return fig


def make_capital_flow_chart(
    df: Optional[pd.DataFrame],
    capital_flow: Optional[Dict] = None,
    title: str = "资金流（成交额 + 换手率）",
) -> go.Figure:
    """成交额柱状（左 Y）+ 换手率折线（右 Y）。

    main_net 主力净流入按日（如可得）作为额外散点叠加；缺失则只显示成交额/换手率。
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty or "date" not in df.columns:
        return _empty_figure("行情数据不足以判断（无法绘制资金流）")

    fig = go.Figure()
    # 成交额（左 Y）：amount 字段，单位元；展示时换算亿元
    if "amount" in df.columns:
        amount_yi = df["amount"] / 1e8
        fig.add_trace(go.Bar(
            x=df["date"], y=amount_yi, name="成交额（亿元）",
            marker_color="#1f77b4", opacity=0.6,
            yaxis="y1",
        ))
    # 换手率（右 Y）：turnover 字段（小数，乘 100 显示）
    if "turnover" in df.columns:
        # 兼容 turnover 是 0.012 (小数) 或 1.2 (%) 两种形态：>1 视为已百分比
        tr = df["turnover"]
        if tr.dropna().abs().max() <= 1.0 if not tr.dropna().empty else True:
            tr = tr * 100
        fig.add_trace(go.Scatter(
            x=df["date"], y=tr, name="换手率（%）",
            mode="lines", line=dict(color="#ff7f0e", width=1.5),
            yaxis="y2",
        ))
    # 主力净流入（如 capital_flow.main_fund_recent 可得，按日叠加）
    cf = capital_flow or {}
    recent = cf.get("main_fund_recent") or []
    if recent:
        try:
            dates = [r.get("date") for r in recent]
            nets = [r.get("main_net") for r in recent]
            # main_net 单位通常是元，亿元展示更直观
            nets_yi = [
                (v / 1e8) if isinstance(v, (int, float)) else None for v in nets
            ]
            fig.add_trace(go.Scatter(
                x=dates, y=nets_yi, name="主力净流入（亿元）",
                mode="lines+markers",
                line=dict(color="#d62728", width=1.5, dash="dot"),
                yaxis="y1",
            ))
        except Exception:
            pass

    fig.update_layout(
        title=f"{title}　（{_DISCLAIMER}）",
        xaxis_title="日期",
        yaxis=dict(title="成交额 / 主力净流入（亿元）", side="left"),
        yaxis2=dict(title="换手率（%）", overlaying="y", side="right",
                    showgrid=False),
        margin=dict(l=10, r=10, t=50, b=10),
        height=400,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        barmode="overlay",
    )
    return fig
