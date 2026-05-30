"""A 股数据 provider，基于 AKShare（只读）。

只负责 A 股，6 位数字代码即可（无需 sh/sz 前缀）。
所有数据块都会记录：数据来源（_sources）+ 抓取时间（_fetched_at）。
任何子接口失败都不会抛出，而是降级为 None / mock 并在 data_quality 里标注，
保证无网络 / 未装 akshare 时也能跑通全流程。

绝不调用任何下单、交易、live、行情订阅接口——本模块只读。
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# === pandas-3 / pyarrow 兼容性补丁（必须在 import akshare 之前生效）===
try:
    pd.set_option("future.infer_string", False)
    pd.set_option("mode.string_storage", "python")
except Exception:
    pass


A_SHARE_CODE_RE = re.compile(r"^\d{6}$")
_NAME_CACHE_FILE = Path(__file__).resolve().parent.parent / "data" / "a_share_names.json"
_name_cache: Dict[str, str] = {}

MARKET_NAME = "A股"
CURRENCY = "CNY"


# =====================================================
# 工具
# =====================================================

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _normalize_symbol(symbol: str) -> str:
    return (symbol or "").strip()


def _to_yyyymmdd(s: str) -> str:
    if not s:
        return ""
    return s.strip().replace("-", "").replace("/", "")


def _try_import_akshare():
    try:
        import akshare as ak

        return ak
    except Exception:
        return None


def _exchange_prefix(symbol: str) -> str:
    """6 开头沪市；0/3 开头深市；4/8/9 北交所（本期不支持）。"""
    if not symbol:
        return ""
    head = symbol[0]
    if head == "6":
        return "sh"
    if head in ("0", "3"):
        return "sz"
    if head in ("4", "8", "9"):
        return "bj"
    return ""


def _safe_float(v) -> Optional[float]:
    if v is None:
        return None
    try:
        if isinstance(v, str):
            s = v.strip().replace(",", "").replace("%", "")
            if s in ("", "--", "nan", "None", "-"):
                return None
            v = s
        f = float(v)
        if np.isnan(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _str_or_none(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in ("--", "nan", "None"):
        return None
    return s


def _first_existing(df: pd.DataFrame, candidates):
    for c in candidates:
        if c in df.columns:
            return c
    return None


def _baidu_valuation_latest(ak, symbol: str, indicator: str) -> Optional[float]:
    """百度股市通估值（总市值/市盈率(TTM)/市净率），取近一年最新一行的值。"""
    try:
        df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator=indicator, period="近一年")
    except Exception:
        return None
    if df is None or df.empty:
        return None
    val_col = _first_existing(df, ["value", "数值"]) or df.columns[-1]
    try:
        return _safe_float(df.iloc[-1].get(val_col))
    except Exception:
        return None


def _default_start() -> str:
    return (datetime.now() - timedelta(days=365)).strftime("%Y%m%d")


def _default_end() -> str:
    return datetime.now().strftime("%Y%m%d")


# =====================================================
# 名称缓存
# =====================================================

def _load_name_cache(force: bool = False) -> Dict[str, str]:
    global _name_cache
    if _name_cache and not force:
        return _name_cache
    if not force and _NAME_CACHE_FILE.exists():
        try:
            with open(_NAME_CACHE_FILE, "r", encoding="utf-8") as f:
                _name_cache = json.load(f)
                if _name_cache:
                    return _name_cache
        except Exception:
            pass
    ak = _try_import_akshare()
    if ak is None:
        return {}
    try:
        df = ak.stock_info_a_code_name()
        if df is None or df.empty:
            return {}
        _name_cache = dict(zip(df["code"].astype(str), df["name"].astype(str)))
        try:
            _NAME_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(_NAME_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(_name_cache, f, ensure_ascii=False)
        except Exception:
            pass
        return _name_cache
    except Exception:
        return {}


# =====================================================
# 校验
# =====================================================

def validate_symbol(symbol: str) -> bool:
    sym = _normalize_symbol(symbol)
    if not A_SHARE_CODE_RE.match(sym):
        return False
    # 北交所本期不支持
    return _exchange_prefix(sym) in ("sh", "sz")


# =====================================================
# A. 公司基本面 / 基础信息
# =====================================================

def get_stock_info(symbol: str) -> Dict:
    symbol = _normalize_symbol(symbol)
    info: Dict = {
        "name": "",
        "industry": None,
        "main_business": None,
        "listing_date": None,
        "current_price": None,
        "market_cap": None,
        "circulating_market_cap": None,
        "total_share": None,
        "float_share": None,
        "pe": None,
        "pb": None,
        "_sources": [],
        "_fetched_at": _now(),
    }
    ak = _try_import_akshare()

    name_map = _load_name_cache()
    if name_map.get(symbol):
        info["name"] = name_map[symbol]
        info["_sources"].append("stock_info_a_code_name（新浪）")

    if ak is None:
        if not info["name"]:
            info["name"] = f"A股-{symbol}"
        return info

    # 东财个股基础信息（市值/股本/行业/上市时间）
    try:
        df = ak.stock_individual_info_em(symbol=symbol)
        if df is not None and not df.empty:
            kv = dict(zip(df["item"].astype(str), df["value"]))
            info["name"] = info["name"] or _str_or_none(kv.get("股票简称")) or info["name"]
            info["industry"] = _str_or_none(kv.get("行业"))
            info["listing_date"] = _str_or_none(kv.get("上市时间"))
            info["market_cap"] = _safe_float(kv.get("总市值"))
            info["circulating_market_cap"] = _safe_float(kv.get("流通市值"))
            info["total_share"] = _safe_float(kv.get("总股本"))
            info["float_share"] = _safe_float(kv.get("流通股"))
            info["_sources"].append("stock_individual_info_em（东财）")
    except Exception:
        pass

    # 主营业务（同花顺）
    try:
        df = ak.stock_zyjs_ths(symbol=symbol)
        if df is not None and not df.empty:
            row = df.iloc[0]
            info["main_business"] = _str_or_none(row.get("主营业务"))
            if not info["industry"]:
                info["industry"] = _str_or_none(row.get("产品类型")) or _str_or_none(
                    row.get("产品名称")
                )
            info["_sources"].append("stock_zyjs_ths（同花顺）")
    except Exception:
        pass

    # 总市值 / PE / PB（百度股市通估值，最新值；东财个股接口在本机不稳定时用此兜底）
    try:
        baidu_used = False
        if info["market_cap"] is None:
            mc = _baidu_valuation_latest(ak, symbol, "总市值")
            if mc is not None:
                # 百度返回单位为「亿元」，存为带单位字符串便于报告直接展示
                info["market_cap"] = f"{round(mc, 2)}亿元"
                baidu_used = True
        if info["pe"] is None:
            pe = _baidu_valuation_latest(ak, symbol, "市盈率(TTM)")
            if pe is not None:
                info["pe"] = round(pe, 2)
                baidu_used = True
        if info["pb"] is None:
            pb = _baidu_valuation_latest(ak, symbol, "市净率")
            if pb is not None:
                info["pb"] = round(pb, 2)
                baidu_used = True
        if baidu_used:
            info["_sources"].append("stock_zh_valuation_baidu（百度股市通）")
    except Exception:
        pass

    if not info["name"]:
        info["name"] = f"A股-{symbol}"
    return info


# =====================================================
# B. 历史行情（技术面输入）
# =====================================================

_HIST_COL_MAP = {
    "日期": "date", "开盘": "open", "最高": "high", "最低": "low",
    "收盘": "close", "成交量": "volume", "成交额": "amount",
    "涨跌幅": "pct_change", "换手率": "turnover_rate", "振幅": "amplitude",
}


def _normalize_hist(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={k: v for k, v in _HIST_COL_MAP.items() if k in df.columns})
    for c in ("date", "open", "high", "low", "close", "volume"):
        if c not in df.columns:
            df[c] = np.nan
    try:
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    except Exception:
        df["date"] = df["date"].astype(str)
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")
    if "turnover_rate" in df.columns:
        df["turnover_rate"] = pd.to_numeric(df["turnover_rate"], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def _resample_kline(df: pd.DataFrame, target: str) -> pd.DataFrame:
    rule = {"weekly": "W", "monthly": "ME"}.get(target.lower())
    if rule is None or df is None or df.empty:
        return df
    d = df.copy()
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date")
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    if "amount" in d.columns:
        agg["amount"] = "sum"
    agg = {k: v for k, v in agg.items() if k in d.columns}
    out = d.resample(rule).agg(agg).dropna(how="all").reset_index()
    out["date"] = out["date"].dt.strftime("%Y-%m-%d")
    return out


def get_history(
    symbol: str,
    start_date: str,
    end_date: str,
    period: str = "daily",
    adjust: str = "",
) -> pd.DataFrame:
    symbol = _normalize_symbol(symbol)
    start = _to_yyyymmdd(start_date) or _default_start()
    end = _to_yyyymmdd(end_date) or _default_end()
    target = (period or "daily").lower()

    ak = _try_import_akshare()
    if ak is None:
        return _mock_history(symbol, start, end, "未安装 akshare")

    prefix = _exchange_prefix(symbol)
    if prefix not in ("sh", "sz"):
        return _mock_history(symbol, start, end, f"无法识别交易所或不支持：{symbol}")

    prefixed = prefix + symbol

    # 1) 东财日 K（含成交额/换手率，资金面会用到）
    try:
        df = ak.stock_zh_a_hist(
            symbol=symbol, period="daily", start_date=start, end_date=end, adjust=adjust or ""
        )
        if df is not None and not df.empty:
            df = _normalize_hist(df)
            df.attrs["source"] = "stock_zh_a_hist（东财）"
            return _resample_kline(df, target) if target != "daily" else df
    except Exception:
        pass

    # 2) 新浪日 K
    try:
        df = ak.stock_zh_a_daily(symbol=prefixed, adjust=adjust or "", start_date=start, end_date=end)
        if df is not None and not df.empty:
            df = _normalize_hist(df)
            df.attrs["source"] = "stock_zh_a_daily（新浪）"
            return _resample_kline(df, target) if target != "daily" else df
    except Exception:
        pass

    # 3) 腾讯日 K（无 volume，用 amount 近似）
    try:
        df = ak.stock_zh_a_hist_tx(symbol=prefixed, adjust=adjust or "", start_date=start, end_date=end)
        if df is not None and not df.empty:
            if "volume" not in df.columns and "amount" in df.columns:
                df = df.copy()
                df["volume"] = df["amount"]
            df = _normalize_hist(df)
            df.attrs["source"] = "stock_zh_a_hist_tx（腾讯）"
            return _resample_kline(df, target) if target != "daily" else df
    except Exception:
        pass

    return _mock_history(symbol, start, end, "东财/新浪/腾讯日K均失败")


# =====================================================
# A. 财务（基本面深入）
# =====================================================

def _pick_latest_report_col(df: pd.DataFrame):
    key_cols = {"指标", "选项"}
    candidates = [c for c in df.columns if c not in key_cols]
    parseable = []
    for c in candidates:
        try:
            parseable.append((pd.to_datetime(str(c)), c))
        except Exception:
            continue
    if parseable:
        parseable.sort(reverse=True)
        return parseable[0][1]
    return candidates[-1] if candidates else None


def get_financials(symbol: str) -> Dict:
    symbol = _normalize_symbol(symbol)
    out: Dict = {
        "snapshot": {},
        "indicators_latest": {},
        "growth": {},
        "_sources": [],
        "_fetched_at": _now(),
    }
    ak = _try_import_akshare()
    if ak is None:
        return out

    # 1) 财务摘要（营收/净利润/现金流等绝对值）
    try:
        df = ak.stock_financial_abstract(symbol=symbol)
        if df is not None and not df.empty:
            latest_col = _pick_latest_report_col(df)
            key_col = "指标" if "指标" in df.columns else (
                "选项" if "选项" in df.columns else df.columns[0]
            )
            if latest_col is not None:
                snap = {}
                for _, row in df.iterrows():
                    key = str(row.get(key_col, "")).strip()
                    if key:
                        snap[key] = _safe_float(row.get(latest_col))
                out["latest_period"] = str(latest_col)
                out["snapshot"] = snap
                out["_sources"].append("stock_financial_abstract（新浪）")
    except Exception:
        pass

    # 2) 财务分析指标（ROE、负债率、净利率等）
    try:
        try:
            df2 = ak.stock_financial_analysis_indicator(symbol=symbol)
        except TypeError:
            df2 = ak.stock_financial_analysis_indicator(symbol=symbol, start_year="2020")
        if df2 is not None and not df2.empty:
            df2 = df2.copy()
            date_col = df2.columns[0]
            try:
                df2 = df2.sort_values(date_col, ascending=False)
            except Exception:
                pass
            latest_row = df2.iloc[0]
            interested = [
                "净资产收益率(%)", "总资产利润率(%)", "销售净利率(%)", "销售毛利率(%)",
                "资产负债率(%)", "流动比率", "速动比率", "摊薄每股收益(元)",
                "主营业务收入增长率(%)", "净利润增长率(%)",
            ]
            latest = {k: _safe_float(latest_row.get(k)) for k in interested if k in latest_row.index}
            if latest:
                out["indicators_latest"] = latest
                out["indicators_period"] = str(latest_row.get(date_col, ""))
                out["_sources"].append("stock_financial_analysis_indicator（新浪）")
                # 把增长率单独提到 growth 区
                if latest.get("主营业务收入增长率(%)") is not None:
                    out["growth"]["营收增长率(%)"] = latest["主营业务收入增长率(%)"]
                if latest.get("净利润增长率(%)") is not None:
                    out["growth"]["净利润增长率(%)"] = latest["净利润增长率(%)"]
    except Exception:
        pass

    return out


# =====================================================
# C. 资金面（主力 / 北向 / 成交额 / 换手率）
# =====================================================

def _capital_metrics_from_hist(h) -> Dict:
    """从日K最新一行取 成交额 / 换手率（纯计算，便于单测，不联网）。

    - 东财源 stock_zh_a_hist：normalize 后含 turnover_rate（已是百分比，直接用）。
    - 新浪源 stock_zh_a_daily：含 turnover（小数 = 成交量/流通股），×100 才是换手率百分比。
    """
    out = {"amount_latest": None, "turnover_rate_latest": None}
    if h is None or getattr(h, "empty", True):
        return out
    last = h.iloc[-1]
    if "amount" in h.columns:
        out["amount_latest"] = _safe_float(last.get("amount"))
    tr = _safe_float(last.get("turnover_rate")) if "turnover_rate" in h.columns else None
    if tr is None and "turnover" in h.columns:
        tv = _safe_float(last.get("turnover"))
        tr = round(tv * 100, 4) if tv is not None else None
    out["turnover_rate_latest"] = tr
    return out


def get_capital_flow(symbol: str, hist_df: Optional[pd.DataFrame] = None) -> Dict:
    symbol = _normalize_symbol(symbol)
    out: Dict = {
        "main_fund_recent": [],     # 近几日主力净流入
        "main_fund_5d_sum": None,
        "turnover_rate_latest": None,
        "amount_latest": None,      # 最新成交额（元）
        "northbound": None,         # 北向（best effort，不可得则 None）
        "_sources": [],
        "_fetched_at": _now(),
    }
    ak = _try_import_akshare()
    if ak is None:
        return out

    prefix = _exchange_prefix(symbol)

    # 主力资金流（东财个股资金流）
    try:
        if prefix in ("sh", "sz"):
            df = ak.stock_individual_fund_flow(stock=symbol, market=prefix)
            if df is not None and not df.empty:
                col_date = _first_existing(df, ["日期"])
                col_main = _first_existing(df, ["主力净流入-净额", "主力净流入"])
                col_to = _first_existing(df, ["换手率"])
                tail = df.tail(5)
                recent = []
                for _, row in tail.iterrows():
                    recent.append({
                        "date": str(row.get(col_date, "")) if col_date else "",
                        "main_net": _safe_float(row.get(col_main)) if col_main else None,
                    })
                out["main_fund_recent"] = recent
                vals = [r["main_net"] for r in recent if r["main_net"] is not None]
                out["main_fund_5d_sum"] = round(sum(vals), 2) if vals else None
                if col_to:
                    out["turnover_rate_latest"] = _safe_float(df.iloc[-1].get(col_to))
                out["_sources"].append("stock_individual_fund_flow（东财）")
    except Exception:
        pass

    # 成交额 / 换手率兜底：主力资金流接口（东财 push2）在本机偶发被服务端断连，
    # 失败时从日K取最新成交额与换手率，保证资金面不至于整段缺失。
    try:
        h = hist_df
        if h is None or getattr(h, "empty", True):
            h = get_history(symbol, _default_start(), _default_end())
        if h is not None and not h.empty and not getattr(h, "attrs", {}).get("is_mock"):
            m = _capital_metrics_from_hist(h)
            if out["amount_latest"] is None and m["amount_latest"] is not None:
                out["amount_latest"] = m["amount_latest"]
            if out["turnover_rate_latest"] is None and m["turnover_rate_latest"] is not None:
                out["turnover_rate_latest"] = m["turnover_rate_latest"]
            if out["amount_latest"] is not None or out["turnover_rate_latest"] is not None:
                src = (getattr(h, "attrs", {}) or {}).get("source", "日K")
                out["_sources"].append(f"{src}（成交额/换手率兜底）")
    except Exception:
        pass

    # 北向资金（市场级 best effort；个股实时北向已停止披露，故只取汇总作参考）
    try:
        df = ak.stock_hsgt_fund_flow_summary_em()
        if df is not None and not df.empty:
            out["northbound"] = {
                "note": "北向为市场级汇总（个股实时北向已停止披露），仅作环境参考",
                "rows": df.tail(4).to_dict(orient="records"),
            }
            out["_sources"].append("stock_hsgt_fund_flow_summary_em（东财，市场级）")
    except Exception:
        pass

    return out


# =====================================================
# D. 消息面
# =====================================================

_NEWS_DT_FORMATS = (
    "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d",
    "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M", "%Y/%m/%d",
)


def _parse_news_dt(s) -> Optional[datetime]:
    """尽力解析新闻发布时间，解析不了返回 None（不误杀，后续保留该条）。"""
    if not s:
        return None
    txt = str(s).strip()
    for fmt in _NEWS_DT_FORMATS:
        try:
            return datetime.strptime(txt, fmt)
        except (ValueError, TypeError):
            continue
    return None


def _norm_title(t) -> str:
    """标题标准化用于去重：去空白、转小写。"""
    if not t:
        return ""
    return re.sub(r"\s+", "", str(t)).lower()


def _dedup_and_filter_news(
    items: List[Dict], now: Optional[datetime] = None, max_age_days: int = 30, limit: int = 12,
) -> List[Dict]:
    """对新闻做：① 按时间降序（新在前、无日期排后）② 时效过滤（早于 cutoff 丢弃，解析不了保留）
    ③ 标题去重（保留最新一条）④ 截断到 limit。

    纯计算、可单测、不联网。若时效过滤后为空（新闻都很旧），退回按时间降序的全量，
    避免消息面整段空白——但顺序仍是新在前，分析师可据日期自行判断时效。
    """
    if not items:
        return []
    now = now or datetime.now()
    cutoff = now - timedelta(days=max_age_days)

    def _key(it):
        dt = _parse_news_dt(it.get("date"))
        return (dt is not None, dt or datetime.min)

    ordered = sorted(items, key=_key, reverse=True)
    fresh = [it for it in ordered
             if (_parse_news_dt(it.get("date")) is None
                 or _parse_news_dt(it.get("date")) >= cutoff)]
    base = fresh if fresh else ordered

    seen = set()
    result: List[Dict] = []
    for it in base:
        key = _norm_title(it.get("title"))
        if key and key in seen:
            continue
        seen.add(key)
        result.append(it)
        if len(result) >= limit:
            break
    return result


def get_news(symbol: str) -> List[Dict]:
    symbol = _normalize_symbol(symbol)
    ak = _try_import_akshare()
    if ak is None:
        return _mock_news(symbol, "未安装 akshare")
    try:
        df = ak.stock_news_em(symbol=symbol)
    except Exception as e:
        return _mock_news(symbol, f"新闻接口异常：{e}")
    if df is None or df.empty:
        return _mock_news(symbol, "新闻接口返回为空")

    col_title = _first_existing(df, ["新闻标题", "标题"])
    col_time = _first_existing(df, ["发布时间", "时间"])
    col_content = _first_existing(df, ["新闻内容", "内容", "摘要"])
    col_source = _first_existing(df, ["文章来源", "来源"])
    col_link = _first_existing(df, ["新闻链接", "链接", "url"])

    out: List[Dict] = []
    for _, row in df.head(50).iterrows():
        title = _str_or_none(row.get(col_title)) if col_title else None
        content = _str_or_none(row.get(col_content)) if col_content else None
        out.append({
            "title": title or "(无标题)",
            "date": (_str_or_none(row.get(col_time)) if col_time else "") or "",
            "source": (_str_or_none(row.get(col_source)) if col_source else None) or "东方财富",
            "summary": (content or title or "")[:240],
            "url": (_str_or_none(row.get(col_link)) if col_link else "") or "",
            "is_mock": False,
        })
    # 去重（标题）+ 时效过滤（默认近30天）+ 按时间降序，避免重复/过期新闻干扰消息面判断
    out = _dedup_and_filter_news(out, max_age_days=30, limit=12)
    return out or _mock_news(symbol, "解析新闻为空")


# =====================================================
# 统一编排
# =====================================================

def fetch_market_data(
    symbol: str,
    start_date: str = "",
    end_date: str = "",
    period: str = "daily",
    adjust: str = "",
) -> Dict:
    """统一返回标准化 market_data，并对每个数据块标注来源/抓取时间/质量。"""
    symbol = _normalize_symbol(symbol)
    errors: List[str] = []
    dq = {
        "price_data": "ok",
        "financial_data": "ok",
        "capital_data": "ok",
        "news_data": "ok",
    }

    if not validate_symbol(symbol):
        return {
            "market": MARKET_NAME, "symbol": symbol, "name": "", "currency": CURRENCY,
            "current_price": None, "info": {}, "history": pd.DataFrame(),
            "financials": {}, "capital_flow": {}, "news": [], "indicators": {},
            "data_quality": {k: "failed" for k in dq}, "fetched_at": _now(),
            "errors": [f"股票代码不合法或非沪深 A 股：{symbol}（仅支持 6 位数字、6/0/3 开头）"],
        }

    info = _safe_call(get_stock_info, symbol, default={}, errors=errors, label="基础信息")

    history = _safe_call(get_history, symbol, start_date, end_date, period, adjust,
                         default=pd.DataFrame(), errors=errors, label="历史行情")
    if history is None or history.empty:
        dq["price_data"] = "failed"
        errors.append("历史行情为空")
    elif getattr(history, "attrs", {}).get("is_mock"):
        dq["price_data"] = "mock"
        errors.append("行情数据来源为 mock，请审慎对待")

    financials = _safe_call(get_financials, symbol, default={}, errors=errors, label="财务")
    if not financials or (not financials.get("snapshot") and not financials.get("indicators_latest")):
        dq["financial_data"] = "partial"

    capital = _safe_call(get_capital_flow, symbol, history, default={}, errors=errors, label="资金面")
    if not capital or not capital.get("_sources"):
        dq["capital_data"] = "failed"
    elif not capital.get("main_fund_recent"):
        # 主力资金流缺失（仅靠日K成交额/换手率兜底）时如实标 partial
        dq["capital_data"] = "partial"

    news = _safe_call(get_news, symbol, default=[], errors=errors, label="新闻")
    if not news:
        dq["news_data"] = "partial"
    elif any(n.get("is_mock") for n in news):
        dq["news_data"] = "mock"

    current_price = info.get("current_price")
    if current_price is None and history is not None and not history.empty and "close" in history.columns:
        try:
            current_price = float(history["close"].iloc[-1])
        except Exception:
            current_price = None

    return {
        "market": MARKET_NAME,
        "symbol": symbol,
        "name": info.get("name", "") or f"A股-{symbol}",
        "currency": CURRENCY,
        "current_price": current_price,
        "info": info,
        "history": history,
        "financials": financials,
        "capital_flow": capital,
        "news": news,
        "indicators": {},
        "data_quality": dq,
        "fetched_at": _now(),
        "errors": errors,
    }


def _safe_call(fn, *args, default=None, errors=None, label=""):
    try:
        return fn(*args)
    except Exception as e:
        if errors is not None:
            errors.append(f"{label}获取失败：{e}")
        return default


# =====================================================
# mock 兜底
# =====================================================

def _mock_history(symbol: str, start: str, end: str, reason: str = "") -> pd.DataFrame:
    try:
        start_dt = datetime.strptime(start, "%Y%m%d")
    except Exception:
        start_dt = datetime.now() - timedelta(days=365)
    try:
        end_dt = datetime.strptime(end, "%Y%m%d")
    except Exception:
        end_dt = datetime.now()
    if end_dt <= start_dt:
        end_dt = start_dt + timedelta(days=180)

    dates = pd.date_range(start_dt, end_dt, freq="B")
    n = len(dates)
    if n == 0:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])

    rng = np.random.default_rng(abs(hash(symbol)) % (2 ** 32))
    rets = rng.normal(0, 0.015, size=n)
    price = 30.0
    closes = []
    for r in rets:
        price = max(1.0, price * (1 + r))
        closes.append(price)
    closes = np.array(closes)
    opens = closes * (1 + rng.normal(0, 0.005, size=n))
    highs = np.maximum(opens, closes) * (1 + np.abs(rng.normal(0, 0.005, size=n)))
    lows = np.minimum(opens, closes) * (1 - np.abs(rng.normal(0, 0.005, size=n)))
    volumes = rng.integers(1_000_000, 10_000_000, size=n).astype(float)

    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in dates],
        "open": np.round(opens, 2),
        "high": np.round(highs, 2),
        "low": np.round(lows, 2),
        "close": np.round(closes, 2),
        "volume": volumes,
    })
    df.attrs["is_mock"] = True
    df.attrs["mock_reason"] = reason
    df.attrs["source"] = f"mock（{reason}）"
    return df


def _mock_news(symbol: str, reason: str = "") -> List[Dict]:
    today = datetime.now().strftime("%Y-%m-%d")
    return [{
        "title": f"[占位] {symbol} 新闻接口暂不可用",
        "date": today,
        "source": "mock",
        "summary": f"新闻接口暂不可用（{reason}），当前为模拟/占位数据，消息面不足以判断。",
        "url": "",
        "is_mock": True,
    }]
