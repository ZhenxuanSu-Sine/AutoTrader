"""Offline CSMAR data import utilities."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
import shutil

import pandas as pd

from autotrader.data.schema import normalize_bars

A_SHARE_MARKET_TYPES = {1, 4, 16, 32, 64}


def discover_csmar_files(root: str | Path) -> dict[str, list[Path]]:
    """Find known CSMAR NDJSON files under ``root``."""

    base = Path(root)
    return {
        "company": sorted(base.rglob("TRD_Co.json")),
        "daily": sorted(path for path in base.rglob("TRD_Dalyr*.json") if "[DES]" not in path.name),
        "index_basic": sorted(base.rglob("IDX_Idxinfo.json")),
    }


def market_suffix(market_type: int, code: str) -> str:
    """Map CSMAR market type/code to a common exchange suffix."""

    if market_type in {1, 32}:
        return "SH"
    if market_type in {4, 16}:
        return "SZ"
    if market_type == 64:
        return "BJ"
    if code.startswith("6"):
        return "SH"
    if code.startswith(("0", "2", "3")):
        return "SZ"
    return "BJ"


def format_symbol(code: str, market_type: int) -> str:
    normalized = str(code).zfill(6)
    return f"{normalized}.{market_suffix(market_type, normalized)}"


def read_company_file(path: str | Path) -> pd.DataFrame:
    """Read and normalize CSMAR company metadata."""

    frame = pd.read_json(path, lines=True, dtype={"Stkcd": "string"})
    frame["Stkcd"] = frame["Stkcd"].astype("string").str.zfill(6)
    frame["Markettype"] = pd.to_numeric(frame["Markettype"], errors="coerce").astype("Int64")
    frame["is_a_share"] = (
        frame["Markettype"].isin(A_SHARE_MARKET_TYPES) & frame["Curtrd"].eq("CNY")
    )
    frame["symbol"] = [
        format_symbol(code, int(market_type))
        if pd.notna(market_type)
        else f"{code}.UNK"
        for code, market_type in zip(frame["Stkcd"], frame["Markettype"])
    ]
    return frame


def company_lookup(company: pd.DataFrame) -> pd.DataFrame:
    """Return the subset of company fields needed by daily imports."""

    columns = [
        "Stkcd",
        "symbol",
        "Stknme",
        "Listdt",
        "Statco",
        "Statdt",
        "Markettype",
        "Curtrd",
        "Indcd",
        "Indnme",
        "Nnindcd",
        "Nnindnme",
        "IndcdZX",
        "IndnmeZX",
        "is_a_share",
    ]
    return company[[column for column in columns if column in company.columns]].copy()


def _read_daily_chunks(paths: Iterable[Path], chunksize: int) -> Iterable[pd.DataFrame]:
    for path in paths:
        yield from pd.read_json(path, lines=True, chunksize=chunksize, dtype={"Stkcd": "string"})


def normalize_daily_chunk(chunk: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    """Convert a CSMAR daily-return chunk to canonical bars plus metadata."""

    data = chunk.copy()
    data["Stkcd"] = data["Stkcd"].astype("string").str.zfill(6)
    data = data.merge(lookup, on="Stkcd", how="left")
    data = data[data["is_a_share"].fillna(False)].copy()
    if data.empty:
        return pd.DataFrame()
    renamed = data.rename(
        columns={
            "Trddt": "timestamp",
            "Opnprc": "open",
            "Hiprc": "high",
            "Loprc": "low",
            "Clsprc": "close",
            "Dnshrtrd": "volume",
            "Dnvaltrd": "amount",
            "Dsmvosd": "float_market_cap",
            "Dsmvtll": "total_market_cap",
            "Dretwd": "return_with_dividend",
            "Dretnd": "return_without_dividend",
            "ChangeRatio": "change_ratio",
            "Stknme": "name",
            "Listdt": "list_date",
            "Statco": "status",
            "Statdt": "status_date",
            "Markettype": "market_type",
            "Indcd": "industry_code_a",
            "Indnme": "industry_name_a",
            "Nnindcd": "industry_code_csrc_2012",
            "Nnindnme": "industry_name_csrc_2012",
            "IndcdZX": "industry_code_assoc",
            "IndnmeZX": "industry_name_assoc",
        }
    )
    keep = [
        "timestamp",
        "symbol",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "float_market_cap",
        "total_market_cap",
        "return_with_dividend",
        "return_without_dividend",
        "change_ratio",
        "name",
        "list_date",
        "status",
        "status_date",
        "market_type",
        "industry_code_a",
        "industry_name_a",
        "industry_code_csrc_2012",
        "industry_name_csrc_2012",
        "industry_code_assoc",
        "industry_name_assoc",
    ]
    bars = normalize_bars(renamed[[column for column in keep if column in renamed.columns]])
    bars["year"] = bars["timestamp"].dt.year.astype("int16")
    return bars


def import_daily_to_yearly_parquet(
    *,
    raw_root: str | Path,
    output_root: str | Path,
    chunksize: int = 250_000,
) -> pd.DataFrame:
    """Import CSMAR daily NDJSON files into yearly parquet files.

    Returns a compact per-year summary.
    """

    files = discover_csmar_files(raw_root)
    if not files["company"]:
        raise FileNotFoundError(f"TRD_Co.json not found under {raw_root}")
    if not files["daily"]:
        raise FileNotFoundError(f"TRD_Dalyr*.json not found under {raw_root}")
    lookup = company_lookup(read_company_file(files["company"][0]))
    out = Path(output_root)
    out.mkdir(parents=True, exist_ok=True)
    parts = out / "_parts"
    if parts.exists():
        shutil.rmtree(parts)
    parts.mkdir(parents=True, exist_ok=True)

    part_counts: dict[int, int] = {}
    raw_year_rows: dict[int, int] = {}

    for chunk in _read_daily_chunks(files["daily"], chunksize):
        bars = normalize_daily_chunk(chunk, lookup)
        if bars.empty:
            continue
        for year, group in bars.groupby("year", sort=False):
            year = int(year)
            count = part_counts.get(year, 0)
            part_path = parts / f"year={year}" / f"part-{count:05d}.parquet"
            part_path.parent.mkdir(parents=True, exist_ok=True)
            group.drop(columns=["year"]).to_parquet(part_path, index=False)
            part_counts[year] = count + 1
            raw_year_rows[year] = raw_year_rows.get(year, 0) + len(group)

    summary_rows: list[dict] = []
    for year in sorted(part_counts):
        year_parts = sorted((parts / f"year={year}").glob("part-*.parquet"))
        frame = pd.concat([pd.read_parquet(path) for path in year_parts], ignore_index=True)
        raw_rows = len(frame)
        frame = (
            frame.drop_duplicates(["timestamp", "symbol"], keep="last")
            .sort_values(["timestamp", "symbol"])
            .reset_index(drop=True)
        )
        path = out / f"year={year}" / "bars.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path, index=False)
        summary_rows.append(
            {
                "year": year,
                "raw_rows": raw_rows,
                "rows": len(frame),
                "duplicates_removed": raw_rows - len(frame),
                "symbols": frame["symbol"].nunique(),
                "start": frame["timestamp"].min().date().isoformat(),
                "end": frame["timestamp"].max().date().isoformat(),
                "path": str(path),
            }
        )
    shutil.rmtree(parts)

    summary = pd.DataFrame(summary_rows).sort_values("year").reset_index(drop=True)
    summary.to_csv(out / "import_summary.csv", index=False, encoding="utf-8-sig")
    return summary
