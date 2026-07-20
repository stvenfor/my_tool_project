"""Official-exchange ETF share parsers for the review report."""

from __future__ import annotations

import io
import json
import math
import re
import zipfile
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from .reporting import ReportDataError, SharePoint


XLSX_NAMESPACE = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


class SseShareProvider:
    URL = "https://query.sse.com.cn/commonQuery.do"

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.opener = opener
        self.clock = clock

    def fetch_date(self, trading_date: date) -> list[SharePoint]:
        params = {
            "isPagination": "true",
            "pageHelp.pageSize": "10000",
            "pageHelp.pageNo": "1",
            "pageHelp.beginPage": "1",
            "pageHelp.cacheSize": "1",
            "pageHelp.endPage": "1",
            "sqlId": "COMMON_SSE_ZQPZ_ETFZL_XXPL_ETFGM_SEARCH_L",
            "STAT_DATE": trading_date.isoformat(),
        }
        request = Request(
            f"{self.URL}?{urlencode(params)}",
            headers={"Referer": "https://www.sse.com.cn/", "User-Agent": _user_agent()},
        )
        try:
            with self.opener(request, timeout=15) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise ReportDataError("sse_share_endpoint_unavailable") from exc
        return parse_sse_share_payload(
            payload, fetched_at=self.clock(), expected_date=trading_date
        )


