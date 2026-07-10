# scripts/probe_longwindow.py
from __future__ import annotations
import argparse, os, time, random, threading
from collections import deque, defaultdict
from datetime import datetime
from pathlib import Path
import csv
import pandas as pd
import numpy as np

try:
    import akshare as ak
except ImportError as e:
    raise SystemExit("pip install akshare") from e

def _to_prefixed(s6: str) -> str:
    return ("sh" if s6.startswith(("5","6")) else "sz") + s6

def fetch_em_hist(s, beg, end, adj):  return ak.stock_zh_a_hist(symbol=s, period="daily", start_date=beg, end_date=end, adjust=adj)
def fetch_tx_hist(s, beg, end, adj):  return ak.stock_zh_a_hist_tx(symbol=_to_prefixed(s), start_date=beg, end_date=end, adjust=adj)
def fetch_sina_daily(s,beg,end,adj):  return ak.stock_zh_a_daily(symbol=_to_prefixed(s), start_date=beg, end_date=end, adjust=adj)

SOURCES = {"em_hist": fetch_em_hist, "tx_hist": fetch_tx_hist, "sina_daily": fetch_sina_daily}

class RateLimiter:
    """per-source: min interval + sliding window cap"""
    def __init__(self, min_interval_s: float, window_s: int|None, max_in_window: int|None):
        from collections import deque
        self.min_interval = float(min_interval_s)
        self.window_s = window_s
        self.max_in_window = max_in_window
        self._next_allowed = defaultdict(float)   # key -> monotonic time
        self._hits = defaultdict(lambda: deque()) # key -> timestamps deque
        self._lock = threading.Lock()

    def acquire(self, key: str):
        now = time.monotonic()
        with self._lock:
            wait = max(0.0, self._next_allowed[key] - now)
        if wait > 0: time.sleep(wait)

        if self.window_s and self.max_in_window:
            # ensure window cap
            while True:
                with self._lock:
                    dq = self._hits[key]
                    tnow = time.monotonic()
                    while dq and (tnow - dq[0] > self.window_s):
                        dq.popleft()
                    if len(dq) < self.max_in_window:
                        dq.append(tnow)
                        self._next_allowed[key] = tnow + self.min_interval
                        break
                    else:
                        sleep_for = self.window_s - (tnow - dq[0]) + random.random()*0.05
                time.sleep(max(0.01, sleep_for))
        else:
            with self._lock:
                self._next_allowed[key] = time.monotonic() + self.min_interval

class CircuitBreaker:
    """per-source: if recent fail ratio exceeds threshold, cooldown"""
    def __init__(self, lookback:int=40, fail_ratio:float=0.5, cooldown_s:int=300):
        self.lookback=lookback; self.fail_ratio=fail_ratio; self.cooldown_s=cooldown_s
        self._buf = defaultdict(lambda: deque(maxlen=self.lookback))
        self._open_until = defaultdict(float)
        self._lock = threading.Lock()

    def before(self, key:str):
        with self._lock:
            t = self._open_until[key]
        if t > time.monotonic():
            time.sleep(t - time.monotonic())

    def after(self, key:str, ok:bool):
        with self._lock:
            self._buf[key].append(1 if ok else 0)
            b = self._buf[key]
            if len(b) >= self.lookback:
                r = 1 - (sum(b)/len(b))
                if r >= self.fail_ratio:
                    self._open_until[key] = time.monotonic() + self.cooldown_s

def run_probe(sources, codes, beg, end, minutes, min_interval, window_s, max_in_window,
              workers, out_csv, seed=42, no_proxy=False):
    if no_proxy:
        for k in ("HTTP_PROXY","HTTPS_PROXY","http_proxy","https_proxy"): os.environ.pop(k, None)
        os.environ["NO_PROXY"]="*"

    lim = RateLimiter(min_interval, window_s, max_in_window)
    cb  = CircuitBreaker(lookback=40, fail_ratio=0.5, cooldown_s=300)

    Path(out_csv).parent.mkdir(parents=True, exist_ok=True)
    if not Path(out_csv).exists() or Path(out_csv).stat().st_size==0:
        with open(out_csv,"w",newline="",encoding="utf-8") as f:
            csv.writer(f).writerow(["ts","source","symbol","ok","latency_s","err_type","err_msg"])

    rnd = random.Random(seed)
    end_at = time.monotonic() + minutes*60
    idx = 0
    while time.monotonic() < end_at:
        batch = []
        rnd.shuffle(codes)
        for src in sources:
            for sym in codes[:workers]:  # 每轮仅对每个源发 workers 个任务
                batch.append((src, sym))
        rnd.shuffle(batch)

        for src, sym in batch:
            t0 = time.perf_counter()
            errt=""; errm=""; ok=0
            try:
                cb.before(src)
                lim.acquire(src)
                df = SOURCES[src](sym, beg, end, "")
                ok = 1 if (isinstance(df, pd.DataFrame) and len(df)>=0) else 0
            except Exception as e:
                errt=type(e).__name__; errm=str(e)[:300]
            cb.after(src, bool(ok))
            lat = time.perf_counter()-t0
            with open(out_csv,"a",newline="",encoding="utf-8") as f:
                csv.writer(f).writerow([datetime.now().isoformat(timespec="seconds"), src, sym, ok, f"{lat:.4f}", errt, errm])

        # 轻微节奏：每轮间隔
        time.sleep(max(0.0, min_interval*0.2))
        idx += 1

if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Long-window rate-limit probe for AKShare sources")
    ap.add_argument("--sources", default="em_hist,sina_daily,tx_hist")
    ap.add_argument("--codes-file", required=True)
    ap.add_argument("--start", default="20240215")
    ap.add_argument("--end",   default="20240215")
    ap.add_argument("--minutes", type=int, default=45)
    ap.add_argument("--min-interval", type=float, default=0.6, help="per-source minimal interval (s)")
    ap.add_argument("--window-s", type=int, default=600, help="sliding window seconds")
    ap.add_argument("--max-in-window", type=int, default=350, help="max requests per source within window")
    ap.add_argument("--workers", type=int, default=3, help="per round, tasks per source")
    ap.add_argument("--out", default="logs/longwindow_probe.csv")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--no-proxy", action="store_true")
    args = ap.parse_args()

    df = pd.read_csv(args.codes_file)
    col = next((c for c in ["symbol","code","代码"] if c in df.columns), df.columns[0])
    codes = df[col].astype(str).str.extract(r"(\d{6})", expand=False).dropna().unique().tolist()

    sources=[s.strip() for s in args.sources.split(",") if s.strip()]
    run_probe(sources, codes, args.start, args.end, args.minutes,
              args.min_interval, args.window_s, args.max_in_window,
              args.workers, args.out, no_proxy=args.no_proxy)
