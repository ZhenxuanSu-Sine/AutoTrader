"""Evaluate the selected high-Sharpe candidates against equal weight."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies import equal_weight_weights
from autotrader.strategies.high_sharpe import (
    blend_weights,
    breadth_regime_weights,
    defensive_composite_weights,
    dual_momentum_rotation_weights,
    multi_horizon_trend_weights,
)


def selected_candidates(bars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    trend = multi_horizon_trend_weights(
        bars,
        horizons=(20, 60),
        vol_window=20,
        target_volatility=0.08,
        rebalance="weekly",
    )
    dual = dual_momentum_rotation_weights(
        bars,
        lookback=20,
        trend_window=100,
        top_n=2,
        vol_window=20,
        target_volatility=0.15,
        rebalance="monthly",
    )
    defensive = defensive_composite_weights(
        bars,
        momentum_windows=(60, 120),
        trend_window=100,
        top_n=3,
        target_volatility=0.15,
        rebalance="monthly",
    )
    breadth = breadth_regime_weights(
        bars,
        trend_window=100,
        breadth_threshold=0.8,
        vol_window=20,
        target_volatility=0.15,
        rebalance="monthly",
    )
    ensemble = blend_weights(trend, dual, defensive, breadth)
    return {
        "trend_20_60_vol08_weekly": trend,
        "dual_momentum_20_top2_vol15": dual,
        "breadth_80_vol15_monthly": breadth,
        "ensemble_trend_dual_defensive_breadth": ensemble,
    }


def compact_summary(summary: pd.DataFrame, full: pd.DataFrame) -> pd.DataFrame:
    selected = summary[
        [
            "strategy", "window_months", "window_count", "profitable_window_ratio",
            "window_return_median", "window_return_q05", "window_return_q95",
            "sharpe_median", "sharpe_q25", "max_drawdown_median", "turnover_median",
            "total_cost_median",
        ]
    ]
    return selected.merge(full, on="strategy", how="left").sort_values(
        ["window_months", "sharpe_median"], ascending=[True, False]
    )


def write_markdown(table: pd.DataFrame, output: Path) -> None:
    display = table.copy()
    for column in [
        "profitable_window_ratio", "window_return_median", "window_return_q05",
        "window_return_q95", "max_drawdown_median", "full_annual_return",
        "full_max_drawdown",
    ]:
        display[column] = display[column].map(lambda value: f"{value:.2%}")
    columns = [
        "strategy", "window_months", "window_count", "profitable_window_ratio",
        "window_return_median", "window_return_q05", "sharpe_median",
        "sharpe_q25", "max_drawdown_median", "turnover_median",
    ]
    output.write_text(
        "# High-Sharpe 候选策略\n\n"
        "以下参数在同一份 2015-2026 固定股票池上筛选并评测，属于明确的样本内结果。"
        "目标是提高滚动 Sharpe，不代表未来表现。所有候选均为长仓、不加杠杆、CPU 计算。\n\n"
        "## 候选设计\n\n"
        "- `trend_20_60_vol08_weekly`：20/60日多周期趋势，逆波动配置，8%目标波动，周调仓。\n"
        "- `dual_momentum_20_top2_vol15`：绝对趋势过滤后选20日相对动量前两名。\n"
        "- `breadth_80_vol15_monthly`：至少80%股票位于100日均线上方才承担风险。\n"
        "- `ensemble_*`：趋势、双动量、防御复合和市场宽度四模型平均。\n\n"
        "研究依据包括 Time Series Momentum、Volatility-Managed Portfolios 和 Faber Tactical "
        "Asset Allocation；本实现是适配当前A股样本的工程变体，不是论文原样复刻。\n\n"
        + display[columns].to_markdown(index=False)
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate selected high-Sharpe candidates")
    parser.add_argument("--data", default="data/market/akshare_sina/stock/1d")
    parser.add_argument("--output", default="reports/high_sharpe_candidates")
    parser.add_argument("--markdown", default="HIGH_SHARPE_CANDIDATES.md")
    parser.add_argument("--step-months", type=int, default=1)
    args = parser.parse_args()

    files = sorted(Path(args.data).glob("*.parquet"))
    if not files:
        raise SystemExit(f"no parquet files found in {args.data}")
    bars = pd.concat([pd.read_parquet(path) for path in files], ignore_index=True).sort_values(
        ["timestamp", "symbol"]
    ).reset_index(drop=True)
    candidates = selected_candidates(bars)

    fixed_weights = {"equal_weight": equal_weight_weights(bars), **candidates}
    engine = PortfolioEngine(BacktestConfig(initial_cash=1_000_000))
    full_rows = []
    for name, weights in fixed_weights.items():
        metrics = engine.run(bars, weights).metrics
        full_rows.append(
            {
                "strategy": name,
                "full_sharpe": metrics["sharpe"],
                "full_annual_return": metrics["annual_return"],
                "full_max_drawdown": metrics["max_drawdown"],
                "full_turnover": metrics["turnover"],
            }
        )
    full = pd.DataFrame(full_rows)

    def equal_factory(context, start, end):
        current = context[context["timestamp"].between(start, end, inclusive="both")]
        return equal_weight_weights(current)

    factories = {"equal_weight": equal_factory}
    factories.update(
        {
            name: (lambda context, start, end, frame=frame: frame[frame["timestamp"] <= end])
            for name, frame in candidates.items()
        }
    )
    print("Running selected candidates through full rolling evaluation...", flush=True)
    rolling = RollingWindowBacktester(
        BacktestConfig(initial_cash=1_000_000),
        RollingWindowConfig((1, 3, 6, 12, 36), step_months=args.step_months),
    ).run(bars, factories)

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    rolling.windows.to_csv(output / "windows.csv", index=False, encoding="utf-8-sig")
    rolling.summary.to_csv(output / "summary.csv", index=False, encoding="utf-8-sig")
    table = compact_summary(rolling.summary, full)
    table.to_csv(output / "comparison.csv", index=False, encoding="utf-8-sig")
    write_markdown(table, Path(args.markdown))
    print(table.to_string(index=False))


if __name__ == "__main__":
    main()
