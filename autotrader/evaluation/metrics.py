from __future__ import annotations

import math

import numpy as np
import pandas as pd


def performance_metrics(equity: pd.Series, annualization: int = 252) -> dict[str, float]:
    """Calculate common metrics from a mark-to-market equity curve."""

    values = pd.to_numeric(equity, errors="coerce").dropna()
    if len(values) < 2 or (values <= 0).any():
        raise ValueError("equity must contain at least two positive observations")
    returns = values.pct_change().dropna()
    total_return = float(values.iloc[-1] / values.iloc[0] - 1)
    periods = len(returns)
    annual_return = float((1 + total_return) ** (annualization / periods) - 1)
    volatility = float(returns.std(ddof=1) * math.sqrt(annualization)) if periods > 1 else 0.0
    sharpe = float(returns.mean() / returns.std(ddof=1) * math.sqrt(annualization)) if periods > 1 and returns.std(ddof=1) > 0 else 0.0
    drawdown = values / values.cummax() - 1
    return {
        "total_return": total_return,
        "annual_return": annual_return,
        "annual_volatility": volatility,
        "sharpe": sharpe,
        "max_drawdown": float(drawdown.min()),
        "final_equity": float(values.iloc[-1]),
    }


def closed_trade_metrics(trades: pd.DataFrame) -> dict[str, float]:
    """Calculate win rate from completed long-position episodes."""

    if trades.empty:
        return {"closed_trade_count": 0.0, "trade_win_rate": float("nan")}
    positions: dict[str, int] = {}
    cash_flows: dict[str, float] = {}
    outcomes: list[float] = []
    ordered = trades.sort_values(["timestamp"], kind="stable")
    for row in ordered.itertuples(index=False):
        symbol = str(row.symbol)
        quantity = int(row.quantity)
        positions.setdefault(symbol, 0)
        cash_flows.setdefault(symbol, 0.0)
        if row.side == "buy":
            positions[symbol] += quantity
            cash_flows[symbol] -= float(row.notional) + float(row.fees)
        else:
            positions[symbol] -= quantity
            cash_flows[symbol] += float(row.notional) - float(row.fees)
            if positions[symbol] == 0:
                outcomes.append(cash_flows[symbol])
                cash_flows[symbol] = 0.0
    return {
        "closed_trade_count": float(len(outcomes)),
        "trade_win_rate": float(np.mean(np.asarray(outcomes) > 0))
        if outcomes
        else float("nan"),
    }


def backtest_metrics(
    equity: pd.Series,
    trades: pd.DataFrame,
    annualization: int = 252,
    financing_cost: float = 0.0,
) -> dict[str, float]:
    """Combine return, risk, execution-cost and trade metrics."""

    metrics = performance_metrics(equity, annualization)
    values = pd.to_numeric(equity, errors="coerce").dropna()
    returns = values.pct_change().dropna()
    downside = returns[returns < 0]
    downside_vol = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    average_equity = float(values.mean())
    notional = float(trades["notional"].sum()) if not trades.empty else 0.0
    fees = float(trades["fees"].sum()) if not trades.empty else 0.0
    slippage = float(trades["slippage_cost"].sum()) if not trades.empty else 0.0
    max_drawdown = metrics["max_drawdown"]
    metrics.update(
        {
            "sortino": float(returns.mean() / downside_vol * math.sqrt(annualization))
            if downside_vol > 0
            else 0.0,
            "calmar": float(metrics["annual_return"] / abs(max_drawdown))
            if max_drawdown < 0
            else 0.0,
            "daily_win_rate": float((returns > 0).mean()) if len(returns) else 0.0,
            "trade_count": float(len(trades)),
            "turnover": notional / average_equity if average_equity > 0 else 0.0,
            "fees": fees,
            "slippage_cost": slippage,
            "financing_cost": float(financing_cost),
            "total_cost": fees + slippage + financing_cost,
            "cost_rate": (fees + slippage + financing_cost) / average_equity
            if average_equity > 0
            else 0.0,
            **closed_trade_metrics(trades),
        }
    )
    return metrics
