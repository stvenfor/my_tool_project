"""Pure calculations for the date-stamped ETF review report."""

from __future__ import annotations

import math
import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Optional, Sequence

from .market_data import DailyBar


class ReportDataError(ValueError):
    """A stable report-data validation error."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class SharePoint:
    code: str
    date: date
    shares: float
    source: str
    fetched_at: datetime


@dataclass(frozen=True)
class KdjValue:
    k: float
    d: float
    j: float
    state: str


@dataclass(frozen=True)
class MacdValue:
    dif: float
    dea: float
    histogram: float
    state: str


@dataclass(frozen=True)
class FlowWindow:
    window: int
    value_cny: Optional[float]
    price_basis: str
    reason: Optional[str] = None


@dataclass(frozen=True)
class SentimentValue:
    score: float
    label: str
    missing_inputs: tuple[str, ...]


def calculate_kdj(bars: Sequence[DailyBar], period: int = 9) -> KdjValue:
    if len(bars) < period:
        raise ReportDataError("insufficient_bars_for_kdj")
    _validate_bars(bars)
    k = 50.0
    d = 50.0
    previous_k = k
    previous_d = d
    for index, bar in enumerate(bars):
        window = bars[max(0, index - period + 1) : index + 1]
        lowest = min(item.low for item in window)
        highest = max(item.high for item in window)
        rsv = 50.0 if highest == lowest else (bar.close - lowest) / (highest - lowest) * 100
        previous_k, previous_d = k, d
        k = (2 * k + rsv) / 3
        d = (2 * d + k) / 3
    j = 3 * k - 2 * d
    if k >= 80 and d >= 80:
        state = "超买"
    elif k <= 20 and d <= 20:
        state = "超卖"
    elif k > d and previous_k <= previous_d:
        state = "金叉"
    elif k < d and previous_k >= previous_d:
        state = "死叉"
    elif k > d:
        state = "多头"
    elif k < d:
        state = "空头"
    else:
        state = "中性"
    return KdjValue(k=k, d=d, j=j, state=state)


def calculate_macd(bars: Sequence[DailyBar]) -> MacdValue:
    if len(bars) < 26:
        raise ReportDataError("insufficient_bars_for_macd")
    _validate_bars(bars)
    ema12 = bars[0].close
    ema26 = bars[0].close
    dea = 0.0
    previous_dif = 0.0
    previous_dea = 0.0
    dif = 0.0
    for bar in bars:
        ema12 = (2 * bar.close + 11 * ema12) / 13
        ema26 = (2 * bar.close + 25 * ema26) / 27
        previous_dif, previous_dea = dif, dea
        dif = ema12 - ema26
        dea = (2 * dif + 8 * dea) / 10
    histogram = 2 * (dif - dea)
    if dif > dea and previous_dif <= previous_dea:
        state = "金叉"
    elif dif < dea and previous_dif >= previous_dea:
        state = "死叉"
    elif dif > dea and dif > 0 and dea > 0:
        state = "零轴上多头"
    elif dif < dea and dif < 0 and dea < 0:
        state = "零轴下空头"
    else:
        state = "收敛"
    return MacdValue(dif=dif, dea=dea, histogram=histogram, state=state)


def calculate_share_flows(
    points: Sequence[SharePoint],
    bars: Sequence[DailyBar],
    *,
    windows: Sequence[int] = (5, 10, 20),
    split_factors: Optional[Mapping[date, float]] = None,
) -> dict[int, FlowWindow]:
    _validate_bars(bars)
    by_date: dict[date, SharePoint] = {}
    for point in points:
        if point.date in by_date or not math.isfinite(point.shares) or point.shares < 0:
            raise ReportDataError("malformed_share_point")
        by_date[point.date] = point
    factors = dict(split_factors or {})
    results: dict[int, FlowWindow] = {}
    for window in windows:
        if window <= 0:
            raise ReportDataError("invalid_flow_window")
        if len(bars) < window + 1:
            results[window] = FlowWindow(window, None, "close", "insufficient_flow_history")
            continue
        total = 0.0
        reason: Optional[str] = None
        start = len(bars) - window
        for index in range(start, len(bars)):
            previous_bar = bars[index - 1]
            current_bar = bars[index]
            previous = by_date.get(previous_bar.date)
            current = by_date.get(current_bar.date)
            if previous is None or current is None:
                reason = "missing_share_date"
                break
            factor = factors.get(current_bar.date)
            if factor is not None:
                if not math.isfinite(factor) or factor <= 0:
                    raise ReportDataError("invalid_split_factor")
                adjusted_previous = previous.shares * factor
            else:
                adjusted_previous = previous.shares
                if _looks_like_unresolved_split(previous.shares, current.shares, previous_bar.close, current_bar.close):
                    reason = "corporate_action_unresolved"
                    break
            total += (current.shares - adjusted_previous) * current_bar.close
        results[window] = FlowWindow(
            window=window,
            value_cny=None if reason else total,
            price_basis="close",
            reason=reason,
        )
    return results


def score_sentiment(
    *,
    flow_5d_cny: Optional[float],
    aum_cny: Optional[float],
    volume_ratio: Optional[float],
    market_breadth_pct: Optional[float],
    rsi14: Optional[float],
    kdj_state: Optional[str],
    macd_state: Optional[str],
) -> SentimentValue:
    components: list[tuple[str, float, float]] = []
    missing: list[str] = []
    if flow_5d_cny is None or aum_cny is None or not math.isfinite(aum_cny) or aum_cny <= 0:
        missing.append("flow_5d")
    else:
        components.append(("flow_5d", _clamp(50 + 2500 * flow_5d_cny / aum_cny), 0.35))
    if volume_ratio is None or not math.isfinite(volume_ratio) or volume_ratio < 0:
        missing.append("volume_ratio")
    else:
        components.append(("volume_ratio", _clamp(50 + 50 * (volume_ratio - 1)), 0.20))
    if market_breadth_pct is None or not math.isfinite(market_breadth_pct):
        missing.append("market_breadth")
    else:
        components.append(("market_breadth", _clamp(market_breadth_pct), 0.20))
    if rsi14 is None or not math.isfinite(rsi14):
        missing.append("rsi14")
    else:
        components.append(("rsi14", _clamp(rsi14), 0.10))
    kdj_scores = {"超卖": 10, "空头": 35, "死叉": 25, "中性": 50, "金叉": 75, "多头": 65, "超买": 90}
    if kdj_state not in kdj_scores:
        missing.append("kdj")
    else:
        components.append(("kdj", float(kdj_scores[kdj_state]), 0.075))
    macd_scores = {"零轴下空头": 25, "死叉": 30, "收敛": 50, "金叉": 70, "零轴上多头": 75}
    if macd_state not in macd_scores:
        missing.append("macd")
    else:
        components.append(("macd", float(macd_scores[macd_state]), 0.075))
    total_weight = sum(weight for _, _, weight in components)
    if total_weight == 0:
        raise ReportDataError("missing_all_sentiment_inputs")
    score = sum(value * weight for _, value, weight in components) / total_weight
    if score < 20:
        label = "极冷"
    elif score < 40:
        label = "偏冷"
    elif score < 60:
        label = "中性"
    elif score < 80:
        label = "偏热"
    else:
        label = "过热"
    return SentimentValue(score=score, label=label, missing_inputs=tuple(missing))


def validate_sector_context(context: Mapping[str, Any], sectors: Sequence[str]) -> None:
    """Validate that each report sector resolves to complete dated evidence."""

    themes = context.get("themes")
    sector_theme = context.get("sector_theme")
    if not isinstance(themes, Mapping) or not isinstance(sector_theme, Mapping):
        raise ReportDataError("malformed_sector_context")
    for sector in sectors:
        theme_name = sector_theme.get(sector)
        if not isinstance(theme_name, str):
            raise ReportDataError(f"unmapped_sector:{sector}")
        theme = themes.get(theme_name)
        if not isinstance(theme, Mapping):
            raise ReportDataError(f"missing_theme:{theme_name}")
        for dimension in ("policy", "fundamental"):
            evidence = theme.get(dimension)
            if not isinstance(evidence, Mapping):
                raise ReportDataError(f"missing_{dimension}_evidence:{theme_name}")
            for field in ("text", "title", "publisher", "date", "url"):
                value = evidence.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise ReportDataError(
                        f"missing_{dimension}_{field}:{theme_name}"
                    )
            try:
                date.fromisoformat(str(evidence["date"]))
            except ValueError as exc:
                raise ReportDataError(
                    f"invalid_{dimension}_date:{theme_name}"
                ) from exc
            if not str(evidence["url"]).startswith("https://"):
                raise ReportDataError(f"invalid_{dimension}_url:{theme_name}")


def render_report_markdown(report: Mapping[str, Any]) -> str:
    """Render the enhanced review as a Feishu-compatible Markdown document."""

    title = str(report.get("title") or "ETF精简代表池技术面审阅")
    data_date = str(report.get("data_date") or "")
    generated_at = str(report.get("generated_at") or "")
    definition = str(report.get("flow_definition") or "")
    rows = list(report.get("rows", []))
    counts = {
        action: sum(str(row.get("action")) == action for row in rows)
        for action in ("技术候选", "观察", "不追涨", "暂缓")
    }
    lines = [
        f"# {title}",
        "",
        f"- 数据日期：{data_date}",
        f"- 生成时间：{generated_at}",
        f"- 份额净流入口径：{definition}",
        "- 本表用于规则化观察，不构成收益承诺；买入前仍需核对实时价格、溢折价与最新公告。",
        f"- 状态概览：技术候选 {counts['技术候选']} 只、观察 {counts['观察']} 只、不追涨 {counts['不追涨']} 只、暂缓 {counts['暂缓']} 只。",
        "- 当前结论：本表尚未完成24小时内双来源催化、实时溢折价和相对基准强度复核，因此不输出买入指令。",
        "",
        "| 状态 | 代码 | 名称 | 趋势 | 5日 | 10日 | 20日 | RSI14 | KDJ | MACD | 情绪 | 净流入截至 | 5日份额净流入 | 10日份额净流入 | 20日份额净流入 | 政策面 | 基本面 | 技术面 | 情绪面 |",
        "|---|---|---|---|---:|---:|---:|---:|---|---|---|---|---:|---:|---:|---|---|---|---|",
    ]
    for row in rows:
        kdj = _mapping(row.get("kdj"))
        macd = _mapping(row.get("macd"))
        sentiment = _mapping(row.get("sentiment"))
        flows = _mapping(row.get("flows"))
        values = [
            row.get("action", ""),
            row.get("code", ""),
            row.get("name", ""),
            row.get("trend", ""),
            _format_pct(row.get("ret5_pct")),
            _format_pct(row.get("ret10_pct")),
            _format_pct(row.get("ret20_pct")),
            _format_number(row.get("rsi14"), 1),
            f"K {_format_number(kdj.get('k'), 1)} / D {_format_number(kdj.get('d'), 1)} / J {_format_number(kdj.get('j'), 1)}（{kdj.get('state', 'N/A')}）",
            f"DIF {_format_number(macd.get('dif'), 4)} / DEA {_format_number(macd.get('dea'), 4)} / 柱 {_format_number(macd.get('histogram'), 4)}（{macd.get('state', 'N/A')}）",
            f"{_format_number(sentiment.get('score'), 1)}（{sentiment.get('label', 'N/A')}）",
            row.get("flow_as_of") or "N/A",
            _format_flow(_mapping(flows.get("5"))),
            _format_flow(_mapping(flows.get("10"))),
            _format_flow(_mapping(flows.get("20"))),
            row.get("policy_reason", ""),
            row.get("fundamental_reason", ""),
            row.get("technical_reason", ""),
            row.get("sentiment_reason", ""),
        ]
        lines.append("| " + " | ".join(_escape_markdown(value) for value in values) + " |")
    lines.extend(
        [
            "",
            "## 数据说明",
            "",
            "- 5/10/20日净流入为交易所披露基金份额的相邻交易日变化乘以当日收盘价后求和；这是份额申赎资金的估算，不等同于二级市场主动买卖资金。",
            "- 单个窗口缺少份额日期或存在无法解释的基金份额折算时，仅该窗口显示 N/A，不以 0 代替，也不扩大为全表错误。",
            "- KDJ 参数为 9，MACD 参数为 12/26/9；情绪分数会对缺失分项重新归一化权重。技术候选只是进入后续催化、溢价和相对强度复核，不等同于买入信号。",
            "",
            "## 数据来源",
            "",
            "- 基金份额：[上海证券交易所 ETF 规模](https://www.sse.com.cn/assortment/fund/etf/list/scale/)；[深圳证券交易所 ETF 基金规模](https://www.szse.cn/market/fund/volume/etf/index.html)。",
            "- 复权日线：腾讯公共行情接口；成交前以券商实时行情为准。份额流的价格基准为当日收盘价。",
            "- 政策面与基本面：每行均附发布机构、日期、标题和原始链接；背景证据不自动视为24小时内交易催化。",
            "",
        ]
    )
    return "\n".join(lines)


def render_report_csv(report: Mapping[str, Any]) -> str:
    """Render a flat, machine-readable companion CSV."""

    headers = [
        "状态", "代码", "名称", "趋势", "5日涨跌幅_%", "10日涨跌幅_%", "20日涨跌幅_%",
        "RSI14", "K", "D", "J", "KDJ状态", "DIF", "DEA", "MACD柱", "MACD状态",
        "情绪分数", "情绪标签", "情绪缺失项", "净流入截至", "5日份额净流入_元", "5日净流入错误",
        "10日份额净流入_元", "10日净流入错误", "20日份额净流入_元", "20日净流入错误",
        "政策面理由", "基本面理由", "技术面理由", "情绪面理由",
    ]
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=headers, lineterminator="\n")
    writer.writeheader()
    for row in report.get("rows", []):
        kdj = _mapping(row.get("kdj"))
        macd = _mapping(row.get("macd"))
        sentiment = _mapping(row.get("sentiment"))
        flows = _mapping(row.get("flows"))
        flow5 = _mapping(flows.get("5"))
        flow10 = _mapping(flows.get("10"))
        flow20 = _mapping(flows.get("20"))
        writer.writerow(
            {
                "状态": row.get("action", ""),
                "代码": row.get("code", ""),
                "名称": row.get("name", ""),
                "趋势": row.get("trend", ""),
                "5日涨跌幅_%": _csv_number(row.get("ret5_pct"), 4),
                "10日涨跌幅_%": _csv_number(row.get("ret10_pct"), 4),
                "20日涨跌幅_%": _csv_number(row.get("ret20_pct"), 4),
                "RSI14": _csv_number(row.get("rsi14"), 4),
                "K": _csv_number(kdj.get("k"), 2),
                "D": _csv_number(kdj.get("d"), 2),
                "J": _csv_number(kdj.get("j"), 2),
                "KDJ状态": kdj.get("state", ""),
                "DIF": _csv_number(macd.get("dif"), 6),
                "DEA": _csv_number(macd.get("dea"), 6),
                "MACD柱": _csv_number(macd.get("histogram"), 6),
                "MACD状态": macd.get("state", ""),
                "情绪分数": _csv_number(sentiment.get("score"), 2),
                "情绪标签": sentiment.get("label", ""),
                "情绪缺失项": ";".join(sentiment.get("missing_inputs", [])),
                "净流入截至": row.get("flow_as_of") or "",
                "5日份额净流入_元": _csv_number(flow5.get("value_cny"), 2),
                "5日净流入错误": flow5.get("reason") or "",
                "10日份额净流入_元": _csv_number(flow10.get("value_cny"), 2),
                "10日净流入错误": flow10.get("reason") or "",
                "20日份额净流入_元": _csv_number(flow20.get("value_cny"), 2),
                "20日净流入错误": flow20.get("reason") or "",
                "政策面理由": row.get("policy_reason", ""),
                "基本面理由": row.get("fundamental_reason", ""),
                "技术面理由": row.get("technical_reason", ""),
                "情绪面理由": row.get("sentiment_reason", ""),
            }
        )
    return output.getvalue()


def _looks_like_unresolved_split(
    previous_shares: float,
    current_shares: float,
    previous_price: float,
    current_price: float,
) -> bool:
    if previous_shares <= 0 or current_shares <= 0:
        return False
    share_ratio = current_shares / previous_shares
    price_ratio = current_price / previous_price
    large_ratio = share_ratio >= 1.5 or share_ratio <= (2 / 3)
    return large_ratio and abs(share_ratio * price_ratio - 1) <= 0.05


def _validate_bars(bars: Sequence[DailyBar]) -> None:
    if not bars:
        raise ReportDataError("missing_bars")
    for left, right in zip(bars, bars[1:]):
        if left.date >= right.date:
            raise ReportDataError("conflicting_bar_order")


def _clamp(value: float) -> float:
    return min(100.0, max(0.0, value))


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _format_pct(value: Any) -> str:
    return "N/A" if not isinstance(value, (int, float)) else f"{value:+.2f}%"


def _format_number(value: Any, decimals: int) -> str:
    return "N/A" if not isinstance(value, (int, float)) else f"{value:.{decimals}f}"


def _csv_number(value: Any, decimals: int) -> str:
    return "" if not isinstance(value, (int, float)) else f"{value:.{decimals}f}"


def _format_flow(flow: Mapping[str, Any]) -> str:
    value = flow.get("value_cny")
    if isinstance(value, (int, float)):
        if abs(value) >= 100_000_000:
            return f"{value / 100_000_000:+.2f}亿"
        return f"{value / 10_000:+.2f}万"
    reasons = {
        "missing_share_date": "缺少交易日份额",
        "corporate_action_unresolved": "基金份额折算待核对",
        "insufficient_flow_history": "历史交易日不足",
        "share_source_unavailable": "交易所份额源不可用",
    }
    reason = str(flow.get("reason") or "数据缺失")
    return f"N/A（{reasons.get(reason, reason)}）"


def _escape_markdown(value: Any) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")
