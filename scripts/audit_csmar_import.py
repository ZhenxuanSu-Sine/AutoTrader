"""Audit imported CSMAR parquet bars."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit imported CSMAR bars")
    parser.add_argument("--data", default="data/market/csmar/stock/1d")
    parser.add_argument("--output", default="reports/csmar_import_audit")
    args = parser.parse_args()

    files = sorted(Path(args.data).glob("year=*/bars.parquet"))
    if not files:
        raise SystemExit(f"no parquet files found under {args.data}")
    frames = []
    yearly = []
    for path in files:
        frame = pd.read_parquet(path)
        frames.append(frame)
        yearly.append(
            {
                "year": int(path.parent.name.split("=")[1]),
                "rows": len(frame),
                "symbols": frame["symbol"].nunique(),
                "start": frame["timestamp"].min(),
                "end": frame["timestamp"].max(),
                "duplicate_keys": int(frame.duplicated(["timestamp", "symbol"]).sum()),
                "null_core": int(
                    frame[["timestamp", "symbol", "open", "high", "low", "close", "volume"]]
                    .isna()
                    .any(axis=1)
                    .sum()
                ),
            }
        )
    bars = pd.concat(frames, ignore_index=True)
    by_date = bars.groupby("timestamp")["symbol"].nunique()
    summary = {
        "rows": len(bars),
        "symbols": bars["symbol"].nunique(),
        "dates": bars["timestamp"].nunique(),
        "start": bars["timestamp"].min(),
        "end": bars["timestamp"].max(),
        "duplicate_keys": int(bars.duplicated(["timestamp", "symbol"]).sum()),
        "daily_symbols_min": int(by_date.min()),
        "daily_symbols_median": float(by_date.median()),
        "daily_symbols_max": int(by_date.max()),
        "daily_symbols_mean": float(by_date.mean()),
        "bad_ohlc": int(
            (
                (bars["high"] < bars[["open", "low", "close"]].max(axis=1))
                | (bars["low"] > bars[["open", "high", "close"]].min(axis=1))
            ).sum()
        ),
    }
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(yearly).to_csv(output / "yearly.csv", index=False, encoding="utf-8-sig")
    by_date.rename("symbols").reset_index().to_csv(
        output / "daily_coverage.csv", index=False, encoding="utf-8-sig"
    )
    pd.Series(summary).to_csv(output / "summary.csv", header=["value"], encoding="utf-8-sig")
    print(pd.Series(summary).to_string())
    print(pd.DataFrame(yearly).to_string(index=False))


if __name__ == "__main__":
    main()
