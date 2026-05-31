"""Streamlit 单页 UI（只读投研分析）。

运行：
    streamlit run app.py

注意：本页面只展示研究报告，没有任何下单 / 交易 / live 按钮。
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.charts import make_capital_flow_chart, make_kline_chart, make_macd_chart
from src.report_generator import save_report_to_file
from src.snapshot import save_snapshot
from src.workflow import run_analysis

st.set_page_config(page_title="A股只读投研分析 Agent", page_icon="📑", layout="wide")

st.title("📑 A股个股投研分析 Agent（只读 / 研究用途）")
st.caption("仅供研究学习，不构成投资建议，不含买卖指令，不执行任何交易。")

with st.sidebar:
    st.header("参数")
    symbol = st.text_input("A股代码（6位）", value="600519", max_chars=6)
    depth = st.selectbox("分析深度", config.ANALYSIS_DEPTHS, index=1)
    period = st.selectbox("数据周期", list(config.PERIOD_MAP.keys()), index=0)
    adjust = st.selectbox("复权方式", list(config.ADJUST_MAP.keys()), index=1)
    run_btn = st.button("开始分析", type="primary", use_container_width=True)

    s = config.get_settings_summary()
    st.divider()
    st.write("**运行配置**")
    st.json({
        "model": s["model"],
        "mock_mode": s["mock_mode"],
        "只读": s["only_readonly"],
        "下单": s["enable_trading"],
        "live": s["enable_live"],
        "市场": s["only_market"],
    })
    if s["mock_mode"]:
        st.warning("当前为 mock 模式：无 API Key 或未联网，结论仅用于流程验证。")

if run_btn:
    if not symbol or not symbol.isdigit() or len(symbol) != 6:
        st.error("请输入正确的 6 位 A 股代码。")
        st.stop()

    progress = st.progress(0, text="准备中…")
    stages_total = 9
    state = {"i": 0}

    def on_stage(stage_id, stage_zh, ctx):
        state["i"] += 1
        progress.progress(min(state["i"] / stages_total, 1.0), text=stage_zh)

    with st.spinner("分析中…"):
        result = run_analysis(
            symbol=symbol, period_zh=period, adjust_zh=adjust, depth=depth, on_stage=on_stage
        )
    progress.empty()

    if not result["ok"]:
        st.error(result["error"])
        st.stop()

    c1, c2, c3 = st.columns(3)
    c1.metric("最终结论（观察分级）", result["conclusion"])
    c2.metric("风险等级", result["risk_level"])
    c3.metric("数据可信度", result["data_quality"].get("overall", "未知"))

    # 资金面关键指标（结构化字段，缺失统一显示"不足以判断"）
    cap = (result.get("market_data") or {}).get("capital_flow") or {}
    _amt = cap.get("amount_latest")
    _tr = cap.get("turnover_rate_latest")
    _mf = cap.get("main_fund_5d_sum")
    d1, d2, d3 = st.columns(3)
    d1.metric("最新成交额", f"{round(_amt / 1e8, 2)} 亿元" if isinstance(_amt, (int, float)) else "不足以判断")
    d2.metric("最新换手率", f"{_tr}%" if isinstance(_tr, (int, float)) else "不足以判断")
    d3.metric("近5日主力净流入", f"{round(_mf / 1e8, 2)} 亿元" if isinstance(_mf, (int, float)) else "不足以判断")

    if result["conflict"].get("conflict"):
        st.warning(result["conflict"].get("message", "基本面与技术面存在冲突，已保留分歧。"))

    # ---- 图表区（K 线 / MACD / 资金流）----
    md = result.get("market_data") or {}
    history_df = md.get("history")
    capital_flow = md.get("capital_flow") or {}
    with st.expander("📈 图表（K 线 / MACD / 资金流）", expanded=True):
        st.caption("图表仅为研究展示，不构成任何买卖指令。")
        tab_kline, tab_macd, tab_cap = st.tabs(["K 线 + MA", "MACD", "资金流"])
        with tab_kline:
            st.plotly_chart(make_kline_chart(history_df), use_container_width=True)
        with tab_macd:
            st.plotly_chart(make_macd_chart(history_df), use_container_width=True)
        with tab_cap:
            st.plotly_chart(
                make_capital_flow_chart(history_df, capital_flow=capital_flow),
                use_container_width=True,
            )

    st.markdown(result["final_report"])

    path = save_report_to_file(symbol, result["final_report"])
    st.success(f"报告已保存：{path}")
    col_dl_md, col_dl_snap = st.columns(2)
    with col_dl_md:
        st.download_button(
            "下载报告 (Markdown)",
            data=result["final_report"],
            file_name=f"A股_{symbol}_report.md",
            mime="text/markdown",
        )
    with col_dl_snap:
        try:
            snap_path = save_snapshot(symbol, md)
            st.caption(f"数据快照已保存：{snap_path.name}（可用于复现 / A-B 模型对比）")
            st.download_button(
                "下载数据快照 (JSON)",
                data=snap_path.read_bytes(),
                file_name=snap_path.name,
                mime="application/json",
            )
        except Exception as e:
            st.caption(f"快照落地失败：{e}（不影响报告）")
