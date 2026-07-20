#!/usr/bin/env python3
"""Stable JSON CLI for the local, advisory-only ETF monitor."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence

from src.audit import (
    EXACT_DUPLICATE_GROUPS,
    choose_recommendation,
    is_eligible,
    load_universe,
    sector_market_groups,
    tradable_records,
)
from src.market_data import MarketDataError, SHANGHAI_TZ, collect_trading_session
from src.portfolio import (
    BUY_BLOCK_DRAWDOWN_PCT,
    MAX_ETF_COST_CNY,
    MAX_OPEN_POSITIONS,
    MAX_RISK_EXPOSURE_CNY,
    MAX_SINGLE_TRANCHE_CNY,
    MAX_TRANCHES_PER_ETF,
    advance_cooldown,
    new_portfolio_state,
    record_buy,
    record_sell,
    validate_portfolio_state,
)
from src.scanner import monitor_positions_from_provider, scan_etf


SCHEMA_VERSION = 1
TARGET_TRANCHE_CNY = 10_000
MODULE_ROOT = Path(__file__).resolve().parent
STATE_DIR = MODULE_ROOT / "state"
STATE_PATH = STATE_DIR / "portfolio.json"
LIVE_PROVIDER_REASONS = [
    "missing_live_trading_calendar_provider",
    "missing_live_catalyst_provider",
    "missing_live_benchmark_mapping",
]
CATALYST_PENDING_REASONS = {
    "primary_catalyst_not_confirmed",
    "independent_corroboration_missing",
}


class JsonArgumentParser(argparse.ArgumentParser):
    """Raise parse errors so stdout remains a single JSON document."""

    def error(self, message: str) -> None:
        raise ValueError(message)


class JsonFixtureProvider:
    """Offline provider backed by the documented JSON fixture contract."""

    def __init__(
        self,
        path: Path,
        records: Sequence[Mapping[str, Any]],
        *,
        position_codes: Sequence[str] = (),
    ) -> None:
        try:
            raw = json.loads(
                path.read_text(encoding="utf-8"),
                parse_constant=_reject_json_constant,
            )
            if not isinstance(raw, dict):
                raise ValueError("provider fixture must be a JSON object")
            self.payload = _typed_fixture(raw)
            self.as_of = self.payload.get("as_of")
            if self.as_of is not None and not isinstance(self.as_of, datetime):
                raise ValueError("provider fixture as_of must be an ISO timestamp")
        except (
            argparse.ArgumentTypeError,
            json.JSONDecodeError,
            OSError,
            TypeError,
            ValueError,
        ) as exc:
            raise ValueError(f"invalid provider fixture: {exc}") from exc
        self.scan_codes = _unique(str(record["code"]) for record in records)
        self.quote_codes = _unique(list(self.scan_codes) + list(position_codes))
        self.multicode_scan = len(self.scan_codes) > 1
        self.multicode_quotes = len(self.quote_codes) > 1

    def get_current_quotes(self, code: str) -> Any:
        return deepcopy(
            _fixture_value(
                self.payload,
                "current_quotes",
                code,
                require_mapping=self.multicode_quotes,
                mapping_kind="code",
            )
        )

    def get_daily_bars(self, code: str) -> Any:
        return deepcopy(
            _fixture_value(
                self.payload,
                "daily_bars",
                code,
                require_mapping=self.multicode_scan,
                mapping_kind="code",
            )
        )

    def get_aum(self, code: str) -> Any:
        return deepcopy(
            _fixture_value(
                self.payload,
                "aum",
                code,
                require_mapping=self.multicode_scan,
                mapping_kind="code",
            )
        )

    def get_premium(self, code: str) -> Any:
        return deepcopy(
            _fixture_value(
                self.payload,
                "premium",
                code,
                require_mapping=self.multicode_scan,
                mapping_kind="code",
            )
        )

    def get_benchmark_bars(self, benchmark: str) -> Any:
        return deepcopy(
            _fixture_value(
                self.payload,
                "benchmark_bars",
                benchmark,
                require_mapping=self.multicode_scan,
                mapping_kind="benchmark",
            )
        )

    def get_trading_calendar(self, session_date: date) -> Any:
        calendar = self.payload.get("calendar")
        if isinstance(calendar, dict) and session_date.isoformat() in calendar:
            return deepcopy(calendar[session_date.isoformat()])
        return deepcopy(calendar)

    def get_catalyst(self, code: str) -> Any:
        return deepcopy(
            _fixture_value(
                self.payload,
                "catalyst",
                code,
                require_mapping=self.multicode_scan,
                mapping_kind="code",
            )
        )


def fixture_payload_from_provider(provider: Any) -> dict[str, Any]:
    """Serialize a provider-like object into the offline fixture schema."""
    return _json_ready(
        {
            "as_of": provider.as_of,
            "current_quotes": provider.quotes,
            "daily_bars": provider.bars,
            "aum": provider.aum,
            "premium": provider.premium,
            "benchmark_bars": provider.benchmark,
            "calendar": provider.calendar,
            "catalyst": provider.catalyst,
        }
    )


def build_parser() -> argparse.ArgumentParser:
    parser = JsonArgumentParser(prog="etf-monitor")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("audit", help="summarize the reviewed static universe")

    buy = commands.add_parser("record-buy", help="record an actual broker buy fill")
    buy.add_argument("code")
    buy.add_argument("--price", type=float, required=True)
    buy_fill = buy.add_mutually_exclusive_group(required=True)
    buy_fill.add_argument("--shares", type=float)
    buy_fill.add_argument("--amount", type=float)
    buy.add_argument("--confirm-second-tranche", action="store_true")

    sell = commands.add_parser("record-sell", help="record an actual broker sell fill")
    sell.add_argument("code")
    sell.add_argument("--price", type=float, required=True)
    sell_fill = sell.add_mutually_exclusive_group(required=True)
    sell_fill.add_argument("--shares", type=float)
    sell_fill.add_argument("--amount", type=float)

    for name in ("scan", "scheduled-check"):
        command = commands.add_parser(name)
        command.add_argument(
            "--code", action="append", dest="codes", required=name == "scan"
        )
        source = command.add_mutually_exclusive_group()
        source.add_argument("--fixture", type=Path)
        source.add_argument("--provider", choices=("public",), default="public")
        command.add_argument("--as-of", type=_aware_datetime)
        if name == "scheduled-check":
            command.add_argument("--invalidated-code", action="append", default=[])
    return parser


def execute(
    arguments: Sequence[str],
    *,
    provider: Any = None,
    state_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Execute one command and return its JSON-compatible result."""
    command = str(arguments[0]) if arguments else ""
    fallback_at = datetime.now(SHANGHAI_TZ)
    try:
        namespace = build_parser().parse_args(list(arguments))
        state_file = Path(state_path) if state_path is not None else STATE_PATH
        if namespace.command == "audit":
            return _audit_result()
        if namespace.command == "record-buy":
            return _record_buy_result(namespace, state_file)
        if namespace.command == "record-sell":
            return _record_sell_result(namespace, state_file)

        records = _scan_records(namespace.codes)
        if provider is None and namespace.fixture is not None:
            position_codes: list[str] = []
            if namespace.command == "scheduled-check":
                fixture_state = _load_state(state_file)
                positions = fixture_state["positions"]
                if not isinstance(positions, Mapping):
                    raise ValueError("invalid portfolio state")
                position_codes = [str(code) for code in positions]
            provider = JsonFixtureProvider(
                namespace.fixture,
                records,
                position_codes=position_codes,
            )
        observed_at = namespace.as_of or getattr(provider, "as_of", None)
        if observed_at is None:
            observed_at = datetime.now(SHANGHAI_TZ)
        if provider is None:
            return _unconfigured_live_result(namespace.command, records, observed_at)
        if namespace.command == "scan":
            return _scan_result(records, provider, observed_at)
        return _scheduled_result(
            records,
            provider,
            observed_at,
            state_file,
            namespace.invalidated_code,
        )
    except MarketDataError as exc:
        return _command_error_result(
            arguments,
            command,
            "DATA_ERROR",
            [exc.reason],
            source_timestamp=exc.source_timestamp or fallback_at,
        )
    except (KeyError, IndexError, OSError, TypeError, ValueError) as exc:
        return _command_error_result(
            arguments,
            command,
            "INPUT_ERROR",
            [str(exc)],
            source_timestamp=fallback_at,
        )


