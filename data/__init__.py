"""数据包。

提供统一的数据访问接口，包括数据源、存储和加载器。
"""

from data.sources import AkshareDataSource
from data.storage import ParquetStorage
from data.loaders import BacktraderDataLoader

__all__ = ['AkshareDataSource', 'ParquetStorage', 'BacktraderDataLoader']
