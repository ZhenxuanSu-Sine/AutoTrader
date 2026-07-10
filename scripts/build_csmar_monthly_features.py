"""Precompute monthly CSMAR price/volume factors for faster strategy search."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.run_csmar_strategies import load_bars


def build_features(bars: pd.DataFrame) -> pd.DataFrame:
    data = bars.sort_values(["symbol", "timestamp"]).copy()
    grouped = data.groupby("symbol", sort=False)
    close = grouped["close"]
    returns = close.pct_change()
    for window in (5, 20, 60, 120):
        data[f"ret_{window}"] = close.pct_change(window)
    for window in (20, 60):
        data[f"vol_{window}"] = (
            returns.groupby(data["symbol"], sort=False)
            .rolling(window, min_periods=window)
            .std()
            .reset_index(level=0, drop=True)
            * (252**0.5)
        )
    high_120 = close.transform(lambda values: values.rolling(120).max())
    data["drawdown_120"] = data["close"] / high_120 - 1
    data["liquidity_20"] = grouped["amount"].transform(lambda values: values.rolling(20).mean())
    data["history"] = grouped["close"].cumcount() + 1

    data = data.sort_values(["timestamp", "symbol"])
    data["month"] = data["timestamp"].dt.to_period("M")
    rebalance_dates = data.groupby("month")["timestamp"].min()
    monthly = data[data["timestamp"].isin(rebalance_dates)].copy()

    rank_columns = [
        "ret_5",
        "ret_20",
        "ret_60",
        "ret_120",
        "vol_20",
        "vol_60",
        "drawdown_120",
        "liquidity_20",
        "float_market_cap",
        "total_market_cap",
    ]
    for column in rank_columns:
        ascending = column not in {"vol_20", "vol_60"}
        monthly[f"{column}_rank"] = monthly[column].groupby(monthly["timestamp"]).rank(
            ascending=ascending, pct=True
        )
    return monthly.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build monthly CSMAR features")
    parser.add_argument("--data", default="data/market/csmar/stock/1d_total_return")
    parser.add_argument("--output", default="data/features/csmar/monthly_price_volume.parquet")
    args = parser.parse_args()

    bars = load_bars(args.data)
    features = build_features(bars)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(output, index=False)
    print(
        f"Saved {len(features):,} monthly rows, {features['symbol'].nunique():,} symbols "
        f"to {output}"
    )


if __name__ == "__main__":
    main()
