"""Contract tests for the ETF monitor command-line interface."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[1]
sys.path.insert(0, str(MODULE_ROOT))

import cli  # noqa: E402
from src.portfolio import new_portfolio_state, record_buy  # noqa: E402
from tests.test_market_data import FixtureProvider  # noqa: E402


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_path = Path(self.temporary.name) / "state" / "portfolio.json"
        self.code = "512890"

    def execute(self, arguments, *, provider=None):
        return cli.execute(
            arguments,
            provider=provider,
            state_path=self.state_path,
        )

    def test_audit_returns_stable_reviewed_universe_summary(self) -> None:
        first = self.execute(["audit"])
        second = self.execute(["audit"])

        self.assertEqual(first, second)
        self.assertEqual("OK", first["status"])
        self.assertEqual(107, first["record_count"])
        self.assertEqual(106, first["tradable_count"])
        self.assertEqual(13, first["exact_duplicate_group_count"])
        self.assertEqual(["883432"], first["excluded_codes"])
        self.assertFalse(first["orders_placed"])

    def test_record_buy_and_sell_persist_actual_fills(self) -> None:
        bought = self.execute(
            ["record-buy", self.code, "--price", "10", "--amount", "10000"]
        )
        sold = self.execute(
            ["record-sell", self.code, "--price", "11", "--shares", "100"]
        )

        self.assertEqual("RECORDED", bought["status"])
        self.assertEqual(1000, bought["position"]["shares"])
        self.assertEqual("RECORDED", sold["status"])
        self.assertEqual(900, sold["position"]["shares"])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(sold["state"], persisted)
        self.assertFalse(sold["orders_placed"])

    def test_second_tranche_requires_explicit_renewed_confirmation(self) -> None:
        self.execute(["record-buy", self.code, "--price", "10", "--amount", "10000"])

        refused = self.execute(
            ["record-buy", self.code, "--price", "9", "--amount", "9000"]
        )
        accepted = self.execute(
            [
                "record-buy",
                self.code,
                "--price",
                "9",
                "--amount",
                "9000",
                "--confirm-second-tranche",
            ]
        )

        self.assertEqual("INPUT_ERROR", refused["status"])
        self.assertIn("second tranche", refused["reasons"][0])
        self.assertEqual("RECORDED", accepted["status"])
        self.assertEqual(2, accepted["position"]["tranche_count"])

    def test_scan_accepts_an_injected_offline_provider(self) -> None:
        provider = FixtureProvider()

        result = self.execute(["scan", "--code", self.code], provider=provider)

        self.assertEqual("BUY_CANDIDATE", result["status"])
        self.assertEqual(self.code, result["results"][0]["code"])
        self.assertEqual(provider.timestamp.isoformat(), result["source_timestamp"])
        self.assertEqual(-3.0, result["results"][0]["risk_controls"]["stop_loss_pct"])
        self.assertTrue(
            result["results"][0]["risk_controls"]["broker_recheck_required"]
        )
        self.assertFalse(result["orders_placed"])

    def test_scan_accepts_a_json_fixture_without_network_access(self) -> None:
        provider = FixtureProvider()
        fixture_path = Path(self.temporary.name) / "provider.json"
        fixture_path.write_text(
            json.dumps(cli.fixture_payload_from_provider(provider), ensure_ascii=False),
            encoding="utf-8",
        )

        result = self.execute(
            ["scan", "--code", self.code, "--fixture", str(fixture_path)]
        )

        self.assertEqual("BUY_CANDIDATE", result["status"])
        self.assertEqual(provider.timestamp.isoformat(), result["source_timestamp"])

    def test_unconfigured_live_dependencies_fail_closed(self) -> None:
        result = self.execute(["scan", "--code", self.code, "--provider", "public"])

        self.assertEqual("DATA_ERROR", result["status"])
        self.assertEqual(
            [
                "missing_live_trading_calendar_provider",
                "missing_live_catalyst_provider",
                "missing_live_benchmark_mapping",
            ],
            result["reasons"],
        )
        self.assertFalse(result["orders_placed"])

    def test_scheduled_check_classifies_catalyst_confirmation(self) -> None:
        needs_provider = FixtureProvider()
        needs_provider.catalyst["primary_confirmed"] = False
        needs_provider.catalyst["corroborated"] = False
        needs = self.execute(
            ["scheduled-check", "--code", self.code], provider=needs_provider
        )

        actionable = self.execute(
            ["scheduled-check", "--code", self.code], provider=FixtureProvider()
        )

        self.assertEqual("BUY_CANDIDATE_NEEDS_CATALYST", needs["status"])
        self.assertEqual("BUY_CANDIDATE", actionable["status"])
        self.assertTrue(actionable["advisory_only"])
        self.assertFalse(actionable["orders_placed"])

    def test_scheduled_check_deduplicates_position_alerts_across_runs(self) -> None:
        state = record_buy(
            new_portfolio_state(), self.code, 9.90, amount=9_900
        )
        self.state_path.parent.mkdir(parents=True)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        provider = FixtureProvider()
        provider.catalyst["primary_confirmed"] = False
        provider.catalyst["corroborated"] = False

        first = self.execute(
            ["scheduled-check", "--code", self.code], provider=provider
        )
        second = self.execute(
            ["scheduled-check", "--code", self.code], provider=provider
        )

        self.assertEqual("POSITION_ALERT", first["status"])
        self.assertEqual({"profit_4_5", "profit_5"}, {
            alert["kind"] for alert in first["alerts"]
        })
        for alert in first["alerts"]:
            self.assertEqual(provider.timestamp.isoformat(), alert["source_timestamp"])
            self.assertEqual(-3.0, alert["risk_controls"]["stop_loss_pct"])
            self.assertTrue(alert["risk_controls"]["broker_recheck_required"])
        self.assertEqual("BUY_CANDIDATE_NEEDS_CATALYST", second["status"])
        self.assertEqual([], second["alerts"])

    def test_position_alerts_remain_available_when_catalyst_data_is_missing(self) -> None:
        state = record_buy(new_portfolio_state(), self.code, 10.80, amount=10_800)
        self.state_path.parent.mkdir(parents=True)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")
        provider = FixtureProvider()
        provider.catalyst = None

        result = self.execute(
            ["scheduled-check", "--code", self.code], provider=provider
        )

        self.assertEqual("POSITION_ALERT", result["status"])
        self.assertIn("stop", {alert["kind"] for alert in result["alerts"]})
        self.assertEqual("DATA_ERROR", result["scan_results"][0]["status"])

    def test_scheduled_holiday_is_no_action_and_never_advances_by_guess(self) -> None:
        provider = FixtureProvider()
        provider.calendar["is_trading_session"] = False

        result = self.execute(
            ["scheduled-check", "--code", self.code], provider=provider
        )

        self.assertEqual("NO_ACTION", result["status"])
        self.assertIn("not_trading_session", result["reasons"])

    def test_main_prints_one_canonical_json_document(self) -> None:
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(["audit"], state_path=self.state_path)

        parsed = json.loads(output.getvalue())
        self.assertEqual("audit", parsed["command"])
        self.assertEqual(
            json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            + "\n",
            output.getvalue(),
        )
        self.assertEqual(0, exit_code)

    def test_docs_packages_and_runtime_state_contract_are_present(self) -> None:
        module_package = json.loads((MODULE_ROOT / "package.json").read_text())
        root_package = json.loads((REPO_ROOT / "package.json").read_text())
        readme = (MODULE_ROOT / "README.md").read_text(encoding="utf-8")
        prompt = (MODULE_ROOT / "automation-prompt.md").read_text(encoding="utf-8")
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

        self.assertIn("scheduled-check", module_package["scripts"])
        self.assertIn("etf:scheduled-check", root_package["scripts"])
        for phrase in (
            "--price ACTUAL_PRICE",
            "--shares ACTUAL_SHARES",
            "--amount ACTUAL_FILL_AMOUNT_CNY",
            "--confirm-second-tranche",
            "券商",
            "实时价",
            "溢折价",
        ):
            self.assertIn(phrase, readme)
        for phrase in (
            "11:15",
            "14:45",
            "Asia/Shanghai",
            "权威一级来源",
            "独立确认",
            "休市",
            "冲突",
        ):
            self.assertIn(phrase, prompt)
        self.assertIn("modules/etf-monitor/state/", gitignore)


if __name__ == "__main__":
    unittest.main()
