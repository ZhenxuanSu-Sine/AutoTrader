"""
批量获取股票历史数据。

使用重构后的数据源和存储模块。
"""

from __future__ import annotations
import argparse
from pathlib import Path
import time
import random
from tqdm import tqdm

from data.sources.akshare_source import AkshareDataSource
from data.storage.parquet_storage import ParquetStorage
from utils.universe import load_universe, extract_symbols
from utils.proxy import setup_proxy, clear_proxy

def main():
    parser = argparse.ArgumentParser(description="批量获取股票历史数据")
    parser.add_argument("--codes", default=None, help="逗号分隔的股票代码")
    parser.add_argument("--universe", default=None, help="包含股票代码的CSV文件（列名: symbol/code/代码）")
    parser.add_argument("--start", required=True, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", required=True, help="结束日期 YYYYMMDD")
    parser.add_argument("--outdir", default="data/ohlcv/daily/akshare")
    parser.add_argument("--adjust", default="", choices=["", "qfq", "hfq"])
    parser.add_argument("--source-order", default="em_hist,sina_daily,tx_hist",
                        help="逗号分隔的数据源优先级列表")
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--http-proxy", default=None)
    parser.add_argument("--retries", type=int, default=3, help="每个数据源的重试次数")
    args = parser.parse_args()

    # 设置代理
    if args.no_proxy:
        clear_proxy()
    if args.http_proxy:
        setup_proxy(args.http_proxy)

    # 加载股票代码列表
    symbols = []
    if args.universe:
        symbols += load_universe(args.universe)
    if args.codes:
        symbols += extract_symbols(args.codes)
    symbols = list(set(symbols))
    if not symbols:
        raise SystemExit("未提供股票代码，请使用 --codes 或 --universe")

    # 初始化数据源和存储
    source = AkshareDataSource()
    storage = ParquetStorage(base_dir=str(Path(args.outdir).parent))
    sources = [s.strip() for s in args.source_order.split(",") if s.strip()]

    # 初始化源级失败计数
    source_fail_count = {src: 0 for src in sources}
    success_count = 0
    fail_count = 0

    pbar = tqdm(symbols, desc="获取股票数据", unit="只")

    for code in pbar:
        df = None
        for src in sources:
            for attempt in range(1, args.retries + 1):
                try:
                    df = source.fetch_daily(code, args.start, args.end, args.adjust, src)
                    if not df.empty:
                        break
                except Exception as e:
                    wait = 0.5 * (2 ** (attempt - 1)) + random.random() * 0.5
                    time.sleep(wait)
            if df is not None and not df.empty:
                break
            else:
                source_fail_count[src] += 1

        if df is None or df.empty:
            fail_count += 1
        else:
            storage.save(df, code, subdir=Path(args.outdir).name)
            success_count += 1

        # 动态刷新进度条并显示各源失败数
        pbar.set_postfix({"成功": success_count, "失败": fail_count, **source_fail_count})
        pbar.update(0)  # 不增加计数，只刷新 postfix

if __name__ == "__main__":
    main()