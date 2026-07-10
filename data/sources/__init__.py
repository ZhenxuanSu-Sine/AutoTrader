"""数据源模块。

提供统一的数据源接口，支持多种数据源（AKShare等）。
"""

from data.sources.akshare_source import AkshareDataSource

__all__ = ['AkshareDataSource']

