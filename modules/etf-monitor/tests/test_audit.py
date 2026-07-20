"""Tests for the reviewed ETF universe audit."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from src.audit import (  # noqa: E402  (module root is deliberately local)
    EXACT_DUPLICATE_GROUPS,
    LOW_TURNOVER_CNY,
    choose_recommendation,
    load_universe,
    render_exact_duplicates_report,
    render_sector_overlap_report,
    sector_market_groups,
    tradable_records,
)


class AuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = load_universe()

    def test_reviewed_universe_has_107_unique_records_and_expected_kinds(self) -> None:
        self.assertEqual(107, len(self.records))
        self.assertEqual(107, len({record["code"] for record in self.records}))
        self.assertEqual(106, sum(record["kind"] == "ETF" for record in self.records))
        self.assertEqual(1, sum(record["kind"] == "INDEX" for record in self.records))

    def test_index_883432_is_excluded_from_tradable_records(self) -> None:
        index = next(record for record in self.records if record["code"] == "883432")
        self.assertEqual("INDEX", index["kind"])
        self.assertNotIn(index, tradable_records(self.records))
        self.assertEqual(106, len(tradable_records(self.records)))

    def test_exact_duplicate_groups_match_reviewed_membership(self) -> None:
        expected = {
            "512890/159525",
            "159659/159941/159660",
            "159500/510500",
            "159937/518880",
            "159995/159801",
            "159713/516780",
            "512000/512880",
            "588000/588060/588950",
            "588790/588760",
            "159875/516160",
            "159857/515790",
            "516750/159745",
            "588170/589020",
        }
        actual = {
            "/".join(record["code"] for record in members)
            for members in EXACT_DUPLICATE_GROUPS.values()
        }
        self.assertEqual(expected, actual)

    def test_sector_overlap_keeps_same_sector_in_different_markets_separate(self) -> None:
        groups = sector_market_groups(self.records)
        self.assertEqual(["513650"], [record["code"] for record in groups[("broad_market", "US")]])
        self.assertEqual(["513520"], [record["code"] for record in groups[("broad_market", "JP")]])
        report = render_sector_overlap_report(self.records)
        self.assertIn("broad_market × US", report)
        self.assertIn("broad_market × JP", report)

    def test_choice_prefers_eligible_then_turnover_then_lower_code(self) -> None:
        records = [
            {"code": "200000", "kind": "ETF", "screenshot_turnover_cny": LOW_TURNOVER_CNY - 1},
            {"code": "300000", "kind": "ETF", "screenshot_turnover_cny": LOW_TURNOVER_CNY},
            {"code": "100000", "kind": "ETF", "screenshot_turnover_cny": LOW_TURNOVER_CNY},
        ]
        self.assertEqual("100000", choose_recommendation(records)["code"])

    def test_exact_report_recommends_highest_turnover_eligible_member_deterministically(self) -> None:
        report = render_exact_duplicates_report(self.records)
        self.assertIn("159659/159941/159660", report)
        self.assertIn("| 159941 |", report)
        self.assertIn("13 exact duplicate groups", report)

    def test_low_turnover_unique_products_are_observation_only(self) -> None:
        report = render_sector_overlap_report(self.records)
        self.assertIn("Observation-only unique products", report)
        self.assertIn("516960", report)
        self.assertIn("below CNY 50,000,000", report)

    def test_reports_state_the_reviewed_and_tradable_record_totals(self) -> None:
        self.assertIn("107 unique records", render_exact_duplicates_report(self.records))
        self.assertIn("106 tradable ETFs", render_sector_overlap_report(self.records))


if __name__ == "__main__":
    unittest.main()
