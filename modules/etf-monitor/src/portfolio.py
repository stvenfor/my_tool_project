"""Pure accounting and risk controls for the local ETF monitor.

Every public state-transforming function returns a copied JSON-compatible state;
callers can persist that return value without relying on in-place mutation.
"""

from __future__ import annotations

from copy import deepcopy
from collections.abc import Iterable, Mapping
from datetime import date
import math
from typing import Any


INITIAL_CAPITAL_CNY = 100_000
MAX_RISK_EXPOSURE_CNY = 40_000
MAX_SINGLE_TRANCHE_CNY = 11_000
MAX_OPEN_POSITIONS = 2
MAX_TRANCHES_PER_ETF = 2
MAX_ETF_COST_CNY = 20_000
PROFIT_4_5_PCT = 0.045
PROFIT_5_PCT = 0.05
STOP_LOSS_PCT = -0.03
BUY_BLOCK_DRAWDOWN_PCT = 0.015
RISK_EXIT_DRAWDOWN_PCT = 0.02
COOLDOWN_TRADING_DAYS = 10
PORTFOLIO_SCHEMA_VERSION = 2

_EPSILON = 1e-8
_ALERT_FLAG_KEYS = frozenset({"profit_4_5", "profit_5", "stop", "risk_exit"})
_POSITION_KEYS = frozenset(
    {
        "code",
        "cycle_id",
        "shares",
        "cost_basis_cny",
        "weighted_cost_cny",
        "tranche_count",
        "entry_tranche_costs_cny",
        "alert_acknowledged",
    }
)
_STATE_KEYS = frozenset(
    {
        "schema_version",
        "initial_capital_cny",
        "cash_reserve_cny",
        "cash_cny",
        "realized_pnl_cny",
        "high_watermark_equity_cny",
        "drawdown_pct",
        "risk_drawdown_active",
        "risk_reset_pending",
        "valuation_required",
        "cooldown_remaining_trading_days",
        "last_cooldown_trading_day",
        "processed_cooldown_trading_days",
        "next_cycle_by_code",
        "positions",
    }
)


def new_portfolio_state(initial_capital_cny: float = INITIAL_CAPITAL_CNY) -> dict[str, Any]:
    """Create the JSON-compatible initial persistent portfolio state."""
    capital = _positive_number(initial_capital_cny, "initial capital")
    state = {
        "schema_version": PORTFOLIO_SCHEMA_VERSION,
        "initial_capital_cny": _money(capital),
        "cash_reserve_cny": _money(max(0.0, capital - MAX_RISK_EXPOSURE_CNY)),
        "cash_cny": _money(capital),
        "realized_pnl_cny": 0.0,
        "high_watermark_equity_cny": _money(capital),
        "drawdown_pct": 0.0,
        "risk_drawdown_active": False,
        "risk_reset_pending": False,
        "valuation_required": False,
        "cooldown_remaining_trading_days": 0,
        "last_cooldown_trading_day": None,
        "processed_cooldown_trading_days": [],
        "next_cycle_by_code": {},
        "positions": {},
    }
    validate_portfolio_state(state)
    return state


