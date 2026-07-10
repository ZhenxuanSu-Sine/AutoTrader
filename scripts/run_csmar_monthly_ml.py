"""Run CPU-friendly monthly ML stock-selection candidates on CSMAR data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.strategies.monthly_ml import MonthlyMLConfig, monthly_ml_prediction_weights
from scripts.run_csmar_strategies import load_bars


def candidate_configs() -> dict[str, MonthlyMLConfig]:
    configs: dict[str, MonthlyMLConfig] = {}
    for train_window in (60, 84, 120):
        for top_n in (50, 100):
            for allocation in ("cap", "score"):
                name = f"ml_ridge_tw{train_window}_top{top_n}_{allocation}"
                configs[name] = MonthlyMLConfig(
                    model_type="ridge",
                    train_window_months=train_window,
                    min_train_months=36,
                    min_train_observations=20_000,
                    top_n=top_n,
                    liquidity_quantile=0.40,
                    cap_quantile=0.40,
                    allocation=allocation,
                )
    return configs


def signal_activity(weights: pd.DataFrame) -> dict[str, float]:
    if weights.empty:
        return {
            "active_months": 0.0,
            "first_signal": float("nan"),
            "last_signal": float("nan"),
            "average_holding_count": 0.0,
        }
    counts = weights.groupby("timestamp")["symbol"].nunique()
    return {
        "active_months": float(counts.size),
        "first_signal": weights["timestamp"].min(),
        "last_signal": weights["timestamp"].max(),
        "average_holding_count": float(counts.mean()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run monthly CSMAR ML candidates")
    parser.add_argument("--data", default="data/market/csmar/stock/1d_combined_total_return")
    parser.add_argument(
        "--features",
        default="data/features/csmar/monthly_price_volume_combined.parquet",
    )
    parser.add_argument("--output", default="reports/csmar_combined_monthly_ml")
    parser.add_argument("--max-candidates", type=int, default=12)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    print("Loading bars and monthly features...", flush=True)
    bars = load_bars(args.data)
    features = pd.read_parquet(args.features)
    engine = PortfolioEngine(BacktestConfig(initial_cash=1_000_000))

    rows = []
    for number, (name, config) in enumerate(candidate_configs().items(), start=1):
        if number > args.max_candidates:
            break
        print(f"Training {name}...", flush=True)
        weights = monthly_ml_prediction_weights(features, config)
        weights.to_csv(output / f"weights_{name}.csv", index=False, encoding="utf-8-sig")
        if weights.empty:
            rows.append({"strategy": name, "empty": True})
            continue
        result = engine.run(bars, weights)
        rows.append({"strategy": name, "empty": False, **result.metrics, **signal_activity(weights)})
        print(f"Finished {name}: sharpe={result.metrics['sharpe']:.3f}", flush=True)

    results = pd.DataFrame(rows)
    if "sharpe" in results:
        results = results.sort_values("sharpe", ascending=False, na_position="last")
    results.to_csv(output / "full_period.csv", index=False, encoding="utf-8-sig")
    display = [
        "strategy",
        "annual_return",
        "sharpe",
        "max_drawdown",
        "trade_count",
        "turnover",
        "total_cost",
        "active_months",
        "average_holding_count",
    ]
    print(results[[column for column in display if column in results.columns]].to_string(index=False))


if __name__ == "__main__":
    main()
