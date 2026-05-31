"""锁定 report_generator.build_batch_summary 的行为：

- 严格度排序：高风险 → 暂不参与 → 谨慎关注 → 观察
- 表格 / 分组 / 失败标的 / 报告链接生成
- 头部元信息：模型 / 时间 / 总耗时 / 缓存状态
- 禁词扫描通过（汇总里不含任何 _FORBIDDEN 词）

纯单元，不联网、不调 LLM、不依赖 akshare。
"""

from __future__ import annotations

import os
import sys
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.report_generator import build_batch_summary, _FORBIDDEN  # noqa: E402


def _ok(symbol, name, conclusion, risk="中", fb="偏强", tb="中性",
        conflict=False, insufficient=False, day="2026-05-29", path=""):
    return {
        "symbol": symbol, "name": name, "ok": True,
        "conclusion": conclusion, "risk_level": risk,
        "fundamental_bias": fb, "technical_bias": tb,
        "conflict": conflict, "insufficient": insufficient,
        "latest_trade_day": day, "report_path": path,
    }


class TestStrictestFirstOrdering(unittest.TestCase):
    def test_sort_by_strictness(self):
        # 故意打乱：观察 / 高风险 / 谨慎关注 / 暂不参与
        results = [
            _ok("600519", "茅台", "观察"),
            _ok("000001", "平安", "高风险"),
            _ok("300750", "宁德", "谨慎关注"),
            _ok("600036", "招行", "暂不参与"),
        ]
        md = build_batch_summary(results, "2026-05-30 21:00",
                                 "2026-05-30 22:00", 3600.0, True)
        # 表格里高风险行必须在最前面，观察在最后面
        hf_pos = md.find("000001")
        an_pos = md.find("600036")
        jk_pos = md.find("300750")
        gc_pos = md.find("600519")
        self.assertLess(hf_pos, an_pos)
        self.assertLess(an_pos, jk_pos)
        self.assertLess(jk_pos, gc_pos)

    def test_same_strictness_sorted_by_symbol(self):
        results = [
            _ok("600519", "x", "高风险"),
            _ok("000001", "y", "高风险"),
            _ok("300750", "z", "高风险"),
        ]
        md = build_batch_summary(results, "t1", "t2", 1.0, True)
        # 表格里同级按 symbol 升序
        p1 = md.find("| 000001")
        p2 = md.find("| 300750")
        p3 = md.find("| 600519")
        self.assertLess(p1, p2)
        self.assertLess(p2, p3)


class TestMetadataHeader(unittest.TestCase):
    def test_header_contains_model_and_times(self):
        results = [_ok("600519", "茅台", "谨慎关注")]
        md = build_batch_summary(results, "2026-05-30 21:00:00",
                                 "2026-05-30 21:30:00", 1800.0, True)
        self.assertIn("分析模型", md)
        self.assertIn("启动时间", md)
        self.assertIn("2026-05-30 21:00:00", md)
        self.assertIn("完成时间", md)
        self.assertIn("2026-05-30 21:30:00", md)
        self.assertIn("总耗时", md)
        self.assertIn("1800.0 秒", md)

    def test_counts_show_success_and_failure(self):
        results = [
            _ok("600519", "茅台", "观察"),
            {"symbol": "999999", "ok": False, "error": "代码非法"},
        ]
        md = build_batch_summary(results, "t1", "t2", 10.0, True)
        self.assertIn("标的数量：2", md)
        self.assertIn("成功 1", md)
        self.assertIn("失败 1", md)

    def test_cache_state_shown(self):
        md_on = build_batch_summary([_ok("600519", "x", "观察")],
                                    "a", "b", 1.0, True)
        md_off = build_batch_summary([_ok("600519", "x", "观察")],
                                     "a", "b", 1.0, False)
        self.assertIn("启用", md_on)
        self.assertIn("禁用", md_off)


