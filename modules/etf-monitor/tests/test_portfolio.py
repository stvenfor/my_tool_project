"""Tests for ETF portfolio accounting and risk controls."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

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
    def setUp(self) -> None:
        self.state = new_portfolio_state()

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
        self.assertEqual(INITIAL_CAPITAL_CNY - 18_000, after_second["cash_cny"])

    def test_second_tranche_requires_external_confirmation(self) -> None:
        after_first = record_buy(self.state, "510300", price=10, amount=10_000)

        with self.assertRaisesRegex(ValueError, "confirmation"):
            record_buy(after_first, "510300", price=8, amount=8_000)

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
                record_buy(self.state, "159915", price=10, amount=15_000),
                "159915",
                price=10,
                amount=6_000,
                second_tranche_confirmed=True,
            )

        state = record_buy(state, "159915", price=10, amount=20_000)
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

    def test_drawdown_blocks_buys_and_starts_distinct_day_cooldown_with_risk_alerts(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=20_000)
        state = record_buy(state, "159915", price=10, amount=20_000)
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

        state = advance_cooldown(state, "2026-07-20")
        state = advance_cooldown(state, "2026-07-20")
        self.assertEqual(COOLDOWN_TRADING_DAYS - 1, state["cooldown_remaining_trading_days"])
        for day in range(21, 30):
            state = advance_cooldown(state, f"2026-07-{day}")
        self.assertEqual(0, state["cooldown_remaining_trading_days"])
        state, _ = update_drawdown(state, {"510300": 10, "159915": 10})
        with self.assertRaisesRegex(ValueError, "two open ETFs"):
            record_buy(state, "510500", price=10, amount=1)

    def test_recovery_then_new_drawdown_breach_alerts_every_open_risk_position_again(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=20_000)
        state = record_buy(state, "159915", price=10, amount=20_000)
        state, first_breach = update_drawdown(state, {"510300": 9.5, "159915": 9.5})
        state, recovery = update_drawdown(state, {"510300": 10, "159915": 10})
        state, second_breach = update_drawdown(state, {"510300": 9.5, "159915": 9.5})

        self.assertEqual(2, len(first_breach))
        self.assertEqual([], recovery)
        self.assertEqual(2, len(second_breach))
        self.assertTrue(all(alert["kind"] == "risk_exit" for alert in second_breach))

    def test_cooldown_uses_each_valid_trading_day_label_at_most_once(self) -> None:
        state = new_portfolio_state()
        state["cooldown_remaining_trading_days"] = 3
        state = advance_cooldown(state, "2026-07-20")
        state = advance_cooldown(state, "2026-07-21")
        replayed = advance_cooldown(state, "2026-07-20")

        self.assertEqual(1, replayed["cooldown_remaining_trading_days"])
        for invalid_day in ("", "not-a-date", "2026-02-30", 20260720):
            with self.assertRaises(ValueError):
                advance_cooldown(replayed, invalid_day)  # type: ignore[arg-type]

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

    def test_drawdown_updates_high_watermark_from_realized_portfolio_equity(self) -> None:
        state = record_buy(self.state, "510300", price=10, amount=10_000)
        state, _ = update_drawdown(state, {"510300": 11})
        state, _ = update_drawdown(state, {"510300": 10})

        self.assertEqual(101_000, state["high_watermark_equity_cny"])
        self.assertAlmostEqual(100 / 10_100, state["drawdown_pct"], places=8)


if __name__ == "__main__":
    unittest.main()
