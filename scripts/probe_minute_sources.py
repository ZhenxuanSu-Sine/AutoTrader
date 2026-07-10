"""Probe free minute-level data sources without bulk downloading."""

from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def probe_baostock_5m(symbol: str, start: str, end: str, timeout: int) -> dict:
    import baostock as bs

    socket.setdefaulttimeout(timeout)
    row = {
        "source": "baostock",
        "endpoint": "query_history_k_data_plus",
        "symbol": symbol,
        "period": "5",
        "ok": False,
        "rows": 0,
        "first": "",
        "last": "",
        "columns": "",
        "latency_s": 0.0,
        "error": "",
    }
    started = time.perf_counter()
    try:
        login = bs.login()
        if login.error_code != "0":
            row["error"] = f"login {login.error_code}: {login.error_msg}"
            return row
        fields = "date,time,code,open,high,low,close,volume,amount,adjustflag"
        result = bs.query_history_k_data_plus(
            symbol,
            fields,
            start_date=start,
            end_date=end,
            frequency="5",
            adjustflag="3",
        )
        if result.error_code != "0":
            row["error"] = f"query {result.error_code}: {result.error_msg}"
            return row
        rows = []
        while result.next():
            rows.append(result.get_row_data())
        frame = pd.DataFrame(rows, columns=result.fields)
        row.update(
            {
                "ok": True,
                "rows": len(frame),
                "first": "" if frame.empty else f"{frame.iloc[0]['date']} {frame.iloc[0]['time']}",
                "last": "" if frame.empty else f"{frame.iloc[-1]['date']} {frame.iloc[-1]['time']}",
                "columns": ",".join(frame.columns),
            }
        )
    except Exception as exc:  # noqa: BLE001 - probe script should record all failures.
        row["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        row["latency_s"] = round(time.perf_counter() - started, 3)
        try:
            bs.logout()
        except Exception:
            pass
    return row


def probe_akshare_sina(symbol: str, periods: list[str], adjust: str) -> list[dict]:
    import akshare as ak

    rows = []
    for period in periods:
        row = {
            "source": "akshare",
            "endpoint": "stock_zh_a_minute",
            "symbol": symbol,
            "period": period,
            "ok": False,
            "rows": 0,
            "first": "",
            "last": "",
            "columns": "",
            "latency_s": 0.0,
            "error": "",
        }
        started = time.perf_counter()
        try:
            frame = ak.stock_zh_a_minute(symbol=symbol, period=period, adjust=adjust)
            row.update(
                {
                    "ok": True,
                    "rows": len(frame),
                    "first": "" if frame.empty else str(frame.iloc[0]["day"]),
                    "last": "" if frame.empty else str(frame.iloc[-1]["day"]),
                    "columns": ",".join(frame.columns),
                }
            )
        except Exception as exc:  # noqa: BLE001
            row["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            row["latency_s"] = round(time.perf_counter() - started, 3)
        rows.append(row)
    return rows


def probe_akshare_em(symbol: str, start: str, end: str, period: str, adjust: str) -> dict:
    import akshare as ak

    row = {
        "source": "akshare",
        "endpoint": "stock_zh_a_hist_min_em",
        "symbol": symbol,
        "period": period,
        "ok": False,
        "rows": 0,
        "first": "",
        "last": "",
        "columns": "",
        "latency_s": 0.0,
        "error": "",
    }
    started = time.perf_counter()
    try:
        frame = ak.stock_zh_a_hist_min_em(
            symbol=symbol,
            period=period,
            start_date=start,
            end_date=end,
            adjust=adjust,
        )
        row.update(
            {
                "ok": True,
                "rows": len(frame),
                "first": "" if frame.empty else str(frame.iloc[0, 0]),
                "last": "" if frame.empty else str(frame.iloc[-1, 0]),
                "columns": ",".join(frame.columns),
            }
        )
    except Exception as exc:  # noqa: BLE001
        row["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        row["latency_s"] = round(time.perf_counter() - started, 3)
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe minute data sources")
    parser.add_argument("--output", default="reports/minute_source_probe/probe.csv")
    parser.add_argument("--baostock-symbol", default="sz.000001")
    parser.add_argument("--akshare-symbol", default="sz000001")
    parser.add_argument("--akshare-em-symbol", default="000001")
    parser.add_argument("--start-date", default="2024-01-02")
    parser.add_argument("--end-date", default="2024-01-05")
    parser.add_argument("--em-start", default="2024-01-02 09:30:00")
    parser.add_argument("--em-end", default="2024-01-02 15:00:00")
    parser.add_argument("--timeout", type=int, default=15)
    args = parser.parse_args()

    rows = [
        probe_baostock_5m(args.baostock_symbol, args.start_date, args.end_date, args.timeout)
    ]
    rows.extend(probe_akshare_sina(args.akshare_symbol, ["1", "5", "15", "30", "60"], ""))
    rows.append(probe_akshare_em(args.akshare_em_symbol, args.em_start, args.em_end, "1", ""))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_csv(output, index=False, encoding="utf-8-sig")
    print(frame.to_string(index=False))
    print(f"\nSaved: {output}")


if __name__ == "__main__":
    main()
