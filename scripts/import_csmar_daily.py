"""Import downloaded CSMAR daily files into canonical parquet bars."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotrader.data.sources.csmar import import_daily_to_yearly_parquet


def main() -> None:
    parser = argparse.ArgumentParser(description="Import CSMAR daily NDJSON files")
    parser.add_argument("--raw-root", default="data")
    parser.add_argument("--output", default="data/market/csmar/stock/1d")
    parser.add_argument("--chunksize", type=int, default=250_000)
    args = parser.parse_args()

    summary = import_daily_to_yearly_parquet(
        raw_root=args.raw_root,
        output_root=args.output,
        chunksize=args.chunksize,
    )
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
