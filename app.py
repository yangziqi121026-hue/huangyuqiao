"""Streamlit 单页 UI（只读投研分析）。

运行：
    streamlit run app.py

注意：本页面只展示研究报告，没有任何下单 / 交易 / live 按钮。
"""

from __future__ import annotations

import streamlit as st

from src import config
from src.workflow import run_analysis
from src.report_generator import save_report_to_file

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

    if result["conflict"].get("conflict"):
        st.warning(result["conflict"].get("message", "基本面与技术面存在冲突，已保留分歧。"))

    st.markdown(result["final_report"])

    path = save_report_to_file(symbol, result["final_report"])
    st.success(f"报告已保存：{path}")
    st.download_button(
        "下载报告 (Markdown)",
        data=result["final_report"],
        file_name=f"A股_{symbol}_report.md",
        mime="text/markdown",
    )
