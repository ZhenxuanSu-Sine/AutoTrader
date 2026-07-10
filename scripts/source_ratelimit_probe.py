# scripts/source_ratelimit_probe.py
from __future__ import annotations

import argparse
import csv
import logging
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd

try:
    import akshare as ak
except ImportError as exc:
    raise SystemExit("AKShare not installed. Please `pip install akshare`.") from exc

# ---------- Logger ----------
def _logger(verbosity: int = 1) -> logging.Logger:
    lg = logging.getLogger("ratelimit_probe")
    lg.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO if verbosity == 1 else logging.DEBUG if verbosity >= 2 else logging.WARNING)
    ch.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s: %(message)s"))
    lg.handlers.clear()
    lg.addHandler(ch)
    return lg

# ---------- Normalization ----------
def _normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["datetime", "open", "high", "low", "close", "volume"])
    df = df.copy()
    candidates = [
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume"},
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量(手)": "volume"},
        {"日期": "datetime", "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量(股)": "volume"},
        {"date": "datetime", "open": "open", "high": "high", "low": "low", "close": "close", "volume": "volume"},
    ]
    for mp in candidates:
        if all(k in df.columns for k in mp.keys()):
            df = df.rename(columns=mp)
            break
    if "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    for c in ["open", "high", "low", "close", "volume"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

# ---------- Sources ----------
def _to_prefixed(symbol6: str) -> str:
    return ("sh" if symbol6.startswith(("5", "6")) else "sz") + symbol6

def fetch_em_hist(symbol6: str, beg: str, end: str, adjust: str) -> pd.DataFrame:
    df = ak.stock_zh_a_hist(symbol=symbol6, period="daily", start_date=beg, end_date=end, adjust=adjust)
    return _normalize_ohlcv(df)

def fetch_tx_hist(symbol6: str, beg: str, end: str, adjust: str) -> pd.DataFrame:
    df = ak.stock_zh_a_hist_tx(symbol=_to_prefixed(symbol6), start_date=beg, end_date=end, adjust=adjust)
    return _normalize_ohlcv(df)

def fetch_sina_daily(symbol6: str, beg: str, end: str, adjust: str) -> pd.DataFrame:
    df = ak.stock_zh_a_daily(symbol=_to_prefixed(symbol6), start_date=beg, end_date=end, adjust=adjust)
    return _normalize_ohlcv(df)

SOURCE_FUNCS: Dict[str, Callable[[str, str, str, str], pd.DataFrame]] = {
    "em_hist": fetch_em_hist,
    "tx_hist": fetch_tx_hist,
    "sina_daily": fetch_sina_daily,
}

# ---------- Result schema ----------
@dataclass
class ProbeResult:
    ts: str
    source: str
    mode: str
    symbol: str
    beg: str
    end: str
    attempt: int
    latency_s: float
    rows: int
    ok: int
    err_type: str
    err_msg: str

