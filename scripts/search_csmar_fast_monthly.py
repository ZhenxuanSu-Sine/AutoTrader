"""Fast monthly strategy search on precomputed CSMAR features.

The first pass uses close-to-close matrix returns for speed and ignores costs.
Top candidates are then exported as target weights for exact PortfolioEngine
confirmation in a separate step or by this script's confirmation stage.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autotrader.backtest import BacktestConfig, PortfolioEngine
from scripts.run_csmar_strategies import load_bars


def approx_metrics(returns: pd.Series) -> dict[str, float]:
    returns = returns.fillna(0.0)
    equity = (1 + returns).cumprod()
    total = float(equity.iloc[-1] - 1)
    annual = float(equity.iloc[-1] ** (252 / len(equity)) - 1)
    vol = float(returns.std(ddof=1) * np.sqrt(252))
    dd = equity / equity.cummax() - 1
    return {
        "approx_total_return": total,
        "approx_annual_return": annual,
        "approx_volatility": vol,
        "approx_sharpe": annual / vol if vol > 0 else 0.0,
        "approx_max_drawdown": float(dd.min()),
    }


def monthly_weights(
    features: pd.DataFrame,
    *,
    top_n: int,
    score: pd.Series,
    eligible: pd.Series,
    allocation: str,
) -> pd.DataFrame:
    data = features[["timestamp", "symbol", "float_market_cap", "vol_60"]].copy()
    data["score"] = score
    data["eligible"] = eligible
    rank = data["score"].where(data["eligible"]).groupby(data["timestamp"]).rank(
        ascending=False, method="first"
    )
    selected = data["eligible"] & (rank <= top_n)
    if allocation == "equal":
        raw = selected.astype(float)
    elif allocation == "cap":
        raw = data["float_market_cap"].where(selected, 0.0).clip(lower=0)
    elif allocation == "inverse_vol":
        raw = (1 / data["vol_60"].replace(0, pd.NA)).where(selected, 0.0)
    else:
        raise ValueError("allocation must be equal, cap or inverse_vol")
    total = raw.groupby(data["timestamp"]).transform("sum")
    data["weight"] = (raw / total.replace(0, pd.NA)).fillna(0.0)
    return data[["timestamp", "symbol", "weight"]]


def candidate_specs(features: pd.DataFrame):
    base = (features["history"] >= 252) & features["liquidity_20_rank"].notna()
    for top_n in (50, 100, 200, 500):
        for liq in (0.4, 0.6, 0.75):
            for capq in (0.4, 0.6, 0.75):
                eligible = base & (features["liquidity_20_rank"] >= liq) & (
                    features["float_market_cap_rank"] >= capq
                )
                score = (
                    0.55 * features["vol_60_rank"]
                    + 0.25 * features["drawdown_120_rank"]
                    + 0.20 * features["float_market_cap_rank"]
                )
                for allocation in ("cap", "inverse_vol", "equal"):
                    yield (
                        f"def_top{top_n}_liq{liq:.2f}_capq{capq:.2f}_{allocation}",
                        top_n,
                        score,
                        eligible,
                        allocation,
                    )
    for top_n in (50, 100, 200):
        for liq in (0.5, 0.7):
            eligible = base & (features["liquidity_20_rank"] >= liq) & (
                features["ret_120"] > 0
            )
            score = (
                0.45 * (1 - features["ret_20_rank"])
                + 0.25 * features["ret_120_rank"]
                + 0.20 * features["vol_60_rank"]
                + 0.10 * features["float_market_cap_rank"]
            )
            for allocation in ("equal", "inverse_vol"):
                yield (
                    f"rev20_trend120_top{top_n}_liq{liq:.2f}_{allocation}",
                    top_n,
                    score,
                    eligible,
                    allocation,
                )


def weights_to_matrix(weights: pd.DataFrame, dates: pd.Index, symbols: pd.Index) -> pd.DataFrame:
    monthly = weights.pivot(index="timestamp", columns="symbol", values="weight").reindex(
        columns=symbols, fill_value=0.0
    )
    daily = monthly.reindex(dates).ffill().shift(1).fillna(0.0)
    return daily


def main() -> None:
    parser = argparse.ArgumentParser(description="Fast CSMAR monthly strategy search")
    parser.add_argument("--data", default="data/market/csmar/stock/1d_total_return")
    parser.add_argument("--features", default="data/features/csmar/monthly_price_volume.parquet")
    parser.add_argument("--output", default="reports/csmar_fast_monthly_search")
    parser.add_argument("--top", type=int, default=8)
    parser.add_argument("--max-candidates", type=int, default=140)
    parser.add_argument("--confirm", type=int, default=5)
    args = parser.parse_args()

    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    print("Loading bars and features...", flush=True)
    bars = load_bars(args.data)
    features = pd.read_parquet(args.features)
    dates = pd.Index(sorted(bars["timestamp"].unique()))
    symbols = pd.Index(sorted(bars["symbol"].unique()))
    returns = (
        bars.pivot(index="timestamp", columns="symbol", values="close")
        .reindex(index=dates, columns=symbols)
        .pct_change()
        .fillna(0.0)
    )

    rows = []
    saved_weights: dict[str, pd.DataFrame] = {}
    for number, (name, top_n, score, eligible, allocation) in enumerate(
        candidate_specs(features), start=1
    ):
        if number > args.max_candidates:
            break
        weights = monthly_weights(
            features,
            top_n=top_n,
            score=score,
            eligible=eligible,
            allocation=allocation,
        )
        daily = weights_to_matrix(weights, dates, symbols)
        port_ret = (daily * returns).sum(axis=1)
        row = {"strategy": name, **approx_metrics(port_ret)}
        rows.append(row)
        saved_weights[name] = weights[weights["weight"] > 0].copy()
        if number % 20 == 0:
            print(f"screened {number}", flush=True)

    screen = pd.DataFrame(rows).sort_values("approx_sharpe", ascending=False)
    screen.to_csv(output / "approx_screen.csv", index=False, encoding="utf-8-sig")
    print(screen.head(args.top).to_string(index=False))

    engine_rows = []
    engine = PortfolioEngine(BacktestConfig(initial_cash=1_000_000))
    for name in screen.head(args.confirm)["strategy"]:
        print(f"Confirming {name} with PortfolioEngine...", flush=True)
        result = engine.run(bars, saved_weights[name])
        engine_rows.append({"strategy": name, **result.metrics})
        saved_weights[name].to_csv(output / f"weights_{name}.csv", index=False, encoding="utf-8-sig")
    confirmed = pd.DataFrame(engine_rows).sort_values("sharpe", ascending=False)
    confirmed.to_csv(output / "confirmed.csv", index=False, encoding="utf-8-sig")
    print(confirmed.to_string(index=False))


if __name__ == "__main__":
    main()
