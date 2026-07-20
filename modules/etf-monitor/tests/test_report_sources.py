"""Fixture-only tests for official exchange ETF share sources."""

from __future__ import annotations

import io
import json
import sys
import unittest
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from xml.sax.saxutils import escape


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from src.reporting import ReportDataError  # noqa: E402
from src.report_sources import (  # noqa: E402
    SseShareProvider,
    SzseShareProvider,
    parse_sse_share_payload,
    parse_szse_share_xlsx,
)


FETCHED_AT = datetime(2026, 7, 20, 18, 0, tzinfo=timezone(timedelta(hours=8)))


def _xlsx_bytes(rows: list[list[object]]) -> bytes:
    shared: list[str] = []
    shared_index: dict[str, int] = {}

    def cell(reference: str, value: object) -> str:
        if isinstance(value, str):
            if value not in shared_index:
                shared_index[value] = len(shared)
                shared.append(value)
            return f'<c r="{reference}" t="s"><v>{shared_index[value]}</v></c>'
        return f'<c r="{reference}"><v>{value}</v></c>'

    xml_rows = []
    for row_index, values in enumerate(rows, start=1):
        cells = []
        for column_index, value in enumerate(values, start=1):
            column = chr(ord("A") + column_index - 1)
            cells.append(cell(f"{column}{row_index}", value))
        xml_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'<sheetData>{"".join(xml_rows)}</sheetData></worksheet>'
    )
    shared_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        f'count="{len(shared)}" uniqueCount="{len(shared)}">'
        + "".join(f"<si><t>{escape(value)}</t></si>" for value in shared)
        + "</sst>"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("xl/sharedStrings.xml", shared_xml)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)
    return output.getvalue()


class ReportSourceTests(unittest.TestCase):
    def test_sse_parser_normalizes_ten_thousand_share_units(self) -> None:
        payload = {
            "result": [
                {
                    "SEC_CODE": "510050",
                    "SEC_NAME": "50ETF",
                    "STAT_DATE": "2026-07-20",
                    "TOT_VOL": "5533716.68",
                }
            ]
        }

        points = parse_sse_share_payload(
            payload, fetched_at=FETCHED_AT, expected_date=date(2026, 7, 20)
        )

        self.assertEqual(1, len(points))
        self.assertEqual("510050", points[0].code)
        self.assertEqual(date(2026, 7, 20), points[0].date)
        self.assertEqual(55_337_166_800, points[0].shares)
        self.assertEqual("sse_etf_scale", points[0].source)

    def test_sse_parser_rejects_rows_for_an_unexpected_date(self) -> None:
        payload = {
            "result": [
                {
                    "SEC_CODE": "510050",
                    "SEC_NAME": "50ETF",
                    "STAT_DATE": "2026-07-19",
                    "TOT_VOL": "1",
                }
            ]
        }

        with self.assertRaisesRegex(ReportDataError, "unexpected_sse_share_date"):
            parse_sse_share_payload(
                payload, fetched_at=FETCHED_AT, expected_date=date(2026, 7, 20)
            )

    def test_szse_parser_reads_date_code_name_and_exact_share_units(self) -> None:
        payload = _xlsx_bytes(
            [
                ["日期", "基金代码", "基金简称", "基金规模(份)"],
                ["2026-07-17", "159915", "创业板ETF", 1_234_567_890],
                ["2026-07-20", "159995", "芯片ETF", 14_068_360_000],
            ]
        )

        points = parse_szse_share_xlsx(
            payload,
            fetched_at=FETCHED_AT,
            start_date=date(2026, 7, 17),
            end_date=date(2026, 7, 20),
        )

        self.assertEqual(2, len(points))
        self.assertEqual("159915", points[0].code)
        self.assertEqual(date(2026, 7, 17), points[0].date)
        self.assertEqual(1_234_567_890, points[0].shares)
        self.assertEqual("szse_fund_scale_daily", points[0].source)
        self.assertEqual("159995", points[1].code)
        self.assertEqual(14_068_360_000, points[1].shares)

    def test_szse_parser_rejects_missing_required_columns(self) -> None:
        payload = _xlsx_bytes([["日期", "基金代码"], ["2026-07-20", "159915"]])

        with self.assertRaisesRegex(ReportDataError, "missing_szse_share_columns"):
            parse_szse_share_xlsx(
                payload,
                fetched_at=FETCHED_AT,
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 20),
            )

    def test_szse_parser_rejects_invalid_xlsx(self) -> None:
        with self.assertRaisesRegex(ReportDataError, "malformed_szse_share_xlsx"):
            parse_szse_share_xlsx(
                b"not-a-zip",
                fetched_at=FETCHED_AT,
                start_date=date(2026, 7, 20),
                end_date=date(2026, 7, 20),
            )

    def test_sse_provider_uses_official_date_endpoint(self) -> None:
        payload = json.dumps(
            {
                "result": [
                    {
                        "SEC_CODE": "510050",
                        "SEC_NAME": "50ETF",
                        "STAT_DATE": "2026-07-20",
                        "TOT_VOL": "1",
                    }
                ]
            }
        ).encode()
        seen = []

        def opener(request, timeout):
            seen.append((request, timeout))
            return _Response(payload)

        points = SseShareProvider(opener=opener, clock=lambda: FETCHED_AT).fetch_date(
            date(2026, 7, 20)
        )

        self.assertEqual(10_000, points[0].shares)
        self.assertIn("query.sse.com.cn/commonQuery.do", seen[0][0].full_url)
        self.assertIn("STAT_DATE=2026-07-20", seen[0][0].full_url)
        self.assertEqual("https://www.sse.com.cn/", seen[0][0].headers["Referer"])
        self.assertEqual(15, seen[0][1])

    def test_szse_provider_uses_official_daily_range_endpoint(self) -> None:
        payload = _xlsx_bytes(
            [
                ["日期", "基金代码", "基金简称", "基金规模(份)"],
                ["2026-07-20", "159915", "创业板ETF", 123],
            ]
        )
        seen = []

        def opener(request, timeout):
            seen.append((request, timeout))
            return _Response(payload)

        points = SzseShareProvider(opener=opener, clock=lambda: FETCHED_AT).fetch_range(
            date(2026, 7, 20), date(2026, 7, 20)
        )

        self.assertEqual(123, points[0].shares)
        self.assertIn("www.szse.cn/api/report/ShowReport", seen[0][0].full_url)
        self.assertIn("txtStart=2026-07-20", seen[0][0].full_url)
        self.assertIn("txtEnd=2026-07-20", seen[0][0].full_url)
        self.assertIn("jjlb=ETF", seen[0][0].full_url)
        self.assertEqual(15, seen[0][1])


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self) -> bytes:
        return self.payload


if __name__ == "__main__":
    unittest.main()
