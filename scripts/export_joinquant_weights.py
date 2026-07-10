"""Export saved AutoTrader strategy weights to JoinQuant-compatible files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotrader.exporters.joinquant import export_joinquant_weights


def main() -> None:
    parser = argparse.ArgumentParser(description="Export strategy weights for JoinQuant")
    parser.add_argument("--weights", required=True, help="input CSV with timestamp,symbol,weight")
    parser.add_argument("--output-csv", required=True, help="JoinQuant CSV output path")
    parser.add_argument(
        "--output-python",
        help="optional JoinQuant helper .py with embedded WEIGHTS mapping",
    )
    parser.add_argument(
        "--summary",
        help="optional summary CSV path; defaults to output CSV with .summary.csv suffix",
    )
    parser.add_argument(
        "--include-unsupported",
        action="store_true",
        help="keep unsupported suffixes such as .BJ instead of dropping them",
    )
    parser.add_argument(
        "--min-weight",
        type=float,
        default=0.0,
        help="drop rows with weight <= min-weight",
    )
    args = parser.parse_args()

    weights = pd.read_csv(args.weights)
    result = export_joinquant_weights(
        weights,
        args.output_csv,
        python_path=args.output_python,
        summary_path=args.summary,
        include_unsupported=args.include_unsupported,
        min_weight=args.min_weight,
    )
    print(f"input_rows={result.input_rows}")
    print(f"exported_rows={result.exported_rows}")
    print(f"dropped_rows={result.dropped_rows}")
    print(f"dates={result.dates}")
    print(f"securities={result.securities}")
    print(f"csv={result.csv_path}")
    if result.python_path:
        print(f"python={result.python_path}")
    print(f"summary={result.summary_path}")


if __name__ == "__main__":
    main()
