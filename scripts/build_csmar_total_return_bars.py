"""Build total-return adjusted CSMAR daily bars.

CSMAR daily files provide raw OHLC prices plus ``return_with_dividend``.  Many
technical signals should be computed on a continuous total-return price series;
otherwise ex-dividend/split-like jumps can pollute momentum and volatility.

This script creates adjusted OHLC bars by reconstructing a per-symbol
total-return close and scaling raw OHLC by adjusted_close / raw_close.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def load_bars(path: str) -> pd.DataFrame:
    files = sorted(Path(path).glob("year=*/bars.parquet"))
    if not files:
        raise FileNotFoundError(f"no yearly parquet bars under {path}")
    return (
        pd.concat([pd.read_parquet(file) for file in files], ignore_index=True)
        .sort_values(["symbol", "timestamp"])
        .reset_index(drop=True)
    )


def build_total_return_bars(bars: pd.DataFrame) -> pd.DataFrame:
    data = bars.copy()
    data["return_with_dividend"] = pd.to_numeric(
        data["return_with_dividend"], errors="coerce"
    ).fillna(0.0)

    def adjust_symbol(group: pd.DataFrame) -> pd.DataFrame:
        group = group.sort_values("timestamp").copy()
        first_close = float(group["close"].iloc[0])
        growth = (1 + group["return_with_dividend"]).cumprod()
        # CSMAR's first-day return is from prior/IPO reference. Anchor the
        # adjusted series at the first observed close to avoid injecting a
        # pre-sample move.
        growth = growth / float(growth.iloc[0])
        group["raw_close"] = group["close"]
        group["adjusted_close"] = first_close * growth
        factor = group["adjusted_close"] / group["close"].replace(0, pd.NA)
        group["adjustment_factor"] = factor.astype(float)
        for column in ["open", "high", "low", "close"]:
            group[column] = group[column] * group["adjustment_factor"]
        return group

    adjusted = data.groupby("symbol", group_keys=False, sort=False).apply(adjust_symbol)
    adjusted = adjusted.reset_index(drop=True).sort_values(["timestamp", "symbol"])
    return adjusted


def write_yearly(bars: pd.DataFrame, output: str) -> pd.DataFrame:
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    for year, frame in bars.groupby(bars["timestamp"].dt.year):
        path = out / f"year={int(year)}" / "bars.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        rows.append(
            {
                "year": int(year),
                "rows": len(frame),
                "symbols": frame["symbol"].nunique(),
                "start": frame["timestamp"].min().date().isoformat(),
                "end": frame["timestamp"].max().date().isoformat(),
                "path": str(path),
            }
        )
    summary = pd.DataFrame(rows).sort_values("year")
    summary.to_csv(out / "import_summary.csv", index=False, encoding="utf-8-sig")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Build CSMAR total-return bars")
    parser.add_argument("--input", default="data/market/csmar/stock/1d")
    parser.add_argument("--output", default="data/market/csmar/stock/1d_total_return")
    args = parser.parse_args()

    print("Loading raw CSMAR bars...", flush=True)
    bars = load_bars(args.input)
    print(f"Loaded {len(bars):,} rows, {bars['symbol'].nunique():,} symbols", flush=True)
    print("Building adjusted OHLC...", flush=True)
    adjusted = build_total_return_bars(bars)
    summary = write_yearly(adjusted, args.output)
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