def _write_header_if_empty(csv_path: Path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    if not csv_path.exists() or csv_path.stat().st_size == 0:
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow([c for c in ProbeResult.__annotations__.keys()])

def _record(csv_path: Path, r: ProbeResult):
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([getattr(r, k) for k in ProbeResult.__annotations__.keys()])

# ---------- Modes already in v1 ----------
def run_single(fetch: Callable, source: str, symbol: str, beg: str, end: str, adjust: str,
               attempts: int, base_sleep: float, jitter: float, csv_path: Path, lg: logging.Logger):
    for i in range(1, attempts + 1):
        t0 = time.perf_counter()
        err_type = ""; err_msg = ""; rows = 0; ok = 0
        try:
            df = fetch(symbol, beg, end, adjust)
            rows = 0 if df is None else len(df); ok = 1
        except Exception as e:
            err_type = type(e).__name__; err_msg = str(e)[:500]
        latency = time.perf_counter() - t0
        _record(csv_path, ProbeResult(datetime.now().isoformat(timespec="seconds"), source, "single",
                                      symbol, beg, end, i, latency, rows, ok, err_type, err_msg))
        time.sleep(base_sleep + random.random() * jitter)

def run_burst(fetch: Callable, source: str, symbol: str, beg: str, end: str, adjust: str,
              burst: int, csv_path: Path, lg: logging.Logger):
    for i in range(1, burst + 1):
        t0 = time.perf_counter()
        err_type = ""; err_msg = ""; rows = 0; ok = 0
        try:
            df = fetch(symbol, beg, end, adjust)
            rows = 0 if df is None else len(df); ok = 1
        except Exception as e:
            err_type = type(e).__name__; err_msg = str(e)[:500]
        latency = time.perf_counter() - t0
        _record(csv_path, ProbeResult(datetime.now().isoformat(timespec="seconds"), source, "burst",
                                      symbol, beg, end, i, latency, rows, ok, err_type, err_msg))

def run_paced(fetch: Callable, source: str, symbol: str, beg: str, end: str, adjust: str,
              times_n: int, interval: float, jitter: float, csv_path: Path, lg: logging.Logger):
    for i in range(1, times_n + 1):
        t0 = time.perf_counter()
        err_type = ""; err_msg = ""; rows = 0; ok = 0
        try:
            df = fetch(symbol, beg, end, adjust)
            rows = 0 if df is None else len(df); ok = 1
        except Exception as e:
            err_type = type(e).__name__; err_msg = str(e)[:500]
        latency = time.perf_counter() - t0
        _record(csv_path, ProbeResult(datetime.now().isoformat(timespec="seconds"), source, "paced",
                                      symbol, beg, end, i, latency, rows, ok, err_type, err_msg))
        time.sleep(interval + random.random() * jitter)

# ---------- NEW: daily-batch mode ----------
def _load_codes(args) -> List[str]:
    codes: List[str] = []
    if args.codes_file:
        df = pd.read_csv(args.codes_file)
        col = None
        for c in ["symbol", "code", "代码"]:
            if c in df.columns: col = c; break
        if col is None: col = df.columns[0]
        codes = df[col].astype(str).str.extract(r"(\d{6})", expand=False).dropna().tolist()
    if args.codes:
        codes += [c.strip()[-6:] for c in args.codes.split(",") if c.strip()]
    codes = list({c for c in codes if c and len(c)==6})
    if args.codes_n and args.codes_n < len(codes):
        random.seed(args.seed)
        codes = random.sample(codes, args.codes_n)
    if not codes:
        raise SystemExit("No codes provided. Use --codes-file and/or --codes.")
    return codes

def _task(fetch: Callable, source: str, sym: str, beg: str, end: str, adjust: str,
          task_jitter: float, lg: logging.Logger) -> ProbeResult:
    if task_jitter > 0:
        time.sleep(random.random() * task_jitter)
    t0 = time.perf_counter()
    err_type = ""; err_msg = ""; rows = 0; ok = 0
    try:
        df = fetch(sym, beg, end, adjust)
        rows = 0 if df is None else len(df); ok = 1
    except Exception as e:
        err_type = type(e).__name__; err_msg = str(e)[:500]
    latency = time.perf_counter() - t0
    return ProbeResult(datetime.now().isoformat(timespec="seconds"), source, "daily_batch",
                       sym, beg, end, 1, latency, rows, ok, err_type, err_msg)

def run_daily_batch(fetch: Callable, source: str, codes: List[str], beg: str, end: str, adjust: str,
                    workers: int, csv_path: Path, task_jitter: float, lg: logging.Logger):
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(_task, fetch, source, sym, beg, end, adjust, task_jitter, lg): sym for sym in codes}
        for fut in as_completed(futs):
            pr = fut.result()
            _record(csv_path, pr)

