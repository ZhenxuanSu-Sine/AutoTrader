"""Parquet格式数据存储实现。"""

from pathlib import Path
from typing import Optional
import pandas as pd


class ParquetStorage:
    """Parquet格式数据存储类。

    提供数据的保存、读取和合并功能。
    """

    def __init__(self, base_dir: str = "data/ohlcv/daily"):
        """
        Args:
            base_dir: 数据存储的基础目录
        """
        self.base_dir = Path(base_dir)

    def get_path(self, symbol: str, subdir: Optional[str] = None) -> Path:
        """获取指定股票的数据文件路径。

        Args:
            symbol: 6位股票代码
            subdir: 子目录，如"akshare"

        Returns:
            文件路径
        """
        if subdir:
            return self.base_dir / subdir / f"symbol={symbol}.parquet"
        return self.base_dir / f"symbol={symbol}.parquet"

    def save(self, df: pd.DataFrame, symbol: str, subdir: Optional[str] = None, merge: bool = False) -> None:
        """保存数据到Parquet文件。

        Args:
            df: 要保存的DataFrame
            symbol: 股票代码
            subdir: 子目录
            merge: 如果文件已存在，是否合并数据（去重并排序）
        """
        path = self.get_path(symbol, subdir)
        path.parent.mkdir(parents=True, exist_ok=True)

        if merge and path.exists():
            old_df = pd.read_parquet(path)
            merged = pd.concat([old_df, df], axis=0, ignore_index=True)
            merged = merged.drop_duplicates(subset=["datetime"]).sort_values("datetime")
            merged.to_parquet(path, index=False)
        else:
            df.to_parquet(path, index=False)

    def load(self, symbol: str, subdir: Optional[str] = None) -> pd.DataFrame:
        """从Parquet文件加载数据。

        Args:
            symbol: 股票代码
            subdir: 子目录

        Returns:
            DataFrame

        Raises:
            FileNotFoundError: 如果文件不存在
        """
        path = self.get_path(symbol, subdir)
        if not path.exists():
            raise FileNotFoundError(f"数据文件不存在: {path}")
        return pd.read_parquet(path)

    def exists(self, symbol: str, subdir: Optional[str] = None) -> bool:
        """检查数据文件是否存在。

        Args:
            symbol: 股票代码
            subdir: 子目录

        Returns:
            是否存在
        """
        return self.get_path(symbol, subdir).exists()

    def get_max_date(self, symbol: str, subdir: Optional[str] = None) -> Optional[str]:
        """获取数据文件中的最大日期。

        Args:
            symbol: 股票代码
            subdir: 子目录

        Returns:
            最大日期字符串（YYYYMMDD格式），如果文件不存在或为空则返回None
        """
        if not self.exists(symbol, subdir):
            return None
        df = pd.read_parquet(self.get_path(symbol, subdir), columns=["datetime"])
        if df.empty:
            return None
        return df["datetime"].max().strftime("%Y%m%d")

