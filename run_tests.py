"""一键运行单元测试（只读项目的安全/逻辑回归）。

用法：
    python run_tests.py            # 跑全部测试
    python run_tests.py -q         # 安静模式（只看汇总）

特点：
- 纯标准库 unittest，无需安装 pytest。
- 不联网、不调用 LLM、不依赖 akshare —— 跑的是纯逻辑（指标/冲突对齐/结论抽取/禁词安全网）。
- 退出码 0 表示全部通过，非 0 表示有失败（方便接入 CI / pre-commit）。
"""

from __future__ import annotations

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.abspath(__file__))
TESTS_DIR = os.path.join(ROOT, "tests")


def main() -> int:
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    verbosity = 1 if "-q" in sys.argv else 2
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=TESTS_DIR, top_level_dir=ROOT)
    runner = unittest.TextTestRunner(verbosity=verbosity)
    result = runner.run(suite)

    print("\n" + "=" * 56)
    if result.wasSuccessful():
        print(f"✅ 全部通过：{result.testsRun} 个用例")
    else:
        print(
            f"❌ 有失败：共 {result.testsRun} 个，"
            f"失败 {len(result.failures)}，错误 {len(result.errors)}"
        )
    print("（这些测试不联网、不调 LLM，只验证只读分析的核心逻辑与安全约束）")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
