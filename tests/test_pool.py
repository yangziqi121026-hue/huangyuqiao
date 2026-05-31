"""锁定 src/pool.py 的解析规则：注释 / 空行 / 内联注释 / 去重 / 非法代码过滤。

纯标准库 unittest，不读真实文件（少量 read_pool_file 用 tmp 文件）。
"""

from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.pool import parse_pool_text, read_pool_file  # noqa: E402


class TestParsePoolText(unittest.TestCase):
    def test_simple_codes_one_per_line(self):
        text = "600519\n000001\n300750"
        self.assertEqual(parse_pool_text(text), ["600519", "000001", "300750"])

    def test_empty_and_whitespace_lines_skipped(self):
        text = "\n   \n600519\n\n000001\n"
        self.assertEqual(parse_pool_text(text), ["600519", "000001"])

    def test_full_line_comment_skipped(self):
        text = "# 这是注释\n600519\n# 又一条注释\n000001"
        self.assertEqual(parse_pool_text(text), ["600519", "000001"])

    def test_inline_comment_stripped(self):
        text = "600519 # 贵州茅台\n000001  # 平安银行"
        self.assertEqual(parse_pool_text(text), ["600519", "000001"])

    def test_dedup_preserves_first_order(self):
        text = "600519\n000001\n600519\n300750\n000001"
        self.assertEqual(parse_pool_text(text), ["600519", "000001", "300750"])

    def test_invalid_codes_dropped(self):
        text = "\n".join([
            "600519",        # ✓ 沪市
            "000001",        # ✓ 深市
            "300750",        # ✓ 创业板
            "12345",         # ✗ 5 位
            "1234567",       # ✗ 7 位
            "abcdef",        # ✗ 非数字
            "800001",        # ✗ 北交所
            "400001",        # ✗ 北交所
            "900001",        # ✗ 北交所/B股
            "AAPL",          # ✗ 美股
        ])
        self.assertEqual(parse_pool_text(text), ["600519", "000001", "300750"])

    def test_extra_columns_after_code_kept_via_first_token(self):
        # 行内代码后面有空格分隔的名称列时，取第一个 token
        text = "600519 贵州茅台 白酒\n000001 平安银行 银行"
        self.assertEqual(parse_pool_text(text), ["600519", "000001"])

    def test_leading_trailing_whitespace_per_line(self):
        text = "   600519   \n\t000001\t\n  300750"
        self.assertEqual(parse_pool_text(text), ["600519", "000001", "300750"])

    def test_empty_input(self):
        self.assertEqual(parse_pool_text(""), [])
        self.assertEqual(parse_pool_text(None), [])

    def test_mixed_comments_and_codes(self):
        text = """\
# 银行板块
000001  # 平安银行
600036  # 招商银行

# 白酒
600519  # 贵州茅台
000858  # 五粮液
# 600519 重复（应去重）
600519
"""
        self.assertEqual(
            parse_pool_text(text),
            ["000001", "600036", "600519", "000858"],
        )


class TestReadPoolFile(unittest.TestCase):
    def test_missing_file_returns_empty_list(self):
        self.assertEqual(read_pool_file("/no/such/path/pool.txt"), [])

    def test_read_real_tmpfile(self):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as f:
            f.write("600519 # 茅台\n# 一条注释\n000001\n")
            tmp_path = f.name
        try:
            self.assertEqual(read_pool_file(tmp_path), ["600519", "000001"])
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_read_passes_path_obj(self):
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".txt", delete=False
        ) as f:
            f.write("300750\n")
            tmp_path = Path(f.name)
        try:
            self.assertEqual(read_pool_file(tmp_path), ["300750"])
        finally:
            tmp_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
