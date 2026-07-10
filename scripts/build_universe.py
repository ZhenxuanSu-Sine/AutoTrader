# scripts/build_universe.py
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd

try:
    import akshare as ak
except ImportError as exc:
    raise SystemExit("AKShare not installed. Please `pip install akshare`.") from exc


def _ensure_out(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _code_name_df() -> pd.DataFrame:
    df = ak.stock_info_a_code_name()
    rename_map = {
        "code": "symbol",
        "证券代码": "symbol",
        "代码": "symbol",
        "名称": "name",
        "证券简称": "name",
        "name": "name",
    }
    for col, new in rename_map.items():
        if col in df.columns:
            df = df.rename(columns={col: new})
    if "symbol" not in df.columns:
        df = df.rename(columns={df.columns[0]: "symbol"})
    keep = [c for c in ["symbol", "name"] if c in df.columns]
    df = df[keep].copy()
    df["symbol"] = df["symbol"].astype(str).str.extract(r"(\d{6})", expand=False)
    df = df.dropna(subset=["symbol"]).drop_duplicates(subset=["symbol"]).reset_index(drop=True)
    return df


def _delist_table_sh() -> pd.DataFrame:
    try:
        df = ak.stock_info_sh_delist()
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    for col in ["COMPANY_CODE", "COMPANYCODE", "证券代码", "代码", "code", "symbol"]:
        if col in df.columns:
            df["symbol"] = df[col].astype(str).str.extract(r"(\d{6})", expand=False)
            break
    if "symbol" not in df.columns:
        c0 = df.columns[0]
        df["symbol"] = df[c0].astype(str).str.extract(r"(\d{6})", expand=False)
    df = df.dropna(subset=["symbol"]).drop_duplicates(subset=["symbol"]).reset_index(drop=True)
    return df


def _delist_table_sz() -> pd.DataFrame:
    try:
        df = ak.stock_info_sz_delist()
    except Exception:
        return pd.DataFrame()
    if df.empty:
        return df
    for col in ["证券代码", "代码", "code", "symbol"]:
        if col in df.columns:
            df["symbol"] = df[col].astype(str).str.extract(r"(\d{6})", expand=False)
            break
    if "symbol" not in df.columns:
        c0 = df.columns[0]
        df["symbol"] = df[c0].astype(str).str.extract(r"(\d{6})", expand=False)
    df = df.dropna(subset=["symbol"]).drop_duplicates(subset=["symbol"]).reset_index(drop=True)
    return df


def main() -> None:
    ap = argparse.ArgumentParser(description="Build A-share universe and delisting tables via AKShare.")
    ap.add_argument("--out", default="meta/universe", help="Output directory")
    args = ap.parse_args()

    out = Path(args.out)
    _ensure_out(out)

    codes = _code_name_df()
    codes.to_csv(out / "a_share_codes.csv", index=False, encoding="utf-8-sig")
    print(f"Saved {len(codes)} symbols → {out/'a_share_codes.csv'}")

    sh = _delist_table_sh()
    if not sh.empty:
        sh.to_csv(out / "delisted_sh.csv", index=False, encoding="utf-8-sig")
        print(f"Saved SH delist → {out/'delisted_sh.csv'}  ({len(sh)})")
    else:
        print("Shanghai delist table not available.")
    sz = _delist_table_sz()
    if not sz.empty:
        sz.to_csv(out / "delisted_sz.csv", index=False, encoding="utf-8-sig")
        print(f"Saved SZ delist → {out/'delisted_sz.csv'}  ({len(sz)})")
    else:
        print("Shenzhen delist table not available.")


if __name__ == "__main__":
    main()
