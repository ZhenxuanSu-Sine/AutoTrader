"""评估指标模块。

提供回测结果的评估指标计算。
"""

from typing import Dict


def calculate_basic_metrics(results: Dict) -> Dict:
    """计算基础评估指标。

    Args:
        results: 回测结果字典，包含initial_cash, final_value等

    Returns:
        包含评估指标的字典
    """
    initial_cash = results['initial_cash']
    final_value = results['final_value']
    return_pct = results['return_pct']

    return {
        'initial_cash': initial_cash,
        'final_value': final_value,
        'return_pct': return_pct,
        'profit': final_value - initial_cash,
    }


def print_results(strategy_name: str, results: Dict) -> None:
    """打印回测结果。

    Args:
        strategy_name: 策略名称
        results: 回测结果字典
    """
    metrics = calculate_basic_metrics(results)
    print(f"策略 '{strategy_name}' 回测结果:")
    print(f"  初始资金: {metrics['initial_cash']:.2f}")
    print(f"  期末资金: {metrics['final_value']:.2f}")
    print(f"  收益率: {metrics['return_pct']:.2f}%")
    print(f"  盈亏: {metrics['profit']:.2f}")

