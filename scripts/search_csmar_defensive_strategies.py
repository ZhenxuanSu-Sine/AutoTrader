"""Search defensive CSMAR daily strategies on total-return bars."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotrader.backtest import BacktestConfig, PortfolioEngine
from autotrader.evaluation.rolling import RollingWindowBacktester, RollingWindowConfig
from autotrader.strategies.high_sharpe import _risk_weights, multifactor_stock_selection_weights
from scripts.run_csmar_strategies import load_bars


def large_cap_low_vol_weights(
    bars: pd.DataFrame,
    *,
    top_n: int = 200,
    liquidity_quantile: float = 0.50,
    cap_quantile: float = 0.50,
    vol_window: int = 60,
    drawdown_window: int = 120,
    trend_window: int = 120,
    minimum_history: int = 252,
    low_vol_weight: float = 0.45,
    cap_weight: float = 0.35,
    drawdown_weight: float = 0.20,
    require_trend: bool = False,
    allocation: str = "cap",
) -> pd.DataFrame:
    data = bars.copy().sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    grouped = data.groupby("symbol", sort=False)
    returns = grouped["close"].pct_change()
    data["volatility"] = (
        returns.groupby(data["symbol"], sort=False)
        .rolling(vol_window, min_periods=vol_window)
        .std()
        .reset_index(level=0, drop=True)
        * (252**0.5)
    )
    rolling_high = grouped["close"].transform(
        lambda values: values.rolling(drawdown_window).max()
    )
    drawdown = data["close"] / rolling_high - 1
    history = grouped["close"].transform(lambda values: values.rolling(minimum_history).count())
    liquidity = grouped["amount"].transform(lambda values: values.rolling(20).mean())
    trend_average = grouped["close"].transform(lambda values: values.rolling(trend_window).mean())

    low_vol_score = data["volatility"].groupby(data["timestamp"]).rank(ascending=False, pct=True)
    cap_score = data["float_market_cap"].groupby(data["timestamp"]).rank(pct=True)
    drawdown_score = drawdown.groupby(data["timestamp"]).rank(pct=True)
    liquidity_rank = liquidity.groupby(data["timestamp"]).rank(pct=True)
    cap_rank = data["float_market_cap"].groupby(data["timestamp"]).rank(pct=True)
    total = low_vol_weight + cap_weight + drawdown_weight
    score = (
        low_vol_score * low_vol_weight
        + cap_score * cap_weight
        + drawdown_score * drawdown_weight
    ) / total
    eligible = (
        (history >= minimum_history)
        & (liquidity_rank >= liquidity_quantile)
        & (cap_rank >= cap_quantile)
        & score.notna()
    )
    if require_trend:
        eligible &= data["close"] > trend_average

    rank = score.where(eligible).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = eligible & (rank <= top_n)

    data["month"] = data["timestamp"].dt.to_period("M")
    rebalance_dates = data.groupby("month")["timestamp"].min()
    data = data[data["timestamp"].isin(rebalance_dates)].copy()
    selected = selected.loc[data.index]
    score = score.loc[data.index]

    if allocation == "cap":
        raw = data["float_market_cap"].where(selected, 0.0).clip(lower=0)
        total_raw = raw.groupby(data["timestamp"]).transform("sum")
        data["weight"] = (raw / total_raw.replace(0, pd.NA)).fillna(0.0)
    elif allocation == "equal":
        count = selected.astype(float).groupby(data["timestamp"]).transform("sum")
        data["weight"] = (selected.astype(float) / count.replace(0, pd.NA)).fillna(0.0)
    elif allocation == "inverse_vol":
        data["weight"] = _risk_weights(
            data,
            score.where(selected, 0.0),
            target_volatility=0.08,
            max_gross=1.0,
        )
    else:
        raise ValueError("allocation must be cap, equal or inverse_vol")
    return data[["timestamp", "symbol", "weight"]]


def iter_candidates(bars: pd.DataFrame):
    for top_n in (50, 100):
        for target in (0.06, 0.08):
            for liquidity in (0.50, 0.60):
                name = f"mf_def_top{top_n}_v{target:.2f}_liq{liquidity:.2f}"
                yield name, multifactor_stock_selection_weights(
                    bars,
                    top_n=top_n,
                    momentum_windows=(20, 60, 120),
                    vol_window=60,
                    drawdown_window=120,
                    liquidity_window=20,
                    liquidity_quantile=liquidity,
                    trend_window=100,
                    minimum_history=252,
                    momentum_weight=0.10,
                    low_vol_weight=0.45,
                    drawdown_weight=0.45,
                    target_volatility=target,
                    rebalance="monthly",
                    max_gross=1.0,
                )
    for top_n in (100, 200, 500):
        for liquidity in (0.40, 0.50):
            for cap_q in (0.60, 0.75):
                for allocation in ("cap",):
                    name = (
                        f"large_lowvol_top{top_n}_liq{liquidity:.2f}"
                        f"_capq{cap_q:.2f}_{allocation}"
                    )
                    yield name, large_cap_low_vol_weights(
                        bars,
                        top_n=top_n,
                        liquidity_quantile=liquidity,
                        cap_quantile=cap_q,
                        allocation=allocation,
                    )
def score(row: pd.Series) -> float:
    drawdown_penalty = max(0.0, abs(row["max_drawdown"]) - 0.20) * 2
    return float(row["sharpe"] + row["annual_return"] - drawdown_penalty)


def main() -> None:
    parser = argparse.ArgumentParser(description="Search defensive CSMAR strategies")
    parser.add_argument("--data", default="data/market/csmar/stock/1d_total_return")
    parser.add_argument("--output", default="reports/csmar_defensive_search")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--max-candidates", type=int, default=20)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    bars = load_bars(args.data)
    engine = PortfolioEngine(BacktestConfig(initial_cash=1_000_000))
    rows = []
    viable = {}
    print(f"Screening up to {args.max_candidates} candidates...", flush=True)
    for number, (name, weights) in enumerate(iter_candidates(bars), start=1):
        if number > args.max_candidates:
            break
        result = engine.run(bars, weights)
        row = {"strategy": name, **result.metrics}
        row["score"] = score(pd.Series(row))
        rows.append(row)
        viable[name] = weights
        print(f"{number} {name}: sharpe={row['sharpe']:.3f}", flush=True)
    screen = pd.DataFrame(rows).sort_values("score", ascending=False)
    screen.to_csv(output / "full_period_screen.csv", index=False, encoding="utf-8-sig")

    selected = screen.head(args.top)["strategy"].tolist()
    factories = {
        name: (lambda context, start, end, frame=viable[name]: frame[frame["timestamp"] <= end])
        for name in selected
    }
    rolling = RollingWindowBacktester(
        BacktestConfig(initial_cash=1_000_000),
        RollingWindowConfig((12, 36), step_months=6),
    ).run(bars, factories)
    rolling.windows.to_csv(output / "rolling_windows.csv", index=False, encoding="utf-8-sig")
    rolling.summary.to_csv(output / "rolling_summary.csv", index=False, encoding="utf-8-sig")
    comparison = screen.merge(
        rolling.summary[
            [
                "strategy",
                "window_months",
                "window_return_median",
                "window_return_q05",
                "sharpe_median",
                "max_drawdown_median",
                "profitable_window_ratio",
            ]
        ],
        on="strategy",
        how="inner",
    )
    comparison.to_csv(output / "comparison.csv", index=False, encoding="utf-8-sig")
    print(
        screen[
            ["strategy", "annual_return", "sharpe", "max_drawdown", "turnover", "score"]
        ].head(args.top).to_string(index=False)
    )
    print(comparison.to_string(index=False))


if __name__ == "__main__":
    main()
