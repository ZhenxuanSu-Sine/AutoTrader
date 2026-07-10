"""Canonical long-form bar schema.

Every data provider must cross this boundary before storage or research.  One
row represents one symbol at one timestamp; this works for daily and intraday
bars and avoids provider-specific column names leaking into strategies.
"""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

BAR_COLUMNS = ("timestamp", "symbol", "open", "high", "low", "close", "volume")
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume")

COMMON_COLUMN_ALIASES = {
    "datetime": "timestamp",
    "date": "timestamp",
    "日期": "timestamp",
    "代码": "symbol",
    "股票代码": "symbol",
    "开盘": "open",
    "最高": "high",
    "最低": "low",
    "收盘": "close",
    "成交量": "volume",
    "成交额": "amount",
}


def normalize_bars(
    frame: pd.DataFrame,
    *,
    symbol: str | None = None,
    column_map: Mapping[str, str] | None = None,
) -> pd.DataFrame:
    """Normalize provider output and validate the canonical bar contract."""

    mapping = dict(COMMON_COLUMN_ALIASES)
    if column_map:
        mapping.update(column_map)
    bars = frame.rename(columns={key: value for key, value in mapping.items() if key in frame}).copy()
    if "symbol" not in bars and symbol is not None:
        bars["symbol"] = str(symbol)

    missing = set(BAR_COLUMNS) - set(bars.columns)
    if missing:
        raise ValueError(f"missing bar columns: {sorted(missing)}")

    bars["timestamp"] = pd.to_datetime(bars["timestamp"], errors="coerce")
    bars["symbol"] = bars["symbol"].astype("string").str.strip()
    for column in NUMERIC_COLUMNS:
        bars[column] = pd.to_numeric(bars[column], errors="coerce")
    if "amount" in bars:
        bars["amount"] = pd.to_numeric(bars["amount"], errors="coerce")

    ordered = list(BAR_COLUMNS) + [column for column in bars.columns if column not in BAR_COLUMNS]
    bars = bars.loc[:, ordered].sort_values(["timestamp", "symbol"], kind="stable")
    bars = bars.reset_index(drop=True)
    validate_bars(bars)
    return bars


def validate_bars(bars: pd.DataFrame) -> None:
    """Raise ``ValueError`` when bars could make research results ambiguous."""

    missing = set(BAR_COLUMNS) - set(bars.columns)
    if missing:
        raise ValueError(f"missing bar columns: {sorted(missing)}")
    if bars.empty:
        raise ValueError("bar data is empty")
    if bars[list(BAR_COLUMNS)].isna().any().any():
        bad = bars[list(BAR_COLUMNS)].columns[bars[list(BAR_COLUMNS)].isna().any()].tolist()
        raise ValueError(f"bar data contains nulls in: {bad}")
    if bars["symbol"].str.len().eq(0).any():
        raise ValueError("symbol must not be empty")
    if bars.duplicated(["timestamp", "symbol"]).any():
        raise ValueError("duplicate (timestamp, symbol) bars")
    if not pd.api.types.is_datetime64_any_dtype(bars["timestamp"]):
        raise ValueError("timestamp must be a pandas datetime dtype")
    if (bars[["open", "high", "low", "close"]] <= 0).any().any():
        raise ValueError("OHLC prices must be positive")
    if (bars["volume"] < 0).any():
        raise ValueError("volume must be non-negative")
    if (bars["high"] + np.finfo(float).eps < bars[["open", "close", "low"]].max(axis=1)).any():
        raise ValueError("high is below another OHLC price")
    if (bars["low"] - np.finfo(float).eps > bars[["open", "close", "high"]].min(axis=1)).any():
        raise ValueError("low is above another OHLC price")
