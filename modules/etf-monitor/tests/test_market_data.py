"""Fixture-only tests for public parsing and snapshot validation."""

from __future__ import annotations

import json
import sys
import unittest
from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "market"
sys.path.insert(0, str(MODULE_ROOT))

from src.market_data import (  # noqa: E402
    MarketDataError,
    collect_market_snapshot,
    parse_eastmoney_bars,
    parse_eastmoney_quote,
    parse_tencent_quote,
)


def _fixture(name: str):
    return json.loads((FIXTURE_ROOT / name).read_text(encoding="utf-8"))


class FixtureProvider:
    def __init__(self) -> None:
        fixture = _fixture("valid_market.json")
        self.as_of = datetime.fromisoformat(fixture["as_of"])
        self.timestamp = datetime.fromisoformat(fixture["source_timestamp"])
        start = date.fromisoformat(fixture["dates_start"])
        self.quotes = [
            {
                "source": "eastmoney",
                "price": 10.400,
                "previous_close": 10.360,
                "turnover_cny": fixture["latest_turnover_cny"],
                "timestamp": self.timestamp,
            },
            {
                "source": "tencent",
                "price": 10.401,
                "previous_close": 10.360,
                "turnover_cny": fixture["latest_turnover_cny"],
                "timestamp": self.timestamp,
            },
        ]
        self.bars = []
        self.benchmark = []
        for offset, close in enumerate(fixture["closes"]):
            latest = offset == len(fixture["closes"]) - 1
            self.bars.append(
                {
                    "date": start + timedelta(days=offset),
                    "open": close - 0.02,
                    "close": close,
                    "high": close + 0.02,
                    "low": close - 0.02,
                    "volume": fixture["latest_volume"] if latest else fixture["volume"],
                    "turnover_cny": fixture["latest_turnover_cny"] if latest else fixture["turnover_cny"],
                    "source": "eastmoney",
                    "timestamp": self.timestamp,
                }
            )
        for offset, close in enumerate(fixture["benchmark_closes"]):
            self.benchmark.append(
                {
                    "date": start + timedelta(days=offset),
                    "open": close,
                    "close": close,
                    "high": close + 0.01,
                    "low": close - 0.01,
                    "volume": 1_000_000,
                    "turnover_cny": 100_000_000,
                    "source": "eastmoney",
                    "timestamp": self.timestamp,
                }
            )
        self.aum = {"value": fixture["aum_cny"], "source": "tencent", "timestamp": self.timestamp}
        self.premium = {"value": fixture["premium_pct"], "source": "tencent", "timestamp": self.timestamp}
        self.calendar = {
            "session_date": self.bars[-1]["date"],
            "is_trading_session": True,
            "source": "exchange_calendar",
            "timestamp": self.timestamp,
        }
        self.catalyst = {
            "primary_confirmed": True,
            "corroborated": True,
            "adverse": False,
            "source": "primary+independent",
            "timestamp": self.timestamp,
        }

    def get_current_quotes(self, code):
        return deepcopy(self.quotes)

    def get_daily_bars(self, code):
        return deepcopy(self.bars)

    def get_aum(self, code):
        return deepcopy(self.aum)

    def get_premium(self, code):
        return deepcopy(self.premium)

    def get_benchmark_bars(self, benchmark):
        return deepcopy(self.benchmark)

    def get_trading_calendar(self, session_date):
        return deepcopy(self.calendar)

    def get_catalyst(self, code):
        return deepcopy(self.catalyst)


class MarketDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FixtureProvider()
        self.record = {"code": "510300", "market": "CN", "tracking_index": "000300"}

    def test_public_endpoint_parsers_apply_documented_units_and_timestamps(self) -> None:
        eastmoney = parse_eastmoney_quote(
            _fixture("eastmoney_quote.json"), self.provider.timestamp
        )
        fields = [""] * 83
        for index, value in _fixture("tencent_quote.json")["fields"].items():
            fields[int(index)] = value
        tencent = parse_tencent_quote('v_sh510300="' + "~".join(fields) + '";')
        bars = parse_eastmoney_bars(
            _fixture("eastmoney_bars.json"), self.provider.timestamp
        )

        self.assertEqual(10.4, eastmoney.price)
        self.assertEqual(75_000_000, eastmoney.turnover_cny)
        self.assertEqual(10.401, tencent.price)
        self.assertEqual(3_500_000_000, tencent.aum_cny)
        self.assertEqual(0.4, tencent.premium_pct)
        self.assertEqual(self.provider.timestamp, tencent.timestamp)
        self.assertEqual(75_000_000, bars[-1].turnover_cny)

    def test_snapshot_accepts_complete_fresh_agreeing_fixture_data(self) -> None:
        snapshot = collect_market_snapshot(
            self.record, self.provider, as_of=self.provider.as_of
        )

        self.assertEqual("510300", snapshot.code)
        self.assertAlmostEqual(10.4005, snapshot.current_price)
        self.assertEqual(61, len(snapshot.bars))
        self.assertEqual(self.provider.timestamp, snapshot.source_timestamp)

    def test_snapshot_rejects_prices_disagreeing_by_more_than_point_three_percent(self) -> None:
        self.provider.quotes[1]["price"] = 10.45

        with self.assertRaisesRegex(MarketDataError, "quote_price_conflict"):
            collect_market_snapshot(self.record, self.provider, as_of=self.provider.as_of)

    def test_snapshot_rejects_stale_and_missing_data(self) -> None:
        stale = FixtureProvider()
        stale.quotes[0]["timestamp"] = stale.as_of - timedelta(minutes=16)
        with self.assertRaisesRegex(MarketDataError, "stale_quote"):
            collect_market_snapshot(self.record, stale, as_of=stale.as_of)

        missing = FixtureProvider()
        missing.aum = None
        with self.assertRaisesRegex(MarketDataError, "missing_aum"):
            collect_market_snapshot(self.record, missing, as_of=missing.as_of)

    def test_snapshot_rejects_holidays_and_conflicting_session_dates(self) -> None:
        self.provider.calendar["is_trading_session"] = False
        with self.assertRaisesRegex(MarketDataError, "not_trading_session"):
            collect_market_snapshot(self.record, self.provider, as_of=self.provider.as_of)

        conflict = FixtureProvider()
        conflict.calendar["session_date"] = conflict.bars[-1]["date"] - timedelta(days=1)
        with self.assertRaisesRegex(MarketDataError, "session_date_conflict"):
            collect_market_snapshot(self.record, conflict, as_of=conflict.as_of)


if __name__ == "__main__":
    unittest.main()
