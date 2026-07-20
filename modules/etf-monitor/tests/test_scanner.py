"""High-confidence scanner gate and position-monitoring tests."""

from __future__ import annotations

import math
import sys
import unittest
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from src.market_data import collect_market_snapshot  # noqa: E402
from src.portfolio import new_portfolio_state, record_buy  # noqa: E402
from src.scanner import (  # noqa: E402
    evaluate_snapshot,
    monitor_positions,
    monitor_positions_from_provider,
    scan_etf,
)
from tests.test_market_data import FixtureProvider  # noqa: E402


class ScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = FixtureProvider()
        self.record = {"code": "510300", "market": "CN", "tracking_index": "000300"}

    def scan(self):
        return scan_etf(self.record, self.provider, as_of=self.provider.as_of)

    def test_breakout_path_emits_timestamped_buy_candidate(self) -> None:
        result = self.scan()

        self.assertEqual("BUY_CANDIDATE", result["status"])
        self.assertIn("breakout_confirmed", result["reasons"])
        self.assertEqual(self.provider.timestamp.isoformat(), result["source_timestamp"])

    def test_pullback_reclaim_path_is_valid_without_breakout_volume(self) -> None:
        current_ma20 = sum(bar["close"] for bar in self.provider.bars[-20:]) / 20
        self.provider.bars[-1].update(
            open=10.34,
            close=10.36,
            high=self.provider.bars[-2]["high"],
            low=current_ma20 - 0.01,
            turnover_cny=60_000_000,
            volume=1_000_000,
        )
        for quote in self.provider.quotes:
            quote["price"] = 10.36

        result = self.scan()

        self.assertEqual("BUY_CANDIDATE", result["status"])
        self.assertIn("pullback_reclaim_confirmed", result["reasons"])

    def test_breakout_requires_volume_even_when_turnover_is_amplified(self) -> None:
        self.provider.bars[-1].update(
            low=10.30,
            turnover_cny=100_000_000,
            volume=1_190_000,
        )

        result = self.scan()

        self.assertEqual("NO_ACTION", result["status"])
        self.assertIn("no_valid_entry_pattern", result["reasons"])

    def test_each_numeric_gate_vetoes_the_candidate(self) -> None:
        cases = []

        def case(reason, mutate):
            provider = FixtureProvider()
            mutate(provider)
            cases.append((reason, provider))

        def set_latest(provider, *, open_price, close, high, low):
            provider.bars[-1].update(
                open=open_price, close=close, high=high, low=low
            )
            for quote in provider.quotes:
                quote["price"] = close

        def set_previous_close(provider, close):
            for quote in provider.quotes:
                quote["previous_close"] = close
            provider.bars[-2].update(
                open=close, close=close, high=close + 0.01, low=close - 0.01
            )

        case("insufficient_bars", lambda p: p.bars.pop(0))
        case("average_turnover_below_cny_50000000", lambda p: [bar.update(turnover_cny=49_000_000) for bar in p.bars[-20:]])
        case("aum_below_cny_200000000", lambda p: p.aum.update(value=199_999_999))
        case("premium_above_0.5_pct", lambda p: p.premium.update(value=0.51))
        case("close_not_above_ma20", lambda p: set_latest(p, open_price=9.0, close=9.0, high=9.01, low=8.99))
        case("close_not_above_ma60", lambda p: [bar.update(open=11.0, close=11.0, high=11.01, low=10.99) for bar in p.bars[:41]])
        case("ma20_not_rising", lambda p: p.bars[-21].update(open=20.0, close=20.0, high=20.01, low=19.99))
        case("relative_return_not_positive", lambda p: p.benchmark[-21].update(open=5.0, close=5.0, high=5.01, low=4.99))
        case("no_valid_entry_pattern", lambda p: (set_latest(p, open_price=10.34, close=10.36, high=p.bars[-2]["high"], low=10.30), p.bars[-1].update(turnover_cny=60_000_000, volume=1_000_000)))
        case("daily_gain_above_3_pct", lambda p: set_previous_close(p, 10.0))
        case("distance_above_ma20_over_5_pct", lambda p: set_latest(p, open_price=10.58, close=10.6, high=10.62, low=10.57))

        for expected_reason, provider in cases:
            with self.subTest(expected_reason):
                result = scan_etf(self.record, provider, as_of=provider.as_of)
                self.assertEqual("NO_ACTION", result["status"])
                self.assertIn(expected_reason, result["reasons"])

    def test_cross_border_and_commodity_use_one_percent_premium_cap(self) -> None:
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
                provider.premium["value"] = 0.99
                record = dict(self.record, market=market)
                self.assertEqual(
                    "BUY_CANDIDATE",
                    scan_etf(record, provider, as_of=provider.as_of)["status"],
                )
                provider.premium["value"] = 1.01
                result = scan_etf(record, provider, as_of=provider.as_of)
                self.assertIn("premium_above_1.0_pct", result["reasons"])

    def test_each_catalyst_gate_vetoes_and_adverse_catalyst_vetoes(self) -> None:
        for field, value, reason in (
            ("primary_confirmed", False, "primary_catalyst_not_confirmed"),
            ("corroborated", False, "independent_corroboration_missing"),
            ("adverse", True, "adverse_catalyst_present"),
        ):
            with self.subTest(field):
                provider = FixtureProvider()
                provider.catalyst[field] = value
                result = scan_etf(self.record, provider, as_of=provider.as_of)
                self.assertEqual("NO_ACTION", result["status"])
                self.assertIn(reason, result["reasons"])

    def test_missing_stale_conflicting_and_holiday_data_return_data_error(self) -> None:
        providers = []
        missing = FixtureProvider()
        missing.catalyst = None
        providers.append(("missing_catalyst", missing))
        stale = FixtureProvider()
        stale.quotes[1]["timestamp"] = stale.as_of - timedelta(minutes=16)
        providers.append(("stale_quote", stale))
        conflict = FixtureProvider()
        conflict.quotes[1]["price"] = 10.45
        providers.append(("quote_price_conflict", conflict))
        holiday = FixtureProvider()
        holiday.calendar["is_trading_session"] = False
        providers.append(("not_trading_session", holiday))

        for reason, provider in providers:
            with self.subTest(reason):
                result = scan_etf(self.record, provider, as_of=provider.as_of)
                self.assertEqual("DATA_ERROR", result["status"])
                self.assertIn(reason, result["reasons"])
                self.assertIn("source_timestamp", result)

    def test_position_monitoring_runs_without_catalyst_and_emits_profit_stop_drawdown(self) -> None:
        state = new_portfolio_state()
        state = record_buy(state, "510300", price=10, amount=10_000)
        state = record_buy(
            state,
            "510300",
            price=10,
            amount=10_000,
            second_tranche_confirmed=True,
        )
        state = record_buy(state, "159915", price=10, amount=10_000)
        state = record_buy(
            state,
            "159915",
            price=10,
            amount=10_000,
            second_tranche_confirmed=True,
        )

        updated, output = monitor_positions(
            state,
            {"510300": 10.5, "159915": 8.0},
            source_timestamp=self.provider.timestamp,
            invalidated_codes={"159915"},
        )

        kinds = {(alert["code"], alert["kind"]) for alert in output["alerts"]}
        self.assertIn(("510300", "profit_4_5"), kinds)
        self.assertIn(("510300", "profit_5"), kinds)
        self.assertIn(("159915", "stop"), kinds)
        self.assertIn(("510300", "risk_exit"), kinds)
        self.assertEqual(self.provider.timestamp.isoformat(), output["source_timestamp"])
        self.assertIn("position_monitoring_completed", output["reasons"])
        self.assertGreaterEqual(updated["drawdown_pct"], 0.02)

    def test_provider_backed_position_monitoring_does_not_require_catalyst(self) -> None:
        state = record_buy(
            new_portfolio_state(), "510300", price=9.9, amount=10_000
        )
        state = record_buy(
            state,
            "510300",
            price=9.9,
            amount=10_000,
            second_tranche_confirmed=True,
        )
        self.provider.catalyst = None

        _, output = monitor_positions_from_provider(
            state, self.provider, as_of=self.provider.as_of
        )

        self.assertEqual("POSITION_ALERT", output["status"])
        self.assertIn("position_monitoring_completed", output["reasons"])

    def test_provider_position_alerts_use_each_codes_quote_timestamp(self) -> None:
        state = new_portfolio_state()
        state = record_buy(state, "510300", price=9.9, amount=10_000)
        state = record_buy(
            state,
            "510300",
            price=9.9,
            amount=10_000,
            second_tranche_confirmed=True,
        )
        state = record_buy(state, "159915", price=9.9, amount=10_000)
        state = record_buy(
            state,
            "159915",
            price=9.9,
            amount=10_000,
            second_tranche_confirmed=True,
        )
        timestamps = {
            "510300": self.provider.timestamp - timedelta(minutes=4),
            "159915": self.provider.timestamp - timedelta(minutes=1),
        }
        base_quotes = deepcopy(self.provider.quotes)

        def quotes_for(code):
            quotes = deepcopy(base_quotes)
            for quote in quotes:
                quote["timestamp"] = timestamps[code]
            return quotes

        self.provider.get_current_quotes = quotes_for

        _, output = monitor_positions_from_provider(
            state, self.provider, as_of=self.provider.as_of
        )

        self.assertEqual(
            timestamps["510300"].isoformat(), output["source_timestamp"]
        )
        for alert in output["alerts"]:
            self.assertEqual(
                timestamps[alert["code"]].isoformat(),
                alert.get("source_timestamp"),
            )

    def test_exact_three_percent_gain_and_five_percent_ma20_distance_pass(self) -> None:
        exact_gain = FixtureProvider()
        midpoint = sum(quote["price"] for quote in exact_gain.quotes) / 2
        exact_previous_close = midpoint / 1.03
        for quote in exact_gain.quotes:
            quote["previous_close"] = exact_previous_close
        exact_gain.bars[-2].update(
            open=exact_previous_close,
            close=exact_previous_close,
            high=exact_previous_close + 0.01,
            low=exact_previous_close - 0.01,
        )
        gain_result = scan_etf(self.record, exact_gain, as_of=exact_gain.as_of)

        exact_distance = FixtureProvider()
        previous_19_sum = sum(bar["close"] for bar in exact_distance.bars[-20:-1])
        exact_close = 1.05 * previous_19_sum / (20 - 1.05)
        exact_distance.bars[-1].update(
            open=exact_close - 0.02,
            close=exact_close,
            high=exact_close + 0.02,
            low=exact_close - 0.02,
        )
        for quote in exact_distance.quotes:
            quote["price"] = exact_close
        distance_result = scan_etf(
            self.record, exact_distance, as_of=exact_distance.as_of
        )

        self.assertEqual("BUY_CANDIDATE", gain_result["status"])
        self.assertNotIn("daily_gain_above_3_pct", gain_result["reasons"])
        self.assertEqual("BUY_CANDIDATE", distance_result["status"])
        self.assertNotIn("distance_above_ma20_over_5_pct", distance_result["reasons"])

    def test_cross_market_lag_uses_last_twenty_one_common_dates(self) -> None:
        for market in ("HK", "US", "COMMODITY"):
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

                result = scan_etf(record, provider, as_of=provider.as_of)

                self.assertEqual("BUY_CANDIDATE", result["status"])
                self.assertIn("all_high_confidence_gates_passed", result["reasons"])

    def test_cross_market_holiday_calendar_accepts_lag_but_old_bars_fail_closed(self) -> None:
        holiday = FixtureProvider()
        for _ in range(3):
            holiday.benchmark.pop()
        holiday.benchmark_calendar["latest_completed_session_date"] = (
            holiday.benchmark[-1]["date"]
        )

        holiday_result = scan_etf(
            dict(self.record, market="US"), holiday, as_of=holiday.as_of
        )

        self.assertEqual("BUY_CANDIDATE", holiday_result["status"])

        weeks_old = FixtureProvider()
        for _ in range(15):
            weeks_old.benchmark.pop()
        old_result = scan_etf(
            dict(self.record, market="US"), weeks_old, as_of=weeks_old.as_of
        )

        self.assertEqual("DATA_ERROR", old_result["status"])
        self.assertIn("benchmark_session_date_conflict", old_result["reasons"])

    def test_cn_lagged_benchmark_returns_data_error(self) -> None:
        old_bar = deepcopy(self.provider.benchmark[0])
        old_bar["date"] -= timedelta(days=1)
        self.provider.benchmark.pop()
        self.provider.benchmark.insert(0, old_bar)

        result = self.scan()

        self.assertEqual("DATA_ERROR", result["status"])
        self.assertIn("benchmark_session_date_conflict", result["reasons"])

    def test_direct_nan_snapshot_returns_data_error(self) -> None:
        snapshot = collect_market_snapshot(
            self.record, self.provider, as_of=self.provider.as_of
        )

        result = evaluate_snapshot(replace(snapshot, current_price=math.nan))

        self.assertEqual("DATA_ERROR", result["status"])
        self.assertIn("malformed_snapshot", result["reasons"])

    def test_direct_malformed_bar_collection_returns_data_error(self) -> None:
        snapshot = collect_market_snapshot(
            self.record, self.provider, as_of=self.provider.as_of
        )

        result = evaluate_snapshot(replace(snapshot, bars=42))

        self.assertEqual("DATA_ERROR", result["status"])
        self.assertIn("malformed_daily_bar", result["reasons"])

    def test_direct_cross_market_snapshot_requires_fresh_authoritative_calendar(self) -> None:
        snapshot = collect_market_snapshot(
            dict(self.record, market="US"),
            self.provider,
            as_of=self.provider.as_of,
        )

        valid = evaluate_snapshot(snapshot)
        self.assertEqual("BUY_CANDIDATE", valid["status"])

        calendar = snapshot.benchmark_calendar
        cases = (
            (replace(snapshot, benchmark_calendar=None), "missing_benchmark_calendar"),
            (
                replace(
                    snapshot,
                    benchmark_calendar=replace(
                        calendar, timestamp=calendar.timestamp.replace(tzinfo=None)
                    ),
                ),
                "missing_benchmark_calendar_timestamp",
            ),
            (
                replace(
                    snapshot,
                    benchmark_calendar=replace(
                        calendar, timestamp=snapshot.observed_at - timedelta(hours=25)
                    ),
                ),
                "stale_benchmark_calendar",
            ),
            (
                replace(
                    snapshot,
                    benchmark_calendar=replace(calendar, source=""),
                ),
                "missing_source",
            ),
            (
                replace(
                    snapshot,
                    benchmark_calendar=replace(
                        calendar,
                        latest_completed_session_date=calendar.latest_completed_session_date
                        - timedelta(days=1),
                    ),
                ),
                "benchmark_session_date_conflict",
            ),
        )
        for candidate, reason in cases:
            with self.subTest(reason):
                result = evaluate_snapshot(candidate)
                self.assertEqual("DATA_ERROR", result["status"])
                self.assertIn(reason, result["reasons"])

    def test_direct_cross_market_snapshot_requires_observation_and_calendar_provenance(self) -> None:
        snapshot = collect_market_snapshot(
            dict(self.record, market="HK"),
            self.provider,
            as_of=self.provider.as_of,
        )
        calendar = snapshot.benchmark_calendar
        previous_observation = snapshot.observed_at - timedelta(days=1)
        cases = (
            (
                replace(snapshot, observed_at=snapshot.observed_at.replace(tzinfo=None)),
                "malformed_snapshot",
            ),
            (
                replace(
                    snapshot,
                    sources=tuple(
                        source
                        for source in snapshot.sources
                        if source != calendar.source
                    ),
                ),
                "benchmark_calendar_source_missing",
            ),
            (
                replace(
                    snapshot,
                    source_timestamp=calendar.timestamp + timedelta(minutes=1),
                ),
                "benchmark_calendar_timestamp_conflict",
            ),
            (
                replace(
                    snapshot,
                    observed_at=previous_observation,
                    benchmark_calendar=replace(
                        calendar, timestamp=calendar.timestamp - timedelta(days=1)
                    ),
                    source_timestamp=snapshot.source_timestamp - timedelta(days=1),
                ),
                "observation_session_date_conflict",
            ),
        )
        for candidate, reason in cases:
            with self.subTest(reason):
                result = evaluate_snapshot(candidate)
                self.assertEqual("DATA_ERROR", result["status"])
                self.assertIn(reason, result["reasons"])

    def test_direct_snapshot_revalidates_both_quote_sources_and_freshness(self) -> None:
        snapshot = collect_market_snapshot(
            self.record, self.provider, as_of=self.provider.as_of
        )
        quotes = snapshot.quotes
        cases = (
            (
                replace(snapshot, quotes=42),
                "malformed_quote",
            ),
            (
                replace(snapshot, quotes=quotes[:1]),
                "missing_independent_quote",
            ),
            (
                replace(
                    snapshot,
                    quotes=(
                        quotes[0],
                        replace(
                            quotes[1],
                            timestamp=snapshot.observed_at - timedelta(minutes=16),
                        ),
                    ),
                ),
                "stale_quote",
            ),
            (
                replace(
                    snapshot,
                    quotes=(
                        replace(
                            quotes[0],
                            timestamp=quotes[0].timestamp.replace(tzinfo=None),
                        ),
                        quotes[1],
                    ),
                ),
                "missing_quote_timestamp",
            ),
            (
                replace(snapshot, current_price=snapshot.current_price + 0.01),
                "quote_snapshot_price_conflict",
            ),
        )
        for candidate, reason in cases:
            with self.subTest(reason):
                result = evaluate_snapshot(candidate)
                self.assertEqual("DATA_ERROR", result["status"])
                self.assertIn(reason, result["reasons"])

    def test_direct_snapshot_revalidates_all_supporting_data_freshness(self) -> None:
        snapshot = collect_market_snapshot(
            self.record, self.provider, as_of=self.provider.as_of
        )
        stale_at = snapshot.observed_at - timedelta(hours=25)
        cases = (
            (
                replace(
                    snapshot,
                    bars=(replace(snapshot.bars[0], timestamp=stale_at),)
                    + snapshot.bars[1:],
                ),
                "stale_daily_bars",
            ),
            (
                replace(
                    snapshot,
                    benchmark_bars=(
                        replace(snapshot.benchmark_bars[0], timestamp=stale_at),
                    )
                    + snapshot.benchmark_bars[1:],
                ),
                "stale_benchmark_bars",
            ),
            (
                replace(
                    snapshot,
                    catalyst=replace(snapshot.catalyst, timestamp=stale_at),
                ),
                "stale_catalyst",
            ),
            (
                replace(
                    snapshot,
                    aum_metric=replace(snapshot.aum_metric, timestamp=stale_at),
                ),
                "stale_aum",
            ),
            (
                replace(
                    snapshot,
                    premium_metric=replace(
                        snapshot.premium_metric,
                        timestamp=snapshot.premium_metric.timestamp.replace(
                            tzinfo=None
                        ),
                    ),
                ),
                "missing_metric_timestamp",
            ),
        )
        for candidate, reason in cases:
            with self.subTest(reason):
                result = evaluate_snapshot(candidate)
                self.assertEqual("DATA_ERROR", result["status"])
                self.assertIn(reason, result["reasons"])

    def test_direct_snapshot_revalidates_structured_values_and_all_provenance(self) -> None:
        snapshot = collect_market_snapshot(
            self.record, self.provider, as_of=self.provider.as_of
        )
        cases = (
            (
                replace(
                    snapshot,
                    aum_metric=replace(
                        snapshot.aum_metric, value=snapshot.aum_cny + 1
                    ),
                ),
                "aum_metric_conflict",
            ),
            (
                replace(
                    snapshot,
                    premium_metric=replace(
                        snapshot.premium_metric, value=snapshot.premium_pct + 0.01
                    ),
                ),
                "premium_metric_conflict",
            ),
            (
                replace(
                    snapshot,
                    aum_metric=replace(snapshot.aum_metric, source="aum_authority"),
                ),
                "snapshot_source_missing",
            ),
            (
                replace(snapshot, trading_calendar=None),
                "missing_trading_calendar",
            ),
            (
                replace(
                    snapshot,
                    source_timestamp=snapshot.source_timestamp
                    - timedelta(minutes=1),
                ),
                "source_timestamp_conflict",
            ),
        )
        for candidate, reason in cases:
            with self.subTest(reason):
                result = evaluate_snapshot(candidate)
                self.assertEqual("DATA_ERROR", result["status"])
                self.assertIn(reason, result["reasons"])

    def test_direct_snapshot_with_insufficient_common_dates_returns_data_error(self) -> None:
        snapshot = collect_market_snapshot(
            self.record, self.provider, as_of=self.provider.as_of
        )
        shifted_benchmark = tuple(
            replace(bar, date=bar.date - timedelta(days=41))
            for bar in snapshot.benchmark_bars
        )

        result = evaluate_snapshot(
            replace(
                snapshot,
                market="HK",
                benchmark_bars=shifted_benchmark,
                benchmark_calendar=replace(
                    snapshot.benchmark_calendar,
                    latest_completed_session_date=shifted_benchmark[-1].date,
                ),
            )
        )

        self.assertEqual("DATA_ERROR", result["status"])
        self.assertIn("insufficient_common_bar_dates", result["reasons"])


if __name__ == "__main__":
    unittest.main()
