"""Run baseline strategies on imported CSMAR all-A daily data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies.high_sharpe import multifactor_stock_selection_weights
from autotrader.strategies.ml import rolling_ml_prediction_weights


def load_bars(path: str, *, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    files = sorted(Path(path).glob("year=*/bars.parquet"))
    if not files:
        files = sorted(Path(path).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet files under {path}")
    frames = []
    for file in files:
        frame = pd.read_parquet(file)
        if start is not None:
            frame = frame[frame["timestamp"] >= pd.Timestamp(start)]
        if end is not None:
            frame = frame[frame["timestamp"] <= pd.Timestamp(end)]
        if not frame.empty:
            frames.append(frame)
    if not frames:
        raise ValueError("date filters removed all bars")
    return (
        pd.concat(frames, ignore_index=True)
        .sort_values(["timestamp", "symbol"])
        .reset_index(drop=True)
    )


def build_factor_candidates(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    common = dict(
        momentum_windows=(20, 60, 120),
        vol_window=60,
        drawdown_window=120,
        liquidity_window=20,
        trend_window=100,
        minimum_history=252,
        rebalance="monthly",
        max_gross=1.0,
    )
    return {
        "csmar_balanced_top30_v10_liq70": multifactor_stock_selection_weights(
            bars,
            top_n=30,
            liquidity_quantile=0.70,
            momentum_weight=0.50,
            low_vol_weight=0.25,
            drawdown_weight=0.25,
            target_volatility=0.10,
            **common,
        ),
        "csmar_balanced_top50_v10_liq70": multifactor_stock_selection_weights(
            bars,
            top_n=50,
            liquidity_quantile=0.70,
            momentum_weight=0.50,
            low_vol_weight=0.25,
            drawdown_weight=0.25,
            target_volatility=0.10,
            **common,
        ),
        "csmar_defensive_top50_v08_liq60": multifactor_stock_selection_weights(
            bars,
            top_n=50,
            liquidity_quantile=0.60,
            momentum_weight=0.20,
            low_vol_weight=0.40,
            drawdown_weight=0.40,
            target_volatility=0.08,
            **common,
        ),
        "csmar_momentum_top30_v12_liq70": multifactor_stock_selection_weights(
            bars,
            top_n=30,
            liquidity_quantile=0.70,
            momentum_weight=1.00,
            low_vol_weight=0.00,
            drawdown_weight=0.00,
            target_volatility=0.12,
            **common,
        ),
    }


def build_ml_candidate(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    return {
        "csmar_ridge_h5_top30_weekly": rolling_ml_prediction_weights(
            bars,
            model_type="ridge",
            prediction_horizon=5,
            train_window_days=504,
            retrain="monthly",
            rebalance="weekly",
            top_n=30,
            minimum_prediction=0.0,
            target_volatility=0.10,
            max_gross=1.0,
            min_train_observations=50_000,
            random_state=42,
        )
    }


def signal_activity(weights: pd.DataFrame) -> dict[str, float]:
    gross = weights.groupby("timestamp")["weight"].sum()
    return {
        "active_signal_ratio": float((gross > 1e-9).mean()),
        "average_gross_weight": float(gross.mean()),
        "gross_weight_q95": float(gross.quantile(0.95)),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run strategies on CSMAR daily data")
    parser.add_argument("--data", default="data/market/csmar/stock/1d")
    parser.add_argument("--output", default="reports/csmar_strategies")
    parser.add_argument("--start", default=None)
    parser.add_argument("--end", default=None)
    parser.add_argument("--include-ml", action="store_true")
    parser.add_argument("--rolling-step-months", type=int, default=6)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    print("Loading CSMAR bars...", flush=True)
    bars = load_bars(args.data, start=args.start, end=args.end)
    print(
        f"Loaded {len(bars):,} rows, {bars['symbol'].nunique():,} symbols, "
        f"{bars['timestamp'].min().date()}..{bars['timestamp'].max().date()}",
        flush=True,
    )
    print("Building factor candidates...", flush=True)
    frames = build_factor_candidates(bars)
    if args.include_ml:
        print("Building ML candidate...", flush=True)
        frames.update(build_ml_candidate(bars))

    config = BacktestConfig(initial_cash=1_000_000)
    engine = PortfolioEngine(config)
    rows = []
    viable = {}
    for name, weights in frames.items():
        if weights.empty:
            print(f"EMPTY {name}", flush=True)
            continue
        print(f"Backtesting {name} ({len(weights):,} target rows)...", flush=True)
        result = engine.run(bars, weights)
        row = {"strategy": name, **result.metrics, **signal_activity(weights)}
        rows.append(row)
        viable[name] = weights
    full = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    full.to_csv(output / "full_period.csv", index=False, encoding="utf-8-sig")

    factories = {
        name: (lambda context, start, end, frame=frame: frame[frame["timestamp"] <= end])
        for name, frame in viable.items()
    }
    print("Running rolling windows...", flush=True)
    rolling = RollingWindowBacktester(
        config,
        RollingWindowConfig((12, 36), step_months=args.rolling_step_months),
    ).run(bars, factories)
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    rolling.summary.to_csv(output / "rolling_summary.csv", index=False, encoding="utf-8-sig")
    summary = rolling.summary[
        [
            "strategy",
            "window_months",
            "window_count",
            "window_return_median",
            "window_return_q05",
            "sharpe_median",
            "max_drawdown_median",
            "profitable_window_ratio",
        ]
    ].merge(
        full[
            [
                "strategy",
                "annual_return",
                "sharpe",
                "max_drawdown",
                "turnover",
                "total_cost",
                "average_gross_weight",
            ]
        ],
        on="strategy",
        how="left",
    )
    summary.to_csv(output / "comparison.csv", index=False, encoding="utf-8-sig")
    print(full.to_string(index=False))
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
