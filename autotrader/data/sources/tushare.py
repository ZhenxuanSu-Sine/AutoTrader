"""Tushare adapter for canonical AutoTrader bars."""

from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from autotrader.data.schema import normalize_bars


def load_tushare_token(env_file: str | Path = ".env") -> str:
    """Load a token without requiring or exposing ``python-dotenv``."""

    token = os.getenv("TUSHARE_TOKEN", "").strip()
    path = Path(env_file)
    if not token and path.exists():
        for raw in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "TUSHARE_TOKEN":
                token = value.strip().strip("'\"")
                break
    if not token or token.lower() == "your_token_here":
        raise RuntimeError("TUSHARE_TOKEN is missing")
    return token


class TushareDataSource:
    """Fetch adjusted A-share bars through Tushare Pro."""

    def __init__(self, token: str | None = None) -> None:
        try:
            import tushare as ts
        except ImportError as exc:
            raise ImportError("install the data extra: pip install -e '.[data]'") from exc
        self._ts = ts
        self._token = token or load_tushare_token()
        self._pro = ts.pro_api(self._token)

    def fetch_stock_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        """Return canonical daily bars for one ``000001.SZ`` style symbol."""

        frame = self._ts.pro_bar(
            api=self._pro,
            ts_code=symbol,
            asset="E",
            adj=adjust,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )
        if frame is None or frame.empty:
            raise RuntimeError(f"Tushare returned no daily bars for {symbol}")
        frame = frame.copy()
        if "ts_code" not in frame:
            frame["ts_code"] = symbol
        return normalize_bars(
            frame,
            column_map={
                "trade_date": "timestamp",
                "ts_code": "symbol",
                "vol": "volume",
            },
        )

    def fetch_index_daily(
        self, symbol: str, start_date: str, end_date: str
    ) -> pd.DataFrame:
        frame = self._pro.index_daily(
            ts_code=symbol,
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
        )
        if frame is None or frame.empty:
            raise RuntimeError(f"Tushare returned no index bars for {symbol}")
        return normalize_bars(
            frame,
            column_map={
                "trade_date": "timestamp",
                "ts_code": "symbol",
                "vol": "volume",
            },
        )