class TestFailureSection(unittest.TestCase):
    def test_no_failures_shown_explicitly(self):
        md = build_batch_summary([_ok("600519", "x", "观察")],
                                 "a", "b", 1.0, True)
        self.assertIn("全部成功", md)

    def test_failures_table_rendered(self):
        results = [
            _ok("600519", "x", "观察"),
            {"symbol": "999999", "ok": False, "error": "代码非法"},
            {"symbol": "888888", "ok": False, "error": "AKShare 超时|重试失败"},
        ]
        md = build_batch_summary(results, "a", "b", 1.0, True)
        self.assertIn("| 999999 |", md)
        self.assertIn("| 888888 |", md)
        # 错误中的 | 应被替换为 /，避免破坏表格列
        self.assertIn("AKShare 超时/重试失败", md)


class TestReportLinks(unittest.TestCase):
    def test_link_uses_filename_only(self):
        results = [_ok("600519", "茅台", "谨慎关注",
                       path="C:/abs/path/to/A股_600519_20260530.md")]
        md = build_batch_summary(results, "a", "b", 1.0, True)
        # 链接应该用相对文件名，不暴露绝对路径
        self.assertIn("A股_600519_20260530.md", md)
        self.assertNotIn("C:/abs/path/to/", md)

    def test_no_path_no_link(self):
        results = [_ok("600519", "茅台", "谨慎关注", path="")]
        md = build_batch_summary(results, "a", "b", 1.0, True)
        # 不会因为缺路径报错，且表格仍生成
        self.assertIn("600519", md)
        self.assertIn("谨慎关注", md)


class TestGroupingSection(unittest.TestCase):
    def test_all_four_groups_appear_even_if_empty(self):
        results = [_ok("600519", "茅台", "谨慎关注")]
        md = build_batch_summary(results, "a", "b", 1.0, True)
        # 4 个分组小标题必须都出现，缺的分组显示"（无）"
        for label in ("高风险", "暂不参与", "谨慎关注", "观察"):
            self.assertIn(label, md)
        # 至少 3 个空组
        self.assertGreaterEqual(md.count("（无）"), 3)

    def test_group_counts_correct(self):
        results = [
            _ok("600519", "茅台", "高风险"),
            _ok("000001", "平安", "高风险"),
            _ok("300750", "宁德", "谨慎关注"),
        ]
        md = build_batch_summary(results, "a", "b", 1.0, True)
        self.assertIn("高风险 (2)", md)
        self.assertIn("谨慎关注 (1)", md)
        self.assertIn("暂不参与 (0)", md)
        self.assertIn("观察 (0)", md)


class TestSafetyNet(unittest.TestCase):
    def test_no_forbidden_word_in_summary_template(self):
        # 汇总模板里固定文字不应触发任何禁词（确保汇总不需要二次 sanitize）
        results = [
            _ok("600519", "茅台", "高风险"),
            _ok("000001", "平安", "观察"),
        ]
        md = build_batch_summary(results, "a", "b", 1.0, True)
        for w in _FORBIDDEN:
            self.assertNotIn(w, md, f"汇总模板中出现禁词 {w!r}")

    def test_must_contain_disclaimer(self):
        md = build_batch_summary([_ok("600519", "x", "观察")],
                                 "a", "b", 1.0, True)
        self.assertIn("不构成投资建议", md)
        self.assertIn("不含任何买卖指令", md)
        self.assertIn("免责声明", md)


class TestEdgeCases(unittest.TestCase):
    def test_empty_results(self):
        # 空批次也应能生成合法汇总（标的=0、成功=0、失败=0）
        md = build_batch_summary([], "a", "b", 0.0, True)
        self.assertIn("标的数量：0", md)
        self.assertIn("全部成功", md)

    def test_all_failed(self):
        results = [
            {"symbol": "999999", "ok": False, "error": "x"},
            {"symbol": "888888", "ok": False, "error": "y"},
        ]
        md = build_batch_summary(results, "a", "b", 0.0, True)
        self.assertIn("成功 0", md)
        self.assertIn("失败 2", md)
        # 表格仍然有表头，但 body 为空
        self.assertIn("| 代码 | 名称 | 最终结论", md)


if __name__ == "__main__":
    unittest.main(verbosity=2)
