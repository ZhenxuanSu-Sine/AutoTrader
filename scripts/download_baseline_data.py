"""Download the small, reproducible baseline universe from Tushare."""

from __future__ import annotations

import argparse
import time
from pathlib import Path

from autotrader.data.sources import AkshareDataSource, TushareDataSource


DEFAULT_SYMBOLS = [
    "000001.SZ",  # 平安银行
    "000333.SZ",  # 美的集团
    "600000.SH",  # 浦发银行
    "600036.SH",  # 招商银行
    "600519.SH",  # 贵州茅台
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Download qfq daily bars for baseline research")
    parser.add_argument("--start", default="20150101")
    parser.add_argument("--end", default="20260706")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--source", choices=["akshare", "tushare"], default="akshare")
    parser.add_argument("--output", default="data/market/akshare_sina/stock/1d")
    parser.add_argument(
        "--request-interval",
        type=float,
        default=2.0,
        help="Seconds between symbols; increase this when a provider enforces tighter limits",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    source = AkshareDataSource() if args.source == "akshare" else TushareDataSource()
    pending = []
    for symbol in args.symbols:
        path = output / f"{symbol}.parquet"
        if path.exists() and not args.force:
            print(f"SKIP {symbol}: {path} already exists", flush=True)
        else:
            pending.append((symbol, path))

    for index, (symbol, path) in enumerate(pending):
        if index:
            time.sleep(args.request_interval)
        print(f"FETCH {args.source} {symbol} {args.start}..{args.end}", flush=True)
        bars = source.fetch_stock_daily(symbol, args.start, args.end, adjust="qfq")
        bars.to_parquet(path, index=False)
        print(
            f"SAVED {symbol}: {len(bars)} rows, "
            f"{bars['timestamp'].min().date()}..{bars['timestamp'].max().date()}",
            flush=True,
        )


if __name__ == "__main__":
    main()
