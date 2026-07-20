#!/usr/bin/env python3.12
"""Generate the date-stamped representative ETF review from public data."""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from src.market_data import DailyBar, PublicMarketDataProvider
from src.report_generator import build_report
from src.report_sources import SseShareProvider, SzseShareProvider
from src.reporting import ReportDataError, SharePoint, render_report_csv, render_report_markdown


MODULE_ROOT = Path(__file__).resolve().parent
DEFAULT_REPORT = MODULE_ROOT / "reports" / "representative-technical-review-2026-07-20.json"
DEFAULT_CONTEXT = MODULE_ROOT / "data" / "sector-context-2026-07-20.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--context", type=Path, default=DEFAULT_CONTEXT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--output-markdown",
        type=Path,
        default=DEFAULT_REPORT.with_suffix(".md"),
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=DEFAULT_REPORT.with_suffix(".csv"),
    )
    parser.add_argument("--workers", type=int, default=8)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    context = json.loads(args.context.read_text(encoding="utf-8"))
    codes = [str(row["code"]) for row in seed["rows"]]
    provider = PublicMarketDataProvider(calendar_provider=object(), catalyst_provider=object())
    bars_by_code, bar_errors = collect_bars(codes, provider, workers=args.workers)
    if bar_errors:
        details = ", ".join(f"{code}:{reason}" for code, reason in sorted(bar_errors.items()))
        raise RuntimeError(f"daily_bar_collection_failed:{details}")
    shares_by_code, share_errors = collect_shares(codes, bars_by_code)
    report = build_report(
        seed=seed,
        bars_by_code=bars_by_code,
        shares_by_code=shares_by_code,
        share_errors=share_errors,
        context=context,
        generated_at=datetime.now(SHANGHAI),
    )
    if len(report["rows"]) != len(codes):
        raise RuntimeError("report_row_count_mismatch")
    args.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    args.output_markdown.write_text(render_report_markdown(report), encoding="utf-8")
    args.output_csv.write_text(render_report_csv(report), encoding="utf-8")
    flow_counts = {
        window: sum(
            row["flows"][str(window)]["value_cny"] is not None
            for row in report["rows"]
        )
        for window in (5, 10, 20)
    }
    print(
        json.dumps(
            {
                "rows": len(report["rows"]),
                "data_date": report["data_date"],
                "flow_available": flow_counts,
                "share_errors": share_errors,
                "outputs": {
                    "json": str(args.output_json),
                    "markdown": str(args.output_markdown),
                    "csv": str(args.output_csv),
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def collect_bars(
    codes: list[str],
    provider: PublicMarketDataProvider,
    *,
    workers: int,
) -> tuple[dict[str, list[DailyBar]], dict[str, str]]:
    bars_by_code: dict[str, list[DailyBar]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as executor:
        futures = {
            executor.submit(_retry, lambda code=code: list(provider.get_daily_bars(code))): code
            for code in codes
        }
        for future in as_completed(futures):
            code = futures[future]
            try:
                bars_by_code[code] = future.result()
            except Exception as exc:
                errors[code] = getattr(exc, "reason", str(exc) or type(exc).__name__)
    return bars_by_code, errors


def collect_shares(
    codes: list[str],
    bars_by_code: dict[str, list[DailyBar]],
) -> tuple[dict[str, list[SharePoint]], dict[str, str]]:
    by_code: dict[str, list[SharePoint]] = defaultdict(list)
    errors: dict[str, str] = {}
    sse_codes = {code for code in codes if code.startswith("5")}
    szse_codes = set(codes) - sse_codes
    all_dates = sorted(
        {
            bar.date
            for bars in bars_by_code.values()
            for bar in bars[-21:]
        }
    )
    sse_failed_dates = 0
    sse = SseShareProvider()
    for trading_date in all_dates:
        try:
            for point in _retry(lambda d=trading_date: sse.fetch_date(d)):
                if point.code in sse_codes:
                    by_code[point.code].append(point)
        except Exception:
            sse_failed_dates += 1
    if all_dates and sse_failed_dates == len(all_dates):
        errors.update({code: "sse_share_endpoint_unavailable" for code in sse_codes})
    if szse_codes and all_dates:
        try:
            points = _retry(
                lambda: SzseShareProvider().fetch_range(all_dates[0], all_dates[-1])
            )
            for point in points:
                if point.code in szse_codes:
                    by_code[point.code].append(point)
        except Exception as exc:
            reason = getattr(exc, "reason", "szse_share_endpoint_unavailable")
            errors.update({code: reason for code in szse_codes})
    for code in codes:
        if code not in errors and not by_code.get(code):
            errors[code] = "share_code_not_found"
    return dict(by_code), errors


def _retry(operation: Callable[[], Any], attempts: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(attempts):
        try:
            return operation()
        except Exception as exc:
            last_error = exc
            if attempt + 1 < attempts:
                time.sleep(0.25 * (attempt + 1))
    assert last_error is not None
    raise last_error


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ReportDataError, RuntimeError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
