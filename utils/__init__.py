"""工具模块。

提供通用的工具函数。
"""

from utils.universe import load_universe, extract_symbols
from utils.proxy import setup_proxy, clear_proxy

__all__ = ['load_universe', 'extract_symbols', 'setup_proxy', 'clear_proxy']

