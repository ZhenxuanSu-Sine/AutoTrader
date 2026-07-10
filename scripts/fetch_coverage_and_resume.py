# scripts/fetch_coverage_and_resume.py
from __future__ import annotations
import argparse
from pathlib import Path
import pandas as pd
from tqdm import tqdm
import subprocess


def _years_between(start: str, end: str) -> list[int]:
    s = pd.to_datetime(start, format='%Y%m%d')
    e = pd.to_datetime(end, format='%Y%m%d')
    return list(range(s.year, e.year + 1))

def _load_universe(csv_path: str) -> list[str]:
    df = pd.read_csv(csv_path)
    for col in ["symbol", "code", "代码"]:
        if col in df.columns:
            return df[col].astype(str).str.extract(r"(\d{6})", expand=False).dropna().unique().tolist()
    return df[df.columns[0]].astype(str).str.extract(r"(\d{6})", expand=False).dropna().unique().tolist()

def main():
    parser = argparse.ArgumentParser(description="Check coverage and resume missing stock data")
    parser.add_argument("--universe", required=True, help="CSV file with stock codes")
    parser.add_argument("--outdir", default="data/ohlcv/daily/akshare")
    parser.add_argument("--start", required=True, help="YYYYMMDD")
    parser.add_argument("--end", required=True, help="YYYYMMDD")
    parser.add_argument("--adjust", default="", choices=["", "qfq", "hfq"])
    parser.add_argument("--source-order", default="em_hist,sina_daily,tx_hist")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--bulk-script", default="scripts/bulk_fetch_akshare.py")
    parser.add_argument("--no-proxy", action="store_true")
    args = parser.parse_args()

    symbols = _load_universe(args.universe)
    years = _years_between(args.start, args.end)

    outdir = Path(args.outdir)
    summary_rows = []
    missing_rows = []

    for sym in tqdm(symbols, desc="Checking coverage", unit="stock"):
        file = outdir / f"symbol={sym}.parquet"
        present_years = set()
        if file.exists():
            df = pd.read_parquet(file, columns=["datetime"])
            present_years.update(pd.to_datetime(df['datetime']).dt.year.unique())
        missing = sorted(set(years) - present_years)
        summary_rows.append({"symbol": sym, "present_years": list(present_years), "missing_years": missing})
        for y in missing:
            missing_rows.append({"symbol": sym, "year": y})

    summary_df = pd.DataFrame(summary_rows)
    missing_df = pd.DataFrame(missing_rows)

    report_dir = Path("reports")
    report_dir.mkdir(exist_ok=True, parents=True)
    summary_df.to_csv(report_dir / "fetch_coverage_summary.csv", index=False)
    missing_df.to_csv(report_dir / "missing_symbol_years.csv", index=False)

    # 自动补拉缺失年份
    for idx, row in tqdm(missing_df.iterrows(), total=len(missing_df), desc="Resuming missing data", unit="task"):
        sym, year = row['symbol'], row['year']
        start_date = f"{year}0101"
        end_date = f"{year}1231"
        cmd = ["python", args.bulk_script, "--codes", sym, "--start", start_date, "--end", end_date, "--outdir", args.outdir, "--adjust", args.adjust, "--source-order", args.source_order, "--retries", str(args.retries)]
        if args.no_proxy:
            cmd.append("--no-proxy")
        subprocess.run(cmd, check=False)

if __name__ == "__main__":
    main()