def main(
    arguments: Optional[Sequence[str]] = None,
    *,
    state_path: Optional[Path] = None,
) -> int:
    """Print exactly one canonical JSON object and return a useful exit code."""
    import sys

    result = execute(sys.argv[1:] if arguments is None else arguments, state_path=state_path)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    return 2 if result["status"] in {"INPUT_ERROR", "DATA_ERROR"} else 0


def _audit_result() -> dict[str, Any]:
    records = load_universe()
    result = _base_result("audit", "OK")
    result.update(
        {
            "record_count": len(records),
            "tradable_count": len(tradable_records(records)),
            "exact_duplicate_group_count": len(EXACT_DUPLICATE_GROUPS),
            "excluded_codes": sorted(
                str(record["code"]) for record in records if record["kind"] != "ETF"
            ),
            "reports": {
                "exact_duplicates": "reports/exact-duplicates.md",
                "sector_overlap": "reports/sector-overlap.md",
            },
        }
    )
    return result


def _record_buy_result(namespace: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    _require_tradable_code(namespace.code)
    state = _load_state(state_path)
    updated = record_buy(
        state,
        namespace.code,
        namespace.price,
        shares=namespace.shares,
        amount=namespace.amount,
        second_tranche_confirmed=namespace.confirm_second_tranche,
    )
    _write_state(state_path, updated)
    result = _base_result("record-buy", "RECORDED", reasons=["actual_fill_recorded"])
    result.update(
        {"code": namespace.code, "position": updated["positions"][namespace.code], "state": updated}
    )
    return result


def _record_sell_result(namespace: argparse.Namespace, state_path: Path) -> dict[str, Any]:
    _require_tradable_code(namespace.code)
    state = _load_state(state_path)
    updated = record_sell(
        state,
        namespace.code,
        namespace.price,
        shares=namespace.shares,
        amount=namespace.amount,
    )
    _write_state(state_path, updated)
    result = _base_result("record-sell", "RECORDED", reasons=["actual_fill_recorded"])
    result.update(
        {
            "code": namespace.code,
            "position": updated["positions"].get(namespace.code),
            "state": updated,
        }
    )
    return result


def _scan_result(records: Sequence[Mapping[str, Any]], provider: Any, observed_at: datetime) -> dict[str, Any]:
    results = [
        _advisory_scan(scan_etf(record, provider, as_of=observed_at))
        for record in records
    ]
    if any(result["status"] == "DATA_ERROR" for result in results):
        status = "DATA_ERROR"
    elif any(result["status"] == "BUY_CANDIDATE" for result in results):
        status = "BUY_CANDIDATE"
    else:
        status = "NO_ACTION"
    reasons = _unique(reason for result in results for reason in result["reasons"])
    result = _base_result("scan", status, reasons=reasons)
    result.update({"source_timestamp": _oldest_timestamp(results, observed_at), "results": results})
    return result


def _scheduled_result(
    records: Sequence[Mapping[str, Any]],
    provider: Any,
    observed_at: datetime,
    state_path: Path,
    invalidated_codes: Sequence[str],
) -> dict[str, Any]:
    state = _load_state(state_path)
    try:
        session = collect_trading_session(provider, observed_at)
    except MarketDataError as exc:
        return _scheduled_terminal_result(
            "DATA_ERROR",
            [exc.reason],
            exc.source_timestamp or observed_at,
        )
    if session.is_trading_session is not True:
        return _scheduled_terminal_result(
            "NO_ACTION",
            ["not_trading_session"],
            session.timestamp,
        )
    calendar_updated = advance_cooldown(
        state,
        session.session_date.isoformat(),
        confirmed_trading_session=True,
    )

    updated, position_result = monitor_positions_from_provider(
        calendar_updated,
        provider,
        as_of=observed_at,
        invalidated_codes=invalidated_codes,
    )
    scans = []
    for record in records:
        scan = _advisory_scan(scan_etf(record, provider, as_of=observed_at))
        gate = _portfolio_gate(updated, str(record["code"]))
        scan["portfolio_gate"] = gate
        scan["reasons"] = _unique(list(scan["reasons"]) + list(gate["reasons"]))
        scans.append(scan)
    if updated != state:
        _write_state(state_path, updated)

    classified = [_scheduled_scan_status(scan) for scan in scans]
    alerts = [
        _advisory_alert(alert, str(position_result["source_timestamp"]))
        for alert in position_result.get("alerts", [])
    ]
    if alerts:
        status = "POSITION_ALERT"
    elif position_result["status"] == "DATA_ERROR":
        status = "DATA_ERROR"
    elif "DATA_ERROR" in classified:
        status = "DATA_ERROR"
    elif "BUY_CANDIDATE" in classified:
        status = "BUY_CANDIDATE"
    elif "BUY_CANDIDATE_NEEDS_CATALYST" in classified:
        status = "BUY_CANDIDATE_NEEDS_CATALYST"
    else:
        status = "NO_ACTION"

    reasons = _unique(
        list(position_result.get("reasons", []))
        + [reason for scan in scans for reason in scan["reasons"]]
    )
    result = _base_result("scheduled-check", status, reasons=reasons)
    result.update(
        {
            "source_timestamp": _oldest_timestamp(
                [position_result] + scans, observed_at
            ),
            "alerts": alerts,
            "scan_results": scans,
        }
    )
    return result


def _scheduled_terminal_result(
    status: str, reasons: Sequence[str], source_timestamp: datetime
) -> dict[str, Any]:
    result = _base_result("scheduled-check", status, reasons=reasons)
    result.update(
        {
            "source_timestamp": _timestamp_text(source_timestamp).isoformat(),
            "alerts": [],
            "scan_results": [],
        }
    )
    return result


def _scheduled_scan_status(result: Mapping[str, Any]) -> str:
    gate = result.get("portfolio_gate", {})
    if isinstance(gate, Mapping) and gate.get("allowed") is False:
        return "NO_ACTION"
    reasons = set(result.get("reasons", []))
    gate_reasons = (
        set(gate.get("reasons", [])) if isinstance(gate, Mapping) else set()
    )
    scanner_reasons = reasons - gate_reasons
    if result.get("status") == "DATA_ERROR" and scanner_reasons == {
        "not_trading_session"
    }:
        return "NO_ACTION"
    if result.get("status") == "BUY_CANDIDATE":
        return "BUY_CANDIDATE"
    if (
        result.get("status") == "NO_ACTION"
        and scanner_reasons
        and scanner_reasons <= CATALYST_PENDING_REASONS
    ):
        return "BUY_CANDIDATE_NEEDS_CATALYST"
    return str(result.get("status", "DATA_ERROR"))


def _advisory_scan(scan: Mapping[str, Any]) -> dict[str, Any]:
    enriched = dict(scan)
    enriched["risk_controls"] = _risk_controls()
    return enriched


def _advisory_alert(alert: Mapping[str, Any], source_timestamp: str) -> dict[str, Any]:
    enriched = dict(alert)
    if "source_timestamp" not in enriched:
        enriched["source_timestamp"] = source_timestamp
    _timestamp_text(enriched["source_timestamp"])
    enriched["risk_controls"] = _risk_controls()
    return enriched


def _portfolio_gate(state: Mapping[str, Any], code: str) -> dict[str, Any]:
    validate_portfolio_state(state)
    positions = state["positions"]

    blocking: list[str] = []
    if float(state["drawdown_pct"]) >= BUY_BLOCK_DRAWDOWN_PCT:
        blocking.append("buy_blocked_by_drawdown")
    if int(state["cooldown_remaining_trading_days"]) > 0:
        blocking.append("buy_blocked_during_cooldown")
    if bool(state["valuation_required"]):
        blocking.append("buy_blocked_pending_valuation")
    if bool(state["risk_reset_pending"]):
        blocking.append("buy_blocked_pending_risk_reset")
    if TARGET_TRANCHE_CNY > MAX_SINGLE_TRANCHE_CNY:
        blocking.append("target_tranche_exceeds_single_tranche_limit")
    post_buy_cash = round(float(state["cash_cny"]) - TARGET_TRANCHE_CNY, 2)
    if post_buy_cash < float(state["cash_reserve_cny"]):
        blocking.append(
            f"cash_reserve_floor_cny_{int(float(state['cash_reserve_cny']))}"
        )

    position = positions.get(code)
    if position is None and len(positions) >= MAX_OPEN_POSITIONS:
        blocking.append("max_open_positions_reached")

    exposure = 0.0
    for candidate in positions.values():
        if not isinstance(candidate, Mapping):
            raise ValueError("invalid portfolio state")
        exposure += float(candidate["cost_basis_cny"])
    if exposure + TARGET_TRANCHE_CNY > MAX_RISK_EXPOSURE_CNY:
        blocking.append("risk_exposure_limit_cny_40000")

    requires_confirmation = False
    if position is not None:
        if not isinstance(position, Mapping):
            raise ValueError("invalid portfolio state")
        if (
            float(position["cost_basis_cny"]) + TARGET_TRANCHE_CNY
            > MAX_ETF_COST_CNY
        ):
            blocking.append("per_etf_cost_limit_cny_20000")
        tranche_count = int(position["tranche_count"])
        if tranche_count >= MAX_TRANCHES_PER_ETF:
            blocking.append("max_tranches_per_etf_reached")
        requires_confirmation = tranche_count == 1

    reasons = list(blocking)
    if requires_confirmation:
        reasons.append("second_tranche_requires_renewed_confirmation")
    return {
        "allowed": not blocking,
        "reasons": reasons,
        "requires_renewed_confirmation": requires_confirmation,
        "target_tranche_cny": TARGET_TRANCHE_CNY,
        "max_single_tranche_cny": MAX_SINGLE_TRANCHE_CNY,
        "cash_reserve_cny": float(state["cash_reserve_cny"]),
    }


def _risk_controls() -> dict[str, Any]:
    return {
        "broker_recheck_required": True,
        "max_single_tranche_cny": MAX_SINGLE_TRANCHE_CNY,
        "invalidation": "signal_invalidation_or_minus_3_pct_from_weighted_cost",
        "max_position_cost_cny": 20_000,
        "second_tranche_requires_renewed_confirmation": True,
        "stop_loss_pct": -3.0,
        "target_tranche_cny": TARGET_TRANCHE_CNY,
    }


def _unconfigured_live_result(
    command: str,
    records: Sequence[Mapping[str, Any]],
    observed_at: datetime,
) -> dict[str, Any]:
    result = _base_result(command, "DATA_ERROR", reasons=LIVE_PROVIDER_REASONS)
    result["source_timestamp"] = observed_at.isoformat()
    if command == "scan":
        result["results"] = []
    else:
        result.update({"alerts": [], "scan_results": []})
    return result


def _scan_records(codes: Optional[Sequence[str]]) -> list[Mapping[str, Any]]:
    universe = load_universe()
    by_code = {str(record["code"]): record for record in tradable_records(universe)}
    selected_codes = list(codes) if codes else _default_scan_codes(universe)
    missing = [code for code in selected_codes if code not in by_code]
    if missing:
        raise ValueError("unknown or non-tradable ETF code: " + ",".join(sorted(missing)))
    return [by_code[code] for code in _unique(selected_codes)]


def _require_tradable_code(code: str) -> None:
    tradable_codes = {
        str(record["code"]) for record in tradable_records(load_universe())
    }
    if code not in tradable_codes:
        raise ValueError(f"unknown or non-tradable ETF code: {code}")


def _default_scan_codes(universe: Sequence[Mapping[str, Any]]) -> list[str]:
    selected = []
    for members in sector_market_groups(universe).values():
        recommendation = choose_recommendation(members)
        if recommendation is not None and is_eligible(recommendation):
            selected.append(str(recommendation["code"]))
    return sorted(selected)


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return new_portfolio_state()
    payload = json.loads(
        path.read_text(encoding="utf-8"),
        parse_constant=_reject_json_constant,
    )
    if not isinstance(payload, dict):
        raise ValueError("portfolio state must be a JSON object")
    validate_portfolio_state(payload)
    return payload


def _write_state(path: Path, state: Mapping[str, Any]) -> None:
    validate_portfolio_state(state)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                state,
                handle,
                allow_nan=False,
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
    finally:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"invalid JSON constant: {value}")


