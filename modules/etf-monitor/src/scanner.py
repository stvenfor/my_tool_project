"""High-confidence ETF candidate scanner and independent position monitoring."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Iterable, Mapping, Optional

from .market_data import (
    MarketDataError,
    MarketDataProvider,
    MarketSnapshot,
    collect_current_quote,
    collect_market_snapshot,
)
from .portfolio import evaluate_position_alerts, update_drawdown


MIN_BARS = 61
MIN_AVERAGE_TURNOVER_CNY = 50_000_000
MIN_AUM_CNY = 200_000_000
DOMESTIC_PREMIUM_CAP_PCT = 0.5
CROSS_BORDER_PREMIUM_CAP_PCT = 1.0
BREAKOUT_ACTIVITY_MULTIPLE = 1.2
MAX_DAILY_GAIN_PCT = 3.0
MAX_DISTANCE_ABOVE_MA20_PCT = 5.0


def scan_etf(
    record: Mapping[str, Any],
    provider: MarketDataProvider,
    *,
    as_of: Optional[datetime] = None,
) -> dict[str, Any]:
    """Collect and evaluate one ETF, returning data errors rather than guessing."""
    observed_at = as_of or datetime.now().astimezone()
    try:
        snapshot = collect_market_snapshot(record, provider, as_of=observed_at)
    except MarketDataError as exc:
        timestamp = exc.source_timestamp or observed_at
        return {
            "code": str(record.get("code", "")),
            "status": "DATA_ERROR",
            "source_timestamp": timestamp.isoformat(),
            "reasons": [exc.reason],
        }
    return evaluate_snapshot(snapshot)


def evaluate_snapshot(snapshot: MarketSnapshot) -> dict[str, Any]:
    """Apply every binding scanner gate to a validated market snapshot."""
    reasons: list[str] = []
    bars = snapshot.bars
    benchmark = snapshot.benchmark_bars
    if len(bars) < MIN_BARS or len(benchmark) < MIN_BARS:
        reasons.append("insufficient_bars")
    if len(bars) < 21 or len(benchmark) < 21:
        return _scan_result(snapshot, "NO_ACTION", reasons)

    latest = bars[-1]
    recent_20 = bars[-20:]
    previous_20 = bars[-21:-1]
    ma20 = _average(bar.close for bar in recent_20)
    previous_ma20 = _average(bar.close for bar in previous_20)
    ma60 = _average(bar.close for bar in bars[-60:])
    average_turnover = _average(bar.turnover_cny for bar in recent_20)

    if average_turnover < MIN_AVERAGE_TURNOVER_CNY:
        reasons.append("average_turnover_below_cny_50000000")
    if snapshot.aum_cny < MIN_AUM_CNY:
        reasons.append("aum_below_cny_200000000")
    premium_cap = (
        DOMESTIC_PREMIUM_CAP_PCT
        if snapshot.market.upper() == "CN"
        else CROSS_BORDER_PREMIUM_CAP_PCT
    )
    if snapshot.premium_pct > premium_cap:
        reasons.append(f"premium_above_{premium_cap:.1f}_pct")
    if latest.close <= ma20:
        reasons.append("close_not_above_ma20")
    if latest.close <= ma60:
        reasons.append("close_not_above_ma60")
    if ma20 <= previous_ma20:
        reasons.append("ma20_not_rising")

    etf_return_20 = latest.close / bars[-21].close - 1
    benchmark_return_20 = benchmark[-1].close / benchmark[-21].close - 1
    if etf_return_20 - benchmark_return_20 <= 0:
        reasons.append("relative_return_not_positive")

    previous_high = max(bar.high for bar in previous_20)
    previous_turnover = _average(bar.turnover_cny for bar in previous_20)
    previous_volume = _average(bar.volume for bar in previous_20)
    activity_confirmed = (
        latest.turnover_cny >= BREAKOUT_ACTIVITY_MULTIPLE * previous_turnover
        or latest.volume >= BREAKOUT_ACTIVITY_MULTIPLE * previous_volume
    )
    breakout = latest.close > previous_high and activity_confirmed
    pullback_reclaim = latest.low <= ma20 and latest.close > ma20
    if not breakout and not pullback_reclaim:
        reasons.append("no_valid_entry_pattern")

    daily_gain_pct = (snapshot.current_price / snapshot.previous_close - 1) * 100
    if daily_gain_pct > MAX_DAILY_GAIN_PCT:
        reasons.append("daily_gain_above_3_pct")
    distance_pct = (latest.close / ma20 - 1) * 100
    if distance_pct > MAX_DISTANCE_ABOVE_MA20_PCT:
        reasons.append("distance_above_ma20_over_5_pct")

    if snapshot.catalyst.primary_confirmed is not True:
        reasons.append("primary_catalyst_not_confirmed")
    if snapshot.catalyst.corroborated is not True:
        reasons.append("independent_corroboration_missing")
    if snapshot.catalyst.adverse is not False:
        reasons.append("adverse_catalyst_present")

    if reasons:
        return _scan_result(snapshot, "NO_ACTION", reasons)
    entry_reason = "breakout_confirmed" if breakout else "pullback_reclaim_confirmed"
    return _scan_result(
        snapshot,
        "BUY_CANDIDATE",
        [entry_reason, "all_high_confidence_gates_passed"],
    )


def monitor_positions(
    state: Mapping[str, Any],
    prices: Mapping[str, float],
    *,
    source_timestamp: datetime,
    invalidated_codes: Iterable[str] = (),
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Run profit, stop, invalidation, and drawdown checks without catalysts."""
    if not isinstance(source_timestamp, datetime) or source_timestamp.tzinfo is None:
        raise ValueError("source timestamp must be timezone-aware")
    updated, position_alerts = evaluate_position_alerts(
        state, prices, invalidated_codes=invalidated_codes
    )
    updated, drawdown_alerts = update_drawdown(updated, prices)
    alerts = position_alerts + drawdown_alerts
    return updated, {
        "status": "POSITION_ALERT" if alerts else "NO_ACTION",
        "source_timestamp": source_timestamp.isoformat(),
        "reasons": ["position_monitoring_completed"],
        "alerts": alerts,
    }


def monitor_positions_from_provider(
    state: Mapping[str, Any],
    provider: MarketDataProvider,
    *,
    as_of: Optional[datetime] = None,
    invalidated_codes: Iterable[str] = (),
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    """Validate held-position quotes without fetching catalyst or scan inputs."""
    observed_at = as_of or datetime.now().astimezone()
    prices: dict[str, float] = {}
    timestamps = []
    try:
        for code in state.get("positions", {}):
            quote = collect_current_quote(str(code), provider, as_of=observed_at)
            prices[str(code)] = quote.current_price
            timestamps.append(quote.source_timestamp)
    except MarketDataError as exc:
        timestamp = exc.source_timestamp or observed_at
        return state, {
            "status": "DATA_ERROR",
            "source_timestamp": timestamp.isoformat(),
            "reasons": [exc.reason],
            "alerts": [],
        }
    source_timestamp = min(timestamps) if timestamps else observed_at
    return monitor_positions(
        state,
        prices,
        source_timestamp=source_timestamp,
        invalidated_codes=invalidated_codes,
    )


def _scan_result(
    snapshot: MarketSnapshot, status: str, reasons: list[str]
) -> dict[str, Any]:
    return {
        "code": snapshot.code,
        "status": status,
        "source_timestamp": snapshot.source_timestamp.isoformat(),
        "reasons": reasons,
    }


def _average(values: Iterable[float]) -> float:
    materialized = list(values)
    return sum(materialized) / len(materialized)
