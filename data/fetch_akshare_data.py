# data/fetch_akshare_data.py
"""
Fetch daily OHLCV from AKShare and save to CSV in the framework's standard schema:
columns = ['datetime', 'open', 'high', 'low', 'close', 'volume'] (ascending by datetime).
"""

import argparse
from typing import Optional, Dict

import pandas as pd

try:
    import akshare as ak
except ImportError as exc:  # pragma: no cover
    raise SystemExit("Please `pip install akshare` first.") from exc


def _normalize_ohlcv(df: pd.DataFrame, mapping: Optional[Dict[str, str]] = None) -> pd.DataFrame:
    """
    Normalize various AKShare outputs (which may have Chinese or English headers) to
    ['datetime','open','high','low','close','volume'] and sort ascending by datetime.
    """
    df = df.copy()

    # Auto-detect common column names from AKShare daily endpoints
    candidate_maps = [
        # 中文列名常见于 stock_zh_a_hist(日线)
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"},
        # 英文列名（少见，但预留）
        {"date": "datetime", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
        # 某些情况下“成交量(手)”或“成交量(股)”
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量(手)": "volume"},
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量(股)": "volume"},
    ]
    if mapping:
        candidate_maps.insert(0, mapping)

    for mp in candidate_maps:
        if all(col in df.columns for col in mp.keys()):
            df = df.rename(columns=mp)
            break
    else:
        raise ValueError(f"Cannot find expected OHLCV columns in DataFrame: {df.columns.tolist()}")

    # Keep only required columns, coerce dtypes, sort asc
    use_cols = ["datetime", "open", "high", "low", "close", "volume"]
    df = df[use_cols].copy()
    df["datetime"] = pd.to_datetime(df["datetime"])
    # 数值列容错
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("datetime")
    return df


def fetch_daily_akshare(
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    adjust: str = "",    # "", "qfq", "hfq" 等（按你的需要）
) -> pd.DataFrame:
    """
    Use AKShare to fetch A-share daily bars. You can swap to other AKShare endpoints
    if you need different markets or indices, but keep the output normalized.
    """
    # 典型 A 股日线：ak.stock_zh_a_hist，symbol 示例："000001" 或 "600519"
    # period="daily", adjust 可选 "", "qfq", "hfq"
    df = ak.stock_zh_a_hist(symbol=symbol, period="daily", start_date=start, end_date=end, adjust=adjust)
    return _normalize_ohlcv(df)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch daily bars from AKShare and save as CSV.")
    parser.add_argument("--symbol", required=True, help='A-share code for AKShare, e.g. "000001" or "600519"')
    parser.add_argument("--start", default=None, help="Start date YYYYMMDD (AKShare)")
    parser.add_argument("--end", default=None, help="End date YYYYMMDD (AKShare)")
    parser.add_argument("--adjust", default="", help='Price adjustment: "", "qfq", or "hfq"')
    parser.add_argument("--outfile", required=True, help="Path to output CSV")
    args = parser.parse_args()

    df = fetch_daily_akshare(args.symbol, args.start, args.end, args.adjust)
    df.to_csv(args.outfile, index=False)
    print(f"Saved {len(df)} rows to {args.outfile}")


if __name__ == "__main__":
    main()
