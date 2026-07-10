"""Export target-weight strategies to JoinQuant-compatible files."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


@dataclass(frozen=True)
class JoinQuantExportResult:
    csv_path: Path
    python_path: Path | None
    summary_path: Path
    input_rows: int
    exported_rows: int
    dropped_rows: int
    dates: int
    securities: int


def csmar_symbol_to_joinquant(symbol: str, *, include_unsupported: bool = False) -> str | None:
    """Convert canonical A-share symbols to JoinQuant security codes.

    Supported conversions:

    - ``600000.SH`` -> ``600000.XSHG``
    - ``000001.SZ`` -> ``000001.XSHE``

    JoinQuant's public stock examples and docs use ``.XSHG`` and ``.XSHE``.
    North Exchange symbols are returned only when ``include_unsupported`` is
    true, because they may not be usable in all JoinQuant environments.
    """

    value = str(symbol).strip().upper()
    if value.endswith(".XSHG") or value.endswith(".XSHE"):
        return value
    if value.endswith(".SH"):
        return value[:-3] + ".XSHG"
    if value.endswith(".SZ"):
        return value[:-3] + ".XSHE"
    if value.endswith(".BJ"):
        return value[:-3] + ".BJ" if include_unsupported else None
    if len(value) == 6 and value.isdigit():
        if value.startswith(("5", "6", "9")):
            return value + ".XSHG"
        if value.startswith(("0", "1", "2", "3")):
            return value + ".XSHE"
    return value if include_unsupported else None


def export_joinquant_weights(
    weights: pd.DataFrame,
    csv_path: str | Path,
    *,
    python_path: str | Path | None = None,
    summary_path: str | Path | None = None,
    include_unsupported: bool = False,
    min_weight: float = 0.0,
) -> JoinQuantExportResult:
    """Export ``timestamp/symbol/weight`` rows as JoinQuant target weights.

    The CSV schema is intentionally minimal and stable:

    - ``date``: rebalance date, ``YYYY-MM-DD``
    - ``code``: JoinQuant security code, such as ``600519.XSHG``
    - ``weight``: target portfolio weight
    """

    required = {"timestamp", "symbol", "weight"}
    missing = required - set(weights.columns)
    if missing:
        raise ValueError(f"weights missing columns: {sorted(missing)}")
    if min_weight < 0:
        raise ValueError("min_weight must be non-negative")

    data = weights[list(required)].copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"])
    data["weight"] = pd.to_numeric(data["weight"], errors="raise")
    data = data[data["weight"] > min_weight].copy()
    data["code"] = data["symbol"].map(
        lambda value: csmar_symbol_to_joinquant(
            value, include_unsupported=include_unsupported
        )
    )
    dropped = int(data["code"].isna().sum())
    exported = data[data["code"].notna()].copy()
    exported["date"] = exported["timestamp"].dt.strftime("%Y-%m-%d")
    exported = exported[["date", "code", "weight"]].sort_values(["date", "code"])

    csv_output = Path(csv_path)
    csv_output.parent.mkdir(parents=True, exist_ok=True)
    exported.to_csv(csv_output, index=False, encoding="utf-8-sig")

    py_output = Path(python_path) if python_path is not None else None
    if py_output is not None:
        py_output.parent.mkdir(parents=True, exist_ok=True)
        py_output.write_text(_joinquant_python_template(exported), encoding="utf-8")

    summary_output = Path(summary_path) if summary_path is not None else csv_output.with_suffix(".summary.csv")
    summary_output.parent.mkdir(parents=True, exist_ok=True)
    summary = (
        exported.groupby("date")
        .agg(securities=("code", "nunique"), gross_weight=("weight", "sum"))
        .reset_index()
    )
    summary.to_csv(summary_output, index=False, encoding="utf-8-sig")

    return JoinQuantExportResult(
        csv_path=csv_output,
        python_path=py_output,
        summary_path=summary_output,
        input_rows=int(len(weights)),
        exported_rows=int(len(exported)),
        dropped_rows=dropped,
        dates=int(exported["date"].nunique()) if not exported.empty else 0,
        securities=int(exported["code"].nunique()) if not exported.empty else 0,
    )


def _joinquant_python_template(exported: pd.DataFrame) -> str:
    grouped = {
        date: {
            row.code: round(float(row.weight), 12)
            for row in group.itertuples(index=False)
        }
        for date, group in exported.groupby("date", sort=True)
    }
    return (
        '"""JoinQuant helper generated from AutoTrader target weights.\n\n'
        "Usage inside JoinQuant:\n"
        "1. Paste this file into a strategy or import the WEIGHTS mapping.\n"
        "2. Call rebalance(context) once per trading day.\n"
        '"""\n\n'
        f"WEIGHTS = {grouped!r}\n\n"
        "def initialize(context):\n"
        "    run_daily(rebalance, time='open')\n\n\n"
        "def rebalance(context):\n"
        "    today = context.current_dt.strftime('%Y-%m-%d')\n"
        "    targets = WEIGHTS.get(today)\n"
        "    if not targets:\n"
        "        return\n"
        "    current = set(context.portfolio.positions.keys())\n"
        "    target_codes = set(targets.keys())\n"
        "    for security in current - target_codes:\n"
        "        order_target_percent(security, 0)\n"
        "    for security, weight in targets.items():\n"
        "        order_target_percent(security, weight)\n"
    )
