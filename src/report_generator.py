"""最终 Markdown 报告生成器。

强制要求：
- 报告头部必须含【数据来源】与【数据抓取时间】。
- 基本面 vs 技术面冲突时必须显式提示，且不强行给唯一结论。
- 数据缺失维度必须标注"不足以判断"。
- 最终结论只能是 观察 / 谨慎关注 / 暂不参与 / 高风险（绝不含买卖指令）。
- 整篇报告末尾会过一遍 forbidden-word 扫描，作为安全网。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from .config import ALLOWED_CONCLUSIONS, REPORTS_DIR
from .analysis.data_quality import missing_label

# 禁止出现在报告里的交易指令字样（安全网，命中即软化）
_FORBIDDEN = [
    "必须买入", "必须卖出", "建议买入", "建议卖出", "立即买入", "立即卖出",
    "满仓", "清仓", "加仓", "减仓", "买入信号", "卖出信号",
]


def _strip_md(text: str) -> str:
    return (text or "").replace("**", "").replace("__", "").replace("`", "")


def _extract_field(text: str, key: str) -> str:
    if not text:
        return ""
    m = re.search(re.escape(key) + r"[:：]\s*([^\n]+)", _strip_md(text))
    return m.group(1).strip() if m else ""


def extract_conclusion(committee_text: str) -> str:
    """从投资委员会输出抽取最终结论，强制落到 4 个合法标签之一。"""
    val = _extract_field(committee_text, "最终结论")
    for label in ALLOWED_CONCLUSIONS:
        if label in val:
            return label
    # 兜底：抽不到合法标签时返回最保守的"观察"
    return "观察"


def extract_risk_level(committee_text: str) -> str:
    val = _extract_field(committee_text, "风险等级")
    for kw in ("不足以判断", "高", "中", "低"):
        if kw in val:
            return kw
    return "不足以判断"


def _sanitize(text: str) -> str:
    """安全网：把任何遗漏的交易指令字样软化为研究口径。"""
    out = text or ""
    for w in _FORBIDDEN:
        if w in out:
            out = out.replace(w, f"（已移除交易指令：{w}）")
    return out


def _collect_sources(market_data: Dict) -> List[str]:
    srcs: List[str] = []
    info = market_data.get("info") or {}
    fin = market_data.get("financials") or {}
    cap = market_data.get("capital_flow") or {}
    hist = market_data.get("history")

    srcs += info.get("_sources", [])
    srcs += fin.get("_sources", [])
    srcs += cap.get("_sources", [])
    try:
        hs = getattr(hist, "attrs", {}).get("source")
        if hs:
            srcs.append(hs)
    except Exception:
        pass
    news = market_data.get("news") or []
    if news and not all(n.get("is_mock") for n in news):
        srcs.append("stock_news_em（东财，新闻）")
    # 去重保序
    seen, uniq = set(), []
    for s in srcs:
        if s and s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq or ["（本次未取得任何真实数据源，可能处于 mock 模式）"]


def build_final_report(
    market_data: Dict,
    agent_outputs: Dict[str, str],
    conflict: Dict,
    dq_assessment: Dict,
    period_zh: str = "日线",
    adjust_zh: str = "前复权",
) -> str:
    info = market_data.get("info") or {}
    ind = market_data.get("indicators") or {}
    dq = market_data.get("data_quality") or {}
    errors = market_data.get("errors") or []
    fetched_at = market_data.get("fetched_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    gen_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    committee_txt = agent_outputs.get("investment_committee", "")
    conclusion = extract_conclusion(committee_txt)
    risk_level = extract_risk_level(committee_txt)

    sources = _collect_sources(market_data)
    insufficient = dq_assessment.get("insufficient") or []

    conflict_block = ""
    if conflict.get("conflict"):
        conflict_block = (
            f"\n> {conflict.get('message', '')}\n"
            "> 因基本面与技术面方向冲突，本报告**保留分歧、不给出唯一结论**。\n"
        )
    elif conflict.get("insufficient"):
        conflict_block = f"\n> {conflict.get('message', '')}\n"

    insufficient_block = (
        "、".join(insufficient) if insufficient else "无（各维度数据基本可用）"
    )

    md = f"""# A股个股投研分析报告（只读 / 研究用途）

