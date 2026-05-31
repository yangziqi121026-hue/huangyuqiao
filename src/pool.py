"""批量分析的股票池解析（纯函数，不依赖 akshare / LLM）。

支持的 pool.txt 格式：
- 一行一个 6 位代码
- '#' 之后内容视为注释（行首注释整行跳过；行内注释剥离）
- 空行跳过
- 自动去重（按首次出现顺序保留）
- 过滤非沪深 A 股代码（首位必须 0/3/6；北交所 4/8/9 不支持）

示例：
    # 银行
    000001  # 平安银行
    600036  # 招商银行

    # 白酒
    600519
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Union

_A_SHARE_PATTERN = re.compile(r"^[036]\d{5}$")


def parse_pool_text(text: str) -> List[str]:
    """解析 pool 文本为去重后的合法 6 位代码列表（保留首次出现顺序）。

    非法行（非 6 位 / 非 0/3/6 开头 / 含非数字）静默丢弃，不抛异常。
    """
    if not text:
        return []
    seen: set[str] = set()
    out: List[str] = []
    for raw_line in text.splitlines():
        # 剥离行内注释
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        # 行内可能还有空格分隔的列（如代码后面跟名称），取第一段
        token = line.split()[0]
        if not _A_SHARE_PATTERN.match(token):
            continue
        if token in seen:
            continue
        seen.add(token)
        out.append(token)
    return out


def read_pool_file(path: Union[str, Path], encoding: str = "utf-8") -> List[str]:
    """读取 pool 文件并返回去重合法代码列表。

    文件不存在时返回空列表，由调用方决定如何提示。
    """
    p = Path(path)
    if not p.exists() or not p.is_file():
        return []
    text = p.read_text(encoding=encoding, errors="replace")
    return parse_pool_text(text)
