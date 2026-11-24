import unittest
from datetime import datetime, timedelta, timezone

from autotrader.gold import BankQuote, GoldAdvisor, GoldConfig, Portfolio


NOW = datetime(2026, 11, 24, tzinfo=timezone.utc)


def quote(bank="兴业", buy=900, sell=896, timestamp=NOW):
    return BankQuote(bank, timestamp, buy, sell)


class GoldAdvisorTests(unittest.TestCase):
    def setUp(self):
        self.advisor = GoldAdvisor()

    def test_spread_cost(self):
        q = quote()
        self.assertAlmostEqual(q.round_trip_cost_rate, 4 / 900)

    def test_buy_selects_lowest_cost_bank(self):
        signal = self.advisor.advise(
            Portfolio(20_000, 0), [quote(), quote("浙商", 900, 899)], 0.5, NOW)
        self.assertEqual(signal.action, "BUY")
        self.assertEqual(signal.bank, "浙商")
        self.assertAlmostEqual(signal.grams, 10_000 / 900)

    def test_hard_limit_exits(self):
        signal = self.advisor.advise(
            Portfolio(1000, 20, "兴业"), [quote(sell=690)], 0.8, NOW)
        self.assertEqual(signal.action, "SELL")
        self.assertEqual(signal.grams, 20)

    def test_stale_held_quote_blocks_signal(self):
        signal = self.advisor.advise(
            Portfolio(1000, 20, "兴业"),
            [quote(timestamp=NOW - timedelta(hours=1))], 0.8, NOW)
        self.assertEqual(signal.action, "NO_DATA")

    def test_no_implicit_bank_switch(self):
        signal = self.advisor.advise(
            Portfolio(10_000, 10, "兴业"),
            [quote(), quote("浙商", 900, 899)], 0.7, NOW)
        self.assertEqual(signal.bank, "兴业")

    def test_invalid_quote(self):
        with self.assertRaises(ValueError):
            quote(buy=890, sell=900)

    def test_defense_prevents_new_buy(self):
        signal = self.advisor.advise(
            Portfolio(3000, 15, "兴业"), [quote(sell=850)], 0.8, NOW)
        self.assertEqual(signal.action, "SELL")


if __name__ == "__main__":
    unittest.main()