def _base_result(command: str, status: str, *, reasons: Optional[Sequence[str]] = None) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "command": command,
        "status": status,
        "reasons": list(reasons or []),
        "advisory_only": True,
        "orders_placed": False,
    }


def _command_error_result(
    arguments: Sequence[str],
    command: str,
    status: str,
    reasons: Sequence[str],
    *,
    source_timestamp: datetime,
) -> dict[str, Any]:
    result = _base_result(command, status, reasons=reasons)
    if command == "audit":
        result.update(
            {
                "record_count": None,
                "tradable_count": None,
                "exact_duplicate_group_count": None,
                "excluded_codes": [],
                "reports": {},
            }
        )
    elif command in {"record-buy", "record-sell"}:
        code = str(arguments[1]) if len(arguments) > 1 else None
        result.update({"code": code, "position": None, "state": None})
    elif command == "scan":
        result.update(
            {"source_timestamp": source_timestamp.isoformat(), "results": []}
        )
    elif command == "scheduled-check":
        result.update(
            {
                "source_timestamp": source_timestamp.isoformat(),
                "alerts": [],
                "scan_results": [],
            }
        )
    return result


def _oldest_timestamp(results: Sequence[Mapping[str, Any]], fallback: datetime) -> str:
    timestamps = [
        (_timestamp_text(result["source_timestamp"]), result["source_timestamp"])
        for result in results
        if result.get("source_timestamp")
    ]
    if timestamps:
        _, original = min(timestamps, key=lambda item: item[0])
        return str(original)
    return _timestamp_text(fallback).isoformat()


