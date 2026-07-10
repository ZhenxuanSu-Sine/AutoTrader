# scripts/resume_from_missing_years.py
from __future__ import annotations
import argparse, subprocess, sys, time, random
from pathlib import Path
from collections import defaultdict

import pandas as pd

def _year_blocks(years):
    """[2015,2016,2018] -> [(2015,2016),(2018,2018)]"""
    years = sorted(set(int(y) for y in years))
    if not years: return []
    blocks = []
    s = e = years[0]
    for y in years[1:]:
        if y == e + 1:
            e = y
        else:
            blocks.append((s, e))
            s = e = y
    blocks.append((s, e))
    return blocks

def _run(cmd):
    return subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)

def main():
    ap = argparse.ArgumentParser(description="Resume bulk fetch from missing_symbol_years.csv")
    ap.add_argument("--missing", default="reports/missing_symbol_years.csv",
                    help="CSV with columns: symbol,year")
    ap.add_argument("--bulk-script", default="scripts/bulk_fetch_akshare.py")
    ap.add_argument("--outdir", default="data/ohlcv/daily/akshare")
    ap.add_argument("--adjust", default="")
    ap.add_argument("--bucket-years", type=int, default=5)
    ap.add_argument("--compression", default="zstd")
    ap.add_argument("--zstd-level", type=int, default=3)
    ap.add_argument("--source-order", default="em_hist,sina_daily,tx_hist")
    # “单任务内”的并发我们固定为 1（bulk 内部也有线程池，这里让它更可控）
    ap.add_argument("--bulk-max-workers", type=int, default=1)
    ap.add_argument("--retry", type=int, default=4)
    ap.add_argument("--sleep", type=float, default=1.2)
    ap.add_argument("--backoff", type=float, default=2.0)
    ap.add_argument("--jitter", type=float, default=0.6)
    # 驱动层的并行（同时开几个 bulk 子进程）
    ap.add_argument("--driver-workers", type=int, default=2)
    ap.add_argument("--no-proxy", action="store_true")
    ap.add_argument("--http-proxy", default=None)
    ap.add_argument("--shuffle", action="store_true", help="Shuffle task order to降低同源短时压力")
    args = ap.parse_args()

    df = pd.read_csv(args.missing)
    if not {"symbol","year"}.issubset(df.columns):
        raise SystemExit("missing CSV must have columns: symbol,year")

    # group → symbol: [years...]
    mp = defaultdict(list)
    for _, row in df.iterrows():
        mp[str(row["symbol"])[-6:]].append(int(row["year"]))

    tasks = []  # (symbol, y0, y1)
    for sym, ys in mp.items():
        for y0, y1 in _year_blocks(ys):
            tasks.append((sym, y0, y1))
    if args.shuffle:
        random.shuffle(tasks)

    # 简单的“最多 N 子进程并发”调度
    running = []
    idx = 0

    def launch(task):
        sym, y0, y1 = task
        start = f"{y0}0101"; end = f"{y1}1231"
        cmd = [
            sys.executable, args.bulk_script,
            "--codes", sym,
            "--start", start, "--end", end,
            "--outdir", args.outdir,
            "--adjust", args.adjust,
            "--bucket-years", str(args.bucket_years),
            "--compression", args.compression,
            "--zstd-level", str(args.zstd_level),
            "--source-order", args.source_order,
            "--max-workers", str(args.bulk_max_workers),
            "--retry", str(args.retry),
            "--sleep", str(args.sleep),
            "--backoff", str(args.backoff),
            "--jitter", str(args.jitter),
        ]
        if args.no_proxy: cmd.append("--no-proxy")
        if args.http_proxy: cmd += ["--http-proxy", args.http_proxy]
        print(f"[launch] {sym} {start}..{end}")
        return subprocess.Popen(cmd)

    while idx < len(tasks) or running:
        while idx < len(tasks) and len(running) < args.driver_workers:
            running.append(launch(tasks[idx]))
            idx += 1
        # 清理已结束的
        still = []
        for p in running:
            if p.poll() is None:
                still.append(p)
        running = still
        time.sleep(0.5)

    print("All done.")

if __name__ == "__main__":
    main()