class SzseShareProvider:
    URL = "https://www.szse.cn/api/report/ShowReport"

    def __init__(
        self,
        *,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.opener = opener
        self.clock = clock

    def fetch_range(self, start_date: date, end_date: date) -> list[SharePoint]:
        if start_date > end_date or end_date - start_date > timedelta(days=183):
            raise ReportDataError("invalid_szse_share_range")
        params = {
            "SHOWTYPE": "xlsx",
            "CATALOGID": "scsj_fund_jjgm",
            "TABKEY": "tab1",
            "txtStart": start_date.isoformat(),
            "txtEnd": end_date.isoformat(),
            "jjlb": "ETF",
            "random": "0.5",
        }
        request = Request(
            f"{self.URL}?{urlencode(params)}",
            headers={
                "Referer": "https://www.szse.cn/market/fund/volume/etf/index.html",
                "User-Agent": _user_agent(),
            },
        )
        try:
            with self.opener(request, timeout=15) as response:
                payload = response.read()
        except Exception as exc:
            raise ReportDataError("szse_share_endpoint_unavailable") from exc
        return parse_szse_share_xlsx(
            payload,
            fetched_at=self.clock(),
            start_date=start_date,
            end_date=end_date,
        )


def parse_sse_share_payload(
    payload: Mapping[str, Any], *, fetched_at: datetime, expected_date: date
) -> list[SharePoint]:
    try:
        rows = payload["result"]
        if not isinstance(rows, list):
            raise TypeError
    except (KeyError, TypeError) as exc:
        raise ReportDataError("malformed_sse_share_payload") from exc
    points: list[SharePoint] = []
    seen: set[str] = set()
    for row in rows:
        try:
            if not isinstance(row, Mapping):
                raise TypeError
            code = _code(row["SEC_CODE"])
            point_date = date.fromisoformat(str(row["STAT_DATE"]).strip())
            shares = _nonnegative(row["TOT_VOL"]) * 10_000
        except (KeyError, TypeError, ValueError) as exc:
            raise ReportDataError("malformed_sse_share_row") from exc
        if point_date != expected_date:
            raise ReportDataError("unexpected_sse_share_date")
        if code in seen:
            raise ReportDataError("duplicate_sse_share_code")
        seen.add(code)
        points.append(
            SharePoint(
                code=code,
                date=point_date,
                shares=shares,
                source="sse_etf_scale",
                fetched_at=_timestamp(fetched_at),
            )
        )
    return sorted(points, key=lambda point: point.code)


def parse_szse_share_xlsx(
    payload: bytes,
    *,
    fetched_at: datetime,
    start_date: date,
    end_date: date,
) -> list[SharePoint]:
    if start_date > end_date:
        raise ReportDataError("invalid_szse_share_range")
    try:
        rows = _xlsx_rows(payload)
    except (KeyError, ValueError, zipfile.BadZipFile, ElementTree.ParseError) as exc:
        raise ReportDataError("malformed_szse_share_xlsx") from exc
    if not rows:
        return []
    headers = {str(value).strip(): index for index, value in enumerate(rows[0])}
    required = {"日期", "基金代码", "基金简称", "基金规模(份)"}
    if not required.issubset(headers):
        raise ReportDataError("missing_szse_share_columns")
    points: list[SharePoint] = []
    seen: set[tuple[str, date]] = set()
    for row in rows[1:]:
        if not any(value not in (None, "") for value in row):
            continue
        try:
            point_date = _xlsx_date(_value(row, headers["日期"]))
            code = _code(_value(row, headers["基金代码"]))
            shares = _nonnegative(_value(row, headers["基金规模(份)"]))
        except (TypeError, ValueError) as exc:
            raise ReportDataError("malformed_szse_share_row") from exc
        if not start_date <= point_date <= end_date:
            raise ReportDataError("unexpected_szse_share_date")
        key = (code, point_date)
        if key in seen:
            raise ReportDataError("duplicate_szse_share_point")
        seen.add(key)
        points.append(
            SharePoint(
                code=code,
                date=point_date,
                shares=shares,
                source="szse_fund_scale_daily",
                fetched_at=_timestamp(fetched_at),
            )
        )
    return sorted(points, key=lambda point: (point.date, point.code))


def _xlsx_rows(payload: bytes) -> list[list[Any]]:
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        shared = _shared_strings(archive)
        sheet = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    rows: list[list[Any]] = []
    for row in sheet.findall(f".//{XLSX_NAMESPACE}row"):
        values: dict[int, Any] = {}
        for cell in row.findall(f"{XLSX_NAMESPACE}c"):
            reference = cell.attrib.get("r", "")
            match = re.match(r"([A-Z]+)", reference)
            if not match:
                raise ValueError("missing_cell_reference")
            column = _column_index(match.group(1))
            cell_type = cell.attrib.get("t")
            value_node = cell.find(f"{XLSX_NAMESPACE}v")
            if cell_type == "inlineStr":
                texts = cell.findall(f".//{XLSX_NAMESPACE}t")
                value: Any = "".join(text.text or "" for text in texts)
            elif value_node is None:
                value = None
            elif cell_type == "s":
                value = shared[int(value_node.text or "0")]
            else:
                value = value_node.text
            values[column] = value
        width = max(values, default=-1) + 1
        rows.append([values.get(index) for index in range(width)])
    return rows


def _shared_strings(archive: zipfile.ZipFile) -> list[str]:
    try:
        root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(text.text or "" for text in item.findall(f".//{XLSX_NAMESPACE}t"))
        for item in root.findall(f"{XLSX_NAMESPACE}si")
    ]


def _column_index(letters: str) -> int:
    value = 0
    for letter in letters:
        value = value * 26 + ord(letter) - ord("A") + 1
    return value - 1


def _xlsx_date(value: Any) -> date:
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        serial = float(text)
        if not math.isfinite(serial) or serial <= 0:
            raise
        return date(1899, 12, 30) + timedelta(days=int(serial))


def _value(row: list[Any], index: int) -> Any:
    if index >= len(row):
        raise ValueError("missing_cell")
    return row[index]


def _code(value: Any) -> str:
    text = str(value).strip()
    if re.fullmatch(r"\d+\.0+", text):
        text = text.split(".", 1)[0]
    if not re.fullmatch(r"\d{1,6}", text):
        raise ValueError("invalid_code")
    return text.zfill(6)


def _nonnegative(value: Any) -> float:
    number = float(str(value).replace(",", ""))
    if not math.isfinite(number) or number < 0:
        raise ValueError("invalid_number")
    return number


def _timestamp(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ReportDataError("invalid_fetch_timestamp")
    return value


def _user_agent() -> str:
    return (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0 Safari/537.36"
    )
