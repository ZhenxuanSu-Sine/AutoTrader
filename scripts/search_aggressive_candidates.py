"""Search aggressive candidates against explicit return and risk targets."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies.high_sharpe import (
    breakout_stock_selection_weights,
    multifactor_stock_selection_weights,
    weighted_blend_weights,
)


def build_candidates(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    result = {}
    common = dict(
        momentum_windows=(20, 60, 120),
        vol_window=60,
        drawdown_window=120,
        liquidity_window=20,
        liquidity_quantile=0.30,
        trend_window=100,
        minimum_history=252,
        rebalance="monthly",
    )
    styles = {
        "balanced": (0.50, 0.25, 0.25),
        "momentum": (1.00, 0.00, 0.00),
    }
    for style, factor_weights in styles.items():
        for top_n in (1, 3, 5):
            for target in (0.16, 0.24, 0.32):
                for gross in (1.5, 2.0):
                    name = f"aggr_{style}_top{top_n}_v{target:.2f}_g{gross:.1f}"
                    result[name] = multifactor_stock_selection_weights(
                        bars,
                        top_n=top_n,
                        momentum_weight=factor_weights[0],
                        low_vol_weight=factor_weights[1],
                        drawdown_weight=factor_weights[2],
                        target_volatility=target,
                        max_gross=gross,
                        **common,
                    )
    for breakout_window in (20, 60):
        for top_n in (1, 3):
            for target in (0.20, 0.30):
                for gross in (1.5, 2.0):
                    name = f"breakout_w{breakout_window}_top{top_n}_v{target:.2f}_g{gross:.1f}"
                    result[name] = breakout_stock_selection_weights(
                        bars,
                        top_n=top_n,
                        breakout_window=breakout_window,
                        momentum_window=20,
                        trend_window=100,
                        vol_window=20,
                        minimum_history=120,
                        target_volatility=target,
                        max_gross=gross,
                        rebalance="weekly",
                    )

    continuous_styles = {
        "balanced": (0.50, 0.25, 0.25),
        "defensive": (0.20, 0.40, 0.40),
    }
    for style, factor_weights in continuous_styles.items():
        for top_n in (5, 8):
            for target in (0.16, 0.24, 0.32):
                for gross in (1.5, 2.0):
                    name = f"continuous_{style}_top{top_n}_v{target:.2f}_g{gross:.1f}"
                    result[name] = multifactor_stock_selection_weights(
                        bars,
                        top_n=top_n,
                        momentum_weight=factor_weights[0],
                        low_vol_weight=factor_weights[1],
                        drawdown_weight=factor_weights[2],
                        target_volatility=target,
                        max_gross=gross,
                        require_trend=False,
                        **common,
                    )

    core = multifactor_stock_selection_weights(
        bars,
        top_n=8,
        momentum_weight=0.50,
        low_vol_weight=0.25,
        drawdown_weight=0.25,
        target_volatility=0.08,
        max_gross=1.0,
        **common,
    )
    satellite = breakout_stock_selection_weights(
        bars,
        top_n=3,
        breakout_window=60,
        target_volatility=0.30,
        max_gross=2.0,
        rebalance="weekly",
    )
    result["core70_breakout30"] = weighted_blend_weights([core, satellite], [0.7, 0.3])
    result["core50_breakout50"] = weighted_blend_weights([core, satellite], [0.5, 0.5])
    return result


def target_score(row: pd.Series) -> float:
    """Reward target return/Sharpe and heavily penalize drawdown beyond 30%."""

    drawdown_penalty = max(0.0, abs(row["max_drawdown"]) - 0.30) * 8
    return float(row["sharpe"] + row["annual_return"] - drawdown_penalty)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search aggressive stock strategies")
    parser.add_argument("--data", default="data/market/akshare_sina/selection/1d")
    parser.add_argument("--output", default="reports/aggressive_search")
    parser.add_argument("--top", type=int, default=12)
    parser.add_argument("--rolling-step-months", type=int, default=3)
    parser.add_argument("--borrow-rate", type=float, default=0.05)
    args = parser.parse_args()

    files = sorted(Path(args.data).glob("*.parquet"))
    bars = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True).sort_values(
        ["timestamp", "symbol"]
    ).reset_index(drop=True)
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    print("Building aggressive signals...", flush=True)
    frames = build_candidates(bars)
    config = BacktestConfig(
        initial_cash=1_000_000,
        max_gross_exposure=2.0,
        annual_borrow_rate=args.borrow_rate,
    )
    engine = PortfolioEngine(config)
    rows = []
    viable = {}
    for number, (name, weights) in enumerate(frames.items(), start=1):
        try:
            metrics = engine.run(bars, weights).metrics
            row = {"strategy": name, **metrics}
            row["target_score"] = target_score(pd.Series(row))
            rows.append(row)
            viable[name] = weights
            print(f"Screened {number}/{len(frames)}: {name}", flush=True)
        except RuntimeError as exc:
            print(f"INSOLVENT {name}: {exc}", flush=True)
    screen = pd.DataFrame(rows).sort_values("target_score", ascending=False)
    screen.to_csv(output / "full_period_screen.csv", index=False, encoding="utf-8-sig")

    selected = screen.head(args.top)["strategy"].tolist()
    factories = {
        name: (
            lambda context, start, end, frame=viable[name]: frame[frame["timestamp"] <= end]
        )
        for name in selected
    }
    print(f"Rolling-test top {len(selected)} on 1m and 12m windows...", flush=True)
    rolling = RollingWindowBacktester(
        config,
        RollingWindowConfig((1, 12), step_months=args.rolling_step_months),
    ).run(bars, factories)
    summary = rolling.summary
    one = summary[summary["window_months"] == 1][
        ["strategy", "window_return_median", "window_return_q05", "profitable_window_ratio"]
    ].rename(
        columns={
            "window_return_median": "monthly_return_median",
            "window_return_q05": "monthly_return_q05",
            "profitable_window_ratio": "monthly_profitable_ratio",
        }
    )
    twelve = summary[summary["window_months"] == 12][
        ["strategy", "sharpe_median", "sharpe_q25", "max_drawdown_median"]
    ].rename(
        columns={
            "sharpe_median": "rolling_12m_sharpe_median",
            "sharpe_q25": "rolling_12m_sharpe_q25",
            "max_drawdown_median": "rolling_12m_drawdown_median",
        }
    )
    ranking = screen.merge(one, on="strategy").merge(twelve, on="strategy")
    ranking["meets_full_targets"] = (
        ranking["annual_return"].between(0.25, 0.40)
        & (ranking["sharpe"] >= 1.0)
        & (ranking["max_drawdown"] >= -0.30)
    )
    ranking["meets_monthly_target"] = ranking["monthly_return_median"].between(0.02, 0.03)
    ranking["monthly_distance"] = (ranking["monthly_return_median"] - 0.025).abs()
    ranking = ranking.sort_values(
        ["meets_full_targets", "meets_monthly_target", "rolling_12m_sharpe_median", "monthly_distance"],
        ascending=[False, False, False, True],
    )
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    ranking.to_csv(output / "ranking.csv", index=False, encoding="utf-8-sig")
    columns = [
        "strategy", "annual_return", "sharpe", "max_drawdown", "monthly_return_median",
        "monthly_return_q05", "rolling_12m_sharpe_median", "rolling_12m_drawdown_median",
        "turnover", "financing_cost", "meets_full_targets", "meets_monthly_target",
    ]
    print(ranking[columns].to_string(index=False))


if __name__ == "__main__":
    main()
