"""股票池工具函数。"""

from pathlib import Path
import pandas as pd


def load_universe(csv_path: str) -> list[str]:
    """从CSV文件加载股票代码列表。

    自动识别常见的列名：symbol, code, 代码，或使用第一列。

    Args:
        csv_path: CSV文件路径

    Returns:
        股票代码列表（6位数字字符串）
    """
    df = pd.read_csv(csv_path)
    for col in ["symbol", "code", "代码"]:
        if col in df.columns:
            return df[col].astype(str).str.extract(r"(\d{6})", expand=False).dropna().unique().tolist()
    # 如果没有找到标准列名，使用第一列
    return df[df.columns[0]].astype(str).str.extract(r"(\d{6})", expand=False).dropna().unique().tolist()


def extract_symbols(codes_str: str) -> list[str]:
    """从逗号分隔的代码字符串中提取6位股票代码。

    Args:
        codes_str: 逗号分隔的代码字符串，如"000001,600519,sh600000"

    Returns:
        股票代码列表（6位数字字符串）
    """
    codes = [s.strip()[-6:] for s in codes_str.split(",") if s.strip()]
    return list(set(codes))  # 去重

