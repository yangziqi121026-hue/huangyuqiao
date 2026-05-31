"""端到端 smoke：用纯 mock 跑 build_final_report，验证最终 md 的安全收口。

不联网、不调 LLM、不依赖 akshare；只跑 report_generator.build_final_report，
确保整条管线最终产物满足下列硬约束：

1. 必含 4 档合法结论之一（观察/谨慎关注/暂不参与/高风险）
2. 必不含任何 _FORBIDDEN 字样（即使 mock 输入故意塞了禁词，也要被包裹）
3. 必含「数据来源」「数据抓取时间」字段
4. 必含免责声明语
5. agent 文本里塞的"买入/卖出/做多/止损位"等都会被 _sanitize 软化
6. 委员会同时给出多档时返回最严档

是收口校验的最后一道闸门。
"""

from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.config import ALLOWED_CONCLUSIONS  # noqa: E402
from src.report_generator import build_final_report, _FORBIDDEN  # noqa: E402


def _mock_market_data() -> dict:
    return {
        "market": "A股",
        "symbol": "600519",
        "name": "贵州茅台",
        "current_price": 1680.50,
        "currency": "CNY",
        "fetched_at": "2026-05-30 21:00:00",
        "info": {
            "main_business": "白酒生产销售",
            "industry": "白酒",
            "market_cap": "21000亿元",
            "pe": 25.6,
            "pb": 8.1,
            "_sources": ["AKShare（stock_zh_valuation_baidu）"],
        },
        "financials": {"_sources": ["AKShare（financial_report）"]},
        "capital_flow": {"_sources": ["AKShare（日K成交额兜底）"]},
        "history": None,
        "news": [{"title": "示例新闻", "is_mock": False}],
        "indicators": {
            "trend": "震荡偏强",
            "ma5": 1670.1,
            "ma10": 1665.3,
            "ma20": 1650.0,
            "ma60": 1620.0,
            "macd": 0.12,
            "rsi14": 55.4,
            "support": 1620.0,
            "resistance": 1720.0,
        },
        "data_quality": {
            "price_data": "ok",
            "financial_data": "ok",
            "capital_data": "partial",
            "news_data": "ok",
        },
        "errors": [],
    }


def _mock_agent_outputs_with_forbidden_words() -> dict:
    """故意在每个 agent 文本里塞禁词，验证 _sanitize 安全网生效。"""
    return {
        "fundamental_analyst": "基本面分析：业绩稳健，分析师强烈推荐该公司股票。",
        "technical_analyst": "技术面：MACD 金叉，出现买入信号，建议入场价 1650。",
        "capital_flow_analyst": "资金面：主力净流入扩大，可逢低买入。",
        "news_analyst": "消息面：近期无重大利空。",
        "bull_researcher": "看多：行业景气度高，建议加仓。BUY。",
        "bear_researcher": "看空：估值偏高，建议减仓，止损位 1500。",
        "investment_committee": (
            "- 看多理由：行业景气\n"
            "- 看空理由：估值高\n"
            "- 分歧点：基本面偏强而技术面震荡\n"
            "- 风险等级：中\n"
            "- 观察价位：1620 / 1720\n"
            "- 不确定因素：消费复苏节奏\n"
            "- 最终结论：谨慎关注\n"
        ),
    }


def _mock_conflict_no_conflict() -> dict:
    return {
        "conflict": False,
        "insufficient": False,
        "message": "（基本面与技术面方向不冲突）",
        "fundamental_bias": "偏强",
        "technical_bias": "中性",
    }


def _mock_dq() -> dict:
    return {"overall": "可用", "insufficient": []}


