"""Evaluate saved CSMAR strategy weights with rolling windows."""

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


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate saved CSMAR weights")
    parser.add_argument("--data", default="data/market/csmar/stock/1d_total_return")
    parser.add_argument("--weights-dir", default="reports/csmar_fast_monthly_search")
    parser.add_argument("--output", default="reports/csmar_selected_defensive")
    args = parser.parse_args()

    bars = load_bars(args.data)
    weights_dir = Path(args.weights_dir)
    frames = {}
    for path in sorted(weights_dir.glob("weights_*.csv")):
        name = path.stem.removeprefix("weights_")
        frame = pd.read_csv(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frames[name] = frame[["timestamp", "symbol", "weight"]]
    if not frames:
        raise SystemExit(f"no weights_*.csv found in {weights_dir}")

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    config = BacktestConfig(initial_cash=1_000_000)
    engine = PortfolioEngine(config)
    full = []
    for name, weights in frames.items():
        full.append({"strategy": name, **engine.run(bars, weights).metrics})
    full_frame = pd.DataFrame(full).sort_values("sharpe", ascending=False)
    full_frame.to_csv(output / "full_period.csv", index=False, encoding="utf-8-sig")

    factories = {
        name: (lambda context, start, end, frame=frame: frame[frame["timestamp"] <= end])
        for name, frame in frames.items()
    }
    rolling = RollingWindowBacktester(
        config, RollingWindowConfig((1, 3, 6, 12, 36), step_months=3)
    ).run(bars, factories)
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    rolling.summary.to_csv(output / "rolling_summary.csv", index=False, encoding="utf-8-sig")
    comparison = rolling.summary.merge(
        full_frame[["strategy", "annual_return", "sharpe", "max_drawdown", "turnover", "total_cost"]],
        on="strategy",
        how="left",
    )
    comparison.to_csv(output / "comparison.csv", index=False, encoding="utf-8-sig")
    print(full_frame.to_string(index=False))
    print(
        comparison[
            [
                "strategy",
                "window_months",
                "window_count",
                "window_return_median",
                "window_return_q05",
                "sharpe_median",
                "max_drawdown_median",
                "profitable_window_ratio",
                "annual_return",
                "sharpe",
                "max_drawdown",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
