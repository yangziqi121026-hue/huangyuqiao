"""锁定报告生成器的安全相关逻辑：

- extract_conclusion：最终结论只能落在四档合法标签内，抽不到则回退最保守的"观察"。
- extract_risk_level：风险等级落在 不足以判断/高/中/低。
- _sanitize：禁词安全网——任何买卖指令字样都会被包裹软化。

纯标准库 unittest，无需网络 / akshare / LLM。
运行：python -m unittest discover -s tests
"""

from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.config import ALLOWED_CONCLUSIONS  # noqa: E402
from src.report_generator import (  # noqa: E402
    extract_conclusion,
    extract_risk_level,
    _sanitize,
    _FORBIDDEN,
)


class TestExtractConclusion(unittest.TestCase):
    def test_each_allowed_label(self):
        for label in ALLOWED_CONCLUSIONS:
            txt = f"- 最终结论：{label}\n- 说明：研究观点。"
            self.assertEqual(extract_conclusion(txt), label)

    def test_halfwidth_colon(self):
        self.assertEqual(extract_conclusion("最终结论: 暂不参与"), "暂不参与")

    def test_with_markdown_and_trailing(self):
        txt = "**最终结论：谨慎关注**（仅为研究分级，非交易指令）"
        self.assertEqual(extract_conclusion(txt), "谨慎关注")

    def test_fallback_when_missing(self):
        self.assertEqual(extract_conclusion("这里没有结论字段。"), "观察")
        self.assertEqual(extract_conclusion(""), "观察")

    def test_result_always_in_allowed_set(self):
        for txt in ("最终结论：买入", "随便写点啥", "最终结论：高风险"):
            self.assertIn(extract_conclusion(txt), ALLOWED_CONCLUSIONS)

    def test_illegal_conclusion_falls_back(self):
        # "买入" 不是合法四档之一 → 回退"观察"
        self.assertEqual(extract_conclusion("最终结论：买入"), "观察")


class TestExtractRiskLevel(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(extract_risk_level("风险等级：高"), "高")
        self.assertEqual(extract_risk_level("风险等级：中"), "中")
        self.assertEqual(extract_risk_level("风险等级：低"), "低")
        self.assertEqual(extract_risk_level("风险等级：不足以判断"), "不足以判断")

    def test_fallback(self):
        self.assertEqual(extract_risk_level("没有风险字段"), "不足以判断")


class TestSanitize(unittest.TestCase):
    def test_clean_text_unchanged(self):
        clean = "本报告仅供研究学习，给出观察分级，不含交易指令。"
        self.assertEqual(_sanitize(clean), clean)

    def test_each_forbidden_word_wrapped(self):
        for w in _FORBIDDEN:
            out = _sanitize(f"分析师{w}该标的。")
            self.assertIn(f"（已移除交易指令：{w}）", out)

    def test_multiple_forbidden_in_one_text(self):
        out = _sanitize("先建议买入再清仓，并加仓。")
        self.assertIn("（已移除交易指令：建议买入）", out)
        self.assertIn("（已移除交易指令：清仓）", out)
        self.assertIn("（已移除交易指令：加仓）", out)

    def test_empty(self):
        self.assertEqual(_sanitize(""), "")
        self.assertEqual(_sanitize(None), "")


class TestAllowedConclusions(unittest.TestCase):
    def test_exactly_four_research_labels(self):
        self.assertEqual(ALLOWED_CONCLUSIONS, ("观察", "谨慎关注", "暂不参与", "高风险"))
        # 绝不包含买卖指令字样
        for label in ALLOWED_CONCLUSIONS:
            self.assertNotIn("买", label)
            self.assertNotIn("卖", label)


if __name__ == "__main__":
    unittest.main(verbosity=2)