> 本报告由 AI 多智能体只读分析系统生成，**仅供研究学习，不构成投资建议，不保证收益，不含任何买卖指令，不执行任何交易**。

## 〇、报告元信息
- 市场：{market_data.get('market', '')}（仅 A 股）
- 股票代码：{market_data.get('symbol', '')}
- 股票名称：{market_data.get('name', '')}
- 当前价：{missing_label(market_data.get('current_price'))} {market_data.get('currency', '')}
- 数据周期：{period_zh}　复权方式：{adjust_zh}
- **数据来源**：{('；'.join(sources))}
- **数据抓取时间**：{fetched_at}
- 报告生成时间：{gen_at}
{conflict_block}
## A. 公司基本面
- 主营业务：{missing_label(info.get('main_business'))}
- 所属行业：{missing_label(info.get('industry'))}
- 总市值：{missing_label(info.get('market_cap'))}
- PE / PB：{missing_label(info.get('pe'))} / {missing_label(info.get('pb'))}

{_sanitize(agent_outputs.get('fundamental_analyst', '（无）'))}

## B. 技术面
- 趋势：{ind.get('trend', '不足以判断')}
- MA5/10/20/60：{missing_label(ind.get('ma5'))} / {missing_label(ind.get('ma10'))} / {missing_label(ind.get('ma20'))} / {missing_label(ind.get('ma60'))}
- MACD / RSI14：{missing_label(ind.get('macd'))} / {missing_label(ind.get('rsi14'))}
- 支撑位 / 压力位：{missing_label(ind.get('support'))} / {missing_label(ind.get('resistance'))}

{_sanitize(agent_outputs.get('technical_analyst', '（无）'))}

## C. 资金面

{_sanitize(agent_outputs.get('capital_flow_analyst', '（无）'))}

## D. 消息面

{_sanitize(agent_outputs.get('news_analyst', '（无）'))}

## E. 投资委员会结论

### 看多观点
{_sanitize(agent_outputs.get('bull_researcher', '（无）'))}

### 看空观点
{_sanitize(agent_outputs.get('bear_researcher', '（无）'))}

### 委员会综合结论
{_sanitize(committee_txt or '（无）')}

---

## 综合摘要
- 基本面方向：{conflict.get('fundamental_bias', '不足以判断')}
- 技术面方向：{conflict.get('technical_bias', '不足以判断')}
- 是否存在基本面/技术面冲突：{'是（已保留分歧）' if conflict.get('conflict') else ('数据不足' if conflict.get('insufficient') else '否')}
- 风险等级：{risk_level}
- **最终结论：{conclusion}**（仅为研究观察分级，非交易指令）

## 数据质量与缺失说明
- 行情数据：{dq.get('price_data', 'unknown')}
- 财务数据：{dq.get('financial_data', 'unknown')}
- 资金数据：{dq.get('capital_data', 'unknown')}
- 新闻数据：{dq.get('news_data', 'unknown')}
- 整体可信度：{dq_assessment.get('overall', '未知')}
- 不足以判断的维度：{insufficient_block}
- 数据异常：{('；'.join(errors)) if errors else '无'}

## 免责声明
本报告为 AI 自动生成的只读研究材料，所用数据来自 AKShare 公开接口，可能存在滞后、缺失或错误。
报告不构成任何投资、申购、买卖建议，不预测涨跌，不承诺收益。投资有风险，决策请独立判断并自担风险。
"""
    return _sanitize(md)


def save_report_to_file(symbol: str, content: str) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_symbol = re.sub(r"\W+", "_", symbol or "symbol")
    path = REPORTS_DIR / f"A股_{safe_symbol}_{ts}.md"
    path.write_text(content, encoding="utf-8")
    return path
