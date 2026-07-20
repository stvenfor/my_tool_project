"""Deterministic tests for ETF report calculations and rendering inputs."""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from src.market_data import DailyBar  # noqa: E402
from src.reporting import (  # noqa: E402
    ReportDataError,
    SharePoint,
    calculate_kdj,
    calculate_macd,
    calculate_share_flows,
    score_sentiment,
)


FETCHED_AT = datetime(2026, 7, 20, 16, 0, tzinfo=timezone(timedelta(hours=8)))


def _bars(count: int = 40) -> list[DailyBar]:
    start = date(2026, 5, 1)
    closes = [
        10 + index * 0.2 + (0.3 if index % 3 == 0 else -0.1 if index % 3 == 1 else 0)
        for index in range(count)
    ]
    return [
        DailyBar(
            date=start + timedelta(days=index),
            open=close - 0.1,
            close=close,
            high=close + 0.5,
            low=close - 0.6,
            volume=1_000_000 + index * 10_000,
            turnover_cny=100_000_000 + index * 1_000_000,
            source="fixture",
            timestamp=FETCHED_AT,
        )
        for index, close in enumerate(closes)
    ]


class ReportingIndicatorTests(unittest.TestCase):
    def test_kdj_matches_precomputed_recursive_values(self) -> None:
        value = calculate_kdj(_bars())

        self.assertAlmostEqual(81.02388150468099, value.k, places=10)
        self.assertAlmostEqual(80.15140718726933, value.d, places=10)
        self.assertAlmostEqual(82.7688301395043, value.j, places=10)
        self.assertEqual("超买", value.state)

    def test_macd_matches_precomputed_ema_values(self) -> None:
        value = calculate_macd(_bars())

        self.assertAlmostEqual(1.2787325788745285, value.dif, places=10)
        self.assertAlmostEqual(1.2089254987498184, value.dea, places=10)
        self.assertAlmostEqual(0.1396141602494203, value.histogram, places=10)
        self.assertEqual("零轴上多头", value.state)

    def test_macd_requires_at_least_26_bars(self) -> None:
        with self.assertRaisesRegex(ReportDataError, "insufficient_bars_for_macd"):
            calculate_macd(_bars(25))


class ReportingFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        start = date(2026, 6, 1)
        self.bars = [
            DailyBar(
                date=start + timedelta(days=index),
                open=2,
                close=2,
                high=2.1,
                low=1.9,
                volume=1_000,
                turnover_cny=2_000,
                source="fixture",
                timestamp=FETCHED_AT,
            )
            for index in range(21)
        ]
        self.shares = [
            SharePoint(
                code="510050",
                date=bar.date,
                shares=100 + index * 10,
                source="sse",
                fetched_at=FETCHED_AT,
            )
            for index, bar in enumerate(self.bars)
        ]

    def test_share_flows_sum_last_5_10_20_trading_day_deltas(self) -> None:
        flows = calculate_share_flows(self.shares, self.bars)

        self.assertEqual(100, flows[5].value_cny)
        self.assertEqual(200, flows[10].value_cny)
        self.assertEqual(400, flows[20].value_cny)
        self.assertEqual("close", flows[20].price_basis)
        self.assertIsNone(flows[20].reason)

    def test_missing_share_date_only_invalidates_affected_windows(self) -> None:
        missing_date = self.bars[-8].date
        points = [point for point in self.shares if point.date != missing_date]

        flows = calculate_share_flows(points, self.bars)

        self.assertEqual(100, flows[5].value_cny)
        self.assertIsNone(flows[10].value_cny)
        self.assertEqual("missing_share_date", flows[10].reason)
        self.assertIsNone(flows[20].value_cny)

    def test_unresolved_split_is_not_reported_as_flow(self) -> None:
        bars = self.bars[:3]
        bars = [
            bars[0],
            DailyBar(**{**bars[1].__dict__, "open": 1, "close": 1, "high": 1.05, "low": 0.95}),
            DailyBar(**{**bars[2].__dict__, "open": 1.1, "close": 1.1, "high": 1.15, "low": 1.05}),
        ]
        points = [
            SharePoint("510050", bars[0].date, 100, "sse", FETCHED_AT),
            SharePoint("510050", bars[1].date, 200, "sse", FETCHED_AT),
            SharePoint("510050", bars[2].date, 210, "sse", FETCHED_AT),
        ]

        unresolved = calculate_share_flows(points, bars, windows=(2,))
        adjusted = calculate_share_flows(
            points, bars, windows=(2,), split_factors={bars[1].date: 2.0}
        )

        self.assertEqual("corporate_action_unresolved", unresolved[2].reason)
        self.assertIsNone(unresolved[2].value_cny)
        self.assertAlmostEqual(11, adjusted[2].value_cny)


class ReportingSentimentTests(unittest.TestCase):
    def test_neutral_inputs_produce_neutral_score(self) -> None:
        value = score_sentiment(
            flow_5d_cny=0,
            aum_cny=1_000_000,
            volume_ratio=1,
            market_breadth_pct=50,
            rsi14=50,
            kdj_state="中性",
            macd_state="收敛",
        )

        self.assertAlmostEqual(50, value.score)
        self.assertEqual("中性", value.label)
        self.assertEqual((), value.missing_inputs)

    def test_missing_flow_reweights_other_inputs_without_treating_it_as_zero(self) -> None:
        value = score_sentiment(
            flow_5d_cny=None,
            aum_cny=1_000_000,
            volume_ratio=1,
            market_breadth_pct=50,
            rsi14=50,
            kdj_state="中性",
            macd_state="收敛",
        )

        self.assertAlmostEqual(50, value.score)
        self.assertEqual(("flow_5d",), value.missing_inputs)


if __name__ == "__main__":
    unittest.main()
