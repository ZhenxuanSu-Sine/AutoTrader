"""Search sparse short-term trend-catching candidates."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies.high_sharpe import (
    contraction_breakout_weights,
    sparse_breakout_trend_weights,
)


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
    gross = weights.groupby("timestamp")["weight"].sum().sort_index()
    return {
        "signal_dates": float(len(gross)),
        "active_signal_ratio": float((gross > 1e-9).mean()),
        "average_gross_weight": float(gross.mean()),
        "median_gross_weight": float(gross.median()),
        "gross_weight_q95": float(gross.quantile(0.95)),
    }


def build_candidates(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    candidates = {}
    for breakout_window in (20, 40, 60):
        for top_n in (1, 3):
            for minimum_momentum in (0.02, 0.05):
                for volume_multiple in (1.0, 1.3):
                    name = (
                        f"sparse_w{breakout_window}_top{top_n}"
                        f"_mom{minimum_momentum:.2f}_volx{volume_multiple:.1f}"
                        "_tv0.30"
                    )
                    candidates[name] = sparse_breakout_trend_weights(
                        bars,
                        top_n=top_n,
                        breakout_window=breakout_window,
                        minimum_momentum=minimum_momentum,
                        volume_multiple=volume_multiple,
                        target_volatility=0.30,
                        max_gross=2.0,
                        rebalance="weekly",
                    )
    for breakout_window in (20, 40, 60):
        for top_n in (1, 3):
            for contraction_ratio in (0.60, 0.75):
                name = (
                    f"contract_w{breakout_window}_top{top_n}"
                    f"_cr{contraction_ratio:.2f}_tv0.30"
                )
                candidates[name] = contraction_breakout_weights(
                    bars,
                    top_n=top_n,
                    breakout_window=breakout_window,
                    contraction_ratio=contraction_ratio,
                    target_volatility=0.30,
                    max_gross=2.0,
                    rebalance="weekly",
                )
    for breakout_window in (20, 40, 60):
        for top_n in (1, 2, 3):
            for minimum_momentum in (0.05, 0.08):
                name = f"daily_sparse_w{breakout_window}_top{top_n}_mom{minimum_momentum:.2f}"
                candidates[name] = sparse_breakout_trend_weights(
                    bars,
                    top_n=top_n,
                    breakout_window=breakout_window,
                    minimum_momentum=minimum_momentum,
                    volume_multiple=1.8,
                    breakout_buffer=0.0,
                    maximum_volatility=0.60,
                    target_volatility=0.30,
                    max_gross=2.0,
                    rebalance="daily",
                )
    return candidates


def sparse_trend_score(row: pd.Series) -> float:
    drawdown_penalty = max(0.0, abs(row["max_drawdown"]) - 0.35) * 6
    overactive_penalty = max(0.0, row["active_signal_ratio"] - 0.45) * 1.5
    return float(
        row["sharpe"]
        + row["annual_return"]
        + 0.35 * row["gross_weight_q95"]
        - drawdown_penalty
        - overactive_penalty
    )


def summarize_monthly_tail(windows: pd.DataFrame) -> pd.DataFrame:
    one = windows[windows["window_months"] == 1].copy()
    grouped = one.groupby("strategy")["window_return"]
    return pd.DataFrame(
        {
            "monthly_return_median": grouped.median(),
            "monthly_return_q05": grouped.quantile(0.05),
            "monthly_return_q95": grouped.quantile(0.95),
            "monthly_profitable_ratio": grouped.apply(lambda values: (values > 0).mean()),
            "monthly_big_win_ratio_5pct": grouped.apply(lambda values: (values >= 0.05).mean()),
        }
    ).reset_index()


def main() -> None:
    parser = argparse.ArgumentParser(description="Search sparse short-term trend strategies")
    parser.add_argument("--data", default="data/market/akshare_sina/selection/1d")
    parser.add_argument("--output", default="reports/short_term_trend")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--rolling-step-months", type=int, default=1)
    parser.add_argument("--borrow-rate", type=float, default=0.05)
    args = parser.parse_args()

    bars = load_bars(args.data)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    frames = build_candidates(bars)
    config = BacktestConfig(
        initial_cash=1_000_000,
        max_gross_exposure=2.0,
        annual_borrow_rate=args.borrow_rate,
    )
    engine = PortfolioEngine(config)
    rows = []
    viable = {}
    print(f"Screening {len(frames)} sparse short-term candidates...", flush=True)
    for number, (name, weights) in enumerate(frames.items(), start=1):
        try:
            result = engine.run(bars, weights)
        except RuntimeError as exc:
            print(f"INSOLVENT {name}: {exc}", flush=True)
            continue
        row = {"strategy": name, **result.metrics, **signal_activity(weights)}
        row["sparse_trend_score"] = sparse_trend_score(pd.Series(row))
        rows.append(row)
        viable[name] = weights
        print(f"Screened {number}/{len(frames)}: {name}", flush=True)

    screen = pd.DataFrame(rows).sort_values("sparse_trend_score", ascending=False)
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
    monthly = summarize_monthly_tail(rolling.windows)
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
    ranking = (
        screen.merge(monthly, on="strategy", how="left")
        .merge(twelve, on="strategy", how="left")
        .sort_values("sparse_trend_score", ascending=False)
    )
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    rolling.summary.to_csv(output / "rolling_summary.csv", index=False, encoding="utf-8-sig")
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
        "monthly_big_win_ratio_5pct",
        "rolling_12m_return_median",
        "rolling_12m_sharpe_median",
    ]
    print(ranking[columns].head(args.top).to_string(index=False))


if __name__ == "__main__":
    main()
