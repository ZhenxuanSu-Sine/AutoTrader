"""Run simple dynamic-universe CSMAR benchmarks."""

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
from scripts.run_csmar_strategies import load_bars


def _monthly_rows(bars: pd.DataFrame) -> pd.DataFrame:
    data = bars.copy()
    data["month"] = data["timestamp"].dt.to_period("M")
    rebalance_dates = data.groupby("month")["timestamp"].min()
    return data[data["timestamp"].isin(rebalance_dates)].copy()


def top_liquid_equal_weights(
    bars: pd.DataFrame,
    *,
    top_n: int = 500,
    liquidity_window: int = 20,
) -> pd.DataFrame:
    data = bars.copy()
    data["liquidity"] = data.groupby("symbol", sort=False)["amount"].transform(
        lambda values: values.rolling(liquidity_window, min_periods=liquidity_window).mean()
    )
    selected = _monthly_rows(data)
    rank = selected["liquidity"].groupby(selected["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected["weight"] = (rank <= top_n).astype(float)
    count = selected["weight"].groupby(selected["timestamp"]).transform("sum")
    selected["weight"] = selected["weight"] / count.replace(0, pd.NA)
    return selected[["timestamp", "symbol", "weight"]].fillna({"weight": 0.0})


def top_cap_weighted_weights(
    bars: pd.DataFrame,
    *,
    top_n: int = 500,
    cap_column: str = "float_market_cap",
) -> pd.DataFrame:
    selected = _monthly_rows(bars)
    rank = selected[cap_column].groupby(selected["timestamp"]).rank(
        ascending=False, method="first"
    )
    raw = selected[cap_column].where(rank <= top_n, 0.0).clip(lower=0)
    total = raw.groupby(selected["timestamp"]).transform("sum")
    selected["weight"] = raw / total.replace(0, pd.NA)
    return selected[["timestamp", "symbol", "weight"]].fillna({"weight": 0.0})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run CSMAR benchmark strategies")
    parser.add_argument("--data", default="data/market/csmar/stock/1d")
    parser.add_argument("--output", default="reports/csmar_benchmarks")
    args = parser.parse_args()

    bars = load_bars(args.data)
    frames = {
        "top500_liquid_equal": top_liquid_equal_weights(bars, top_n=500),
        "top1000_liquid_equal": top_liquid_equal_weights(bars, top_n=1000),
        "top500_float_cap_weight": top_cap_weighted_weights(bars, top_n=500),
        "top1000_float_cap_weight": top_cap_weighted_weights(bars, top_n=1000),
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    config = BacktestConfig(initial_cash=1_000_000)
    engine = PortfolioEngine(config)
    rows = []
    for name, weights in frames.items():
        result = engine.run(bars, weights)
        rows.append({"strategy": name, **result.metrics})
    full = pd.DataFrame(rows).sort_values("sharpe", ascending=False)
    full.to_csv(output / "full_period.csv", index=False, encoding="utf-8-sig")
    factories = {
        name: (lambda context, start, end, frame=frame: frame[frame["timestamp"] <= end])
        for name, frame in frames.items()
    }
    rolling = RollingWindowBacktester(
        config,
        RollingWindowConfig((12, 36), step_months=6),
    ).run(bars, factories)
    rolling.summary.to_csv(output / "rolling_summary.csv", index=False, encoding="utf-8-sig")
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    print(full.to_string(index=False))
    print(
        rolling.summary[
            [
                "strategy",
                "window_months",
                "window_return_median",
                "window_return_q05",
                "sharpe_median",
                "max_drawdown_median",
                "profitable_window_ratio",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
