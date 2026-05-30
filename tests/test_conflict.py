"""锁定冲突判定相关逻辑的单元测试（纯标准库 unittest，无需 pytest / 网络 / akshare）。

覆盖：
- parse_analyst_direction：从分析师正文解析方向，且不会把标题里的选项枚举当成答案。
- reconcile_conflict：LLM 定性方向优先、确定性指标兜底；真冲突 / 缺失 / mock 回退。
- _technical_bias：修复后的"多空混合 trend → 中性"行为。

运行：
    python -m unittest discover -s tests
（在项目根目录 ashare_research_agent/ 下执行）
"""

from __future__ import annotations

import os
import sys
import unittest

# 保证从项目根目录导入 src 包
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.analysis.conflict import (  # noqa: E402
    parse_analyst_direction,
    reconcile_conflict,
    _technical_bias,
)


# 取自真实 DeepSeek 输出的代表性片段
FUND_NEUTRAL = (
    "**6. 基本面方向（偏多 / 中性 / 偏空 / 不足以判断）及理由**  \n"
    "**方向：中性**  \n"
    "理由：综合判断长期稳健，但当前数据不足以支持偏多或偏空结论。"
)
FUND_INSUFFICIENT = (
    "**6. 基本面方向（偏多 / 中性 / 偏空 / 不足以判断）及理由**  \n"
    "**不足以判断**。  \n"
    "理由：估值虽低，但盈利能力与成长性数据缺失。"
)
FUND_BULL = (
    "6. 基本面方向（偏多 / 中性 / 偏空 / 不足以判断）及理由\n"
    "方向：偏多\n理由：营收与净利润双增。"
)
TECH_BEAR = (
    "7. **技术面方向（偏多 / 中性 / 偏空 / 不足以判断）及理由**  \n"
    "   **偏空**  \n"
    "   理由：K线空头排列，MACD 死叉。"
)
# 无选项枚举、冒号直答的写法
TECH_BEAR_COLON = "技术面方向：偏空。理由：均线压制。"


class TestParseAnalystDirection(unittest.TestCase):
    def test_fundamental_neutral(self):
        self.assertEqual(parse_analyst_direction(FUND_NEUTRAL, "基本面方向"), "中性")

    def test_fundamental_insufficient(self):
        self.assertEqual(
            parse_analyst_direction(FUND_INSUFFICIENT, "基本面方向"), "不足以判断"
        )

    def test_fundamental_bull_no_markdown(self):
        self.assertEqual(parse_analyst_direction(FUND_BULL, "基本面方向"), "偏多")

    def test_technical_bear(self):
        self.assertEqual(parse_analyst_direction(TECH_BEAR, "技术面方向"), "偏空")

    def test_technical_bear_colon_style(self):
        self.assertEqual(parse_analyst_direction(TECH_BEAR_COLON, "技术面方向"), "偏空")

    def test_options_list_not_taken_as_answer(self):
        """标题里的"（偏多 / 中性 / 偏空 / 不足以判断）"不能被当成答案（否则会误取'偏多'）。"""
        self.assertEqual(parse_analyst_direction(FUND_NEUTRAL, "基本面方向"), "中性")
        self.assertNotEqual(parse_analyst_direction(FUND_NEUTRAL, "基本面方向"), "偏多")

    def test_reason_prose_does_not_override(self):
        """答案后面理由里出现'偏多/偏空'不应覆盖更早出现的真实答案。"""
        self.assertEqual(parse_analyst_direction(FUND_NEUTRAL, "基本面方向"), "中性")

    def test_empty_or_missing(self):
        self.assertIsNone(parse_analyst_direction("", "基本面方向"))
        self.assertIsNone(parse_analyst_direction(None, "基本面方向"))
        self.assertIsNone(
            parse_analyst_direction("这段文字里没有该标题。", "技术面方向")
        )


class TestReconcileConflict(unittest.TestCase):
    def test_llm_overrides_deterministic(self):
        """000001 场景：确定性误判技术面=偏多，但 LLM=偏空，应以 LLM 为准。"""
        det = {"fundamental_bias": "不足以判断", "technical_bias": "偏多"}
        r = reconcile_conflict(det, FUND_INSUFFICIENT, TECH_BEAR)
        self.assertEqual(r["technical_bias"], "偏空")
        self.assertEqual(r["fundamental_bias"], "不足以判断")
        self.assertTrue(r["insufficient"])
        self.assertFalse(r["conflict"])

    def test_true_conflict_flagged(self):
        """600519 场景：基本面偏多 vs 技术面偏空 → 必须判为冲突。"""
        det = {"fundamental_bias": "不足以判断", "technical_bias": "偏空"}
        r = reconcile_conflict(det, FUND_BULL, TECH_BEAR)
        self.assertEqual(r["fundamental_bias"], "偏多")
        self.assertEqual(r["technical_bias"], "偏空")
        self.assertTrue(r["conflict"])
        self.assertFalse(r["insufficient"])
        self.assertIn("冲突", r["message"])

    def test_neutral_vs_bear_not_conflict(self):
        det = {"fundamental_bias": "不足以判断", "technical_bias": "偏空"}
        r = reconcile_conflict(det, FUND_NEUTRAL, TECH_BEAR)
        self.assertEqual(r["fundamental_bias"], "中性")
        self.assertEqual(r["technical_bias"], "偏空")
        self.assertFalse(r["conflict"])
        self.assertFalse(r["insufficient"])

    def test_mock_fallback_to_deterministic(self):
        """mock 输出无方向标题 → 解析为 None → 回退到确定性 bias。"""
        det = {"fundamental_bias": "中性", "technical_bias": "偏空"}
        mock_text = "**基本面分析（mock）**\n- 基本面结论：中性偏谨慎（占位）。"
        r = reconcile_conflict(det, mock_text, mock_text)
        self.assertEqual(r["fundamental_bias"], "中性")
        self.assertEqual(r["technical_bias"], "偏空")
        self.assertFalse(r["conflict"])

    def test_insufficient_when_one_side_missing(self):
        det = {"fundamental_bias": "不足以判断", "technical_bias": "不足以判断"}
        r = reconcile_conflict(det, FUND_INSUFFICIENT, "无方向信息")
        self.assertTrue(r["insufficient"])
        self.assertEqual(r["technical_bias"], "不足以判断")


class TestTechnicalBias(unittest.TestCase):
    def _md(self, trend, bars=242):
        return {"indicators": {"trend": trend, "bars": bars}}

    def test_mixed_signal_is_neutral(self):
        """'短期回调，中期偏强' 同含多空 → 中性（修复前会误判偏多）。"""
        self.assertEqual(_technical_bias(self._md("短期回调，中期偏强")), "中性")

    def test_pure_bear(self):
        self.assertEqual(_technical_bias(self._md("空头排列（下降趋势）")), "偏空")

    def test_pure_bull(self):
        self.assertEqual(_technical_bias(self._md("多头排列（上升趋势）")), "偏多")

    def test_consolidation(self):
        self.assertEqual(_technical_bias(self._md("均线缠绕，区间震荡")), "中性")

    def test_too_few_bars(self):
        self.assertIsNone(_technical_bias(self._md("空头排列（下降趋势）", bars=10)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
