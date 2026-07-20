"""Fixture-only tests for public parsing and snapshot validation."""

from __future__ import annotations

import json
import math
import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "market"
sys.path.insert(0, str(MODULE_ROOT))

from src.market_data import (  # noqa: E402
    CatalystConfirmation,
    DailyBar,
    MarketDataError,
    Quote,
    TimedMetric,
    TradingCalendarState,
    collect_current_quote,
    collect_market_snapshot,
    parse_eastmoney_bars,
    parse_eastmoney_quote,
    parse_tencent_quote,
)
import src.market_data as market_data_module  # noqa: E402


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
        self.benchmark_calendar = {
            "latest_completed_session_date": self.benchmark[-1]["date"],
            "source": "benchmark_exchange_calendar",
            "timestamp": self.timestamp,
        }
        self.benchmark_calendar_calls = []
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
        self.requested_calendar_date = session_date
        return deepcopy(self.calendar)

    def get_benchmark_calendar(self, benchmark, market, as_of_date):
        self.benchmark_calendar_calls.append((benchmark, market, as_of_date))
        return deepcopy(self.benchmark_calendar)

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

    def test_public_bar_parser_rejects_invalid_ohlc(self) -> None:
        payload = _fixture("eastmoney_bars.json")
        fields = payload["data"]["klines"][-1].split(",")
        fields[3] = "10.39"
        payload["data"]["klines"][-1] = ",".join(fields)

        with self.assertRaisesRegex(MarketDataError, "malformed_daily_bar"):
            parse_eastmoney_bars(payload, self.provider.timestamp)

    def test_snapshot_accepts_complete_fresh_agreeing_fixture_data(self) -> None:
        snapshot = collect_market_snapshot(
            self.record, self.provider, as_of=self.provider.as_of
        )

        self.assertEqual("510300", snapshot.code)
        self.assertAlmostEqual(10.4005, snapshot.current_price)
        self.assertEqual(61, len(snapshot.bars))
        self.assertEqual(self.provider.timestamp, snapshot.source_timestamp)
        self.assertEqual(self.provider.calendar["session_date"], snapshot.benchmark_session_date)
        self.assertEqual(self.provider.as_of, snapshot.observed_at)
        self.assertEqual(
            self.provider.calendar["source"], snapshot.benchmark_calendar.source
        )
        self.assertEqual(
            self.provider.calendar["timestamp"], snapshot.benchmark_calendar.timestamp
        )
        self.assertEqual([], self.provider.benchmark_calendar_calls)

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

    def test_typed_quote_validation_rejects_nonfinite_source_and_naive_timestamp(self) -> None:
        valid = Quote(
            source="eastmoney",
            price=10.4,
            previous_close=10.36,
            turnover_cny=75_000_000,
            timestamp=self.provider.timestamp,
        )
        cases = (
            (replace(valid, price=math.nan), "malformed_quote"),
            (replace(valid, source=""), "missing_source"),
            (replace(valid, timestamp=datetime(2026, 7, 20, 15)), "missing_quote_timestamp"),
        )
        for invalid, reason in cases:
            with self.subTest(reason):
                provider = FixtureProvider()
                provider.quotes[0] = invalid
                with self.assertRaisesRegex(MarketDataError, reason):
                    collect_current_quote("510300", provider, as_of=provider.as_of)

    def test_all_other_typed_inputs_are_validated_fail_closed(self) -> None:
        provider = FixtureProvider()
        bar = provider.bars[-1]
        typed_bar = DailyBar(**bar)
        typed_aum = TimedMetric(
            provider.aum["value"], provider.aum["source"], provider.aum["timestamp"]
        )
        typed_calendar = TradingCalendarState(
            provider.calendar["session_date"],
            provider.calendar["is_trading_session"],
            provider.calendar["source"],
            provider.calendar["timestamp"],
        )
        typed_catalyst = CatalystConfirmation(
            provider.catalyst["primary_confirmed"],
            provider.catalyst["corroborated"],
            provider.catalyst["adverse"],
            provider.catalyst["source"],
            provider.catalyst["timestamp"],
        )

        cases = (
            ("bars", replace(typed_bar, high=typed_bar.close - 0.01), "malformed_daily_bar"),
            ("bars", replace(typed_bar, volume=math.inf), "malformed_daily_bar"),
            ("aum", replace(typed_aum, value=math.nan), "malformed_metric"),
            ("calendar", replace(typed_calendar, is_trading_session=1), "malformed_trading_calendar"),
            ("catalyst", replace(typed_catalyst, primary_confirmed=1), "malformed_catalyst"),
        )
        for field, invalid, reason in cases:
            with self.subTest(field=field, reason=reason):
                candidate = FixtureProvider()
                if field == "bars":
                    candidate.bars[-1] = invalid
                else:
                    setattr(candidate, field, invalid)
                with self.assertRaisesRegex(MarketDataError, reason):
                    collect_market_snapshot(self.record, candidate, as_of=candidate.as_of)

    def test_typed_and_mapping_premium_allow_finite_discounts_but_aum_stays_nonnegative(self) -> None:
        for typed in (False, True):
            with self.subTest(typed=typed):
                provider = FixtureProvider()
                provider.premium = (
                    TimedMetric(-0.25, "tencent", provider.timestamp)
                    if typed
                    else {"value": -0.25, "source": "tencent", "timestamp": provider.timestamp}
                )
                snapshot = collect_market_snapshot(
                    self.record, provider, as_of=provider.as_of
                )
                self.assertEqual(-0.25, snapshot.premium_pct)

        provider = FixtureProvider()
        provider.aum = TimedMetric(-1, "tencent", provider.timestamp)
        with self.assertRaisesRegex(MarketDataError, "malformed_metric"):
            collect_market_snapshot(self.record, provider, as_of=provider.as_of)

    def test_previous_close_and_turnover_conflicts_fail_closed(self) -> None:
        cases = (
            ("previous_close", 10.40, "quote_previous_close_conflict"),
            ("turnover_cny", 95_000_000, "quote_turnover_conflict"),
        )
        for field, value, reason in cases:
            with self.subTest(field):
                provider = FixtureProvider()
                provider.quotes[1][field] = value
                with self.assertRaisesRegex(MarketDataError, reason):
                    collect_current_quote("510300", provider, as_of=provider.as_of)

    def test_as_of_uses_shanghai_date_and_calendar_must_match_it(self) -> None:
        as_of_utc = datetime(2026, 7, 20, 16, 5, tzinfo=timezone.utc)

        with self.assertRaisesRegex(MarketDataError, "session_date_conflict"):
            collect_market_snapshot(self.record, self.provider, as_of=as_of_utc)

        self.assertEqual(date(2026, 7, 21), self.provider.requested_calendar_date)

    def test_public_trading_session_normalizes_shanghai_date_and_returns_closure(self) -> None:
        as_of_utc = datetime(2026, 7, 20, 16, 5, tzinfo=timezone.utc)
        self.provider.calendar.update(
            session_date=date(2026, 7, 21), is_trading_session=False
        )

        state = market_data_module.collect_trading_session(
            self.provider, as_of=as_of_utc
        )

        self.assertFalse(state.is_trading_session)
        self.assertEqual(date(2026, 7, 21), state.session_date)
        self.assertEqual(date(2026, 7, 21), self.provider.requested_calendar_date)

    def test_public_trading_session_validates_typed_state(self) -> None:
        self.provider.calendar = TradingCalendarState(
            session_date=self.provider.as_of.date(),
            is_trading_session=False,
            source="exchange_calendar",
            timestamp=self.provider.timestamp,
        )

        state = market_data_module.collect_trading_session(
            self.provider, as_of=self.provider.as_of
        )

        self.assertIsInstance(state, TradingCalendarState)
        self.assertFalse(state.is_trading_session)

    def test_public_trading_session_rejects_stale_conflicting_and_malformed_states(self) -> None:
        cases = []
        stale = FixtureProvider()
        stale.calendar["timestamp"] = stale.as_of - timedelta(hours=25)
        cases.append((stale, "stale_calendar"))
        conflict = FixtureProvider()
        conflict.calendar["session_date"] -= timedelta(days=1)
        cases.append((conflict, "session_date_conflict"))
        malformed = FixtureProvider()
        malformed.calendar["is_trading_session"] = "false"
        cases.append((malformed, "malformed_trading_calendar"))

        for provider, reason in cases:
            with self.subTest(reason):
                with self.assertRaisesRegex(MarketDataError, reason):
                    market_data_module.collect_trading_session(
                        provider, as_of=provider.as_of
                    )

    def test_quote_prices_must_agree_with_latest_and_previous_etf_bars(self) -> None:
        cases = (
            ("price", 10.45, "quote_bar_price_conflict"),
            ("previous_close", 10.40, "previous_close_bar_conflict"),
        )
        for field, value, reason in cases:
            with self.subTest(field):
                provider = FixtureProvider()
                for quote in provider.quotes:
                    quote[field] = value
                with self.assertRaisesRegex(MarketDataError, reason):
                    collect_market_snapshot(
                        self.record, provider, as_of=provider.as_of
                    )

    def test_cross_market_benchmark_may_lag_one_session(self) -> None:
        for market in (
            "US",
            "HK",
            "DE",
            "JP",
            "BR",
            "SEA",
            "CN_KR",
            "CHINA_OFFSHORE",
            "COMMODITY",
        ):
            with self.subTest(market):
                provider = FixtureProvider()
                old_bar = deepcopy(provider.benchmark[0])
                old_bar["date"] -= timedelta(days=1)
                provider.benchmark.pop()
                provider.benchmark.insert(0, old_bar)
                provider.benchmark_calendar["latest_completed_session_date"] = (
                    provider.benchmark[-1]["date"]
                )
                record = dict(self.record, market=market)

                snapshot = collect_market_snapshot(
                    record, provider, as_of=provider.as_of
                )

                self.assertEqual(provider.bars[-1]["date"], snapshot.session_date)
                self.assertEqual(
                    provider.benchmark[-1]["date"], snapshot.benchmark_bars[-1].date
                )
                self.assertEqual(
                    provider.benchmark[-1]["date"], snapshot.benchmark_session_date
                )
                self.assertEqual(
                    [("000300", market, provider.as_of.date())],
                    provider.benchmark_calendar_calls,
                )

    def test_cross_market_benchmark_calendar_rejects_missing_stale_malformed_and_conflicting_data(self) -> None:
        cases = []
        missing = FixtureProvider()
        missing.benchmark_calendar = None
        cases.append((missing, "missing_benchmark_calendar"))

        stale = FixtureProvider()
        stale.benchmark_calendar["timestamp"] = stale.as_of - timedelta(hours=25)
        cases.append((stale, "stale_benchmark_calendar"))

        malformed = FixtureProvider()
        malformed.benchmark_calendar["latest_completed_session_date"] = datetime(
            2026, 7, 20, 0, tzinfo=timezone.utc
        )
        cases.append((malformed, "malformed_benchmark_calendar"))

        missing_source = FixtureProvider()
        missing_source.benchmark_calendar["source"] = ""
        cases.append((missing_source, "missing_source"))

        conflict = FixtureProvider()
        conflict.benchmark_calendar["latest_completed_session_date"] -= timedelta(days=1)
        cases.append((conflict, "benchmark_session_date_conflict"))

        future = FixtureProvider()
        future.benchmark_calendar["latest_completed_session_date"] += timedelta(days=1)
        cases.append((future, "future_benchmark_session"))

        for provider, reason in cases:
            with self.subTest(reason):
                with self.assertRaisesRegex(MarketDataError, reason):
                    collect_market_snapshot(
                        dict(self.record, market="US"),
                        provider,
                        as_of=provider.as_of,
                    )

    def test_freshly_fetched_but_weeks_old_cross_market_bars_fail_closed(self) -> None:
        for _ in range(15):
            self.provider.benchmark.pop()

        with self.assertRaisesRegex(
            MarketDataError, "benchmark_session_date_conflict"
        ):
            collect_market_snapshot(
                dict(self.record, market="US"),
                self.provider,
                as_of=self.provider.as_of,
            )

    def test_cross_market_exchange_holiday_uses_authoritative_completed_session(self) -> None:
        for _ in range(3):
            self.provider.benchmark.pop()
        self.provider.benchmark_calendar["latest_completed_session_date"] = (
            self.provider.benchmark[-1]["date"]
        )
        calendar_timestamp = self.provider.timestamp - timedelta(minutes=30)
        self.provider.benchmark_calendar["timestamp"] = calendar_timestamp

        snapshot = collect_market_snapshot(
            dict(self.record, market="US"),
            self.provider,
            as_of=self.provider.as_of,
        )

        self.assertEqual(
            self.provider.benchmark[-1]["date"], snapshot.benchmark_session_date
        )
        self.assertEqual(calendar_timestamp, snapshot.source_timestamp)
        self.assertIn("benchmark_exchange_calendar", snapshot.sources)

    def test_typed_benchmark_calendar_is_validated_and_direct_snapshot_keeps_expectation(self) -> None:
        state_type = market_data_module.BenchmarkCalendarState
        valid_state = state_type(
            latest_completed_session_date=self.provider.benchmark[-1]["date"],
            source="benchmark_exchange_calendar",
            timestamp=self.provider.timestamp,
        )
        self.provider.benchmark_calendar = valid_state
        snapshot = collect_market_snapshot(
            dict(self.record, market="HK"),
            self.provider,
            as_of=self.provider.as_of,
        )

        with self.assertRaisesRegex(
            MarketDataError, "benchmark_session_date_conflict"
        ):
            market_data_module.validate_market_snapshot(
                replace(
                    snapshot,
                    benchmark_calendar=replace(
                        snapshot.benchmark_calendar,
                        latest_completed_session_date=snapshot.benchmark_session_date
                        - timedelta(days=1),
                    ),
                )
            )

        invalid = FixtureProvider()
        invalid.benchmark_calendar = replace(
            valid_state,
            latest_completed_session_date=datetime(
                2026, 7, 20, 0, tzinfo=timezone.utc
            ),
        )
        with self.assertRaisesRegex(
            MarketDataError, "malformed_benchmark_calendar"
        ):
            collect_market_snapshot(
                dict(self.record, market="HK"), invalid, as_of=invalid.as_of
            )

    def test_public_provider_delegates_benchmark_calendar_and_fails_when_absent(self) -> None:
        class CalendarProvider:
            def __init__(self):
                self.calls = []

            def get_benchmark_calendar(self, benchmark, market, as_of_date):
                self.calls.append((benchmark, market, as_of_date))
                return self_state

        self_state = deepcopy(self.provider.benchmark_calendar)
        delegate = CalendarProvider()
        public = market_data_module.PublicMarketDataProvider(
            calendar_provider=delegate,
            catalyst_provider=object(),
        )

        self.assertEqual(
            self_state,
            public.get_benchmark_calendar("SPX", "US", self.provider.as_of.date()),
        )
        self.assertEqual(
            [("SPX", "US", self.provider.as_of.date())], delegate.calls
        )

        missing = market_data_module.PublicMarketDataProvider(
            calendar_provider=object(),
            catalyst_provider=object(),
        )
        with self.assertRaisesRegex(MarketDataError, "missing_benchmark_calendar"):
            missing.get_benchmark_calendar("SPX", "US", self.provider.as_of.date())

    def test_cn_benchmark_must_end_on_shanghai_session(self) -> None:
        old_bar = deepcopy(self.provider.benchmark[0])
        old_bar["date"] -= timedelta(days=1)
        self.provider.benchmark.pop()
        self.provider.benchmark.insert(0, old_bar)

        with self.assertRaisesRegex(
            MarketDataError, "benchmark_session_date_conflict"
        ):
            collect_market_snapshot(
                self.record, self.provider, as_of=self.provider.as_of
            )

    def test_domestic_and_cross_market_require_twenty_one_common_dates(self) -> None:
        for market in ("CN", "HK"):
            with self.subTest(market):
                provider = FixtureProvider()
                shift_days = 42 if market == "CN" else 41
                for bar in provider.benchmark:
                    bar["date"] -= timedelta(days=shift_days)
                if market == "CN":
                    provider.benchmark[-1]["date"] = provider.bars[-1]["date"]
                else:
                    provider.benchmark_calendar[
                        "latest_completed_session_date"
                    ] = provider.benchmark[-1]["date"]
                record = dict(self.record, market=market)
                with self.assertRaisesRegex(
                    MarketDataError, "insufficient_common_bar_dates"
                ):
                    collect_market_snapshot(record, provider, as_of=provider.as_of)

    def test_benchmark_bars_cannot_be_from_a_future_session(self) -> None:
        self.provider.benchmark[-1]["date"] += timedelta(days=1)

        with self.assertRaisesRegex(MarketDataError, "future_benchmark_bar"):
            collect_market_snapshot(
                self.record, self.provider, as_of=self.provider.as_of
            )


if __name__ == "__main__":
    unittest.main()
