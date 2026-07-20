"""Contract tests for the ETF monitor command-line interface."""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import timedelta
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = MODULE_ROOT.parents[1]
sys.path.insert(0, str(MODULE_ROOT))

import cli  # noqa: E402
from src.market_data import MarketDataError  # noqa: E402
from src.portfolio import new_portfolio_state, record_buy  # noqa: E402
from tests.test_market_data import FixtureProvider  # noqa: E402


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.state_path = Path(self.temporary.name) / "state" / "portfolio.json"
        self.code = "512890"
        self.other_code = "159500"

    def execute(self, arguments, *, provider=None):
        return cli.execute(
            arguments,
            provider=provider,
            state_path=self.state_path,
        )

    def write_state(self, state) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(state), encoding="utf-8")

    def write_fixture(self, payload) -> Path:
        fixture_path = Path(self.temporary.name) / "provider.json"
        fixture_path.write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8"
        )
        return fixture_path

    def mapped_fixture(self, codes):
        provider = FixtureProvider()
        direct = cli.fixture_payload_from_provider(provider)
        records = cli._scan_records(codes)
        payload = {"as_of": direct["as_of"], "calendar": direct["calendar"]}
        for field in ("current_quotes", "daily_bars", "aum", "premium", "catalyst"):
            payload[field] = {code: deepcopy(direct[field]) for code in codes}
        payload["benchmark_bars"] = {
            str(record["tracking_index"]): deepcopy(direct["benchmark_bars"])
            for record in records
        }
        return provider, payload

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

    def test_multicode_json_fixture_requires_code_and_benchmark_mappings(self) -> None:
        direct = cli.fixture_payload_from_provider(FixtureProvider())
        fixture_path = self.write_fixture(direct)

        result = self.execute(
            [
                "scheduled-check",
                "--code",
                self.code,
                "--code",
                self.other_code,
                "--fixture",
                str(fixture_path),
            ]
        )

        self.assertEqual("DATA_ERROR", result["status"])
        self.assertTrue(
            any("requires_code_mapping" in reason for reason in result["reasons"])
        )
        self.assertEqual([], result["alerts"])
        self.assertEqual(2, len(result["scan_results"]))

    def test_multicode_json_fixture_uses_explicit_mappings(self) -> None:
        provider, payload = self.mapped_fixture([self.code, self.other_code])
        fixture_path = self.write_fixture(payload)

        result = self.execute(
            [
                "scheduled-check",
                "--code",
                self.code,
                "--code",
                self.other_code,
                "--fixture",
                str(fixture_path),
            ]
        )

        self.assertEqual("BUY_CANDIDATE", result["status"])
        self.assertEqual(
            {self.code, self.other_code},
            {scan["code"] for scan in result["scan_results"]},
        )
        self.assertEqual(provider.timestamp.isoformat(), result["source_timestamp"])

    def test_multicode_json_fixture_requires_benchmark_key_mapping(self) -> None:
        _, payload = self.mapped_fixture([self.code, self.other_code])
        payload["benchmark_bars"] = next(iter(payload["benchmark_bars"].values()))
        fixture_path = self.write_fixture(payload)

        result = self.execute(
            [
                "scheduled-check",
                "--code",
                self.code,
                "--code",
                self.other_code,
                "--fixture",
                str(fixture_path),
            ]
        )

        self.assertEqual("DATA_ERROR", result["status"])
        self.assertIn(
            "fixture_benchmark_bars_requires_benchmark_mapping", result["reasons"]
        )

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

    def test_scheduled_check_applies_every_portfolio_buy_gate(self) -> None:
        third_code = "159937"
        cases = []

        drawdown = record_buy(new_portfolio_state(), self.code, 10.40, amount=10_000)
        current_equity = drawdown["cash_cny"] + 10_000 / 10.40 * 10.4005
        drawdown["high_watermark_equity_cny"] = round(current_equity / 0.985, 2)
        cases.append(("buy_blocked_by_drawdown", drawdown, self.code))

        cooldown = new_portfolio_state()
        cooldown["cooldown_remaining_trading_days"] = 5
        cases.append(("buy_blocked_during_cooldown", cooldown, self.code))

        two_positions = record_buy(new_portfolio_state(), self.code, 10, amount=10_000)
        two_positions = record_buy(two_positions, self.other_code, 10, amount=10_000)
        cases.append(("max_open_positions_reached", two_positions, third_code))

        exposure = record_buy(new_portfolio_state(), self.code, 10, amount=10_000)
        exposure = record_buy(
            exposure,
            self.code,
            10,
            amount=10_000,
            second_tranche_confirmed=True,
        )
        exposure = record_buy(exposure, self.other_code, 10, amount=11_000)
        cases.append(("risk_exposure_limit_cny_40000", exposure, third_code))

        etf_limit = record_buy(new_portfolio_state(), self.code, 10, amount=7_500)
        etf_limit = record_buy(
            etf_limit,
            self.code,
            10,
            amount=7_500,
            second_tranche_confirmed=True,
        )
        cases.append(("per_etf_cost_limit_cny_20000", etf_limit, self.code))

        tranches = record_buy(new_portfolio_state(), self.code, 10, amount=5_000)
        tranches = record_buy(
            tranches,
            self.code,
            10,
            amount=5_000,
            second_tranche_confirmed=True,
        )
        cases.append(("max_tranches_per_etf_reached", tranches, self.code))

        for reason, state, candidate in cases:
            with self.subTest(reason):
                self.write_state(state)
                result = self.execute(
                    ["scheduled-check", "--code", candidate],
                    provider=FixtureProvider(),
                )
                self.assertEqual("NO_ACTION", result["status"])
                self.assertIn(reason, result["reasons"])
                gate = result["scan_results"][0]["portfolio_gate"]
                self.assertFalse(gate["allowed"])
                self.assertIn(reason, gate["reasons"])

    def test_second_tranche_candidate_requires_manual_renewed_confirmation(self) -> None:
        state = record_buy(new_portfolio_state(), self.code, 10, amount=10_000)
        self.write_state(state)

        result = self.execute(
            ["scheduled-check", "--code", self.code], provider=FixtureProvider()
        )

        self.assertEqual("BUY_CANDIDATE", result["status"])
        gate = result["scan_results"][0]["portfolio_gate"]
        self.assertTrue(gate["allowed"])
        self.assertTrue(gate["requires_renewed_confirmation"])
        self.assertIn(
            "second_tranche_requires_renewed_confirmation", result["reasons"]
        )

    def test_scheduled_check_deduplicates_position_alerts_across_runs(self) -> None:
        state = record_buy(
            new_portfolio_state(), self.code, 9.90, amount=9_900
        )
        self.write_state(state)
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
        self.write_state(state)
        provider = FixtureProvider()
        provider.catalyst = None

        result = self.execute(
            ["scheduled-check", "--code", self.code], provider=provider
        )

        self.assertEqual("POSITION_ALERT", result["status"])
        self.assertIn("stop", {alert["kind"] for alert in result["alerts"]})
        self.assertEqual("DATA_ERROR", result["scan_results"][0]["status"])

    def test_scheduled_holiday_is_no_action_and_never_advances_by_guess(self) -> None:
        state = new_portfolio_state()
        state["cooldown_remaining_trading_days"] = 10
        self.write_state(state)
        provider = FixtureProvider()
        provider.calendar["is_trading_session"] = False

        result = self.execute(
            ["scheduled-check", "--code", self.code], provider=provider
        )

        self.assertEqual("NO_ACTION", result["status"])
        self.assertIn("not_trading_session", result["reasons"])
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(10, persisted["cooldown_remaining_trading_days"])

    def test_scheduled_holiday_with_first_tranche_stays_no_action(self) -> None:
        state = record_buy(new_portfolio_state(), self.code, 9.9, amount=10_000)
        original = deepcopy(state)
        self.write_state(state)
        provider = FixtureProvider()
        provider.calendar["is_trading_session"] = False
        provider.get_current_quotes = lambda code: self.fail(
            "closed-session check consumed position quotes"
        )

        result = self.execute(
            ["scheduled-check", "--code", self.code], provider=provider
        )

        self.assertEqual("NO_ACTION", result["status"])
        self.assertIn("not_trading_session", result["reasons"])
        self.assertEqual([], result["alerts"])
        self.assertEqual([], result["scan_results"])
        self.assertEqual(
            original, json.loads(self.state_path.read_text(encoding="utf-8"))
        )

    def test_invalid_calendar_fails_before_alerts_or_state_changes(self) -> None:
        original = record_buy(new_portfolio_state(), self.code, 9.9, amount=10_000)
        cases = []
        malformed = FixtureProvider()
        malformed.calendar["is_trading_session"] = "false"
        cases.append(("malformed_trading_calendar", malformed))
        stale = FixtureProvider()
        stale.calendar["timestamp"] = stale.as_of - timedelta(hours=25)
        cases.append(("stale_calendar", stale))
        conflict = FixtureProvider()
        conflict.calendar["session_date"] -= timedelta(days=1)
        cases.append(("session_date_conflict", conflict))

        for reason, provider in cases:
            with self.subTest(reason):
                self.write_state(original)
                provider.get_current_quotes = lambda code: self.fail(
                    "invalid-calendar check consumed position quotes"
                )
                result = self.execute(
                    ["scheduled-check", "--code", self.code], provider=provider
                )
                self.assertEqual("DATA_ERROR", result["status"])
                self.assertEqual([reason], result["reasons"])
                self.assertEqual([], result["alerts"])
                self.assertEqual([], result["scan_results"])
                self.assertEqual(
                    original,
                    json.loads(self.state_path.read_text(encoding="utf-8")),
                )

    def test_scheduled_check_advances_cooldown_once_per_confirmed_trading_day(self) -> None:
        state = new_portfolio_state()
        state["cooldown_remaining_trading_days"] = 10
        self.write_state(state)

        first_provider = FixtureProvider()
        self.execute(["scheduled-check", "--code", self.code], provider=first_provider)
        self.execute(["scheduled-check", "--code", self.code], provider=first_provider)
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(9, persisted["cooldown_remaining_trading_days"])

        for offset in range(1, 10):
            provider = FixtureProvider()
            provider.as_of += timedelta(days=offset)
            provider.calendar["session_date"] += timedelta(days=offset)
            provider.calendar["timestamp"] += timedelta(days=offset)
            self.execute(["scheduled-check", "--code", self.code], provider=provider)

        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(0, persisted["cooldown_remaining_trading_days"])
        self.assertEqual(10, len(persisted["processed_cooldown_trading_days"]))

    def test_calendar_advances_cooldown_despite_other_provider_errors(self) -> None:
        state = new_portfolio_state()
        state["cooldown_remaining_trading_days"] = 2
        self.write_state(state)
        missing_catalyst = FixtureProvider()
        missing_catalyst.catalyst = None

        self.execute(
            ["scheduled-check", "--code", self.code], provider=missing_catalyst
        )
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(1, persisted["cooldown_remaining_trading_days"])

        holding = record_buy(new_portfolio_state(), self.code, 10, amount=10_000)
        holding["cooldown_remaining_trading_days"] = 2
        self.write_state(holding)
        quote_error = FixtureProvider()
        quote_error.quotes[1]["price"] = 10.8

        self.execute(["scheduled-check", "--code", self.code], provider=quote_error)
        persisted = json.loads(self.state_path.read_text(encoding="utf-8"))
        self.assertEqual(1, persisted["cooldown_remaining_trading_days"])

    def test_cli_preserves_each_holdings_own_alert_timestamp(self) -> None:
        state = record_buy(new_portfolio_state(), self.code, 9.9, amount=10_000)
        state = record_buy(state, self.other_code, 9.9, amount=10_000)
        self.write_state(state)
        provider = FixtureProvider()
        timestamps = {
            self.code: provider.timestamp - timedelta(minutes=4),
            self.other_code: provider.timestamp - timedelta(minutes=1),
        }
        base_quotes = deepcopy(provider.quotes)

        def quotes_for(code):
            quotes = deepcopy(base_quotes)
            for quote in quotes:
                quote["timestamp"] = timestamps[code]
            return quotes

        provider.get_current_quotes = quotes_for

        result = self.execute(
            ["scheduled-check", "--code", self.code], provider=provider
        )

        by_code = {alert["code"]: alert for alert in result["alerts"]}
        self.assertEqual(
            timestamps[self.code].isoformat(),
            by_code[self.code]["source_timestamp"],
        )
        self.assertEqual(
            timestamps[self.other_code].isoformat(),
            by_code[self.other_code]["source_timestamp"],
        )

    def test_oldest_timestamp_compares_instants_and_rejects_invalid_values(self) -> None:
        fallback = FixtureProvider().as_of
        earlier = "2026-07-20T15:00:00+08:00"
        later_but_lexically_first = "2026-07-20T08:00:00+00:00"

        self.assertEqual(
            earlier,
            cli._oldest_timestamp(
                [
                    {"source_timestamp": later_but_lexically_first},
                    {"source_timestamp": earlier},
                ],
                fallback,
            ),
        )
        for invalid in ("not-a-timestamp", "2026-07-20T15:00:00"):
            with self.subTest(invalid):
                with self.assertRaisesRegex(
                    MarketDataError, "invalid_source_timestamp"
                ):
                    cli._oldest_timestamp([{"source_timestamp": invalid}], fallback)

    def test_command_errors_keep_command_specific_json_fields(self) -> None:
        cases = (
            (
                ["audit", "--bad"],
                {
                    "record_count",
                    "tradable_count",
                    "exact_duplicate_group_count",
                    "excluded_codes",
                    "reports",
                },
            ),
            (
                ["record-buy", self.code, "--price", "10"],
                {"code", "position", "state"},
            ),
            (["scan"], {"source_timestamp", "results"}),
            (
                ["scheduled-check", "--bad"],
                {"source_timestamp", "alerts", "scan_results"},
            ),
        )
        for arguments, fields in cases:
            with self.subTest(arguments):
                result = self.execute(arguments)
                self.assertEqual("INPUT_ERROR", result["status"])
                self.assertTrue(fields <= result.keys())

    def test_corrupt_nested_state_returns_one_scheduled_json_error(self) -> None:
        state = new_portfolio_state()
        state["positions"] = {self.code: {}}
        self.write_state(state)
        fixture_path = self.write_fixture(
            cli.fixture_payload_from_provider(FixtureProvider())
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exit_code = cli.main(
                [
                    "scheduled-check",
                    "--code",
                    self.code,
                    "--fixture",
                    str(fixture_path),
                ],
                state_path=self.state_path,
            )

        result = json.loads(output.getvalue())
        self.assertEqual(2, exit_code)
        self.assertEqual("INPUT_ERROR", result["status"])
        self.assertEqual([], result["alerts"])
        self.assertEqual([], result["scan_results"])
        self.assertIn("source_timestamp", result)

    def test_record_commands_reject_unknown_and_non_tradable_codes(self) -> None:
        for command in ("record-buy", "record-sell"):
            for code in ("883432", "000000"):
                with self.subTest(command=command, code=code):
                    result = self.execute(
                        [command, code, "--price", "10", "--shares", "100"]
                    )
                    self.assertEqual("INPUT_ERROR", result["status"])
                    self.assertEqual(code, result["code"])
                    self.assertIsNone(result["position"])
                    self.assertIsNone(result["state"])
                    self.assertIn(
                        "unknown or non-tradable ETF code", result["reasons"][0]
                    )

    def test_state_json_rejects_nonstandard_constants_and_wrong_schema(self) -> None:
        state = new_portfolio_state()
        raw = json.dumps(state).replace('"cash_cny": 100000.0', '"cash_cny": NaN')
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(raw, encoding="utf-8")

        nonstandard = self.execute(
            ["record-buy", self.code, "--price", "10", "--amount", "10000"]
        )
        self.assertEqual("INPUT_ERROR", nonstandard["status"])
        self.assertIn("invalid JSON constant", nonstandard["reasons"][0])
        self.assertIsNone(nonstandard["state"])

        state = new_portfolio_state()
        state["schema_version"] = 1
        self.write_state(state)
        wrong_schema = self.execute(
            ["record-buy", self.code, "--price", "10", "--amount", "10000"]
        )
        self.assertEqual("INPUT_ERROR", wrong_schema["status"])
        self.assertIn("schema_version", wrong_schema["reasons"][0])

    def test_write_state_validates_before_serializing_nonfinite_values(self) -> None:
        invalid = new_portfolio_state()
        invalid["cash_cny"] = float("nan")

        with self.assertRaisesRegex(ValueError, "finite"):
            cli._write_state(self.state_path, invalid)

        self.assertFalse(self.state_path.exists())

    def test_invalid_fixture_timestamps_return_canonical_input_error(self) -> None:
        valid = cli.fixture_payload_from_provider(FixtureProvider())
        cases = []
        invalid_json = Path(self.temporary.name) / "invalid.json"
        invalid_json.write_text("{not-json", encoding="utf-8")
        cases.append(invalid_json)

        naive_as_of = deepcopy(valid)
        naive_as_of["as_of"] = "2026-07-20T15:05:00"
        cases.append(self.write_fixture(naive_as_of))

        naive_quote = deepcopy(valid)
        naive_quote["current_quotes"][0]["timestamp"] = "2026-07-20T15:00:00"
        quote_path = Path(self.temporary.name) / "naive-quote.json"
        quote_path.write_text(json.dumps(naive_quote), encoding="utf-8")
        cases.append(quote_path)

        for fixture_path in cases:
            with self.subTest(fixture_path.name):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    exit_code = cli.main(
                        [
                            "scan",
                            "--code",
                            self.code,
                            "--fixture",
                            str(fixture_path),
                        ],
                        state_path=self.state_path,
                    )
                result = json.loads(output.getvalue())
                self.assertEqual(2, exit_code)
                self.assertEqual("INPUT_ERROR", result["status"])
                self.assertEqual([], result["results"])
                self.assertIn("source_timestamp", result)

    def test_portfolio_gate_enforces_cash_tranche_and_lifecycle_contract(self) -> None:
        cash = new_portfolio_state()
        cash["cash_cny"] = 65_000.0
        cash_gate = cli._portfolio_gate(cash, self.code)
        self.assertFalse(cash_gate["allowed"])
        self.assertIn("cash_reserve_floor_cny_60000", cash_gate["reasons"])
        self.assertEqual(60_000, cash_gate["cash_reserve_cny"])
        self.assertEqual(10_000, cash_gate["target_tranche_cny"])
        self.assertEqual(11_000, cash_gate["max_single_tranche_cny"])

        valuation = record_buy(new_portfolio_state(), self.code, 10, amount=10_000)
        valuation["valuation_required"] = True
        valuation_gate = cli._portfolio_gate(valuation, self.other_code)
        self.assertIn("buy_blocked_pending_valuation", valuation_gate["reasons"])

        risk_cycle = record_buy(new_portfolio_state(), self.code, 10, amount=10_000)
        risk_cycle["risk_reset_pending"] = True
        risk_gate = cli._portfolio_gate(risk_cycle, self.other_code)
        self.assertIn("buy_blocked_pending_risk_reset", risk_gate["reasons"])

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
            "portfolio_gate",
            "多标 fixture",
            "按 ETF code",
            "benchmark key",
            "同一交易日只递减一次",
            "renewed confirmation",
            "schema_version` 2",
            "CNY 60,000",
            "硬底线",
            "CNY 11,000",
            "10%",
            "整手/成交容差",
            "risk_reset_pending",
            "valuation_required",
            "--invalidated-code CODE",
            "MA20",
            "MA60",
            "20日相对强度不再为正",
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
            "每只 ETF code",
            "benchmark key",
            "portfolio_gate",
            "冷静期",
            "--invalidated-code CODE",
            "MA20",
            "MA60",
            "20日相对强度不再为正",
            "核心催化反转",
            "歧义",
            "依据与时间",
        ):
            self.assertIn(phrase, prompt)
        self.assertIn("modules/etf-monitor/state/", gitignore)


if __name__ == "__main__":
    unittest.main()
