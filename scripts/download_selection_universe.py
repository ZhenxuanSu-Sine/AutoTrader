"""Snapshot a CSI 300 subset and download adjusted daily bars for stock selection."""

from __future__ import annotations

import argparse
import time
from datetime import date
from pathlib import Path

import pandas as pd

from autotrader.data.sources import AkshareDataSource


def tushare_symbol(code: str) -> str:
    return f"{code}.SH" if code.startswith(("5", "6", "9")) else f"{code}.SZ"


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a static stock-selection universe")
    parser.add_argument("--index", default="000300")
    parser.add_argument("--top", type=int, default=40)
    parser.add_argument("--start", default="20150101")
    parser.add_argument("--end", default="20260706")
    parser.add_argument("--output", default="data/market/akshare_sina/selection/1d")
    parser.add_argument("--manifest", default="data/universe/csi300_current_top40.csv")
    parser.add_argument("--request-interval", type=float, default=1.5)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    import akshare as ak

    universe = ak.index_stock_cons_sina(symbol=args.index).copy()
    universe["mktcap"] = pd.to_numeric(universe["mktcap"], errors="coerce")
    universe = universe.sort_values("mktcap", ascending=False).head(args.top).copy()
    universe["ts_code"] = universe["code"].astype(str).str.zfill(6).map(tushare_symbol)
    universe["snapshot_date"] = date.today().isoformat()
    manifest = Path(args.manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    universe[["snapshot_date", "ts_code", "code", "name", "mktcap"]].to_csv(
        manifest, index=False, encoding="utf-8-sig"
    )
    print(f"Saved universe snapshot: {manifest} ({len(universe)} symbols)", flush=True)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    source = AkshareDataSource()
    symbols = universe["ts_code"].tolist()
    failures = []
    for number, symbol in enumerate(symbols, start=1):
        path = output / f"{symbol}.parquet"
        if path.exists() and not args.force:
            print(f"SKIP {number}/{len(symbols)} {symbol}", flush=True)
            continue
        if number > 1:
            time.sleep(args.request_interval)
        try:
            bars = source.fetch_stock_daily(symbol, args.start, args.end, adjust="qfq")
            bars.to_parquet(path, index=False)
            print(f"SAVED {number}/{len(symbols)} {symbol}: {len(bars)} rows", flush=True)
        except Exception as exc:
            failures.append({"symbol": symbol, "error": f"{type(exc).__name__}: {exc}"})
            print(f"FAILED {number}/{len(symbols)} {symbol}: {exc}", flush=True)
    if failures:
        pd.DataFrame(failures).to_csv(output / "failures.csv", index=False, encoding="utf-8-sig")
    print(f"Completed with {len(failures)} failures", flush=True)


if __name__ == "__main__":
    main()

