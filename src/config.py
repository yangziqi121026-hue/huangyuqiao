"""配置加载，集中读取环境变量。

设计原则（写死，不可被参数覆盖）：
- ONLY_READONLY = True：本系统只做只读分析。
- 不存在任何券商 / 下单 / live 相关配置项。
"""

from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"
DATA_DIR.mkdir(exist_ok=True)
REPORTS_DIR.mkdir(exist_ok=True)


def _get_bool(name: str, default: bool = False) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val in ("1", "true", "yes", "on"):
        return True
    if val in ("0", "false", "no", "off"):
        return False
    return default


# ---------- LLM（仅 OpenAI 兼容协议）----------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip()
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini").strip()

# 没有 API Key 时强制 mock；用户也可显式开启 mock 跑通全流程
MOCK_MODE = _get_bool("MOCK_MODE", default=False) or not OPENAI_API_KEY


# ---------- 不可变安全约束（系统级，不接受任何外部覆盖）----------
ONLY_READONLY = True          # 只读分析
ENABLE_TRADING = False        # 永远禁止真实/模拟下单
ENABLE_LIVE = False           # 永远禁止 live / 实时订阅
ONLY_MARKET = "A股"           # 只分析 A 股，不接美股/港股/OKX

# 最终结论只允许这 4 个非交易指令标签（绝不出现"买入/卖出"）
ALLOWED_CONCLUSIONS = ("观察", "谨慎关注", "暂不参与", "高风险")
RISK_LEVELS = ("低", "中", "高", "不足以判断")

ANALYSIS_DEPTHS = ("快速", "标准", "深度")

ADJUST_MAP = {
    "不复权": "",
    "前复权": "qfq",
    "后复权": "hfq",
}

PERIOD_MAP = {
    "日线": "daily",
    "周线": "weekly",
    "月线": "monthly",
}


def get_settings_summary() -> dict:
    return {
        "model": MODEL_NAME,
        "base_url": OPENAI_BASE_URL,
        "mock_mode": MOCK_MODE,
        "has_api_key": bool(OPENAI_API_KEY),
        "only_readonly": ONLY_READONLY,
        "enable_trading": ENABLE_TRADING,
        "enable_live": ENABLE_LIVE,
        "only_market": ONLY_MARKET,
    }
