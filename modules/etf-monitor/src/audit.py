"""Static universe validation and deterministic audit report rendering."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence


LOW_TURNOVER_CNY = 50_000_000
MODULE_ROOT = Path(__file__).resolve().parents[1]
UNIVERSE_PATH = MODULE_ROOT / "data" / "universe.json"


def load_universe(path: Path = UNIVERSE_PATH) -> list[dict[str, object]]:
    """Load the reviewed static universe and reject malformed records."""
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("universe must be a JSON array")
    required = {
        "code",
        "name",
        "kind",
        "market",
        "sector",
        "tracking_index",
        "screenshot_turnover_cny",
    }
    codes: set[str] = set()
    for record in records:
        if not isinstance(record, dict) or required - record.keys():
            raise ValueError("universe record is missing required fields")
        code = record["code"]
        if not isinstance(code, str) or code in codes:
            raise ValueError("universe codes must be unique strings")
        if record["kind"] not in {"ETF", "INDEX"}:
            raise ValueError("universe kind must be ETF or INDEX")
        if not isinstance(record["screenshot_turnover_cny"], int):
            raise ValueError("screenshot turnover must be an integer")
        codes.add(code)
    return records


def tradable_records(records: Iterable[Mapping[str, object]]) -> list[Mapping[str, object]]:
    """Return ETFs only; benchmark/index rows are audit context, not tradable products."""
    return [record for record in records if record["kind"] == "ETF"]


def exact_duplicate_groups(
    records: Iterable[Mapping[str, object]],
) -> dict[str, list[Mapping[str, object]]]:
    """Group reviewed exact-index duplicates in their explicit reviewed code order."""
    grouped: dict[str, dict[str, Mapping[str, object]]] = defaultdict(dict)
    for record in records:
        group = record.get("exact_duplicate_group")
        if group:
            grouped[str(group)][str(record["code"])] = record
    return {
        group: [members[code] for code in group.split("/")]
        for group, members in sorted(grouped.items())
    }


def sector_market_groups(
    records: Iterable[Mapping[str, object]],
) -> dict[tuple[str, str], list[Mapping[str, object]]]:
    """Group tradable ETFs by sector *and* market, preserving market boundaries."""
    grouped: dict[tuple[str, str], list[Mapping[str, object]]] = defaultdict(list)
    for record in tradable_records(records):
        grouped[(str(record["sector"]), str(record["market"]))].append(record)
    return {
        key: sorted(members, key=lambda record: str(record["code"]))
        for key, members in sorted(grouped.items())
    }


def is_eligible(record: Mapping[str, object]) -> bool:
    """Apply this static audit's minimum eligibility rule.

    Dynamic technical, premium, AUM, and catalyst gates are deliberately left to
    the scanner. Screenshot turnover is only a reviewed liquidity screen here.
    """
    return (
        record["kind"] == "ETF"
        and int(record["screenshot_turnover_cny"]) >= LOW_TURNOVER_CNY
    )


def choose_recommendation(
    records: Sequence[Mapping[str, object]],
) -> Optional[Mapping[str, object]]:
    """Choose deterministically: eligibility, turnover, then ascending code."""
    if not records:
        return None
    return min(
        records,
        key=lambda record: (
            not is_eligible(record),
            -int(record["screenshot_turnover_cny"]),
            str(record["code"]),
        ),
    )


def _format_members(members: Sequence[Mapping[str, object]]) -> str:
    return ", ".join(
        f"{record['code']} ({int(record['screenshot_turnover_cny']):,})"
        for record in members
    )


def render_exact_duplicates_report(records: Iterable[Mapping[str, object]]) -> str:
    """Render the exact-index duplicate choice report with stable ordering."""
    records = list(records)
    groups = exact_duplicate_groups(records)
    lines = [
        "# Exact-index duplicate audit",
        "",
        "Static reviewed snapshot. A selection is ordered by eligibility, screenshot turnover, then lower code.",
        "",
        f"Reviewed universe: **{len(records)} unique records**; {len(tradable_records(records))} tradable ETFs.",
        "",
        f"**{len(groups)} exact duplicate groups**",
        "",
        "| Exact group | Tracking index | Members: code (CNY turnover) | Selected ETF | Status |",
        "| --- | --- | --- | --- | --- |",
    ]
    for group, members in groups.items():
        selected = choose_recommendation(members)
        assert selected is not None
        status = "eligible" if is_eligible(selected) else "observation-only"
        lines.append(
            "| {group} | {index} | {members} | {selected} | {status} |".format(
                group=group,
                index=members[0]["tracking_index"],
                members=_format_members(members),
                selected=selected["code"],
                status=status,
            )
        )
    lines.extend(
        [
            "",
            "`883432` is an INDEX benchmark and is excluded from all tradable selections.",
            "",
        ]
    )
    return "\n".join(lines)


def render_sector_overlap_report(records: Iterable[Mapping[str, object]]) -> str:
    """Render all sector × market buckets and flag low-turnover unique ETFs."""
    records = list(records)
    groups = sector_market_groups(records)
    lines = [
        "# Sector × market overlap audit",
        "",
        "Products are compared only within the same sector and market; cross-market products remain separate.",
        "",
        f"Reviewed universe: {len(records)} unique records; **{len(tradable_records(records))} tradable ETFs**.",
        "",
        "| Sector × market | Products: code (CNY turnover) | Classification | Selection |",
        "| --- | --- | --- | --- |",
    ]
    observation_only: list[Mapping[str, object]] = []
    for (sector, market), members in groups.items():
        if len(members) > 1:
            selected = choose_recommendation(members)
            assert selected is not None
            classification = "overlap"
            selection = str(selected["code"])
        else:
            selected = members[0]
            classification = "unique"
            selection = "observation-only" if not is_eligible(selected) else "eligible"
            if not is_eligible(selected):
                observation_only.append(selected)
        lines.append(
            "| {sector} × {market} | {members} | {classification} | {selection} |".format(
                sector=sector,
                market=market,
                members=_format_members(members),
                classification=classification,
                selection=selection,
            )
        )
    lines.extend(
        [
            "",
            "## Observation-only unique products",
            "",
            f"Unique ETFs below CNY {LOW_TURNOVER_CNY:,} screenshot turnover are observation-only:",
            "",
        ]
    )
    for record in sorted(observation_only, key=lambda item: str(item["code"])):
        lines.append(
            f"- `{record['code']}` {record['name']} — {int(record['screenshot_turnover_cny']):,}"
        )
    lines.append("")
    return "\n".join(lines)


_UNIVERSE = load_universe()
EXACT_DUPLICATE_GROUPS = exact_duplicate_groups(_UNIVERSE)
