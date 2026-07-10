"""Search CPU-friendly machine-learning strategy candidates."""

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
from autotrader.strategies.ml import rolling_ml_prediction_weights


def load_bars(path: str) -> pd.DataFrame:
    files = sorted(Path(path).glob("*.parquet"))
    if not files:
        raise FileNotFoundError(f"no parquet files under {path}")
    return (
        pd.concat([pd.read_parquet(file) for file in files], ignore_index=True)
        .sort_values(["timestamp", "symbol"])
        .reset_index(drop=True)
    )


def signal_activity(weights: pd.DataFrame) -> dict[str, float]:
    if weights.empty:
        return {"active_signal_ratio": 0.0, "average_gross_weight": 0.0, "gross_weight_q95": 0.0}
    gross = weights.groupby("timestamp")["weight"].sum()
    return {
        "active_signal_ratio": float((gross > 1e-9).mean()),
        "average_gross_weight": float(gross.mean()),
        "gross_weight_q95": float(gross.quantile(0.95)),
    }


def build_candidates(bars: pd.DataFrame, *, include_slow_models: bool = False) -> dict[str, pd.DataFrame]:
    candidates = {}
    grid = [
        ("ridge", 5, 1, "daily"),
        ("ridge", 5, 3, "daily"),
        ("ridge", 5, 5, "daily"),
        ("ridge", 5, 1, "weekly"),
        ("ridge", 5, 3, "weekly"),
        ("ridge", 10, 1, "weekly"),
        ("ridge", 10, 3, "weekly"),
        ("ridge", 10, 5, "weekly"),
    ]
    if include_slow_models:
        grid.extend(
            [
                ("hist_gradient_boosting", 5, 3, "weekly"),
                ("hist_gradient_boosting", 10, 3, "weekly"),
            ]
        )
    for model, horizon, top_n, rebalance in grid:
        name = f"ml_{model}_h{horizon}_top{top_n}_{rebalance}"
        print(f"Building signal: {name}", flush=True)
        candidates[name] = rolling_ml_prediction_weights(
            bars,
            model_type=model,
            prediction_horizon=horizon,
            train_window_days=756,
            retrain="monthly",
            rebalance=rebalance,
            top_n=top_n,
            minimum_prediction=0.0,
            target_volatility=0.20,
            max_gross=1.5,
            min_train_observations=800,
            random_state=42,
        )
    return candidates


def score(row: pd.Series) -> float:
    drawdown_penalty = max(0.0, abs(row["max_drawdown"]) - 0.35) * 5
    inactivity_bonus = max(0.0, 0.70 - row["active_signal_ratio"]) * 0.2
    return float(row["sharpe"] + row["annual_return"] - drawdown_penalty + inactivity_bonus)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search CPU ML candidates")
    parser.add_argument("--data", default="data/market/akshare_sina/selection/1d")
    parser.add_argument("--output", default="reports/ml_candidates")
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--rolling-step-months", type=int, default=3)
    parser.add_argument(
        "--include-slow-models",
        action="store_true",
        help="also run slower tree models such as HistGradientBoosting",
    )
    args = parser.parse_args()

    bars = load_bars(args.data)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    config = BacktestConfig(initial_cash=1_000_000, max_gross_exposure=1.5)
    engine = PortfolioEngine(config)
    rows = []
    viable = {}
    frames = build_candidates(bars, include_slow_models=args.include_slow_models)
    print(f"Screening {len(frames)} ML candidates...", flush=True)
    for number, (name, weights) in enumerate(frames.items(), start=1):
        if weights.empty:
            print(f"EMPTY {name}", flush=True)
            continue
        result = engine.run(bars, weights)
        row = {"strategy": name, **result.metrics, **signal_activity(weights)}
        row["ml_score"] = score(pd.Series(row))
        rows.append(row)
        viable[name] = weights
        print(f"Screened {number}/{len(frames)}: {name}", flush=True)

    screen = pd.DataFrame(rows).sort_values("ml_score", ascending=False)
    screen.to_csv(output / "full_period_screen.csv", index=False, encoding="utf-8-sig")

    selected = screen.head(args.top)["strategy"].tolist()
    factories = {
        name: (
            lambda context, start, end, frame=viable[name]: frame[frame["timestamp"] <= end]
        )
        for name in selected
    }
    print(f"Rolling-test top {len(selected)} on 1m, 3m and 12m windows...", flush=True)
    rolling = RollingWindowBacktester(
        config,
        RollingWindowConfig((1, 3, 12), step_months=args.rolling_step_months),
    ).run(bars, factories)
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    rolling.summary.to_csv(output / "rolling_summary.csv", index=False, encoding="utf-8-sig")

    one = rolling.summary[rolling.summary["window_months"] == 1][
        ["strategy", "window_return_median", "window_return_q05", "window_return_q95"]
    ].rename(
        columns={
            "window_return_median": "monthly_return_median",
            "window_return_q05": "monthly_return_q05",
            "window_return_q95": "monthly_return_q95",
        }
    )
    twelve = rolling.summary[rolling.summary["window_months"] == 12][
        [
            "strategy",
            "window_return_median",
            "window_return_q05",
            "sharpe_median",
            "max_drawdown_median",
            "profitable_window_ratio",
        ]
    ].rename(
        columns={
            "window_return_median": "rolling_12m_return_median",
            "window_return_q05": "rolling_12m_return_q05",
            "sharpe_median": "rolling_12m_sharpe_median",
            "max_drawdown_median": "rolling_12m_drawdown_median",
            "profitable_window_ratio": "rolling_12m_profitable_ratio",
        }
    )
    ranking = screen.merge(one, on="strategy", how="left").merge(twelve, on="strategy", how="left")
    ranking.to_csv(output / "ranking.csv", index=False, encoding="utf-8-sig")
    columns = [
        "strategy",
        "annual_return",
        "sharpe",
        "max_drawdown",
        "active_signal_ratio",
        "average_gross_weight",
        "monthly_return_median",
        "monthly_return_q95",
        "rolling_12m_return_median",
        "rolling_12m_sharpe_median",
    ]
    print(ranking[columns].head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()
