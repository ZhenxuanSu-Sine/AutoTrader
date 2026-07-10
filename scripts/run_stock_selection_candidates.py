"""Full multi-horizon rolling evaluation for selected stock-picking candidates."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies.high_sharpe import (
    multi_horizon_trend_weights,
    multifactor_stock_selection_weights,
)


def build_selected(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    common = {
        "momentum_windows": (20, 60, 120),
        "vol_window": 60,
        "drawdown_window": 120,
        "liquidity_window": 20,
        "liquidity_quantile": 0.30,
        "trend_window": 100,
        "minimum_history": 252,
        "target_volatility": 0.08,
        "rebalance": "monthly",
    }
    return {
        "trend_all_h20_60_vol08": multi_horizon_trend_weights(
            bars,
            horizons=(20, 60),
            vol_window=20,
            target_volatility=0.08,
            rebalance="weekly",
        ),
        "select_defensive_top5_vol08": multifactor_stock_selection_weights(
            bars,
            top_n=5,
            momentum_weight=0.20,
            low_vol_weight=0.40,
            drawdown_weight=0.40,
            **common,
        ),
        "select_balanced_top3_vol08": multifactor_stock_selection_weights(
            bars,
            top_n=3,
            momentum_weight=0.50,
            low_vol_weight=0.25,
            drawdown_weight=0.25,
            **common,
        ),
        "select_balanced_top8_vol08": multifactor_stock_selection_weights(
            bars,
            top_n=8,
            momentum_weight=0.50,
            low_vol_weight=0.25,
            drawdown_weight=0.25,
            **common,
        ),
        "select_momentum_top8_vol08": multifactor_stock_selection_weights(
            bars,
            top_n=8,
            momentum_weight=1.00,
            low_vol_weight=0.00,
            drawdown_weight=0.00,
            **common,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate selected stock-picking strategies")
    parser.add_argument("--data", default="data/market/akshare_sina/selection/1d")
    parser.add_argument("--output", default="reports/stock_selection_candidates")
    parser.add_argument("--markdown", default="STOCK_SELECTION_RESULTS.md")
    parser.add_argument("--step-months", type=int, default=3)
    args = parser.parse_args()

    files = sorted(Path(args.data).glob("*.parquet"))
    if not files:
        raise SystemExit(f"no parquet files found in {args.data}")
    bars = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True).sort_values(
        ["timestamp", "symbol"]
    ).reset_index(drop=True)
    frames = build_selected(bars)

    engine = PortfolioEngine(BacktestConfig(initial_cash=1_000_000))
    full_rows = []
    for name, weights in frames.items():
        metrics = engine.run(bars, weights).metrics
        full_rows.append(
            {
                "strategy": name,
                "full_sharpe": metrics["sharpe"],
                "full_annual_return": metrics["annual_return"],
                "full_max_drawdown": metrics["max_drawdown"],
                "full_turnover": metrics["turnover"],
            }
        )
    full = pd.DataFrame(full_rows)
    factories = {
        name: (lambda context, start, end, frame=frame: frame[frame["timestamp"] <= end])
        for name, frame in frames.items()
    }
    print(
        f"Running {len(frames)} strategies on 1/3/6/12/36-month windows, "
        f"step={args.step_months}...",
        flush=True,
    )
    rolling = RollingWindowBacktester(
        BacktestConfig(initial_cash=1_000_000),
        RollingWindowConfig((1, 3, 6, 12, 36), step_months=args.step_months),
    ).run(bars, factories)
    columns = [
        "strategy", "window_months", "window_count", "profitable_window_ratio",
        "window_return_median", "window_return_q05", "window_return_q95",
        "sharpe_median", "sharpe_q25", "max_drawdown_median", "turnover_median",
        "total_cost_median",
    ]
    comparison = rolling.summary[columns].merge(full, on="strategy").sort_values(
        ["window_months", "sharpe_median"], ascending=[True, False]
    )

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rolling.windows.to_csv(output / "windows.csv", index=False, encoding="utf-8-sig")
    rolling.summary.to_csv(output / "summary.csv", index=False, encoding="utf-8-sig")
    comparison.to_csv(output / "comparison.csv", index=False, encoding="utf-8-sig")

    display = comparison.copy()
    for column in [
        "profitable_window_ratio", "window_return_median", "window_return_q05",
        "window_return_q95", "max_drawdown_median", "full_annual_return",
        "full_max_drawdown",
    ]:
        display[column] = display[column].map(lambda value: f"{value:.2%}")
    report_columns = [
        "strategy", "window_months", "window_count", "profitable_window_ratio",
        "window_return_median", "window_return_q05", "sharpe_median",
        "max_drawdown_median", "turnover_median",
    ]
    Path(args.markdown).write_text(
        "# 动态选股策略结果\n\n"
        "股票池是运行时获取的当前沪深300市值前40只，存在幸存者偏差；个股积累满252个"
        "交易日后才允许参与。选股和权重仅使用调仓时点已有数据。\n\n"
        + display[report_columns].to_markdown(index=False)
        + "\n",
        encoding="utf-8",
    )
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()

