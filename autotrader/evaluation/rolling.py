"""Rolling-window evaluation built on the existing portfolio engine."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

import pandas as pd

from autotrader.backtest.engine import BacktestConfig, PortfolioEngine
from autotrader.data.schema import normalize_bars

WeightFactory = Callable[[pd.DataFrame, pd.Timestamp, pd.Timestamp], pd.DataFrame]

DEFAULT_WINDOW_MONTHS = (1, 3, 6, 12, 36)
DISTRIBUTION_STATS = {
    "mean": lambda values: values.mean(),
    "median": lambda values: values.median(),
    "std": lambda values: values.std(ddof=1),
    "q05": lambda values: values.quantile(0.05),
    "q25": lambda values: values.quantile(0.25),
    "q75": lambda values: values.quantile(0.75),
    "q95": lambda values: values.quantile(0.95),
}
DISTRIBUTION_METRICS = (
    "window_return",
    "annual_return",
    "annual_volatility",
    "max_drawdown",
    "sharpe",
    "sortino",
    "calmar",
    "daily_win_rate",
    "trade_win_rate",
    "trade_count",
    "closed_trade_count",
    "turnover",
    "fees",
    "slippage_cost",
    "financing_cost",
    "total_cost",
    "cost_rate",
)


@dataclass(frozen=True)
class RollingWindowConfig:
    window_months: tuple[int, ...] = DEFAULT_WINDOW_MONTHS
    step_months: int = 1
    min_bars: int = 2

    def __post_init__(self) -> None:
        if not self.window_months or any(months <= 0 for months in self.window_months):
            raise ValueError("window_months must contain positive integers")
        if self.step_months <= 0:
            raise ValueError("step_months must be positive")
        if self.min_bars < 2:
            raise ValueError("min_bars must be at least 2")


@dataclass
class RollingBacktestResult:
    windows: pd.DataFrame
    summary: pd.DataFrame

    def save_csv(self, detail_path: str, summary_path: str) -> None:
        self.windows.to_csv(detail_path, index=False, encoding="utf-8-sig")
        self.summary.to_csv(summary_path, index=False, encoding="utf-8-sig")


class RollingWindowBacktester:
    """Run independent, terminally-liquidated backtests over calendar windows.

    A weight factory receives history only through the current window end and
    may use pre-window rows for indicator warm-up. Factories must be causal:
    every weight at time ``t`` may depend only on rows at or before ``t``.
    Orders retain the engine's one-bar execution delay.
    """

    def __init__(
        self,
        backtest_config: BacktestConfig | None = None,
        window_config: RollingWindowConfig | None = None,
    ) -> None:
        base = backtest_config or BacktestConfig()
        self.backtest_config = replace(base, liquidate_at_end=True)
        self.window_config = window_config or RollingWindowConfig()

    def run(
        self,
        bars: pd.DataFrame,
        strategies: Mapping[str, WeightFactory],
    ) -> RollingBacktestResult:
        if not strategies:
            raise ValueError("at least one strategy is required")
        data = normalize_bars(bars)
        windows = self._calendar_windows(data)
        rows: list[dict] = []
        engine = PortfolioEngine(self.backtest_config)

        for months, window_start, window_end in windows:
            window_bars = data[
                data["timestamp"].between(window_start, window_end, inclusive="both")
            ].copy()
            context = data[data["timestamp"] <= window_end].copy()
            available_symbols = set(window_bars["symbol"])
            for strategy_name, factory in strategies.items():
                weights = factory(context, window_start, window_end)
                weights = self._window_weights(
                    weights, window_start, window_end, available_symbols
                )
                result = engine.run(window_bars, weights)
                rows.append(
                    {
                        "strategy": strategy_name,
                        "window_months": months,
                        "window_start": window_start,
                        "window_end": window_end,
                        "bar_count": window_bars["timestamp"].nunique(),
                        "row_count": len(window_bars),
                        "window_return": result.metrics["total_return"],
                        "profitable_window": result.metrics["total_return"] > 0,
                        **{
                            key: value
                            for key, value in result.metrics.items()
                            if key != "total_return"
                        },
                    }
                )

        details = pd.DataFrame(rows).sort_values(
            ["strategy", "window_months", "window_start"]
        ).reset_index(drop=True)
        return RollingBacktestResult(details, summarize_rolling_windows(details))

    def _calendar_windows(
        self, data: pd.DataFrame
    ) -> list[tuple[int, pd.Timestamp, pd.Timestamp]]:
        timestamps = pd.Index(data["timestamp"].drop_duplicates().sort_values())
        first_period = timestamps[0].to_period("M")
        last_period = timestamps[-1].to_period("M")
        start_periods = pd.period_range(first_period, last_period, freq="M")
        completeness_limit = timestamps[-1].normalize() + pd.Timedelta(days=1)
        windows = []
        for months in self.window_config.window_months:
            for start_period in start_periods[:: self.window_config.step_months]:
                start_boundary = start_period.start_time
                end_exclusive = (start_period + months).start_time
                if end_exclusive > completeness_limit:
                    continue
                selected = timestamps[
                    (timestamps >= start_boundary) & (timestamps < end_exclusive)
                ]
                if len(selected) < self.window_config.min_bars:
                    continue
                windows.append((months, pd.Timestamp(selected[0]), pd.Timestamp(selected[-1])))
        return windows

    @staticmethod
    def _window_weights(
        weights: pd.DataFrame,
        window_start: pd.Timestamp,
        window_end: pd.Timestamp,
        available_symbols: set[str],
    ) -> pd.DataFrame:
        required = ["timestamp", "symbol", "weight"]
        if not set(required).issubset(weights.columns):
            raise ValueError(f"weight factory must return columns {required}")
        result = weights[required].copy()
        result["timestamp"] = pd.to_datetime(result["timestamp"])
        result = result[
            result["timestamp"].between(window_start, window_end, inclusive="both")
            & result["symbol"].isin(available_symbols)
        ]
        return result.reset_index(drop=True)


def summarize_rolling_windows(details: pd.DataFrame) -> pd.DataFrame:
    """Create one wide comparison row per strategy and window length."""

    required = {"strategy", "window_months", "profitable_window"}
    if not required.issubset(details.columns):
        raise ValueError(f"details must contain {sorted(required)}")
    rows = []
    for (strategy, months), group in details.groupby(
        ["strategy", "window_months"], sort=True
    ):
        row = {
            "strategy": strategy,
            "window_months": int(months),
            "window_count": int(len(group)),
            "profitable_window_ratio": float(group["profitable_window"].mean()),
        }
        for metric in DISTRIBUTION_METRICS:
            values = pd.to_numeric(group[metric], errors="coerce").dropna()
            for stat_name, function in DISTRIBUTION_STATS.items():
                row[f"{metric}_{stat_name}"] = (
                    float(function(values)) if len(values) else float("nan")
                )
        rows.append(row)
    return pd.DataFrame(rows).sort_values(
        ["window_months", "strategy"]
    ).reset_index(drop=True)