# ---------- Main ----------
def main() -> None:
    ap = argparse.ArgumentParser(description="Probe AKShare sources vs. frequency/mode (rate-limit detector)")
    ap.add_argument("--sources", default="em_hist,tx_hist,sina_daily", help="em_hist,tx_hist,sina_daily")
    ap.add_argument("--codes", default=None, help="Comma list of 6-digit symbols")
    ap.add_argument("--codes-file", default=None, help="CSV containing codes (column: symbol/code/代码)")
    ap.add_argument("--codes-n", type=int, default=0, help="Random sample N codes from the union (0=all)")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--start", default="20240101")
    ap.add_argument("--end", default="20240215")
    ap.add_argument("--adjust", default="")
    ap.add_argument("--out", default="logs/ratelimit_probe.csv")
    ap.add_argument("--verbose", action="count", default=1)

    # Light modes (kept)
    ap.add_argument("--single-attempts", type=int, default=0)
    ap.add_argument("--single-sleep", type=float, default=0.8)
    ap.add_argument("--single-jitter", type=float, default=0.4)
    ap.add_argument("--burst-n", type=int, default=0)
    ap.add_argument("--paced-n", type=int, default=0)
    ap.add_argument("--paced-interval", type=float, default=1.0)
    ap.add_argument("--paced-jitter", type=float, default=0.5)

    # Daily-batch mode (NEW)
    ap.add_argument("--daily-batch", action="store_true", help="Simulate daily incremental pull for all codes")
    ap.add_argument("--batch-workers", type=int, default=6, help="Thread pool size for daily-batch")
    ap.add_argument("--task-jitter", type=float, default=0.2, help="Random delay [0, jitter] before each task")
    ap.add_argument("--repeat", type=int, default=1, help="Repeat daily-batch cycles")
    ap.add_argument("--cooldown", type=float, default=30.0, help="Cooldown seconds between cycles")

    # Network
    ap.add_argument("--no-proxy", action="store_true", help="Ignore system proxy (set NO_PROXY=*)")
    ap.add_argument("--http-proxy", default=None, help="http(s)://user:pass@host:port")

    args = ap.parse_args()
    lg = _logger(args.verbose)

    # Proxy handling
    if args.no_proxy:
        for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"):
            os.environ.pop(k, None)
        os.environ["NO_PROXY"] = "*"
        lg.info("Proxy disabled via --no-proxy")
    if args.http_proxy:
        os.environ["HTTP_PROXY"] = args.http_proxy
        os.environ["HTTPS_PROXY"] = args.http_proxy
        lg.info(f"Using explicit proxy: {args.http_proxy}")

    # Setup
    srcs = [s.strip() for s in args.sources.split(",") if s.strip()]
    for s in srcs:
        if s not in SOURCE_FUNCS:
            raise SystemExit(f"Unknown source: {s}. Choices: {list(SOURCE_FUNCS.keys())}")
    codes = _load_codes(args)
    csv_path = Path(args.out)
    _write_header_if_empty(csv_path)
    lg.info(f"Targets → sources={srcs} | codes={len(codes)} | range={args.start}..{args.end}")

    # Light modes (optional)
    for source in srcs:
        fetch = SOURCE_FUNCS[source]
        if args.single_attempts > 0:
            run_single(fetch, source, codes[0], args.start, args.end, args.adjust,
                       attempts=args.single_attempts, base_sleep=args.single_sleep,
                       jitter=args.single_jitter, csv_path=csv_path, lg=lg)
        if args.burst_n > 0:
            run_burst(fetch, source, codes[0], args.start, args.end, args.adjust,
                      burst=args.burst_n, csv_path=csv_path, lg=lg)
        if args.paced_n > 0:
            run_paced(fetch, source, codes[0], args.start, args.end, args.adjust,
                      times_n=args.paced_n, interval=args.paced_interval,
                      jitter=args.paced_jitter, csv_path=csv_path, lg=lg)

    # Daily-batch cycles
    if args.daily_batch:
        for cycle in range(1, args.repeat + 1):
            lg.info(f"[daily-batch] cycle {cycle}/{args.repeat} | workers={args.batch_workers} | task_jitter={args.task_jitter}")
            for source in srcs:
                fetch = SOURCE_FUNCS[source]
                lg.info(f"[daily-batch] source={source} → {len(codes)} tasks")
                run_daily_batch(fetch, source, codes, args.start, args.end, args.adjust,
                                workers=args.batch_workers, csv_path=csv_path,
                                task_jitter=args.task_jitter, lg=lg)
            if cycle < args.repeat:
                lg.info(f"[daily-batch] cooldown {args.cooldown}s ...")
                time.sleep(args.cooldown)

    lg.info(f"Done. Results → {csv_path}")

if __name__ == "__main__":
    main()
