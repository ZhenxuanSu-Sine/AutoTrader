"""
从AKShare获取日线数据并保存为CSV。

使用重构后的数据源模块。
"""

import argparse
from data.sources.akshare_source import AkshareDataSource


def main() -> None:
    parser = argparse.ArgumentParser(description="从AKShare获取日线数据并保存为CSV。")
    parser.add_argument("--symbol", required=True, help='A股代码，如 "000001" 或 "600519"')
    parser.add_argument("--start", default=None, help="开始日期 YYYYMMDD")
    parser.add_argument("--end", default=None, help="结束日期 YYYYMMDD")
    parser.add_argument("--adjust", default="", help='复权类型: "", "qfq", 或 "hfq"')
    parser.add_argument("--outfile", required=True, help="输出CSV文件路径")
    args = parser.parse_args()

    # 使用新的数据源模块
    source = AkshareDataSource()
    df = source.fetch_daily(args.symbol, args.start, args.end, args.adjust)
    df.to_csv(args.outfile, index=False)
    print(f"已保存 {len(df)} 行数据到 {args.outfile}")


if __name__ == "__main__":
    main()
