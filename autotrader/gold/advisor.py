"""Manual-execution gold accumulation signals.

All quotes are CNY per gram. A quote is an executable bank-side bid/ask
snapshot, not a spot-market mid-price. No network or trading APIs are used.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import isfinite

BANKS = frozenset({"兴业", "浙商", "民生", "广发"})


@dataclass(frozen=True)
class BankQuote:
    bank: str
    timestamp: datetime
    buy: float  # customer pays to acquire 1 gram
    sell: float  # customer receives for selling 1 gram
    buy_fee_rate: float = 0.0
    sell_fee_rate: float = 0.0

    def __post_init__(self):
        if self.bank not in BANKS:
            raise ValueError("unsupported bank")
        if self.timestamp.tzinfo is None or self.timestamp.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        if any(not isfinite(x) for x in (self.buy, self.sell, self.buy_fee_rate, self.sell_fee_rate)):
            raise ValueError("non-finite quote")
        if self.buy <= 0 or self.sell <= 0 or self.buy < self.sell:
            raise ValueError("invalid buy/sell quote")
        if not (0 <= self.buy_fee_rate < 1 and 0 <= self.sell_fee_rate < 1):
            raise ValueError("invalid fee rate")

    @property
    def acquisition_cost(self) -> float:
        return self.buy * (1 + self.buy_fee_rate)

    @property
    def liquidation_proceeds(self) -> float:
        return self.sell * (1 - self.sell_fee_rate)

    @property
    def round_trip_cost_rate(self) -> float:
        return 1 - self.liquidation_proceeds / self.acquisition_cost


@dataclass(frozen=True)
class Portfolio:
    cash: float
    grams: float
    bank: str | None = None

    def __post_init__(self):
        if not isfinite(self.cash) or not isfinite(self.grams) or min(self.cash, self.grams) < 0:
            raise ValueError("cash and grams must be finite and nonnegative")
        if self.grams > 0 and self.bank not in BANKS:
            raise ValueError("held gold requires its bank")


@dataclass(frozen=True)
class GoldConfig:
    initial_capital: float = 20_000
    max_loss_fraction: float = 0.25
    warning_fraction: float = 0.15
    defense_fraction: float = 0.20
    max_weight: float = 0.80
    min_trade_cny: float = 100
    quote_max_age_seconds: int = 300

    def __post_init__(self):
        if self.initial_capital <= 0 or not 0 < self.warning_fraction < self.defense_fraction < self.max_loss_fraction < 1:
            raise ValueError("invalid loss limits")
        if not 0 < self.max_weight <= 1 or self.min_trade_cny < 0 or self.quote_max_age_seconds <= 0:
            raise ValueError("invalid trading limits")


@dataclass(frozen=True)
class GoldSignal:
    action: str
    bank: str | None
    grams: float
    equity: float
    target_weight: float
    reason: str


class GoldAdvisor:
    def __init__(self, config: GoldConfig = GoldConfig()):
        self.config = config

    def advise(self, portfolio: Portfolio, quotes: list[BankQuote], target_weight: float,
               now: datetime | None = None) -> GoldSignal:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")
        if not isfinite(target_weight) or not 0 <= target_weight <= 1:
            raise ValueError("target_weight must be in [0, 1]")
        valid = {q.bank: q for q in quotes
                 if 0 <= (now - q.timestamp).total_seconds() <= self.config.quote_max_age_seconds}
        held = valid.get(portfolio.bank) if portfolio.grams else None
        if portfolio.grams and held is None:
            return GoldSignal("NO_DATA", portfolio.bank, 0, portfolio.cash, 0,
                              "held bank quote missing/stale; equity cannot be valued safely")
        equity = portfolio.cash + (portfolio.grams * held.liquidation_proceeds if held else 0)
        loss = max(0, 1 - equity / self.config.initial_capital)
        if loss >= self.config.max_loss_fraction:
            return GoldSignal("SELL" if portfolio.grams else "HALT", portfolio.bank,
                              portfolio.grams, equity, 0, "capital loss limit reached; manual exit required")
        if loss >= self.config.defense_fraction:
            target_weight = 0
        elif loss >= self.config.warning_fraction:
            target_weight = min(target_weight, 0.25)
        target_weight = min(target_weight, self.config.max_weight)
        if portfolio.grams:
            # Never switch banks implicitly: switching requires a separate sale and purchase.
            quote = held
        elif valid:
            quote = min(valid.values(), key=lambda q: q.round_trip_cost_rate)
        else:
            return GoldSignal("NO_DATA", None, 0, equity, target_weight, "no fresh bank quotes")
        current_value = portfolio.grams * quote.liquidation_proceeds
        desired_value = equity * target_weight
        delta = desired_value - current_value
        if delta > self.config.min_trade_cny:
            grams = min(portfolio.cash / quote.acquisition_cost,
                        delta / quote.acquisition_cost)
            if grams * quote.acquisition_cost >= self.config.min_trade_cny:
                return GoldSignal("BUY", quote.bank, grams, equity, target_weight,
                                  "rebalance to target; verify Alipay price and trading window")
        if delta < -self.config.min_trade_cny and portfolio.grams:
            grams = min(portfolio.grams, -delta / quote.liquidation_proceeds)
            return GoldSignal("SELL", quote.bank, grams, equity, target_weight,
                              "rebalance to target; verify Alipay price and trading window")
        return GoldSignal("HOLD", quote.bank, 0, equity, target_weight,
                          "change below minimum trade threshold")
