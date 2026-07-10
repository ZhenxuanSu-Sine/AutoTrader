"""
增量刷新历史数据。

使用重构后的数据源和存储模块。
"""

from __future__ import annotations
import argparse
from pathlib import Path
from datetime import datetime, timedelta

from data.sources.akshare_source import AkshareDataSource
from data.storage.parquet_storage import ParquetStorage
from utils.universe import extract_symbols
from utils.proxy import setup_proxy, clear_proxy

def main():
    parser = argparse.ArgumentParser(description="增量刷新历史数据")
    parser.add_argument("--codes", required=True, help="逗号分隔的股票代码")
    parser.add_argument("--end", default=None, help="结束日期 YYYYMMDD，默认为今天")
    parser.add_argument("--outdir", default="data/ohlcv/daily/akshare")
    parser.add_argument("--adjust", default="", choices=["", "qfq", "hfq"])
    parser.add_argument("--source-order", default="em_hist,sina_daily,tx_hist")
    parser.add_argument("--no-proxy", action="store_true")
    parser.add_argument("--http-proxy", default=None)
    args = parser.parse_args()

    # 设置代理
    if args.no_proxy:
        clear_proxy()
    if args.http_proxy:
        setup_proxy(args.http_proxy)

    # 初始化数据源和存储
    source = AkshareDataSource()
    storage = ParquetStorage(base_dir=str(Path(args.outdir).parent))
    codes = extract_symbols(args.codes)
    sources = [s.strip() for s in args.source_order.split(",") if s.strip()]
    today = datetime.now().strftime("%Y%m%d")
    end_date = args.end or today

    for code in codes:
        # 获取已有数据的最大日期
        max_date = storage.get_max_date(code, subdir=Path(args.outdir).name)
        if max_date is None:
            start_date = "20050101"
        else:
            # 拉取最大日期之后的数据
            dt = datetime.strptime(max_date, "%Y%m%d") + timedelta(days=1)
            start_date = dt.strftime("%Y%m%d")
        if start_date > end_date:
            print(f"[{code}] 数据已是最新")
            continue

        # 尝试从多个数据源获取数据
        df = None
        for src in sources:
            try:
                df = source.fetch_daily(code, start_date, end_date, args.adjust, src)
                if not df.empty:
                    break
            except Exception as e:
                print(f"[{code}] {src} 失败: {e}")
        if df is None or df.empty:
            print(f"[{code}] 所有数据源都失败，无法获取新数据")
            continue

        # 合并并保存数据
        storage.save(df, code, subdir=Path(args.outdir).name, merge=True)

if __name__ == "__main__":
    main()
