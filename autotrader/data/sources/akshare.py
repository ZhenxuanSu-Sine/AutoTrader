"""AKShare adapter using the Sina daily endpoint."""

from __future__ import annotations

import pandas as pd

from autotrader.data.schema import normalize_bars


class AkshareDataSource:
    def __init__(self) -> None:
        try:
            import akshare as ak
        except ImportError as exc:
            raise ImportError("install the data extra: pip install -e '.[data]'") from exc
        self._ak = ak

    @staticmethod
    def _sina_symbol(symbol: str) -> str:
        code = symbol.split(".", 1)[0]
        market = "sh" if code.startswith(("5", "6", "9")) else "sz"
        return market + code

    def fetch_stock_daily(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        *,
        adjust: str = "qfq",
    ) -> pd.DataFrame:
        frame = self._ak.stock_zh_a_daily(
            symbol=self._sina_symbol(symbol),
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust=adjust,
        )
        if frame is None or frame.empty:
            raise RuntimeError(f"AKShare returned no daily bars for {symbol}")
        return normalize_bars(frame, symbol=symbol)

