"""Final evaluation for the first-stage aggressive strategy candidates."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies.high_sharpe import (
    breakout_stock_selection_weights,
    multifactor_stock_selection_weights,
    weighted_blend_weights,
)


def build_candidates(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    common = dict(
        top_n=8,
        momentum_windows=(20, 60, 120),
        vol_window=60,
        drawdown_window=120,
        liquidity_window=20,
        liquidity_quantile=0.30,
        trend_window=100,
        minimum_history=252,
        momentum_weight=0.50,
        low_vol_weight=0.25,
        drawdown_weight=0.25,
        rebalance="monthly",
    )
    core = multifactor_stock_selection_weights(
        bars, target_volatility=0.08, max_gross=1.0, **common
    )
    continuous = multifactor_stock_selection_weights(
        bars,
        target_volatility=0.16,
        max_gross=1.5,
        require_trend=False,
        **common,
    )
    breakout = breakout_stock_selection_weights(
        bars,
        top_n=3,
        breakout_window=60,
        momentum_window=20,
        trend_window=100,
        vol_window=20,
        target_volatility=0.20,
        max_gross=2.0,
        rebalance="weekly",
    )
    return {
        "core_balanced_top8_unlevered": core,
        "aggressive_breakout_top3_g2": breakout,
        "continuous_balanced_top8_g1.5": continuous,
        "core70_breakout30": weighted_blend_weights([core, breakout], [0.7, 0.3]),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate first-stage aggressive candidates")
    parser.add_argument("--data", default="data/market/akshare_sina/selection/1d")
    parser.add_argument("--output", default="reports/aggressive_candidates")
    parser.add_argument("--markdown", default="AGGRESSIVE_CANDIDATES.md")
    parser.add_argument("--step-months", type=int, default=3)
    parser.add_argument("--borrow-rate", type=float, default=0.05)
    args = parser.parse_args()

    files = sorted(Path(args.data).glob("*.parquet"))
    bars = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True).sort_values(
        ["timestamp", "symbol"]
    ).reset_index(drop=True)
    frames = build_candidates(bars)
    config = BacktestConfig(
        initial_cash=1_000_000,
        max_gross_exposure=2.0,
        annual_borrow_rate=args.borrow_rate,
    )
    engine = PortfolioEngine(config)
    full_rows = []
    for name, weights in frames.items():
        metrics = engine.run(bars, weights).metrics
        full_rows.append(
            {
                "strategy": name,
                "full_annual_return": metrics["annual_return"],
                "full_sharpe": metrics["sharpe"],
                "full_max_drawdown": metrics["max_drawdown"],
                "full_turnover": metrics["turnover"],
                "full_financing_cost": metrics["financing_cost"],
            }
        )
    full = pd.DataFrame(full_rows)
    factories = {
        name: (lambda context, start, end, frame=frame: frame[frame["timestamp"] <= end])
        for name, frame in frames.items()
    }
    print("Running final aggressive rolling evaluation...", flush=True)
    rolling = RollingWindowBacktester(
        config,
        RollingWindowConfig((1, 3, 6, 12, 36), step_months=args.step_months),
    ).run(bars, factories)
    columns = [
        "strategy", "window_months", "window_count", "profitable_window_ratio",
        "window_return_median", "window_return_q05", "window_return_q95",
        "sharpe_median", "sharpe_q25", "max_drawdown_median", "turnover_median",
        "financing_cost_median", "total_cost_median",
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
        "# 第一阶段进攻型候选\n\n"
        "目标：年化25%-40%、Sharpe不低于1、最大回撤不超过30%、月收益中位数2%-3%。"
        "回测包含5%年化融资成本，最高总敞口2倍。当前没有候选同时满足四项；报告保留最接近"
        "目标的组合并明确展示差距。\n\n"
        + display[report_columns].to_markdown(index=False)
        + "\n",
        encoding="utf-8",
    )
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()

