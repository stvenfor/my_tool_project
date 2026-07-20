"""End-to-end pure-data tests for the enhanced ETF report builder."""

from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from src.market_data import DailyBar  # noqa: E402
from src.report_generator import build_report  # noqa: E402
from src.reporting import SharePoint  # noqa: E402


FETCHED_AT = datetime(2026, 7, 20, 18, 0, tzinfo=timezone(timedelta(hours=8)))


def _bars() -> list[DailyBar]:
    start = date(2026, 3, 1)
    return [
        DailyBar(
            date=start + timedelta(days=index),
            open=1 + index * 0.01,
            close=1.005 + index * 0.01,
            high=1.02 + index * 0.01,
            low=0.99 + index * 0.01,
            volume=1_000_000 + index * 1_000,
            turnover_cny=10_000_000 + index * 100_000,
            source="fixture",
            timestamp=FETCHED_AT,
        )
        for index in range(80)
    ]


def _context() -> dict[str, object]:
    evidence = {
        "text": "证据正文",
        "title": "证据标题",
        "publisher": "官方机构",
        "date": "2026-07-20",
        "url": "https://example.gov.cn/evidence",
    }
    return {
        "themes": {"broad": {"policy": evidence, "fundamental": evidence}},
        "sector_theme": {"large_cap": "broad"},
    }


class ReportGeneratorTests(unittest.TestCase):
    def test_builder_adds_indicators_flows_sentiment_and_four_reason_dimensions(self) -> None:
        bars = _bars()
        shares = [
            SharePoint(
                code="510050",
                date=bar.date,
                shares=1_000_000 + index * 10_000,
                source="fixture",
                fetched_at=FETCHED_AT,
            )
            for index, bar in enumerate(bars)
        ]
        seed = {
            "data_date": bars[-1].date.isoformat(),
            "rows": [
                {
                    "code": "510050",
                    "name": "上证50ETF华夏",
                    "market": "CN",
                    "sector": "large_cap",
                    "tracking_index": "上证50指数",
                }
            ],
        }

        report = build_report(
            seed=seed,
            bars_by_code={"510050": bars},
            shares_by_code={"510050": shares},
            share_errors={},
            context=_context(),
            generated_at=FETCHED_AT,
        )

        row = report["rows"][0]
        self.assertEqual("close", report["flow_price_basis"])
        self.assertEqual("交易所基金份额变化 × 当日收盘价", report["flow_definition"])
        self.assertIn("k", row["kdj"])
        self.assertIn("dif", row["macd"])
        self.assertIsNotNone(row["flows"]["20"]["value_cny"])
        self.assertIn(row["sentiment"]["label"], {"极冷", "偏冷", "中性", "偏热", "过热"})
        self.assertIn("[官方机构｜2026-07-20｜证据标题]", row["policy_reason"])
        self.assertIn("MA20", row["technical_reason"])
        self.assertIn("份额净流入", row["sentiment_reason"])

    def test_share_source_error_is_scoped_to_one_etf_and_each_window(self) -> None:
        bars = _bars()
        seed = {
            "data_date": bars[-1].date.isoformat(),
            "rows": [
                {
                    "code": "510050",
                    "name": "上证50ETF华夏",
                    "market": "CN",
                    "sector": "large_cap",
                    "tracking_index": "上证50指数",
                }
            ],
        }

        report = build_report(
            seed=seed,
            bars_by_code={"510050": bars},
            shares_by_code={},
            share_errors={"510050": "share_source_unavailable"},
            context=_context(),
            generated_at=FETCHED_AT,
        )

        row = report["rows"][0]
        for window in ("5", "10", "20"):
            self.assertIsNone(row["flows"][window]["value_cny"])
            self.assertEqual("share_source_unavailable", row["flows"][window]["reason"])
        self.assertIn("flow_5d", row["sentiment"]["missing_inputs"])
        self.assertNotEqual("DATA_ERROR", row["sentiment"]["label"])

    def test_flows_end_at_latest_official_share_date_not_the_later_price_date(self) -> None:
        bars = _bars()
        shares = [
            SharePoint(
                code="510050",
                date=bar.date,
                shares=1_000_000 + index * 10_000,
                source="fixture",
                fetched_at=FETCHED_AT,
            )
            for index, bar in enumerate(bars[:-3])
        ]
        seed = {
            "rows": [
                {
                    "code": "510050",
                    "name": "上证50ETF华夏",
                    "market": "CN",
                    "sector": "large_cap",
                    "tracking_index": "上证50指数",
                }
            ]
        }

        report = build_report(
            seed=seed,
            bars_by_code={"510050": bars},
            shares_by_code={"510050": shares},
            share_errors={},
            context=_context(),
            generated_at=FETCHED_AT,
        )

        row = report["rows"][0]
        self.assertEqual(bars[-4].date.isoformat(), row["flow_as_of"])
        self.assertIsNotNone(row["flows"]["20"]["value_cny"])


if __name__ == "__main__":
    unittest.main()