def record_buy(
    state: Mapping[str, Any],
    code: str,
    price: float,
    *,
    shares: float | None = None,
    amount: float | None = None,
    second_tranche_confirmed: bool = False,
) -> dict[str, Any]:
    """Record an actual buy fill after applying all portfolio risk limits.

    Supply exactly one of ``shares`` or ``amount``.  ``amount`` is the actual
    CNY fill amount and is converted to shares at the reported actual price.
    Each tranche is capped at ``MAX_SINGLE_TRANCHE_CNY`` (CNY 11,000), allowing
    10% execution/board-lot tolerance around the approximately CNY 10,000 plan.
    """
    updated = _copy_state(state)
    code = _code(code)
    fill_shares, fill_cost = _fill(price, shares, amount)
    _assert_buys_allowed(updated)
    if fill_cost > MAX_SINGLE_TRANCHE_CNY:
        raise ValueError("single tranche cannot exceed CNY 11,000")

    positions = updated["positions"]
    position = positions.get(code)
    if position is None:
        if len(positions) >= MAX_OPEN_POSITIONS:
            raise ValueError("at most two open ETFs are allowed")
        cycle_id = int(updated["next_cycle_by_code"].get(code, 1))
        position = {
            "code": code,
            "cycle_id": cycle_id,
            "shares": 0.0,
            "cost_basis_cny": 0.0,
            "weighted_cost_cny": 0.0,
            "tranche_count": 0,
            "entry_tranche_costs_cny": [],
            "alert_acknowledged": _empty_alert_flags(),
        }
        positions[code] = position
    elif int(position["tranche_count"]) >= MAX_TRANCHES_PER_ETF:
        raise ValueError("at most two tranches per ETF are allowed")
    elif (
        int(position["tranche_count"]) == 1
        and second_tranche_confirmed is not True
    ):
        raise ValueError("second tranche requires external confirmation")

    if float(position["cost_basis_cny"]) + fill_cost > MAX_ETF_COST_CNY + _EPSILON:
        raise ValueError("per-ETF cost cannot exceed CNY 20,000")
    if _cost_exposure(updated) + fill_cost > MAX_RISK_EXPOSURE_CNY + _EPSILON:
        raise ValueError("risk-asset exposure cannot exceed CNY 40,000")
    post_buy_cash = _money(float(updated["cash_cny"]) - fill_cost)
    if post_buy_cash < float(updated["cash_reserve_cny"]):
        raise ValueError("buy would breach the portfolio cash reserve")
    if float(updated["cash_cny"]) < fill_cost:
        raise ValueError("insufficient cash for buy")

    position["shares"] = _quantity(float(position["shares"]) + fill_shares)
    position["cost_basis_cny"] = _money(float(position["cost_basis_cny"]) + fill_cost)
    position["weighted_cost_cny"] = _money(
        float(position["cost_basis_cny"]) / float(position["shares"])
    )
    position["entry_tranche_costs_cny"].append(fill_cost)
    position["tranche_count"] = int(position["tranche_count"]) + 1
    updated["cash_cny"] = post_buy_cash
    validate_portfolio_state(updated)
    return updated


def record_sell(
    state: Mapping[str, Any],
    code: str,
    price: float,
    *,
    shares: float | None = None,
    amount: float | None = None,
) -> dict[str, Any]:
    """Record an actual partial or full sell fill at its reported price."""
    updated = _copy_state(state)
    code = _code(code)
    sell_shares, proceeds = _fill(price, shares, amount)
    position = updated["positions"].get(code)
    if position is None:
        raise ValueError(f"no open position for {code}")
    held_shares = float(position["shares"])
    if sell_shares > held_shares:
        raise ValueError("cannot sell more shares than are held")

    cost_basis = float(position["cost_basis_cny"])
    remaining_shares = held_shares - sell_shares
    is_full_close = sell_shares == held_shares
    if is_full_close:
        remaining_basis = 0.0
    else:
        remaining_shares = _quantity(remaining_shares)
        remaining_basis = _money(cost_basis * remaining_shares / held_shares)
    released_cost = cost_basis - remaining_basis
    updated["cash_cny"] = _money(float(updated["cash_cny"]) + proceeds)
    updated["realized_pnl_cny"] = _money(
        float(updated["realized_pnl_cny"]) + proceeds - released_cost
    )

    if is_full_close:
        cycle_id = int(position["cycle_id"])
        del updated["positions"][code]
        updated["next_cycle_by_code"][code] = cycle_id + 1
        if updated["positions"]:
            updated["valuation_required"] = True
        else:
            updated["valuation_required"] = False
            _update_cash_only_drawdown(updated)
            _maybe_complete_risk_reset(updated)
        validate_portfolio_state(updated)
        return updated

    position["shares"] = remaining_shares
    position["cost_basis_cny"] = remaining_basis
    position["weighted_cost_cny"] = _money(
        float(position["cost_basis_cny"]) / float(position["shares"])
    )
    updated["valuation_required"] = True
    validate_portfolio_state(updated)
    return updated


