#!/usr/bin/env python3
"""Fetch and freeze the 2026-07-17 THS industry fund-flow close snapshot."""

from __future__ import annotations

import json
import math
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import akshare as ak


TRADE_DATE = "2026-07-17"
TIMEZONE = ZoneInfo("Asia/Shanghai")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "src" / "data" / f"a-share-industry-flow-{TRADE_DATE}.json"


def finite_number(value: object, field: str, industry: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{industry} 的 {field} 不是有限数值: {value!r}")
    return number


def main() -> None:
    now = datetime.now(TIMEZONE)
    if now.date().isoformat() != TRADE_DATE:
        raise RuntimeError(
            f"即时接口只能冻结当天数据；当前上海日期为 {now.date().isoformat()}，目标日期为 {TRADE_DATE}"
        )
    if now.weekday() >= 5:
        raise RuntimeError(f"{TRADE_DATE} 不是工作日，拒绝生成交易日快照")
    if now.time() < time(15, 5):
        raise RuntimeError("尚未到收盘数据稳定时间 15:05，拒绝生成收盘快照")

    frame = ak.stock_fund_flow_industry(symbol="即时")
    expected_columns = {
        "序号",
        "行业",
        "行业指数",
        "行业-涨跌幅",
        "流入资金",
        "流出资金",
        "净额",
        "公司家数",
        "领涨股",
        "领涨股-涨跌幅",
        "当前价",
    }
    missing = expected_columns.difference(frame.columns)
    if missing:
        raise RuntimeError(f"AKShare 返回字段不完整: {sorted(missing)}")
    if len(frame) != 90:
        raise RuntimeError(f"预期 90 个行业，实际返回 {len(frame)} 个，拒绝渲染")

    raw_rows: list[dict[str, object]] = []
    for _, source in frame.iterrows():
        industry = str(source["行业"]).strip()
        raw_rows.append(
            {
                "sourceRank": int(source["序号"]),
                "industry": industry,
                "industryIndex": finite_number(source["行业指数"], "行业指数", industry),
                "changePercent": finite_number(source["行业-涨跌幅"], "行业-涨跌幅", industry),
                "grossInflow": finite_number(source["流入资金"], "流入资金", industry),
                "grossOutflow": finite_number(source["流出资金"], "流出资金", industry),
                "netAmount": finite_number(source["净额"], "净额", industry),
                "companyCount": int(source["公司家数"]),
                "leadingStock": str(source["领涨股"]).strip(),
                "leadingStockChangePercent": finite_number(
                    source["领涨股-涨跌幅"], "领涨股-涨跌幅", industry
                ),
                "currentPrice": finite_number(source["当前价"], "当前价", industry),
            }
        )

    if len({row["industry"] for row in raw_rows}) != len(raw_rows):
        raise RuntimeError("数据中存在重复行业名称")

    positive = sorted(
        (row for row in raw_rows if float(row["netAmount"]) > 0),
        key=lambda row: (-float(row["netAmount"]), str(row["industry"])),
    )
    negative = sorted(
        (row for row in raw_rows if float(row["netAmount"]) < 0),
        key=lambda row: (float(row["netAmount"]), str(row["industry"])),
    )
    if len(positive) < 5 or len(negative) < 5:
        raise RuntimeError("正净额或负净额行业不足 5 个")

    def top_item(row: dict[str, object], rank: int) -> dict[str, object]:
        return {
            "rank": rank,
            "industry": row["industry"],
            "netAmount": row["netAmount"],
            "grossInflow": row["grossInflow"],
            "grossOutflow": row["grossOutflow"],
        }

    payload = {
        "tradeDate": TRADE_DATE,
        "dataCutoff": f"{TRADE_DATE} 15:00:00+08:00",
        "fetchedAt": now.isoformat(timespec="seconds"),
        "timezone": "Asia/Shanghai",
        "source": '同花顺行业资金流，经 AKShare stock_fund_flow_industry(symbol="即时") 获取',
        "sourceUrl": "http://data.10jqka.com.cn/funds/hyzjl/",
        "secondaryCheckUrl": "https://data.eastmoney.com/bkzj/hy.html",
        "unit": "亿元",
        "classification": "同花顺行业分类；不混用概念、地域、ETF、北向或个股资金",
        "akshareVersion": ak.__version__,
        "rawRowCount": len(raw_rows),
        "inflowTop5": [top_item(row, index + 1) for index, row in enumerate(positive[:5])],
        "outflowTop5": [top_item(row, index + 1) for index, row in enumerate(negative[:5])],
        "rawRows": raw_rows,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUTPUT_PATH}")
    print(json.dumps({"inflowTop5": payload["inflowTop5"], "outflowTop5": payload["outflowTop5"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
