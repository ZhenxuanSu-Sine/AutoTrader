"""Backtrader数据加载器。"""

from pathlib import Path
import pandas as pd
import backtrader as bt


class BacktraderDataLoader:
    """Backtrader数据加载器。

    将CSV或Parquet文件加载为Backtrader可用的数据源。
    """

    @staticmethod
    def load_from_file(file_path: str) -> bt.feeds.PandasData:
        """从文件加载数据为Backtrader数据源。

        支持CSV和Parquet格式。文件必须包含以下列：
        datetime, open, high, low, close, volume

        Args:
            file_path: 数据文件路径

        Returns:
            Backtrader PandasData feed
        """
        file_path = Path(file_path)

        if file_path.suffix.lower() == ".parquet":
            df = pd.read_parquet(file_path)
        elif file_path.suffix.lower() == ".csv":
            df = pd.read_csv(file_path, parse_dates=['datetime'])
        else:
            raise ValueError(f"不支持的文件格式: {file_path.suffix}，支持CSV和Parquet")

        # 确保按日期排序
        df = df.sort_values('datetime')

        # 验证必需的列
        required_cols = ['datetime', 'open', 'high', 'low', 'close', 'volume']
        missing_cols = set(required_cols) - set(df.columns)
        if missing_cols:
            raise ValueError(f"缺少必需的列: {missing_cols}")

        return bt.feeds.PandasData(dataname=df, datetime='datetime')

