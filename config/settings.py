"""配置设置类。"""

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Settings:
    """应用配置类。"""

    # 数据目录
    data_dir: str = "data"
    ohlcv_dir: str = "data/ohlcv/daily"
    logs_dir: str = "logs"
    reports_dir: str = "reports"
    meta_dir: str = "meta"

    # 默认数据源配置
    default_data_source: str = "akshare"
    default_source_order: list = None

    # 默认回测配置
    default_initial_cash: float = 100_000.0
    default_commission: float = 0.001
    default_slippage: float = 0.0

    def __post_init__(self):
        """初始化后处理。"""
        if self.default_source_order is None:
            self.default_source_order = ["em_hist", "sina_daily", "tx_hist"]

    def get_ohlcv_path(self, subdir: str = "akshare") -> Path:
        """获取OHLCV数据目录路径。"""
        return Path(self.ohlcv_dir) / subdir

    def get_logs_path(self) -> Path:
        """获取日志目录路径。"""
        return Path(self.logs_dir)

    def get_reports_path(self) -> Path:
        """获取报告目录路径。"""
        return Path(self.reports_dir)


# 全局配置实例
settings = Settings()