def portfolio_equity(state: Mapping[str, Any], prices: Mapping[str, float]) -> dict[str, float]:
    """Calculate cash, realized, unrealized, market-value, and total equity."""
    validate_portfolio_state(state)
    market_value = 0.0
    cost_basis = 0.0
    for code, position in state["positions"].items():
        price = _price_for(prices, code)
        market_value += float(position["shares"]) * price
        cost_basis += float(position["cost_basis_cny"])
    unrealized = market_value - cost_basis
    return {
        "cash_cny": _money(float(state["cash_cny"])),
        "market_value_cny": _money(market_value),
        "cost_basis_cny": _money(cost_basis),
        "realized_pnl_cny": _money(float(state["realized_pnl_cny"])),
        "unrealized_pnl_cny": _money(unrealized),
        "equity_cny": _money(float(state["cash_cny"]) + market_value),
    }


def update_drawdown(
    state: Mapping[str, Any], prices: Mapping[str, float]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Update the high watermark and emit 2% risk-exit alerts once per breach."""
    updated = _copy_state(state)
    equity = portfolio_equity(updated, prices)["equity_cny"]
    high_watermark = max(float(updated["high_watermark_equity_cny"]), equity)
    drawdown = max(0.0, (high_watermark - equity) / high_watermark)
    updated["high_watermark_equity_cny"] = _money(high_watermark)
    updated["drawdown_pct"] = drawdown
    updated["valuation_required"] = False

    alerts: list[dict[str, Any]] = []
    if drawdown >= RISK_EXIT_DRAWDOWN_PCT:
        if not bool(updated["risk_drawdown_active"]):
            _start_risk_cycle(updated)
        updated["risk_drawdown_active"] = True
        for code, position in updated["positions"].items():
            flags = position["alert_acknowledged"]
            if not flags["risk_exit"]:
                flags["risk_exit"] = True
                alerts.append(
                    _alert(code, "risk_exit", _price_for(prices, code), drawdown_pct=drawdown)
                )
    else:
        updated["risk_drawdown_active"] = False
        for position in updated["positions"].values():
            position["alert_acknowledged"]["risk_exit"] = False
    _maybe_complete_risk_reset(updated)
    validate_portfolio_state(updated)
    return updated, alerts


def advance_cooldown(
    state: Mapping[str, Any],
    trading_day: str,
    *,
    confirmed_trading_session: bool,
) -> dict[str, Any]:
    """Consume a confirmed trading session once for the active cooldown."""
    updated = _copy_state(state)
    _valid_trading_day(trading_day)
    if confirmed_trading_session is not True:
        raise ValueError("trading session must be authoritatively confirmed")
    if int(updated["cooldown_remaining_trading_days"]) <= 0:
        return updated
    processed_days = updated["processed_cooldown_trading_days"]
    if trading_day not in processed_days:
        updated["cooldown_remaining_trading_days"] -= 1
        updated["last_cooldown_trading_day"] = trading_day
        processed_days.append(trading_day)
    _maybe_complete_risk_reset(updated)
    validate_portfolio_state(updated)
    return updated


def evaluate_position_alerts(
    state: Mapping[str, Any],
    prices: Mapping[str, float],
    invalidated_codes: Iterable[str] | Mapping[str, bool] = (),
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Emit deduplicated profit and stop alerts for the current holding cycles."""
    updated = _copy_state(state)
    invalidated = _invalidated_set(invalidated_codes)
    alerts: list[dict[str, Any]] = []
    for code, position in updated["positions"].items():
        price = _price_for(prices, code)
        exact_cost_per_share = (
            float(position["cost_basis_cny"]) / float(position["shares"])
        )
        return_pct = price / exact_cost_per_share - 1
        flags = position["alert_acknowledged"]
        if return_pct >= PROFIT_4_5_PCT - _EPSILON and not flags["profit_4_5"]:
            flags["profit_4_5"] = True
            alerts.append(_alert(code, "profit_4_5", price, return_pct=return_pct))
        if return_pct >= PROFIT_5_PCT - _EPSILON and not flags["profit_5"]:
            flags["profit_5"] = True
            alerts.append(_alert(code, "profit_5", price, return_pct=return_pct))
        if (return_pct <= STOP_LOSS_PCT + _EPSILON or code in invalidated) and not flags["stop"]:
            flags["stop"] = True
            alerts.append(
                _alert(
                    code,
                    "stop",
                    price,
                    return_pct=return_pct,
                    reason="signal_invalidation" if code in invalidated else "stop_loss",
                )
            )
    validate_portfolio_state(updated)
    return updated, alerts


def _assert_buys_allowed(state: Mapping[str, Any]) -> None:
    if int(state["cooldown_remaining_trading_days"]) > 0:
        raise ValueError("buy blocked during cooldown")
    if bool(state["valuation_required"]):
        raise ValueError("buy blocked until complete portfolio valuation")
    if bool(state["risk_reset_pending"]):
        raise ValueError("buy blocked until risk reset completes")
    if float(state["drawdown_pct"]) >= BUY_BLOCK_DRAWDOWN_PCT:
        raise ValueError("buy blocked by portfolio drawdown")


def _cost_exposure(state: Mapping[str, Any]) -> float:
    return sum(float(position["cost_basis_cny"]) for position in state["positions"].values())


def _fill(price: float, shares: float | None, amount: float | None) -> tuple[float, float]:
    actual_price = _positive_number(price, "price")
    if (shares is None) == (amount is None):
        raise ValueError("provide exactly one of shares or amount")
    if shares is not None:
        raw_quantity = _positive_number(shares, "shares")
        quantity = _quantity(raw_quantity)
        cost = _money(actual_price * raw_quantity)
    else:
        raw_cost = _positive_number(amount, "amount")
        quantity = _quantity(raw_cost / actual_price)
        cost = _money(raw_cost)
    if quantity <= 0 or cost <= 0:
        raise ValueError("rounded fill shares and amount must both be positive")
    return quantity, cost


def _copy_state(state: Mapping[str, Any]) -> dict[str, Any]:
    validate_portfolio_state(state)
    return deepcopy(dict(state))


def validate_portfolio_state(state: Mapping[str, Any]) -> None:
    """Strictly validate the complete persisted portfolio state schema."""
    if not isinstance(state, Mapping) or set(state.keys()) != _STATE_KEYS:
        raise ValueError("invalid portfolio state fields")
    _require_integer(
        state["schema_version"],
        "schema_version",
        minimum=PORTFOLIO_SCHEMA_VERSION,
        maximum=PORTFOLIO_SCHEMA_VERSION,
    )
    initial_capital = _require_money(
        state["initial_capital_cny"], "initial_capital_cny", minimum=0.01
    )
    cash_reserve = _require_money(
        state["cash_reserve_cny"], "cash_reserve_cny", minimum=0.0
    )
    expected_reserve = _money(max(0.0, initial_capital - MAX_RISK_EXPOSURE_CNY))
    if cash_reserve != expected_reserve:
        raise ValueError("cash_reserve_cny does not match portfolio limits")
    cash = _require_money(state["cash_cny"], "cash_cny", minimum=0.0)
    if cash + _EPSILON < cash_reserve:
        raise ValueError("cash_cny cannot be below the cash reserve")
    realized_pnl = _require_money(state["realized_pnl_cny"], "realized_pnl_cny")
    high_watermark = _require_money(
        state["high_watermark_equity_cny"],
        "high_watermark_equity_cny",
        minimum=0.01,
    )
    drawdown = _require_number(state["drawdown_pct"], "drawdown_pct")
    if not 0.0 <= drawdown <= 1.0:
        raise ValueError("drawdown_pct must be between 0 and 1")
    for field in ("risk_drawdown_active", "risk_reset_pending", "valuation_required"):
        if type(state[field]) is not bool:
            raise ValueError(f"{field} must be a boolean")
    if state["risk_drawdown_active"] and not state["risk_reset_pending"]:
        raise ValueError("active risk drawdown requires a pending reset")

    cooldown_remaining = _require_integer(
        state["cooldown_remaining_trading_days"],
        "cooldown_remaining_trading_days",
        minimum=0,
        maximum=COOLDOWN_TRADING_DAYS,
    )
    processed_days = state["processed_cooldown_trading_days"]
    if not isinstance(processed_days, list) or len(processed_days) > COOLDOWN_TRADING_DAYS:
        raise ValueError("processed cooldown days must be a bounded list")
    if len(processed_days) != len(set(processed_days)):
        raise ValueError("processed cooldown days must be unique")
    for trading_day in processed_days:
        _valid_trading_day(trading_day)
    last_day = state["last_cooldown_trading_day"]
    if last_day is not None:
        _valid_trading_day(last_day)
    if processed_days and last_day != processed_days[-1]:
        raise ValueError("last cooldown day must match the latest processed day")
    if not processed_days and last_day is not None:
        raise ValueError("last cooldown day requires a processed day")

    cycles = state["next_cycle_by_code"]
    if not isinstance(cycles, dict):
        raise ValueError("next_cycle_by_code must be an object")
    for code, cycle_id in cycles.items():
        _code(code)
        _require_integer(cycle_id, f"next cycle for {code}", minimum=1)

    positions = state["positions"]
    if not isinstance(positions, dict) or len(positions) > MAX_OPEN_POSITIONS:
        raise ValueError("positions must contain at most two ETFs")
    if state["valuation_required"] and not positions:
        raise ValueError("valuation cannot be required without an open position")
    exposure = 0.0
    for code, position in positions.items():
        _code(code)
        if not isinstance(position, Mapping) or set(position.keys()) != _POSITION_KEYS:
            raise ValueError(f"invalid position fields for {code}")
        if position["code"] != code:
            raise ValueError(f"position code mismatch for {code}")
        _require_integer(position["cycle_id"], f"cycle_id for {code}", minimum=1)
        shares = _require_number(position["shares"], f"shares for {code}")
        if shares <= 0 or _quantity(shares) != shares:
            raise ValueError(f"shares for {code} must be positive and normalized")
        cost_basis = _require_money(
            position["cost_basis_cny"], f"cost basis for {code}", minimum=0.01
        )
        if cost_basis > MAX_ETF_COST_CNY:
            raise ValueError(f"cost basis for {code} exceeds the per-ETF limit")
        weighted_cost = _require_money(
            position["weighted_cost_cny"], f"weighted cost for {code}", minimum=0.01
        )
        if weighted_cost != _money(cost_basis / shares):
            raise ValueError(f"weighted cost for {code} is inconsistent")
        tranche_count = _require_integer(
            position["tranche_count"],
            f"tranche count for {code}",
            minimum=1,
            maximum=MAX_TRANCHES_PER_ETF,
        )
        entry_costs = position["entry_tranche_costs_cny"]
        if not isinstance(entry_costs, list) or len(entry_costs) != tranche_count:
            raise ValueError(f"entry tranche history length is invalid for {code}")
        entry_cost_total = 0.0
        for index, entry_cost in enumerate(entry_costs, start=1):
            normalized_cost = _require_money(
                entry_cost,
                f"entry tranche {index} cost for {code}",
                minimum=0.01,
            )
            if normalized_cost > MAX_SINGLE_TRANCHE_CNY:
                raise ValueError(f"entry tranche {index} for {code} exceeds the limit")
            entry_cost_total += normalized_cost
        if _money(entry_cost_total) < cost_basis:
            raise ValueError(f"entry tranche history is below current cost basis for {code}")
        flags = position["alert_acknowledged"]
        if not isinstance(flags, Mapping) or set(flags.keys()) != _ALERT_FLAG_KEYS:
            raise ValueError(f"invalid alert flags for {code}")
        if any(type(value) is not bool for value in flags.values()):
            raise ValueError(f"alert flags for {code} must be booleans")
        exposure += cost_basis
    if exposure > MAX_RISK_EXPOSURE_CNY:
        raise ValueError("portfolio exposure exceeds CNY 40,000")
    expected_cash = _money(initial_capital + realized_pnl - exposure)
    if cash != expected_cash:
        raise ValueError("cash accounting identity is inconsistent")
    if not positions:
        if high_watermark < cash:
            raise ValueError("cash-only high watermark cannot be below cash")
        expected_drawdown = max(
            0.0, (high_watermark - cash) / high_watermark
        )
        if abs(drawdown - expected_drawdown) > _EPSILON:
            raise ValueError("cash-only drawdown_pct is inconsistent")
        expected_active = expected_drawdown >= RISK_EXIT_DRAWDOWN_PCT
        if state["risk_drawdown_active"] is not expected_active:
            raise ValueError("cash-only risk_drawdown_active is inconsistent")
        if expected_drawdown >= BUY_BLOCK_DRAWDOWN_PCT:
            if not state["risk_reset_pending"] or cooldown_remaining <= 0:
                raise ValueError("cash-only drawdown requires an active reset cooldown")
        elif state["risk_reset_pending"] or cooldown_remaining != 0:
            raise ValueError("cash-only recovered state cannot have a pending cooldown")


def _empty_alert_flags() -> dict[str, bool]:
    return {"profit_4_5": False, "profit_5": False, "stop": False, "risk_exit": False}


def _start_risk_cycle(state: dict[str, Any]) -> None:
    state["risk_reset_pending"] = True
    state["cooldown_remaining_trading_days"] = COOLDOWN_TRADING_DAYS
    state["last_cooldown_trading_day"] = None
    state["processed_cooldown_trading_days"] = []


def _update_cash_only_drawdown(state: dict[str, Any]) -> None:
    equity = float(state["cash_cny"])
    high_watermark = max(float(state["high_watermark_equity_cny"]), equity)
    drawdown = max(0.0, (high_watermark - equity) / high_watermark)
    state["high_watermark_equity_cny"] = _money(high_watermark)
    state["drawdown_pct"] = drawdown
    if drawdown >= BUY_BLOCK_DRAWDOWN_PCT and not state["risk_reset_pending"]:
        _start_risk_cycle(state)
    state["risk_drawdown_active"] = drawdown >= RISK_EXIT_DRAWDOWN_PCT


def _maybe_complete_risk_reset(state: dict[str, Any]) -> None:
    if (
        state["risk_reset_pending"]
        and int(state["cooldown_remaining_trading_days"]) == 0
        and not state["positions"]
    ):
        state["high_watermark_equity_cny"] = _money(float(state["cash_cny"]))
        state["drawdown_pct"] = 0.0
        state["risk_drawdown_active"] = False
        state["risk_reset_pending"] = False
        state["valuation_required"] = False


def _invalidated_set(values: Iterable[str] | Mapping[str, bool]) -> set[str]:
    if isinstance(values, Mapping):
        return {str(code) for code, invalidated in values.items() if invalidated}
    return {str(code) for code in values}


def _alert(code: str, kind: str, price: float, **details: float | str) -> dict[str, Any]:
    return {"code": code, "kind": kind, "price_cny": _money(price), **details}


def _price_for(prices: Mapping[str, float], code: str) -> float:
    if code not in prices:
        raise ValueError(f"missing price for {code}")
    return _positive_number(prices[code], f"price for {code}")


def _code(value: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError("ETF code must be a non-empty string")
    return value


def _require_number(value: object, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(f"{label} must be a finite number")
    return float(value)


def _require_money(
    value: object, label: str, *, minimum: float | None = None
) -> float:
    number = _require_number(value, label)
    if _money(number) != number:
        raise ValueError(f"{label} must use cent precision")
    if minimum is not None and number < minimum:
        raise ValueError(f"{label} is below its minimum")
    return number


def _require_integer(
    value: object,
    label: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer")
    if minimum is not None and value < minimum:
        raise ValueError(f"{label} is below its minimum")
    if maximum is not None and value > maximum:
        raise ValueError(f"{label} exceeds its maximum")
    return value


def _positive_number(value: float, label: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or value <= 0
    ):
        raise ValueError(f"{label} must be a positive number")
    return float(value)


def _valid_trading_day(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("trading day must be an ISO YYYY-MM-DD string")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as error:
        raise ValueError("trading day must be an ISO YYYY-MM-DD string") from error
    if parsed.isoformat() != value:
        raise ValueError("trading day must be an ISO YYYY-MM-DD string")


def _money(value: float) -> float:
    return round(float(value), 2)


def _quantity(value: float) -> float:
    return round(float(value), 8)