class TestSmokeBuildFinalReport(unittest.TestCase):
    def setUp(self):
        self.md = build_final_report(
            market_data=_mock_market_data(),
            agent_outputs=_mock_agent_outputs_with_forbidden_words(),
            conflict=_mock_conflict_no_conflict(),
            dq_assessment=_mock_dq(),
        )

    def test_report_is_nonempty_markdown(self):
        self.assertTrue(self.md)
        self.assertGreater(len(self.md), 500)
        self.assertIn("# A股个股投研分析报告", self.md)

    def test_must_contain_one_of_allowed_conclusions(self):
        # 综合摘要那一行 "**最终结论：XXX**" 必有一档合法标签
        hits = [c for c in ALLOWED_CONCLUSIONS if f"最终结论：{c}" in self.md]
        self.assertEqual(
            len(hits), 1, f"应仅出现一个合法结论，实际命中：{hits}"
        )

    def test_must_not_contain_any_forbidden_word_raw(self):
        # 即使 mock agent 输出里故意塞了禁词，最终 md 不允许出现裸禁词
        for w in _FORBIDDEN:
            if w in self.md:
                self.assertIn(
                    f"（已移除交易指令：{w}）",
                    self.md,
                    f"禁词 {w!r} 出现在报告中但未被 _sanitize 软化",
                )

    def test_must_contain_data_source_line(self):
        self.assertIn("数据来源摘要", self.md)
        self.assertIn("数据来源（接口级）", self.md)
        self.assertIn("AKShare", self.md)

    def test_must_contain_fetched_at_with_valid_format(self):
        import re
        self.assertIn("数据抓取时间", self.md)
        # 必须是 YYYY-MM-DD HH:MM:SS 格式（非空字符串、非"不足以判断"）
        # 字段名外可能有 ** ** markdown 加粗，用宽松匹配
        m = re.search(r"数据抓取时间[^\n]*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", self.md)
        self.assertIsNotNone(m, "数据抓取时间字段缺失或格式不合法")
        self.assertEqual(m.group(1), "2026-05-30 21:00:00")

    def test_must_contain_analysis_model_field(self):
        # 头部必须暴露生成本报告的 LLM 模型名，否则结论无法溯源
        self.assertIn("分析模型", self.md)
        import re
        m = re.search(r"分析模型[^\n]*[：:]\s*(\S+)", self.md)
        self.assertIsNotNone(m)
        # 模型名应非空、非"不足以判断"
        self.assertNotIn("不足以判断", m.group(0))

    def test_must_contain_latest_trade_day(self):
        self.assertIn("行情最新交易日", self.md)

    def test_must_contain_financial_period(self):
        self.assertIn("财报期", self.md)

    def test_must_contain_disclaimer(self):
        self.assertIn("不构成投资建议", self.md)
        self.assertIn("不含任何买卖指令", self.md)
        self.assertIn("免责声明", self.md)

    def test_sanitize_wraps_inserted_forbidden_words(self):
        # 抽几个故意塞进去的具体禁词，确认都已被替换为软化标记
        # 注意：_FORBIDDEN 里是"加仓"而非"建议加仓"，所以走查软化后的子串
        for w in ("强烈推荐", "买入信号", "建议入场价", "逢低买入", "加仓", "BUY", "减仓", "止损位"):
            self.assertIn(
                f"（已移除交易指令：{w}）",
                self.md,
                f"_sanitize 应软化禁词 {w!r}",
            )


class TestSmokeStrictestConclusionWins(unittest.TestCase):
    """委员会同时写多档时，最终 md 必须落到最严档。"""

    def test_multi_label_picks_strictest(self):
        mkt = _mock_market_data()
        agents = _mock_agent_outputs_with_forbidden_words()
        agents["investment_committee"] = (
            "- 看多理由：略\n"
            "- 看空理由：略\n"
            "- 分歧点：无\n"
            "- 风险等级：高\n"
            "- 观察价位：1500 / 1700\n"
            "- 不确定因素：无\n"
            "- 最终结论：观察 / 高风险\n"
        )
        md = build_final_report(
            market_data=mkt,
            agent_outputs=agents,
            conflict=_mock_conflict_no_conflict(),
            dq_assessment=_mock_dq(),
        )
        self.assertIn("最终结论：高风险", md)
        self.assertNotIn("最终结论：观察**", md)


class TestSmokeReplayBanner(unittest.TestCase):
    """replay 模式头部必须明示 "Replay 模式" 提示 + 原快照保存时间，
    避免用户把重跑当成新抓。非 replay 时不应出现此 banner。"""

    def test_no_banner_when_not_replay(self):
        md = build_final_report(
            market_data=_mock_market_data(),
            agent_outputs=_mock_agent_outputs_with_forbidden_words(),
            conflict=_mock_conflict_no_conflict(),
            dq_assessment=_mock_dq(),
        )
        self.assertNotIn("Replay 模式", md)
        self.assertNotIn("🔁", md)

    def test_banner_present_when_replay(self):
        mkt = _mock_market_data()
        mkt["_replay_from"] = "reports/A股_600519_20260531_133149.snapshot.json"
        mkt["_replay_saved_at"] = "2026-05-31 13:31:49"
        md = build_final_report(
            market_data=mkt,
            agent_outputs=_mock_agent_outputs_with_forbidden_words(),
            conflict=_mock_conflict_no_conflict(),
            dq_assessment=_mock_dq(),
        )
        self.assertIn("Replay 模式", md)
        self.assertIn("🔁", md)
        # 文件名（非绝对路径）出现
        self.assertIn("A股_600519_20260531_133149.snapshot.json", md)
        # 原快照保存时间出现，让用户知道数据时点
        self.assertIn("2026-05-31 13:31:49", md)
        # 报告其它字段照常生成
        self.assertIn("最终结论：", md)


class TestSmokeConflictBlockRendered(unittest.TestCase):
    """方向冲突时报告头部必须明确标注'保留分歧、不给出唯一结论'。"""

    def test_conflict_banner_present(self):
        md = build_final_report(
            market_data=_mock_market_data(),
            agent_outputs=_mock_agent_outputs_with_forbidden_words(),
            conflict={
                "conflict": True,
                "insufficient": False,
                "message": "（基本面偏多 / 技术面偏空，方向冲突）",
                "fundamental_bias": "偏多",
                "technical_bias": "偏空",
            },
            dq_assessment=_mock_dq(),
        )
        self.assertIn("方向冲突", md)
        self.assertIn("保留分歧", md)
        self.assertIn("不给出唯一结论", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
