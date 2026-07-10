# scripts/audit_fetch_coverage.py
from __future__ import annotations
import argparse
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Dict, Set
import pandas as pd

def _years_between(start: str, end: str) -> List[int]:
    s = datetime.strptime(start, "%Y%m%d")
    e = datetime.strptime(end,   "%Y%m%d")
    return list(range(s.year, e.year + 1))

def _load_universe(csv_path: Path) -> List[str]:
    df = pd.read_csv(csv_path)
    for col in ["symbol", "code", "代码"]:
        if col in df.columns:
            return (df[col].astype(str)
                        .str.extract(r"(\d{6})", expand=False)
                        .dropna().unique().tolist())
    first = df.columns[0]
    return (df[first].astype(str)
                .str.extract(r"(\d{6})", expand=False)
                .dropna().unique().tolist())

def _present_years_for_symbol(sym_dir: Path) -> Set[int]:
    years: Set[int] = set()
    for f in sym_dir.glob("*.parquet"):
        try:
            # 只读 datetime 列以降低 IO
            dt = pd.read_parquet(f, columns=["datetime"])
            if dt.empty: 
                continue
            yrs = pd.to_datetime(dt["datetime"], errors="coerce").dt.year.dropna().astype(int).unique().tolist()
            years.update(yrs)
        except Exception:
            continue
    return years

def main():
    ap = argparse.ArgumentParser(description="Audit which years are fetched per symbol (and which are missing).")
    ap.add_argument("--outdir", required=True, help="e.g., data/ohlcv/daily/akshare")
    ap.add_argument("--universe", required=True, help="CSV with column symbol/code/代码")
    ap.add_argument("--start", required=True, help="YYYYMMDD")
    ap.add_argument("--end",   required=True, help="YYYYMMDD")
    ap.add_argument("--report-dir", default="reports", help="Where to write audit CSVs")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    uni = _load_universe(Path(args.universe))
    target_years = _years_between(args.start, args.end)
    report_dir = Path(args.report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    rows_detail = []
    rows_summary = []
    missing_codes: Set[str] = set()

    for sym in uni:
        sym_dir = outdir / f"symbol={sym}"
        present = _present_years_for_symbol(sym_dir) if sym_dir.exists() else set()
        missing = sorted(set(target_years) - present)
        rows_summary.append({
            "symbol": sym,
            "present_years_count": len(present),
            "missing_years_count": len(missing),
            "present_years": ",".join(map(str, sorted(present))) if present else "",
            "missing_years": ",".join(map(str, missing)) if missing else "",
        })
        for y in target_years:
            rows_detail.append({"symbol": sym, "year": y, "present": int(y in present)})
        if missing:
            missing_codes.add(sym)

    df_sum = pd.DataFrame(rows_summary).sort_values(["missing_years_count","symbol"], ascending=[False, True])
    df_det = pd.DataFrame(rows_detail).sort_values(["symbol","year"])

    p_sum = report_dir / "fetch_coverage_summary.csv"
    p_det = report_dir / "fetch_coverage_detail.csv"
    df_sum.to_csv(p_sum, index=False)
    df_det.to_csv(p_det, index=False)

    # 产出一个“只补缺”的 codes CSV，可直接作为 --universe 传入 bulk_fetch
    miss_csv = report_dir / "missing_codes.csv"
    pd.DataFrame({"symbol": sorted(missing_codes)}).to_csv(miss_csv, index=False)

    # 也给一份“缺失按年”的清单
    miss_years = df_det[df_det["present"] == 0][["symbol","year"]]
    miss_years.to_csv(report_dir / "missing_symbol_years.csv", index=False)

    print(f"Done.\nSummary → {p_sum}\nDetail  → {p_det}\nMissing codes → {miss_csv}\nMissing symbol-years → {report_dir / 'missing_symbol_years.csv'}")

if __name__ == "__main__":
    main()
