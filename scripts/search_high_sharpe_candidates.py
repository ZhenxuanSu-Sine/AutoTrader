"""In-sample parameter search for CPU-friendly high-Sharpe candidates."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies.high_sharpe import (
    blend_weights,
    breadth_regime_weights,
    defensive_composite_weights,
    dual_momentum_rotation_weights,
    multi_horizon_trend_weights,
)


def build_candidates(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    candidates = {}
    horizon_sets = [(20, 60), (20, 60, 120), (60, 120, 240)]
    for horizons in horizon_sets:
        tag = "-".join(map(str, horizons))
        for target in (0.08, 0.12, 0.16):
            for rebalance in ("weekly", "monthly"):
                name = f"trend_h{tag}_v{target:.2f}_{rebalance}"
                candidates[name] = multi_horizon_trend_weights(
                    bars,
                    horizons=horizons,
                    vol_window=20,
                    target_volatility=target,
                    rebalance=rebalance,
                )

    for lookback in (20, 60, 120):
        for top_n in (1, 2):
            for target in (0.10, 0.15):
                name = f"dual_mom_l{lookback}_top{top_n}_v{target:.2f}"
                candidates[name] = dual_momentum_rotation_weights(
                    bars,
                    lookback=lookback,
                    trend_window=100,
                    top_n=top_n,
                    vol_window=20,
                    target_volatility=target,
                    rebalance="monthly",
                )

    for top_n in (2, 3):
        for target in (0.10, 0.15):
            name = f"defensive_top{top_n}_v{target:.2f}"
            candidates[name] = defensive_composite_weights(
                bars,
                momentum_windows=(60, 120),
                trend_window=100,
                top_n=top_n,
                target_volatility=target,
                rebalance="monthly",
            )

    for threshold in (0.4, 0.6, 0.8):
        for target in (0.10, 0.15):
            for rebalance in ("weekly", "monthly"):
                name = f"breadth_b{threshold:.1f}_v{target:.2f}_{rebalance}"
                candidates[name] = breadth_regime_weights(
                    bars,
                    trend_window=100,
                    breadth_threshold=threshold,
                    vol_window=20,
                    target_volatility=target,
                    rebalance=rebalance,
                )

    candidates["ensemble_default"] = blend_weights(
        multi_horizon_trend_weights(bars),
        dual_momentum_rotation_weights(bars),
        defensive_composite_weights(bars),
        breadth_regime_weights(bars),
    )
    return candidates


def load_bars(data_dir: str) -> pd.DataFrame:
    files = sorted(Path(data_dir).glob("*.parquet"))
    if not files:
        raise SystemExit(f"no parquet files found in {data_dir}")
    return pd.concat([pd.read_parquet(path) for path in files], ignore_index=True).sort_values(
        ["timestamp", "symbol"]
    ).reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search high-Sharpe candidate parameters")
    parser.add_argument("--data", default="data/market/akshare_sina/stock/1d")
    parser.add_argument("--output", default="reports/high_sharpe_search")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--rolling-step-months", type=int, default=3)
    args = parser.parse_args()

    bars = load_bars(args.data)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    print("Building candidate signal frames...", flush=True)
    candidates = build_candidates(bars)

    engine = PortfolioEngine(BacktestConfig(initial_cash=1_000_000))
    screen_rows = []
    for number, (name, weights) in enumerate(candidates.items(), start=1):
        result = engine.run(bars, weights)
        screen_rows.append({"strategy": name, **result.metrics})
        print(f"Screened {number}/{len(candidates)}: {name}", flush=True)
    screen = pd.DataFrame(screen_rows).sort_values("sharpe", ascending=False)
    screen.to_csv(output / "full_period_screen.csv", index=False, encoding="utf-8-sig")

    selected = screen.head(args.top)["strategy"].tolist()
    rolling_factories = {
        name: (
            lambda context, start, end, frame=candidates[name]: frame[
                frame["timestamp"] <= end
            ]
        )
        for name in selected
    }
    print(f"Running 12-month rolling evaluation for top {len(selected)}...", flush=True)
    rolling = RollingWindowBacktester(
        BacktestConfig(initial_cash=1_000_000),
        RollingWindowConfig((12,), step_months=args.rolling_step_months),
    ).run(bars, rolling_factories)
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    ranking = rolling.summary.merge(
        screen[["strategy", "sharpe", "annual_return", "max_drawdown", "turnover"]],
        on="strategy",
        suffixes=("_rolling", "_full"),
    ).sort_values(
        ["sharpe_median", "window_return_q05"], ascending=[False, False]
    )
    ranking.to_csv(output / "rolling_ranking.csv", index=False, encoding="utf-8-sig")
    print(
        ranking[
            [
                "strategy", "window_count", "profitable_window_ratio",
                "window_return_median", "window_return_q05", "sharpe_median",
                "max_drawdown_median", "turnover_median", "sharpe", "annual_return",
            ]
        ].to_string(index=False)
    )
    print(f"\nSaved search results to {output}")


if __name__ == "__main__":
    main()