def _timestamp_text(value: Any) -> datetime:
    try:
        parsed = (
            value if isinstance(value, datetime) else datetime.fromisoformat(value)
        )
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError
        return parsed
    except (TypeError, ValueError) as exc:
        raise MarketDataError("invalid_source_timestamp") from exc


def _fixture_value(
    payload: Mapping[str, Any],
    field: str,
    key: str,
    *,
    require_mapping: bool,
    mapping_kind: str,
) -> Any:
    if field not in payload:
        return None
    value = payload[field]
    if require_mapping:
        if not isinstance(value, dict):
            raise MarketDataError(
                f"fixture_{field}_requires_{mapping_kind}_mapping"
            )
        if key not in value:
            raise MarketDataError(f"fixture_{field}_missing_{mapping_kind}_key")
        return value[key]
    if isinstance(value, dict) and key in value:
        return value[key]
    return value


def _typed_fixture(value: Any, key: Optional[str] = None) -> Any:
    if isinstance(value, list):
        return [_typed_fixture(item) for item in value]
    if isinstance(value, dict):
        return {item_key: _typed_fixture(item, item_key) for item_key, item in value.items()}
    if isinstance(value, str) and key in {"timestamp", "source_timestamp", "as_of"}:
        return _aware_datetime(value)
    if isinstance(value, str) and key in {"date", "session_date"}:
        return date.fromisoformat(value)
    return value


def _json_ready(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_ready(item) for item in value]
    return value


def _aware_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("timestamp must be ISO 8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("timestamp must include a timezone")
    return parsed


def _unique(values: Sequence[str] | Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values))


if __name__ == "__main__":
    raise SystemExit(main())
