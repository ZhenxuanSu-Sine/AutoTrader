"""Search JoinQuant-ready small-account variants of saved strategy weights."""

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
from autotrader.evaluation.metrics import performance_metrics
from scripts.run_csmar_strategies import load_bars


def small_account_weights(
    weights: pd.DataFrame,
    *,
    initial_cash: float,
    max_positions: int,
    min_position_value: float,
    cash_buffer: float,
) -> pd.DataFrame:
    """Keep only feasible high-weight names and renormalize for small accounts.

    This mirrors the JoinQuant helper's intent. The exact helper additionally
    rounds by live price and board lot; the backtest engine then applies its own
    100-share lot rounding at execution time.
    """

    rows = []
    gross = 1.0 - cash_buffer
    for timestamp, group in weights.groupby("timestamp", sort=True):
        selected = group.sort_values("weight", ascending=False).head(max_positions).copy()
        total = selected["weight"].sum()
        if total <= 0:
            continue
        selected["weight"] = selected["weight"] / total * gross
        selected = selected[selected["weight"] * initial_cash >= min_position_value]
        if selected.empty:
            continue
        selected["weight"] = selected["weight"] / selected["weight"].sum() * gross
        rows.append(selected[["timestamp", "symbol", "weight"]])
    if not rows:
        return pd.DataFrame(columns=["timestamp", "symbol", "weight"])
    return pd.concat(rows, ignore_index=True)


def market_returns(bars: pd.DataFrame) -> tuple[pd.Index, pd.Index, pd.DataFrame]:
    dates = pd.Index(sorted(bars["timestamp"].unique()))
    symbols = pd.Index(sorted(bars["symbol"].unique()))
    close = bars.pivot(index="timestamp", columns="symbol", values="close").reindex(
        index=dates, columns=symbols
    )
    returns = close.pct_change(fill_method=None).fillna(0.0)
    return dates, symbols, returns


def approx_metrics_from_weights(
    dates: pd.Index,
    symbols: pd.Index,
    returns: pd.DataFrame,
    weights: pd.DataFrame,
) -> dict[str, float]:
    monthly = weights.pivot(index="timestamp", columns="symbol", values="weight").reindex(
        columns=symbols, fill_value=0.0
    )
    daily = monthly.reindex(dates).ffill().shift(1).fillna(0.0)
    portfolio_returns = (daily * returns).sum(axis=1)
    equity = (1 + portfolio_returns).cumprod()
    metrics = performance_metrics(equity)
    gross = weights.groupby("timestamp")["weight"].sum()
    counts = weights.groupby("timestamp")["symbol"].nunique()
    metrics.update(
        {
            "average_gross_weight": float(gross.mean()) if len(gross) else 0.0,
            "average_position_count": float(counts.mean()) if len(counts) else 0.0,
            "rebalance_count": float(len(counts)),
        }
    )
    return metrics


def score(row: pd.Series) -> float:
    dd_penalty = max(0.0, abs(row["max_drawdown"]) - 0.35) * 1.5
    too_many_penalty = max(0.0, row["average_position_count"] - 12) * 0.01
    return float(row["sharpe"] + row["annual_return"] - dd_penalty - too_many_penalty)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search small-account JoinQuant variants")
    parser.add_argument("--data", default="data/market/csmar/stock/1d_combined_total_return")
    parser.add_argument("--weights-dir", default="reports/csmar_combined_fast_monthly_search")
    parser.add_argument("--output", default="reports/joinquant_small_account_search")
    parser.add_argument("--initial-cash", nargs="+", type=float, default=[50_000, 100_000, 200_000])
    parser.add_argument("--max-positions", nargs="+", type=int, default=[5, 8, 10, 15, 20])
    parser.add_argument("--min-position-values", nargs="+", type=float, default=[2_000, 3_000, 5_000, 8_000])
    parser.add_argument("--cash-buffers", nargs="+", type=float, default=[0.02, 0.05, 0.10])
    parser.add_argument("--confirm-top", type=int, default=3)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    print("Loading bars...", flush=True)
    bars = load_bars(args.data)
    print("Precomputing daily return matrix...", flush=True)
    dates, symbols, returns = market_returns(bars)
    print("Loading saved weights...", flush=True)
    weight_files = sorted(Path(args.weights_dir).glob("weights_*.csv"))
    if not weight_files:
        raise SystemExit(f"no weights_*.csv files found under {args.weights_dir}")

    cached_weights = {}
    for path in weight_files:
        name = path.stem.removeprefix("weights_")
        frame = pd.read_csv(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        cached_weights[name] = frame[["timestamp", "symbol", "weight"]]

    rows = []
    variants: dict[str, pd.DataFrame] = {}
    for strategy, base_weights in cached_weights.items():
        for initial_cash in args.initial_cash:
            for max_positions in args.max_positions:
                for min_position_value in args.min_position_values:
                    for cash_buffer in args.cash_buffers:
                        small = small_account_weights(
                            base_weights,
                            initial_cash=initial_cash,
                            max_positions=max_positions,
                            min_position_value=min_position_value,
                            cash_buffer=cash_buffer,
                        )
                        if small.empty:
                            continue
                        metrics = approx_metrics_from_weights(dates, symbols, returns, small)
                        row = {
                            "variant": (
                                f"{strategy}_cash{int(initial_cash)}_"
                                f"top{max_positions}_min{int(min_position_value)}_"
                                f"buf{cash_buffer:.2f}"
                            ),
                            "strategy": strategy,
                            "initial_cash": initial_cash,
                            "max_positions": max_positions,
                            "min_position_value": min_position_value,
                            "cash_buffer": cash_buffer,
                            **metrics,
                        }
                        row["score"] = score(pd.Series(row))
                        rows.append(row)
                        variants[row["variant"]] = small

    screen = pd.DataFrame(rows).sort_values("score", ascending=False)
    screen.to_csv(output / "approx_screen.csv", index=False, encoding="utf-8-sig")
    print(screen.head(20).to_string(index=False), flush=True)

    confirm_rows = []
    for row in screen.head(args.confirm_top).itertuples(index=False):
        print(f"Confirming {row.variant} with PortfolioEngine...", flush=True)
        config = BacktestConfig(initial_cash=float(row.initial_cash), lot_size=100)
        result = PortfolioEngine(config).run(bars, variants[row.variant])
        confirm = {
            "variant": row.variant,
            "strategy": row.strategy,
            "initial_cash": row.initial_cash,
            "max_positions": row.max_positions,
            "min_position_value": row.min_position_value,
            "cash_buffer": row.cash_buffer,
            **result.metrics,
        }
        confirm_rows.append(confirm)
        variants[row.variant].to_csv(output / f"weights_{row.variant}.csv", index=False, encoding="utf-8-sig")

    if confirm_rows:
        confirmed = pd.DataFrame(confirm_rows).sort_values("sharpe", ascending=False)
        confirmed.to_csv(output / "confirmed.csv", index=False, encoding="utf-8-sig")
        print(confirmed.to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
