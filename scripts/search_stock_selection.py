"""Search multifactor stock-selection variants on the expanded static universe."""

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


def load_bars(data_dir: str) -> pd.DataFrame:
    files = sorted(Path(data_dir).glob("*.parquet"))
    if not files:
        raise SystemExit(f"no parquet files found in {data_dir}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True).sort_values(
        ["timestamp", "symbol"]
    ).reset_index(drop=True)


def candidates(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    result = {
        "trend_all_h20_60_vol08": multi_horizon_trend_weights(
            bars,
            horizons=(20, 60),
            vol_window=20,
            target_volatility=0.08,
            rebalance="weekly",
        )
    }
    styles = {
        "balanced": (0.50, 0.25, 0.25),
        "momentum": (1.00, 0.00, 0.00),
        "defensive": (0.20, 0.40, 0.40),
    }
    for style, factor_weights in styles.items():
        for top_n in (3, 5, 8):
            for target in (0.08, 0.12):
                name = f"select_{style}_top{top_n}_vol{target:.2f}"
                result[name] = multifactor_stock_selection_weights(
                    bars,
                    top_n=top_n,
                    momentum_windows=(20, 60, 120),
                    vol_window=60,
                    drawdown_window=120,
                    liquidity_window=20,
                    liquidity_quantile=0.30,
                    trend_window=100,
                    minimum_history=252,
                    momentum_weight=factor_weights[0],
                    low_vol_weight=factor_weights[1],
                    drawdown_weight=factor_weights[2],
                    target_volatility=target,
                    rebalance="monthly",
                )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Search stock-selection parameters")
    parser.add_argument("--data", default="data/market/akshare_sina/selection/1d")
    parser.add_argument("--output", default="reports/stock_selection_search")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--rolling-step-months", type=int, default=3)
    args = parser.parse_args()

    bars = load_bars(args.data)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    print(f"Building selection signals for {bars['symbol'].nunique()} stocks...", flush=True)
    frames = candidates(bars)
    engine = PortfolioEngine(BacktestConfig(initial_cash=1_000_000))
    rows = []
    for number, (name, weights) in enumerate(frames.items(), start=1):
        metrics = engine.run(bars, weights).metrics
        rows.append({"strategy": name, **metrics})
        print(f"Screened {number}/{len(frames)}: {name}", flush=True)
    screen = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    screen.to_csv(output / "full_period_screen.csv", index=False, encoding="utf-8-sig")

    selected = screen.head(args.top)["strategy"].tolist()
    factories = {
        name: (
            lambda context, start, end, frame=frames[name]: frame[frame["timestamp"] <= end]
        )
        for name in selected
    }
    print(f"Rolling-test top {len(selected)} candidates...", flush=True)
    rolling = RollingWindowBacktester(
        BacktestConfig(initial_cash=1_000_000),
        RollingWindowConfig((12,), step_months=args.rolling_step_months),
    ).run(bars, factories)
    ranking = rolling.summary.merge(
        screen[["strategy", "sharpe", "annual_return", "max_drawdown", "turnover"]],
        on="strategy",
        suffixes=("_rolling", "_full"),
    ).sort_values(["sharpe_median", "window_return_q05"], ascending=[False, False])
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    ranking.to_csv(output / "rolling_ranking.csv", index=False, encoding="utf-8-sig")
    columns = [
        "strategy", "window_count", "profitable_window_ratio", "window_return_median",
        "window_return_q05", "sharpe_median", "max_drawdown_median", "turnover_median",
        "sharpe", "annual_return",
    ]
    print(ranking[columns].to_string(index=False))


if __name__ == "__main__":
    main()

