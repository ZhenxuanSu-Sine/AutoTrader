"""AKShare数据源实现。

提供统一的AKShare数据获取接口，支持多种AKShare API。
"""

from typing import Optional, Dict
import pandas as pd

try:
    import akshare as ak
except ImportError:
    ak = None


def _to_prefixed(symbol6: str) -> str:
    """将6位股票代码转换为带前缀的格式（sh/sz）。"""
    return ("sh" if symbol6.startswith(("5", "6")) else "sz") + symbol6


def _normalize_ohlcv(df: pd.DataFrame, mapping: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    将AKShare输出的各种格式标准化为统一格式：
    ['datetime', 'open', 'high', 'low', 'close', 'volume']
    并按datetime升序排序。
    """
    df = df.copy()

    # 自动检测常见的列名映射
    candidate_maps = [
        # 中文列名（常见于stock_zh_a_hist日线）
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"},
        # 英文列名
        {"date": "datetime", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
        # 成交量可能有不同后缀
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量(手)": "volume"},
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量(股)": "volume"},
    ]
    if mapping:
        candidate_maps.insert(0, mapping)

    for mp in candidate_maps:
        if all(col in df.columns for col in mp.keys()):
            df = df.rename(columns=mp)
            break
    else:
        raise ValueError(f"无法识别预期的OHLCV列: {df.columns.tolist()}")

    # 只保留必需的列，转换数据类型，排序
    use_cols = ["datetime", "open", "high", "low", "close", "volume"]
    df = df[use_cols].copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    # 数值列容错处理
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("datetime")
    return df


class AkshareDataSource:
    """AKShare数据源类。

    提供统一的接口从AKShare获取A股日线数据，支持多种AKShare API作为备选。
    """

    SUPPORTED_SOURCES = ["em_hist", "sina_daily", "tx_hist"]

    def __init__(self):
        if ak is None:
            raise ImportError("请先安装AKShare: pip install akshare")

    def fetch_daily(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "",
        source: str = "em_hist",
    ) -> pd.DataFrame:
        """
        获取单只股票的日线数据。

        Args:
            symbol: 6位股票代码，如"000001"或"600519"
            start_date: 开始日期，格式YYYYMMDD
            end_date: 结束日期，格式YYYYMMDD
            adjust: 复权类型，可选"", "qfq", "hfq"
            source: 数据源，可选"em_hist", "sina_daily", "tx_hist"

        Returns:
            标准化的DataFrame，包含列：datetime, open, high, low, close, volume
        """
        if source not in self.SUPPORTED_SOURCES:
            raise ValueError(f"不支持的数据源: {source}，支持的数据源: {self.SUPPORTED_SOURCES}")

        if source == "em_hist":
            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily", start_date=start_date, end_date=end_date, adjust=adjust
            )
        elif source == "sina_daily":
            df = ak.stock_zh_a_daily(
                symbol=_to_prefixed(symbol), start_date=start_date, end_date=end_date, adjust=adjust
            )
        elif source == "tx_hist":
            df = ak.stock_zh_a_hist_tx(
                symbol=_to_prefixed(symbol), start_date=start_date, end_date=end_date, adjust=adjust
            )

        return _normalize_ohlcv(df)

    def fetch_daily_with_fallback(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        adjust: str = "",
        source_order: Optional[list] = None,
    ) -> pd.DataFrame:
        """
        使用多个数据源依次尝试获取数据，直到成功。

        Args:
            symbol: 6位股票代码
            start_date: 开始日期，格式YYYYMMDD
            end_date: 结束日期，格式YYYYMMDD
            adjust: 复权类型
            source_order: 数据源优先级列表，默认["em_hist", "sina_daily", "tx_hist"]

        Returns:
            标准化的DataFrame

        Raises:
            RuntimeError: 如果所有数据源都失败
        """
        if source_order is None:
            source_order = ["em_hist", "sina_daily", "tx_hist"]

        last_error = None
        for source in source_order:
            try:
                df = self.fetch_daily(symbol, start_date, end_date, adjust, source)
                if not df.empty:
                    return df
            except Exception as e:
                last_error = e
                continue

        raise RuntimeError(f"所有数据源都失败，最后错误: {last_error}")

