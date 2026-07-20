"""Contract tests for evidence mapping and the enhanced report renderers."""

from __future__ import annotations

import csv
import io
import json
import sys
import unittest
from pathlib import Path


MODULE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MODULE_ROOT))

from src.reporting import (  # noqa: E402
    ReportDataError,
    render_report_csv,
    render_report_markdown,
    validate_sector_context,
)


CONTEXT_PATH = MODULE_ROOT / "data" / "sector-context-2026-07-20.json"
REPORT_PATH = MODULE_ROOT / "reports" / "representative-technical-review-2026-07-20.json"


def _row() -> dict[str, object]:
    return {
        "action": "观察",
        "code": "510050",
        "name": "上证50ETF华夏",
        "trend": "多头",
        "ret5_pct": 1.2,
        "ret10_pct": 2.3,
        "ret20_pct": 4.5,
        "rsi14": 61.2,
        "kdj": {"k": 70.1, "d": 66.2, "j": 77.9, "state": "多头"},
        "macd": {"dif": 0.023, "dea": 0.018, "histogram": 0.01, "state": "零轴上多头"},
        "sentiment": {"score": 64.5, "label": "偏热", "missing_inputs": []},
        "flows": {
            "5": {"value_cny": 123_000_000, "reason": None, "price_basis": "close"},
            "10": {"value_cny": None, "reason": "missing_share_date", "price_basis": "close"},
            "20": {"value_cny": -456_000_000, "reason": None, "price_basis": "close"},
        },
        "policy_reason": "政策面示例",
        "fundamental_reason": "基本面示例",
        "technical_reason": "技术面示例",
        "sentiment_reason": "情绪面示例",
    }


class SectorContextTests(unittest.TestCase):
    def test_every_report_sector_has_policy_and_fundamental_evidence(self) -> None:
        context = json.loads(CONTEXT_PATH.read_text(encoding="utf-8"))
        report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
        sectors = sorted({row["sector"] for row in report["rows"]})

        validate_sector_context(context, sectors)

        for theme in context["themes"].values():
            for dimension in ("policy", "fundamental"):
                evidence = theme[dimension]
                self.assertTrue(evidence["text"])
                self.assertTrue(evidence["title"])
                self.assertTrue(evidence["publisher"])
                self.assertRegex(evidence["date"], r"^2026-\d{2}-\d{2}$")
                self.assertTrue(evidence["url"].startswith("https://"))

    def test_unknown_sector_is_rejected(self) -> None:
        context = {
            "themes": {},
            "sector_theme": {},
        }

        with self.assertRaisesRegex(ReportDataError, "unmapped_sector:unknown"):
            validate_sector_context(context, ["unknown"])


class ReportRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.report = {
            "title": "2026-07-20 ETF精简代表池技术面审阅",
            "data_date": "2026-07-20",
            "generated_at": "2026-07-20T18:00:00+08:00",
            "flow_definition": "交易所基金份额变化 × 当日收盘价",
            "rows": [_row()],
        }

    def test_markdown_contains_all_new_columns_and_window_level_na_reason(self) -> None:
        rendered = render_report_markdown(self.report)

        for header in (
            "KDJ",
            "MACD",
            "情绪",
            "5日份额净流入",
            "10日份额净流入",
            "20日份额净流入",
            "政策面",
            "基本面",
            "技术面",
            "情绪面",
        ):
            self.assertIn(header, rendered)
        self.assertIn("+1.23亿", rendered)
        self.assertIn("N/A（缺少交易日份额）", rendered)
        self.assertIn("-4.56亿", rendered)

    def test_csv_has_machine_readable_new_fields(self) -> None:
        rendered = render_report_csv(self.report)
        self.assertNotIn("\r", rendered)
        rows = list(csv.DictReader(io.StringIO(rendered)))

        self.assertEqual(1, len(rows))
        self.assertEqual("510050", rows[0]["代码"])
        self.assertEqual("70.10", rows[0]["K"])
        self.assertEqual("0.010000", rows[0]["MACD柱"])
        self.assertEqual("123000000.00", rows[0]["5日份额净流入_元"])
        self.assertEqual("missing_share_date", rows[0]["10日净流入错误"])
        self.assertEqual("政策面示例", rows[0]["政策面理由"])


if __name__ == "__main__":
    unittest.main()
