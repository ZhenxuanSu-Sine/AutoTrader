"""
Data download utility for Tushare.

This script fetches daily price data from the Tushare PRO API and
saves it as a CSV file.  It can be run from the command line or
imported as a module.  When used from the command line, specify the
stock code (e.g. ``000001.SZ``), your Tushare token, the start and
end dates, and the output path.  The resulting CSV can then be
ingested by Backtrader via Pandas.

Example usage:

```
python data/fetch_tushare_data.py --token <YOUR_TOKEN> --symbol 000001.SZ \
    --start 20240101 --end 20241231 --outfile data/sample_000001.SZ.csv
```
"""

import argparse
from typing import Optional

import pandas as pd

try:
    import tushare as ts
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "Tushare package is not installed.  Please run 'pip install tushare' first."
    ) from exc


def fetch_daily(
    token: str,
    symbol: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    retry_count: int = 3,
) -> pd.DataFrame:
    """Download daily bars for a single symbol from Tushare.

    Args:
        token: Your Tushare PRO API token.
        symbol: The stock code, e.g. ``000001.SZ``.
        start: The start date (inclusive) in ``YYYYMMDD`` format.  If
            omitted, Tushare will return as many records as available.
        end: The end date (inclusive) in ``YYYYMMDD`` format.  If
            omitted, Tushare will return up to the most recent data.
        retry_count: Number of times to retry the API call in case of
            network issues.

    Returns:
        A Pandas DataFrame containing the daily bars sorted by
        trading date ascending.  The column names are compatible with
        Backtrader's default naming convention (``open``, ``high``,
        ``low``, ``close``, ``volume``).
    """
    # Initialise API
    ts.set_token(token)
    pro = ts.pro_api()

    for attempt in range(retry_count):  # retry loop
        try:
            df = pro.daily(ts_code=symbol, start_date=start, end_date=end)
            break
        except Exception as e:
            if attempt + 1 == retry_count:
                raise
            print(f'API call failed (attempt {attempt + 1}/{retry_count}): {e}. Retrying...')
    else:
        raise RuntimeError('Failed to fetch data from Tushare after retries')

    # Rename columns to Backtrader friendly names and sort by date
    df = df.rename(
        columns={
            'trade_date': 'datetime',
            'open': 'open',
            'high': 'high',
            'low': 'low',
            'close': 'close',
            'vol': 'volume',
        }
    )
    df['datetime'] = pd.to_datetime(df['datetime'])
    df = df.sort_values('datetime')
    df = df[['datetime', 'open', 'high', 'low', 'close', 'volume']]
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description='Fetch daily bars from Tushare.')
    parser.add_argument('--token', required=True, help='Tushare API token')
    parser.add_argument('--symbol', required=True, help='Stock code, e.g. 000001.SZ')
    parser.add_argument('--start', default=None, help='Start date (YYYYMMDD)')
    parser.add_argument('--end', default=None, help='End date (YYYYMMDD)')
    parser.add_argument('--outfile', required=True, help='Path to output CSV file')
    args = parser.parse_args()

    df = fetch_daily(args.token, args.symbol, args.start, args.end)
    df.to_csv(args.outfile, index=False)
    print(f'Saved {len(df)} rows to {args.outfile}')


if __name__ == '__main__':
    main()