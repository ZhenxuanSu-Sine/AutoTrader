"""Small domain objects shared by data, research and execution layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class AssetType(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    FUND = "fund"
    FUTURE = "future"
    METAL = "metal"


class BarFrequency(str, Enum):
    MIN_1 = "1min"
    MIN_5 = "5min"
    MIN_15 = "15min"
    MIN_30 = "30min"
    HOUR_1 = "1h"
    DAY_1 = "1d"


@dataclass(frozen=True)
class CostModel:
    """Simplified mainland stock transaction costs.

    Rates are fractions of notional. Stamp duty is charged only on sells.
    The defaults are intentionally configurable rather than claims about the
    current fee schedule.
    """

    commission_rate: float = 0.0003
    minimum_commission: float = 5.0
    stamp_duty_rate: float = 0.0005
    slippage_rate: float = 0.0002

    def __post_init__(self) -> None:
        for name in ("commission_rate", "minimum_commission", "stamp_duty_rate", "slippage_rate"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    def commission(self, notional: float) -> float:
        return 0.0 if notional <= 0 else max(notional * self.commission_rate, self.minimum_commission)

    def buy_cash_required(self, price: float, quantity: int) -> float:
        notional = price * quantity
        return notional + self.commission(notional)

    def sell_cash_received(self, price: float, quantity: int) -> float:
        notional = price * quantity
        return notional - self.commission(notional) - notional * self.stamp_duty_rate

