"""Run rolling-window evaluation for portfolio baseline strategies."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from autotrader.backtest import BacktestConfig
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies import (
    cross_sectional_momentum_weights,
    equal_weight_weights,
    moving_average_weights,
    time_series_momentum_weights,
    trend_equal_weight_weights,
)


def strategy_factories(bars: pd.DataFrame):
    symbol_count = bars["symbol"].nunique()

    def window_bars(context, start, end):
        return context[context["timestamp"].between(start, end, inclusive="both")]

    # These vectorized baseline functions are causal (trailing rolling/pct_change
    # only), so their signal frames can be computed once and safely sliced at
    # each window end. Execution and portfolio state remain window-independent.
    precomputed = {
        "sma_20_100_equal": moving_average_weights(
            bars, fast=20, slow=100, weight=1.0 / symbol_count
        ),
        "ts_momentum_60_equal": time_series_momentum_weights(
            bars, lookback=60, weight=1.0 / symbol_count
        ),
        "trend_equal_100_monthly": trend_equal_weight_weights(
            bars, window=100, rebalance="monthly"
        ),
        "xs_momentum_60_top2_monthly": cross_sectional_momentum_weights(
            bars, lookback=60, top_n=2
        ),
    }

    def cached(name):
        return lambda context, start, end: precomputed[name][
            precomputed[name]["timestamp"] <= end
        ]

    return {
        "equal_weight": lambda context, start, end: equal_weight_weights(
            window_bars(context, start, end)
        ),
        **{name: cached(name) for name in precomputed},
    }


def comparison_table(summary: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "strategy",
        "window_months",
        "window_count",
        "profitable_window_ratio",
        "window_return_mean",
        "window_return_median",
        "window_return_std",
        "window_return_q05",
        "window_return_q25",
        "window_return_q75",
        "window_return_q95",
        "sharpe_median",
        "max_drawdown_median",
        "max_drawdown_q05",
        "calmar_median",
        "trade_win_rate_median",
        "turnover_median",
        "fees_median",
        "slippage_cost_median",
    ]
    return summary[columns].sort_values(["window_months", "strategy"])


def write_markdown(comparison: pd.DataFrame, output: Path) -> None:
    display = comparison.copy()
    for column in [
        "profitable_window_ratio",
        "window_return_mean",
        "window_return_median",
        "window_return_q05",
        "window_return_q95",
        "max_drawdown_median",
    ]:
        display[column] = display[column].map(lambda value: f"{value:.2%}")
    selected = [
        "strategy",
        "window_months",
        "window_count",
        "profitable_window_ratio",
        "window_return_median",
        "window_return_q05",
        "window_return_q95",
        "sharpe_median",
        "max_drawdown_median",
        "turnover_median",
    ]
    output.write_text(
        "# Rolling Window Baseline\n\n"
        "窗口按自然月定义，每月向前滚动一步；大于 1 个月的窗口相互重叠。每个窗口从现金"
        "开始，信号在下一根 K 线开盘成交，并在窗口最后一根 K 线收盘强制清仓。数据末尾"
        "尚未完成的自然月窗口不会纳入统计。\n\n"
        + display[selected].to_markdown(index=False)
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run rolling-window baseline evaluation")
    parser.add_argument("--data", default="data/market/akshare_sina/stock/1d")
    parser.add_argument("--output", default="reports/rolling_baseline")
    parser.add_argument("--markdown", default="ROLLING_BASELINE_RESULTS.md")
    parser.add_argument("--windows", nargs="+", type=int, default=[1, 3, 6, 12, 36])
    parser.add_argument("--step-months", type=int, default=1)
    args = parser.parse_args()

    files = sorted(Path(args.data).glob("*.parquet"))
    if not files:
        raise SystemExit(f"no parquet files found in {args.data}")
    bars = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
    bars = bars.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

    evaluator = RollingWindowBacktester(
        BacktestConfig(initial_cash=1_000_000, annualization=252),
        RollingWindowConfig(tuple(args.windows), step_months=args.step_months),
    )
    print(
        f"Running {len(args.windows)} window lengths x 5 strategies; "
        f"step={args.step_months} month(s)...",
        flush=True,
    )
    result = evaluator.run(bars, strategy_factories(bars))
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    result.save_csv(output / "windows.csv", output / "summary.csv")
    comparison = comparison_table(result.summary)
    comparison.to_csv(output / "comparison.csv", index=False, encoding="utf-8-sig")
    write_markdown(comparison, Path(args.markdown))
    print(comparison.to_string(index=False))
    print(f"\nSaved {len(result.windows)} window runs and {len(result.summary)} summary rows")


if __name__ == "__main__":
    main()
