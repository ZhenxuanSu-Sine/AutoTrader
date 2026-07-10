"""评估包。

提供回测引擎和评估指标。
"""

from evaluation.backtest import BacktestEngine
from evaluation.metrics import calculate_basic_metrics, print_results

__all__ = ['BacktestEngine', 'calculate_basic_metrics', 'print_results']
