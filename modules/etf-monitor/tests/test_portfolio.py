"""Tests for ETF portfolio accounting and risk controls."""

from __future__ import annotations

from copy import deepcopy
import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from src import portfolio as portfolio_module  # noqa: E402
from src.portfolio import (  # noqa: E402  (module root is deliberately local)
    COOLDOWN_TRADING_DAYS,
    INITIAL_CAPITAL_CNY,
    MAX_ETF_COST_CNY,
    MAX_OPEN_POSITIONS,
    MAX_RISK_EXPOSURE_CNY,
    advance_cooldown,
    evaluate_position_alerts,
    new_portfolio_state,
    portfolio_equity,
    record_buy,
    record_sell,
    update_drawdown,
)


class PortfolioTests(unittest.TestCase):
    TRADING_DAYS = (
        "2026-07-20",
        "2026-07-21",
        "2026-07-22",
        "2026-07-23",
        "2026-07-24",
        "2026-07-27",
        "2026-07-28",
        "2026-07-29",
        "2026-07-30",
        "2026-07-31",
    )

    def setUp(self) -> None:
        self.state = new_portfolio_state()

    def fully_invested_state(self) -> dict[str, object]:
        state = new_portfolio_state()
        for code in ("510300", "159915"):
            state = record_buy(state, code, price=10, amount=10_000)
            state = record_buy(
                state,
                code,
                price=10,
                amount=10_000,
                second_tranche_confirmed=True,
            )
        return state

    def test_new_state_has_auditable_schema_reserve_and_risk_lifecycle(self) -> None:
        state = new_portfolio_state()

        self.assertEqual(portfolio_module.PORTFOLIO_SCHEMA_VERSION, state["schema_version"])
        self.assertEqual(60_000, state["cash_reserve_cny"])
        self.assertFalse(state["valuation_required"])
        self.assertFalse(state["risk_reset_pending"])
        self.assertIsNone(portfolio_module.validate_portfolio_state(state))

    def test_two_buys_calculate_weighted_cost_from_shares_and_amount(self) -> None:
        after_first = record_buy(self.state, "510300", price=10, shares=1_000)
        after_second = record_buy(
            after_first,
            "510300",
            price=8,
            amount=8_000,
            second_tranche_confirmed=True,
        )

        position = after_second["positions"]["510300"]
        self.assertEqual(2_000, position["shares"])
        self.assertEqual(9.0, position["weighted_cost_cny"])
        self.assertEqual(18_000, position["cost_basis_cny"])
        self.assertEqual([10_000, 8_000], position["entry_tranche_costs_cny"])
        self.assertEqual(INITIAL_CAPITAL_CNY - 18_000, after_second["cash_cny"])

    def test_partial_sell_preserves_auditable_entry_tranche_cost_history(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state = record_buy(
            state,
            "510300",
            price=8,
            amount=8_000,
            second_tranche_confirmed=True,
        )
        partially_sold = record_sell(state, "510300", price=10, shares=500)

        position = partially_sold["positions"]["510300"]
        self.assertEqual([10_000, 8_000], position["entry_tranche_costs_cny"])
        self.assertEqual(13_500, position["cost_basis_cny"])

    def test_second_tranche_requires_external_confirmation(self) -> None:
        after_first = record_buy(self.state, "510300", price=10, amount=10_000)

        with self.assertRaisesRegex(ValueError, "confirmation"):
            record_buy(after_first, "510300", price=8, amount=8_000)

    def test_second_tranche_confirmation_must_be_literal_true(self) -> None:
        after_first = record_buy(self.state, "510300", price=10, amount=10_000)

        with self.assertRaisesRegex(ValueError, "confirmation"):
            record_buy(
                after_first,
                "510300",
                price=8,
                amount=8_000,
                second_tranche_confirmed="false",  # type: ignore[arg-type]
            )

    def test_each_tranche_is_limited_to_cny_11000(self) -> None:
        at_limit = record_buy(
            self.state,
            "510300",
            price=10,
            amount=portfolio_module.MAX_SINGLE_TRANCHE_CNY,
        )

        self.assertEqual(
            portfolio_module.MAX_SINGLE_TRANCHE_CNY,
            at_limit["positions"]["510300"]["cost_basis_cny"],
        )
        with self.assertRaisesRegex(ValueError, "single tranche"):
            record_buy(
                self.state,
                "510300",
                price=10,
                amount=portfolio_module.MAX_SINGLE_TRANCHE_CNY + 0.01,
            )

    def test_default_cash_reserve_is_a_hard_post_buy_floor(self) -> None:
        state = new_portfolio_state()
        state["cash_cny"] = state["cash_reserve_cny"]
        state["realized_pnl_cny"] = -MAX_RISK_EXPOSURE_CNY
        state["high_watermark_equity_cny"] = state["cash_cny"]

        with self.assertRaisesRegex(ValueError, "cash reserve"):
            record_buy(state, "510300", price=1, amount=0.01)

    def test_validator_rejects_cash_below_declared_reserve(self) -> None:
        corrupted = new_portfolio_state()
        corrupted["cash_cny"] = corrupted["cash_reserve_cny"] - 0.01

        with self.assertRaisesRegex(ValueError, "cash reserve"):
            portfolio_module.validate_portfolio_state(corrupted)

    def test_validator_rejects_one_cent_cash_inflation_and_understatement(self) -> None:
        for delta in (-0.01, 0.01):
            corrupted = new_portfolio_state()
            corrupted["cash_cny"] += delta
            with self.subTest(delta=delta):
                with self.assertRaisesRegex(ValueError, "accounting"):
                    portfolio_module.validate_portfolio_state(corrupted)

    def test_cash_accounting_identity_accepts_sells_realized_pnl_and_risk_reset(self) -> None:
        partial = record_buy(self.state, "510300", price=10, amount=10_000)
        partial = record_sell(partial, "510300", price=11, shares=500)
        self.assertIsNone(portfolio_module.validate_portfolio_state(partial))

        realized = record_sell(partial, "510300", price=11, shares=500)
        self.assertEqual(1_000, realized["realized_pnl_cny"])
        self.assertIsNone(portfolio_module.validate_portfolio_state(realized))

        risk = record_buy(self.state, "159915", price=10, amount=10_000)
        risk = record_sell(risk, "159915", price=8, shares=1_000)
        for trading_day in self.TRADING_DAYS:
            risk = advance_cooldown(
                risk, trading_day, confirmed_trading_session=True
            )
        self.assertFalse(risk["risk_reset_pending"])
        self.assertIsNone(portfolio_module.validate_portfolio_state(risk))

    def test_validator_rejects_forged_empty_portfolio_drawdown_and_high_watermark(self) -> None:
        forged_drawdown = new_portfolio_state()
        forged_drawdown["cash_cny"] = 70_000.0
        forged_drawdown["realized_pnl_cny"] = -30_000.0
        with self.assertRaisesRegex(ValueError, "drawdown"):
            portfolio_module.validate_portfolio_state(forged_drawdown)

        low_high_watermark = new_portfolio_state()
        low_high_watermark["high_watermark_equity_cny"] = 99_999.99
        with self.assertRaisesRegex(ValueError, "high watermark"):
            portfolio_module.validate_portfolio_state(low_high_watermark)

    def test_validator_rejects_empty_portfolio_risk_lifecycle_contradictions(self) -> None:
        one_six_percent = record_buy(
            self.state, "510300", price=10, amount=10_000
        )
        one_six_percent = record_sell(
            one_six_percent, "510300", price=8.4, shares=1_000
        )
        two_percent = record_buy(self.state, "510300", price=10, amount=10_000)
        two_percent = record_sell(two_percent, "510300", price=8, shares=1_000)

        contradictions = []
        below_threshold_pending = new_portfolio_state()
        below_threshold_pending["risk_reset_pending"] = True
        below_threshold_pending["cooldown_remaining_trading_days"] = 1
        contradictions.append(("below_threshold_pending", below_threshold_pending))

        below_threshold_cooldown = new_portfolio_state()
        below_threshold_cooldown["cooldown_remaining_trading_days"] = 1
        contradictions.append(("below_threshold_cooldown", below_threshold_cooldown))

        wrong_drawdown = deepcopy(one_six_percent)
        wrong_drawdown["drawdown_pct"] += 0.000001
        contradictions.append(("drawdown_mismatch", wrong_drawdown))

        wrong_active = deepcopy(one_six_percent)
        wrong_active["risk_drawdown_active"] = True
        contradictions.append(("one_six_active", wrong_active))

        missing_active = deepcopy(two_percent)
        missing_active["risk_drawdown_active"] = False
        contradictions.append(("two_percent_missing_active", missing_active))

        for label, state in contradictions:
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    portfolio_module.validate_portfolio_state(state)

    def test_validator_accepts_empty_portfolio_buy_block_and_completed_risk_reset(self) -> None:
        one_six_percent = record_buy(
            self.state, "510300", price=10, amount=10_000
        )
        one_six_percent = record_sell(
            one_six_percent, "510300", price=8.4, shares=1_000
        )
        two_percent = record_buy(self.state, "510300", price=10, amount=10_000)
        two_percent = record_sell(two_percent, "510300", price=8, shares=1_000)

        self.assertIsNone(portfolio_module.validate_portfolio_state(one_six_percent))
        self.assertIsNone(portfolio_module.validate_portfolio_state(two_percent))
        epsilon_close = deepcopy(one_six_percent)
        epsilon_close["drawdown_pct"] += 0.000000005
        self.assertIsNone(portfolio_module.validate_portfolio_state(epsilon_close))

        unchanged = one_six_percent
        for trading_day in self.TRADING_DAYS:
            unchanged = advance_cooldown(
                unchanged, trading_day, confirmed_trading_session=True
            )
        self.assertEqual(one_six_percent, unchanged)

        reset = two_percent
        for trading_day in self.TRADING_DAYS:
            reset = advance_cooldown(
                reset, trading_day, confirmed_trading_session=True
            )
        self.assertEqual(reset["cash_cny"], reset["high_watermark_equity_cny"])
        self.assertEqual(0.0, reset["drawdown_pct"])
        self.assertFalse(reset["risk_drawdown_active"])
        self.assertFalse(reset["risk_reset_pending"])
        self.assertEqual(0, reset["cooldown_remaining_trading_days"])
        self.assertIsNone(portfolio_module.validate_portfolio_state(reset))

    def test_fills_that_round_to_zero_cost_or_quantity_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            record_buy(self.state, "510300", price=1, shares=0.0001)
        with self.assertRaises(ValueError):
            record_buy(self.state, "510300", price=10_000_000, amount=0.01)

    def test_tiny_holding_cannot_be_oversold_with_tolerance(self) -> None:
        state = record_buy(self.state, "510300", price=1_000_000, shares=0.00000001)
        cash_before_sale = state["cash_cny"]

        with self.assertRaisesRegex(ValueError, "more shares"):
            record_sell(state, "510300", price=1_000_000, shares=0.00000002)

        self.assertEqual(cash_before_sale, state["cash_cny"])
        self.assertEqual(0.00000001, state["positions"]["510300"]["shares"])

    def test_one_normalized_share_quantum_remaining_is_not_a_full_close(self) -> None:
        state = record_buy(self.state, "510300", price=1_000_000, shares=0.00000002)
        partially_sold = record_sell(state, "510300", price=1_000_000, shares=0.00000001)

        position = partially_sold["positions"]["510300"]
        self.assertEqual(0.00000001, position["shares"])
        self.assertEqual(0.01, position["cost_basis_cny"])
        self.assertEqual(1, position["cycle_id"])
        self.assertEqual(INITIAL_CAPITAL_CNY - 0.01, partially_sold["cash_cny"])

    def test_partial_sell_keeps_average_cost_and_calculates_realized_and_unrealized_pnl(self) -> None:
        state = record_buy(self.state, "510300", price=10, shares=1_000)
        state = record_buy(
            state,
            "510300",
            price=8,
            shares=1_000,
            second_tranche_confirmed=True,
        )
        state = record_sell(state, "510300", price=10, shares=500)

        position = state["positions"]["510300"]
        equity = portfolio_equity(state, {"510300": 10})
        self.assertEqual(1_500, position["shares"])
        self.assertEqual(9.0, position["weighted_cost_cny"])
        self.assertEqual(500, state["realized_pnl_cny"])
        self.assertEqual(1_500, equity["unrealized_pnl_cny"])
        self.assertEqual(INITIAL_CAPITAL_CNY + 2_000, equity["equity_cny"])

    def test_non_cent_average_partial_and_full_sells_release_exact_cost_basis(self) -> None:
        state = record_buy(self.state, "510300", price=10, shares=3)
        state = record_buy(
            state,
            "510300",
            price=10.01,
            shares=2,
            second_tranche_confirmed=True,
        )
        partially_sold = record_sell(state, "510300", price=10, shares=2)
        fully_sold = record_sell(partially_sold, "510300", price=10, shares=3)

        self.assertEqual(30.01, partially_sold["positions"]["510300"]["cost_basis_cny"])
        self.assertEqual(-0.01, partially_sold["realized_pnl_cny"])
        self.assertNotIn("510300", fully_sold["positions"])
        self.assertEqual(-0.02, fully_sold["realized_pnl_cny"])
        self.assertEqual(INITIAL_CAPITAL_CNY - 0.02, fully_sold["cash_cny"])

    def test_partial_sell_rounds_remaining_basis_before_realized_pnl(self) -> None:
        state = record_buy(self.state, "510300", price=1, shares=10_000)

        # The unrounded proportional cost released by this fill is CNY 0.015.
        partially_sold = record_sell(state, "510300", price=2, shares=0.015)

        position = partially_sold["positions"]["510300"]
        self.assertEqual(9_999.985, position["shares"])
        self.assertEqual(9_999.99, position["cost_basis_cny"])
        self.assertEqual(0.02, partially_sold["realized_pnl_cny"])
        self.assertEqual(90_000.03, partially_sold["cash_cny"])
        self.assertEqual(
            partially_sold["cash_cny"],
            partially_sold["initial_capital_cny"]
            + partially_sold["realized_pnl_cny"]
            - position["cost_basis_cny"],
        )
        self.assertIsNone(portfolio_module.validate_portfolio_state(partially_sold))

    def test_full_close_then_reopen_starts_a_fresh_alert_cycle(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state, first_alerts = evaluate_position_alerts(state, {"510300": 10.45})
        state = record_sell(state, "510300", price=10.45, shares=1_000)
        reopened = record_buy(state, "510300", price=10, amount=10_000)
        reopened, reopened_alerts = evaluate_position_alerts(reopened, {"510300": 10.45})

        self.assertEqual(["profit_4_5"], [alert["kind"] for alert in first_alerts])
        self.assertEqual(["profit_4_5"], [alert["kind"] for alert in reopened_alerts])
        self.assertEqual(2, reopened["positions"]["510300"]["cycle_id"])

    def test_open_position_tranche_per_etf_and_exposure_limits_are_enforced(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state = record_buy(
            state,
            "510300",
            price=10,
            amount=10_000,
            second_tranche_confirmed=True,
        )

        with self.assertRaisesRegex(ValueError, "two tranches"):
            record_buy(state, "510300", price=10, amount=1)
        with self.assertRaisesRegex(ValueError, "CNY 20,000"):
            record_buy(
                record_buy(self.state, "159915", price=10, amount=11_000),
                "159915",
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
        self.assertEqual(MAX_OPEN_POSITIONS, len(state["positions"]))
        self.assertEqual(MAX_RISK_EXPOSURE_CNY, sum(
            position["cost_basis_cny"] for position in state["positions"].values()
        ))
        with self.assertRaisesRegex(ValueError, "two open ETFs"):
            record_buy(state, "512000", price=10, amount=1)

    def test_profit_and_stop_threshold_boundaries_deduplicate_within_cycle(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state, no_alerts = evaluate_position_alerts(state, {"510300": 10.449})
        state, profit_alerts = evaluate_position_alerts(state, {"510300": 10.45})
        state, five_percent_alerts = evaluate_position_alerts(state, {"510300": 10.5})
        state, repeated_alerts = evaluate_position_alerts(state, {"510300": 10.5})
        stopped, stop_alerts = evaluate_position_alerts(state, {"510300": 9.7})
        stopped, repeated_stop_alerts = evaluate_position_alerts(stopped, {"510300": 9.6})

        self.assertEqual([], no_alerts)
        self.assertEqual(["profit_4_5"], [alert["kind"] for alert in profit_alerts])
        self.assertEqual(["profit_5"], [alert["kind"] for alert in five_percent_alerts])
        self.assertEqual([], repeated_alerts)
        self.assertEqual(["stop"], [alert["kind"] for alert in stop_alerts])
        self.assertEqual([], repeated_stop_alerts)

    def test_alert_thresholds_use_exact_cost_basis_not_rounded_weighted_display(self) -> None:
        state = record_buy(self.state, "510300", price=10, shares=3)
        state = record_buy(
            state,
            "510300",
            price=10.01,
            shares=2,
            second_tranche_confirmed=True,
        )
        state, early_profit = evaluate_position_alerts(state, {"510300": 10.45})
        state, exact_profit = evaluate_position_alerts(state, {"510300": 10.4542})
        state, exact_stop = evaluate_position_alerts(state, {"510300": 9.702})

        self.assertEqual(10.0, state["positions"]["510300"]["weighted_cost_cny"])
        self.assertEqual([], early_profit)
        self.assertEqual(["profit_4_5"], [alert["kind"] for alert in exact_profit])
        self.assertEqual(["stop"], [alert["kind"] for alert in exact_stop])

    def test_drawdown_blocks_buys_and_starts_distinct_day_cooldown_with_risk_alerts(self) -> None:
        state = self.fully_invested_state()
        state, no_risk_alerts = update_drawdown(state, {"510300": 9.625, "159915": 9.625})
        self.assertEqual([], no_risk_alerts)
        with self.assertRaisesRegex(ValueError, "drawdown"):
            record_buy(state, "510500", price=10, amount=1)

        state, risk_alerts = update_drawdown(state, {"510300": 9.5, "159915": 9.5})
        self.assertEqual(2, len(risk_alerts))
        self.assertEqual(COOLDOWN_TRADING_DAYS, state["cooldown_remaining_trading_days"])
        self.assertTrue(all(alert["kind"] == "risk_exit" for alert in risk_alerts))
        with self.assertRaisesRegex(ValueError, "cooldown"):
            record_buy(state, "510500", price=10, amount=1)

        state = advance_cooldown(
            state, "2026-07-20", confirmed_trading_session=True
        )
        state = advance_cooldown(
            state, "2026-07-20", confirmed_trading_session=True
        )
        self.assertEqual(COOLDOWN_TRADING_DAYS - 1, state["cooldown_remaining_trading_days"])
        for day in (
            "2026-07-21",
            "2026-07-22",
            "2026-07-23",
            "2026-07-24",
            "2026-07-27",
            "2026-07-28",
            "2026-07-29",
            "2026-07-30",
            "2026-07-31",
        ):
            state = advance_cooldown(state, day, confirmed_trading_session=True)
        self.assertEqual(0, state["cooldown_remaining_trading_days"])
        state, _ = update_drawdown(state, {"510300": 10, "159915": 10})
        with self.assertRaisesRegex(ValueError, "risk reset"):
            record_buy(state, "510500", price=10, amount=1)

    def test_recovery_then_new_drawdown_breach_alerts_every_open_risk_position_again(self) -> None:
        state = self.fully_invested_state()
        state, first_breach = update_drawdown(state, {"510300": 9.5, "159915": 9.5})
        state, recovery = update_drawdown(state, {"510300": 10, "159915": 10})
        state, second_breach = update_drawdown(state, {"510300": 9.5, "159915": 9.5})

        self.assertEqual(2, len(first_breach))
        self.assertEqual([], recovery)
        self.assertEqual(2, len(second_breach))
        self.assertTrue(all(alert["kind"] == "risk_exit" for alert in second_breach))

    def test_partial_sell_blocks_buy_until_complete_revaluation(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state = record_sell(state, "510300", price=10, shares=100)

        self.assertTrue(state["valuation_required"])
        with self.assertRaisesRegex(ValueError, "valuation"):
            record_buy(
                state,
                "510300",
                price=10,
                amount=1_000,
                second_tranche_confirmed=True,
            )
        with self.assertRaisesRegex(ValueError, "missing price"):
            update_drawdown(state, {})

        state, _ = update_drawdown(state, {"510300": 10})
        self.assertFalse(state["valuation_required"])
        state = record_buy(
            state,
            "510300",
            price=10,
            amount=1_000,
            second_tranche_confirmed=True,
        )
        self.assertEqual(10_000, state["positions"]["510300"]["cost_basis_cny"])

    def test_full_close_at_two_percent_starts_cooldown_without_prior_valuation(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        closed = record_sell(state, "510300", price=8, shares=1_000)

        self.assertEqual({}, closed["positions"])
        self.assertEqual(0.02, closed["drawdown_pct"])
        self.assertTrue(closed["risk_reset_pending"])
        self.assertEqual(COOLDOWN_TRADING_DAYS, closed["cooldown_remaining_trading_days"])

    def test_empty_portfolio_at_1_6_percent_only_blocks_buys_without_cooldown_or_reset(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state = record_sell(state, "510300", price=8.4, shares=1_000)

        self.assertAlmostEqual(0.016, state["drawdown_pct"])
        self.assertFalse(state["risk_drawdown_active"])
        self.assertFalse(state["risk_reset_pending"])
        self.assertEqual(0, state["cooldown_remaining_trading_days"])
        self.assertEqual(100_000, state["high_watermark_equity_cny"])
        with self.assertRaisesRegex(ValueError, "drawdown"):
            record_buy(state, "510300", price=8.4, amount=10_000)

        unchanged = state
        for trading_day in self.TRADING_DAYS:
            unchanged = advance_cooldown(
                unchanged, trading_day, confirmed_trading_session=True
            )
        self.assertEqual(state, unchanged)
        self.assertEqual(100_000, unchanged["high_watermark_equity_cny"])
        self.assertAlmostEqual(0.016, unchanged["drawdown_pct"])

    def test_prior_two_percent_breach_keeps_cooldown_after_recovery_and_close_at_1_6_percent(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state, _ = update_drawdown(state, {"510300": 8})
        state, _ = update_drawdown(state, {"510300": 8.4})
        closed = record_sell(state, "510300", price=8.4, shares=1_000)

        self.assertAlmostEqual(0.016, closed["drawdown_pct"])
        self.assertFalse(closed["risk_drawdown_active"])
        self.assertTrue(closed["risk_reset_pending"])
        self.assertEqual(
            COOLDOWN_TRADING_DAYS, closed["cooldown_remaining_trading_days"]
        )
        self.assertIsNone(portfolio_module.validate_portfolio_state(closed))

    def test_recovered_empty_portfolio_finishes_existing_risk_cooldown(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state, _ = update_drawdown(state, {"510300": 8})
        for trading_day in self.TRADING_DAYS[:-1]:
            state = advance_cooldown(
                state, trading_day, confirmed_trading_session=True
            )

        state, _ = update_drawdown(state, {"510300": 10})
        closed = record_sell(state, "510300", price=10, shares=1_000)

        self.assertEqual({}, closed["positions"])
        self.assertEqual(0.0, closed["drawdown_pct"])
        self.assertFalse(closed["risk_drawdown_active"])
        self.assertTrue(closed["risk_reset_pending"])
        self.assertEqual(1, closed["cooldown_remaining_trading_days"])
        self.assertEqual(9, len(closed["processed_cooldown_trading_days"]))
        self.assertIsNone(portfolio_module.validate_portfolio_state(closed))

        reset = advance_cooldown(
            closed,
            self.TRADING_DAYS[-1],
            confirmed_trading_session=True,
        )
        self.assertFalse(reset["risk_reset_pending"])
        self.assertEqual(0, reset["cooldown_remaining_trading_days"])
        self.assertEqual([], reset["processed_cooldown_trading_days"])
        self.assertIsNone(reset["last_cooldown_trading_day"])
        self.assertIsNone(portfolio_module.validate_portfolio_state(reset))

    def test_validator_rejects_forged_cooldown_progress_and_last_day(self) -> None:
        risk = record_buy(self.state, "510300", price=10, amount=10_000)
        risk = record_sell(risk, "510300", price=8, shares=1_000)
        after_one_day = advance_cooldown(
            risk, self.TRADING_DAYS[0], confirmed_trading_session=True
        )
        corrupt_states = []

        remaining_without_history = deepcopy(risk)
        remaining_without_history["cooldown_remaining_trading_days"] = 1
        corrupt_states.append(("remaining_without_history", remaining_without_history))

        mismatched_progress = deepcopy(after_one_day)
        mismatched_progress["cooldown_remaining_trading_days"] = 8
        corrupt_states.append(("mismatched_progress", mismatched_progress))

        missing_last_day = deepcopy(after_one_day)
        missing_last_day["last_cooldown_trading_day"] = None
        corrupt_states.append(("missing_last_day", missing_last_day))

        wrong_last_day = deepcopy(after_one_day)
        wrong_last_day["last_cooldown_trading_day"] = self.TRADING_DAYS[1]
        corrupt_states.append(("wrong_last_day", wrong_last_day))

        inactive_with_history = new_portfolio_state()
        inactive_with_history["processed_cooldown_trading_days"] = [
            self.TRADING_DAYS[0]
        ]
        inactive_with_history["last_cooldown_trading_day"] = self.TRADING_DAYS[0]
        corrupt_states.append(("inactive_with_history", inactive_with_history))

        empty_pending_at_zero = deepcopy(risk)
        empty_pending_at_zero["cooldown_remaining_trading_days"] = 0
        empty_pending_at_zero["processed_cooldown_trading_days"] = list(
            self.TRADING_DAYS
        )
        empty_pending_at_zero["last_cooldown_trading_day"] = self.TRADING_DAYS[-1]
        corrupt_states.append(("empty_pending_at_zero", empty_pending_at_zero))

        for label, state in corrupt_states:
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    portfolio_module.validate_portfolio_state(state)

    def test_trigger_exit_and_ten_distinct_sessions_reset_risk_cycle_for_buying(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state, alerts = update_drawdown(state, {"510300": 8})
        state = record_sell(state, "510300", price=8, shares=1_000)

        self.assertEqual(["risk_exit"], [alert["kind"] for alert in alerts])
        with self.assertRaisesRegex(ValueError, "cooldown"):
            record_buy(state, "510300", price=8, amount=10_000)

        for trading_day in self.TRADING_DAYS[:-1]:
            state = advance_cooldown(
                state, trading_day, confirmed_trading_session=True
            )
        repeated = advance_cooldown(
            state, self.TRADING_DAYS[0], confirmed_trading_session=True
        )
        self.assertEqual(1, repeated["cooldown_remaining_trading_days"])
        with self.assertRaisesRegex(ValueError, "cooldown"):
            record_buy(repeated, "510300", price=8, amount=10_000)

        reset = advance_cooldown(
            repeated, self.TRADING_DAYS[-1], confirmed_trading_session=True
        )
        self.assertFalse(reset["risk_reset_pending"])
        self.assertFalse(reset["risk_drawdown_active"])
        self.assertEqual(0.0, reset["drawdown_pct"])
        self.assertEqual(reset["cash_cny"], reset["high_watermark_equity_cny"])
        reopened = record_buy(reset, "510300", price=8, amount=10_000)
        self.assertIn("510300", reopened["positions"])

    def test_completed_cooldown_waits_for_full_exit_before_risk_reset(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state, _ = update_drawdown(state, {"510300": 8})
        for trading_day in self.TRADING_DAYS:
            state = advance_cooldown(
                state, trading_day, confirmed_trading_session=True
            )

        self.assertEqual(0, state["cooldown_remaining_trading_days"])
        self.assertTrue(state["risk_reset_pending"])
        with self.assertRaisesRegex(ValueError, "risk reset"):
            record_buy(
                state,
                "510300",
                price=8,
                amount=1_000,
                second_tranche_confirmed=True,
            )

        closed = record_sell(state, "510300", price=8, shares=1_000)
        self.assertFalse(closed["risk_reset_pending"])
        self.assertEqual(0.0, closed["drawdown_pct"])
        reopened = record_buy(closed, "510300", price=8, amount=10_000)
        self.assertIn("510300", reopened["positions"])

    def test_cooldown_uses_each_valid_trading_day_label_at_most_once(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state = record_sell(state, "510300", price=8, shares=1_000)
        state = advance_cooldown(
            state, "2026-07-20", confirmed_trading_session=True
        )
        state = advance_cooldown(
            state, "2026-07-21", confirmed_trading_session=True
        )
        replayed = advance_cooldown(
            state, "2026-07-20", confirmed_trading_session=True
        )

        self.assertEqual(
            COOLDOWN_TRADING_DAYS - 2,
            replayed["cooldown_remaining_trading_days"],
        )
        for invalid_day in ("", "not-a-date", "2026-02-30", 20260720):
            with self.assertRaises(ValueError):
                advance_cooldown(  # type: ignore[arg-type]
                    replayed, invalid_day, confirmed_trading_session=True
                )

    def test_cooldown_requires_authoritative_trading_session_confirmation(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state = record_sell(state, "510300", price=8, shares=1_000)

        with self.assertRaises(TypeError):
            advance_cooldown(state, "2026-07-20")
        for non_trading_day in ("2026-07-18", "2026-10-01"):
            with self.assertRaises(ValueError):
                advance_cooldown(
                    state, non_trading_day, confirmed_trading_session=False
                )
        self.assertEqual(
            COOLDOWN_TRADING_DAYS,
            state["cooldown_remaining_trading_days"],
        )

    def test_non_finite_fill_and_capital_inputs_are_rejected(self) -> None:
        for non_finite in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                new_portfolio_state(non_finite)
            with self.assertRaises(ValueError):
                record_buy(self.state, "510300", price=non_finite, amount=1)
            with self.assertRaises(ValueError):
                record_buy(self.state, "510300", price=10, shares=non_finite)
            with self.assertRaises(ValueError):
                record_buy(self.state, "510300", price=10, amount=non_finite)

    def test_strict_state_validation_rejects_corrupt_top_level_and_positions(self) -> None:
        holding = record_buy(self.state, "510300", price=10, amount=10_000)
        corrupt_states = []

        missing_field = deepcopy(self.state)
        del missing_field["cash_cny"]
        corrupt_states.append(("missing_field", missing_field))
        for field, value in (
            ("schema_version", 999),
            ("cash_cny", float("nan")),
            ("drawdown_pct", -0.01),
            ("cooldown_remaining_trading_days", 11),
            ("risk_drawdown_active", "false"),
        ):
            corrupted = deepcopy(self.state)
            corrupted[field] = value
            corrupt_states.append((field, corrupted))

        duplicate_days = deepcopy(self.state)
        duplicate_days["processed_cooldown_trading_days"] = [
            "2026-07-20",
            "2026-07-20",
        ]
        duplicate_days["last_cooldown_trading_day"] = "2026-07-20"
        corrupt_states.append(("duplicate_days", duplicate_days))

        bad_cycle = deepcopy(self.state)
        bad_cycle["next_cycle_by_code"] = {"510300": 0}
        corrupt_states.append(("bad_cycle", bad_cycle))

        position_mutations = (
            ("code", "159915"),
            ("shares", 0),
            ("cost_basis_cny", float("inf")),
            ("weighted_cost_cny", 9.99),
            ("tranche_count", 3),
        )
        for field, value in position_mutations:
            corrupted = deepcopy(holding)
            corrupted["positions"]["510300"][field] = value
            corrupt_states.append((f"position_{field}", corrupted))

        bad_alert = deepcopy(holding)
        bad_alert["positions"]["510300"]["alert_acknowledged"]["stop"] = "false"
        corrupt_states.append(("bad_alert", bad_alert))

        too_many_positions = deepcopy(holding)
        for code in ("159915", "512000"):
            position = deepcopy(holding["positions"]["510300"])
            position["code"] = code
            too_many_positions["positions"][code] = position
        corrupt_states.append(("too_many_positions", too_many_positions))

        for label, state in corrupt_states:
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    portfolio_module.validate_portfolio_state(state)

    def test_validator_rejects_corrupt_single_and_double_tranche_history(self) -> None:
        single = record_buy(self.state, "510300", price=10, amount=10_000)
        double = record_buy(
            single,
            "510300",
            price=10,
            amount=10_000,
            second_tranche_confirmed=True,
        )
        corrupt_states = []

        missing = deepcopy(single)
        del missing["positions"]["510300"]["entry_tranche_costs_cny"]
        corrupt_states.append(("missing", missing))

        short = deepcopy(double)
        short["positions"]["510300"]["entry_tranche_costs_cny"] = [10_000]
        corrupt_states.append(("length", short))

        non_finite = deepcopy(single)
        non_finite["positions"]["510300"]["entry_tranche_costs_cny"] = [
            float("nan")
        ]
        corrupt_states.append(("nan", non_finite))

        single_oversize = deepcopy(single)
        single_oversize["positions"]["510300"]["entry_tranche_costs_cny"] = [
            11_000.01
        ]
        corrupt_states.append(("single_oversize", single_oversize))

        double_oversize = deepcopy(double)
        double_oversize["positions"]["510300"]["entry_tranche_costs_cny"] = [
            10_000,
            11_000.01,
        ]
        corrupt_states.append(("double_oversize", double_oversize))

        insufficient_history = deepcopy(single)
        insufficient_history["positions"]["510300"]["entry_tranche_costs_cny"] = [
            9_999.99
        ]
        corrupt_states.append(("one_cent_below_current_basis", insufficient_history))

        for label, state in corrupt_states:
            with self.subTest(label):
                with self.assertRaises(ValueError):
                    portfolio_module.validate_portfolio_state(state)

    def test_every_public_operation_rejects_non_finite_state(self) -> None:
        corrupted = deepcopy(self.state)
        corrupted["cash_cny"] = float("nan")
        operations = (
            lambda: record_buy(corrupted, "510300", price=10, amount=1),
            lambda: record_sell(corrupted, "510300", price=10, amount=1),
            lambda: portfolio_equity(corrupted, {}),
            lambda: update_drawdown(corrupted, {}),
            lambda: advance_cooldown(
                corrupted, "2026-07-20", confirmed_trading_session=True
            ),
            lambda: evaluate_position_alerts(corrupted, {}),
        )

        for operation in operations:
            with self.subTest(operation=operation):
                with self.assertRaises(ValueError):
                    operation()

    def test_validator_rejects_nested_huge_integer_as_value_error(self) -> None:
        corrupted = record_buy(
            self.state, "510300", price=10, amount=10_000
        )
        corrupted["positions"]["510300"]["entry_tranche_costs_cny"] = [
            10**10_000
        ]

        try:
            portfolio_module.validate_portfolio_state(corrupted)
        except Exception as error:  # The exception type is the regression contract.
            self.assertIs(type(error), ValueError)
            self.assertIn("finite", str(error))
        else:
            self.fail("nested huge integer was accepted")

    def test_public_numeric_inputs_reject_huge_integer_as_value_error(self) -> None:
        huge = 10**10_000
        operations = (
            lambda: new_portfolio_state(huge),
            lambda: record_buy(self.state, "510300", price=huge, amount=1),
            lambda: record_buy(self.state, "510300", price=10, amount=huge),
        )

        for operation in operations:
            with self.subTest(operation=operation):
                try:
                    operation()
                except Exception as error:
                    self.assertIs(type(error), ValueError)
                else:
                    self.fail("huge numeric input was accepted")

    def test_drawdown_updates_high_watermark_from_realized_portfolio_equity(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state, _ = update_drawdown(state, {"510300": 11})
        state, _ = update_drawdown(state, {"510300": 10})

        self.assertEqual(101_000, state["high_watermark_equity_cny"])
        self.assertAlmostEqual(100 / 10_100, state["drawdown_pct"], places=8)


if __name__ == "__main__":
    unittest.main()
