"""Run reproducible baseline strategies on the downloaded daily universe."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.strategies import (
    buy_and_hold_weights,
    cross_sectional_momentum_weights,
    equal_weight_weights,
    moving_average_weights,
    time_series_momentum_weights,
    trend_equal_weight_weights,
)


def extra_metrics(result) -> dict[str, float]:
    """Legacy output aliases backed by the engine's unified metrics."""
    return {
        "positive_day_ratio": result.metrics["daily_win_rate"],
        "total_fees": result.metrics["fees"],
    }


def run_one(engine, name: str, scope: str, bars: pd.DataFrame, weights: pd.DataFrame):
    result = engine.run(bars, weights)
    row = {"strategy": name, "scope": scope, **result.metrics, **extra_metrics(result)}
    return row, result


def write_markdown(
    summary: pd.DataFrame, bars: pd.DataFrame, output: Path, source_label: str
) -> None:
    ranked = summary.sort_values("sharpe", ascending=False).copy()
    percent = ["total_return", "annual_return", "annual_volatility", "max_drawdown"]
    for column in percent:
        ranked[column] = ranked[column].map(lambda value: f"{value:.2%}")
    for column in ["sharpe", "sortino", "calmar", "turnover"]:
        ranked[column] = ranked[column].map(lambda value: f"{value:.3f}")
    columns = [
        "strategy", "scope", "total_return", "annual_return", "annual_volatility",
        "sharpe", "sortino", "max_drawdown", "calmar", "turnover", "trade_count",
    ]
    table = ranked[columns].to_markdown(index=False)
    text = f"""# Baseline 回测结果

数据区间：{bars['timestamp'].min().date()} 至 {bars['timestamp'].max().date()}  
频率：日线；价格：{source_label}；初始资金：1,000,000 元。  
固定样本：{', '.join(sorted(bars['symbol'].unique()))}。

交易假设：信号产生于收盘，下一交易日开盘成交；买入按 100 股取整；股票 T+1；佣金
0.03%、最低 5 元；卖出印花税 0.05%；双边滑点 0.02%。

{table}

## 解释边界

- 股票池是事后选定的固定样本，存在幸存者偏差，结果不能视为可投资收益承诺。
- 当前尚未模拟涨跌停、停牌无法成交、冲击成本、分红现金流和容量约束。
- `equal_weight` 是本样本的被动基准；单股票结果用于验证策略行为，不用于横向选股结论。
- `xs_momentum_60_top2_monthly` 每月首个交易日按过去 60 个交易日收益选前两名。
- Sharpe 使用 0 无风险利率；turnover 为全区间成交额除以平均权益，未做年化。
"""
    output.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run baseline strategies")
    parser.add_argument("--data", default="data/market/akshare_sina/stock/1d")
    parser.add_argument("--output", default="reports/baseline")
    parser.add_argument("--markdown", default="BASELINE_RESULTS.md")
    parser.add_argument("--source-label", default="AKShare 新浪日线前复权")
    args = parser.parse_args()

    files = sorted(Path(args.data).glob("*.parquet"))
    if not files:
        raise SystemExit(f"no parquet files found in {args.data}")
    bars = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True)
    bars = bars.sort_values(["timestamp", "symbol"]).reset_index(drop=True)

    output = Path(args.output)
    equity_dir = output / "equity"
    trades_dir = output / "trades"
    equity_dir.mkdir(parents=True, exist_ok=True)
    trades_dir.mkdir(parents=True, exist_ok=True)

    engine = PortfolioEngine(BacktestConfig(initial_cash=1_000_000, annualization=252))
    rows = []

    for symbol, one in bars.groupby("symbol", sort=True):
        definitions = {
            "buy_hold": buy_and_hold_weights(one),
            "sma_20_100": moving_average_weights(one, fast=20, slow=100),
            "ts_momentum_60": time_series_momentum_weights(one, lookback=60),
        }
        for strategy, weights in definitions.items():
            name = f"{strategy}__{symbol}"
            row, result = run_one(engine, name, symbol, one, weights)
            rows.append(row)
            result.equity.to_parquet(equity_dir / f"{name}.parquet")
            result.trades.to_parquet(trades_dir / f"{name}.parquet", index=False)

    portfolio_definitions = {
        "equal_weight": equal_weight_weights(bars),
        "trend_equal_100_monthly": trend_equal_weight_weights(
            bars, window=100, rebalance="monthly"
        ),
        "xs_momentum_60_top2_monthly": cross_sectional_momentum_weights(
            bars, lookback=60, top_n=2
        ),
    }
    for name, weights in portfolio_definitions.items():
        row, result = run_one(engine, name, "portfolio", bars, weights)
        rows.append(row)
        result.equity.to_parquet(equity_dir / f"{name}.parquet")
        result.trades.to_parquet(trades_dir / f"{name}.parquet", index=False)

    summary = pd.DataFrame(rows).sort_values(["scope", "strategy"]).reset_index(drop=True)
    summary.to_csv(output / "summary.csv", index=False, encoding="utf-8-sig")
    write_markdown(summary, bars, Path(args.markdown), args.source_label)
    print(summary.sort_values("sharpe", ascending=False).to_string(index=False))
    print(f"\nSaved {len(summary)} runs to {output}")


if __name__ == "__main__":
    main()
