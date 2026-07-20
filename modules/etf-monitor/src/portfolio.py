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
MAX_OPEN_POSITIONS = 2
MAX_TRANCHES_PER_ETF = 2
MAX_ETF_COST_CNY = 20_000
PROFIT_4_5_PCT = 0.045
PROFIT_5_PCT = 0.05
STOP_LOSS_PCT = -0.03
BUY_BLOCK_DRAWDOWN_PCT = 0.015
RISK_EXIT_DRAWDOWN_PCT = 0.02
COOLDOWN_TRADING_DAYS = 10

_EPSILON = 1e-8


def new_portfolio_state(initial_capital_cny: float = INITIAL_CAPITAL_CNY) -> dict[str, Any]:
    """Create the JSON-compatible initial persistent portfolio state."""
    capital = _positive_number(initial_capital_cny, "initial capital")
    return {
        "schema_version": 1,
        "initial_capital_cny": _money(capital),
        "cash_cny": _money(capital),
        "realized_pnl_cny": 0.0,
        "high_watermark_equity_cny": _money(capital),
        "drawdown_pct": 0.0,
        "risk_drawdown_active": False,
        "cooldown_remaining_trading_days": 0,
        "last_cooldown_trading_day": None,
        "processed_cooldown_trading_days": [],
        "next_cycle_by_code": {},
        "positions": {},
    }


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
    """
    updated = _copy_state(state)
    code = _code(code)
    fill_shares, fill_cost = _fill(price, shares, amount)
    _assert_buys_allowed(updated)

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
    if float(updated["cash_cny"]) + _EPSILON < fill_cost:
        raise ValueError("insufficient cash for buy")

    position["shares"] = _quantity(float(position["shares"]) + fill_shares)
    position["cost_basis_cny"] = _money(float(position["cost_basis_cny"]) + fill_cost)
    position["weighted_cost_cny"] = _money(
        float(position["cost_basis_cny"]) / float(position["shares"])
    )
    position["tranche_count"] = int(position["tranche_count"]) + 1
    updated["cash_cny"] = _money(float(updated["cash_cny"]) - fill_cost)
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
    if sell_shares > held_shares + _EPSILON:
        raise ValueError("cannot sell more shares than are held")

    cost_basis = float(position["cost_basis_cny"])
    remaining_shares = held_shares - sell_shares
    is_full_close = remaining_shares <= _EPSILON
    released_cost = (
        cost_basis if is_full_close else cost_basis * sell_shares / held_shares
    )
    updated["cash_cny"] = _money(float(updated["cash_cny"]) + proceeds)
    updated["realized_pnl_cny"] = _money(
        float(updated["realized_pnl_cny"]) + proceeds - released_cost
    )

    if is_full_close:
        cycle_id = int(position["cycle_id"])
        del updated["positions"][code]
        updated["next_cycle_by_code"][code] = cycle_id + 1
        return updated

    position["shares"] = _quantity(remaining_shares)
    position["cost_basis_cny"] = _money(cost_basis - released_cost)
    position["weighted_cost_cny"] = _money(
        float(position["cost_basis_cny"]) / float(position["shares"])
    )
    return updated


def portfolio_equity(state: Mapping[str, Any], prices: Mapping[str, float]) -> dict[str, float]:
    """Calculate cash, realized, unrealized, market-value, and total equity."""
    _require_state(state)
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

    alerts: list[dict[str, Any]] = []
    if drawdown >= RISK_EXIT_DRAWDOWN_PCT:
        if not bool(updated["risk_drawdown_active"]):
            updated["cooldown_remaining_trading_days"] = COOLDOWN_TRADING_DAYS
            updated["last_cooldown_trading_day"] = None
            updated["processed_cooldown_trading_days"] = []
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
    return updated, alerts


def _assert_buys_allowed(state: Mapping[str, Any]) -> None:
    if int(state["cooldown_remaining_trading_days"]) > 0:
        raise ValueError("buy blocked during cooldown")
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
    _require_state(state)
    updated = deepcopy(dict(state))
    updated.setdefault("processed_cooldown_trading_days", [])
    return updated


def _require_state(state: Mapping[str, Any]) -> None:
    required = {
        "cash_cny",
        "realized_pnl_cny",
        "high_watermark_equity_cny",
        "drawdown_pct",
        "risk_drawdown_active",
        "cooldown_remaining_trading_days",
        "last_cooldown_trading_day",
        "next_cycle_by_code",
        "positions",
    }
    if not isinstance(state, Mapping) or required - state.keys():
        raise ValueError("invalid portfolio state")


def _empty_alert_flags() -> dict[str, bool]:
    return {"profit_4_5": False, "profit_5": False, "stop": False, "risk_exit": False}


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
