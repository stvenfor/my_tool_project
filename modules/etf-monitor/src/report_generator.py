"""Build the date-stamped representative ETF review from validated inputs."""

from __future__ import annotations

import math
from dataclasses import asdict
from datetime import datetime
from statistics import fmean
from typing import Any, Mapping, Sequence

from .market_data import DailyBar
from .reporting import (
    FlowWindow,
    SharePoint,
    calculate_kdj,
    calculate_macd,
    calculate_share_flows,
    score_sentiment,
    validate_sector_context,
)


def build_report(
    *,
    seed: Mapping[str, Any],
    bars_by_code: Mapping[str, Sequence[DailyBar]],
    shares_by_code: Mapping[str, Sequence[SharePoint]],
    share_errors: Mapping[str, str],
    context: Mapping[str, Any],
    generated_at: datetime,
) -> dict[str, Any]:
    """Create one report without performing I/O."""

    source_rows = list(seed.get("rows", []))
    sectors = sorted({str(row["sector"]) for row in source_rows})
    validate_sector_context(context, sectors)
    breadth = _market_breadth(
        source_rows, bars_by_code, shares_by_code, share_errors
    )
    output_rows = []
    for metadata in source_rows:
        code = str(metadata["code"])
        bars = list(bars_by_code[code])
        if len(bars) < 60:
            raise ValueError(f"insufficient_report_bars:{code}")
        close = bars[-1].close
        ma20 = fmean(bar.close for bar in bars[-20:])
        ma60 = fmean(bar.close for bar in bars[-60:])
        prior_ma20 = fmean(bar.close for bar in bars[-25:-5])
        ma20_rising = ma20 > prior_ma20
        ret1 = _return_pct(bars, 1)
        ret5 = _return_pct(bars, 5)
        ret10 = _return_pct(bars, 10)
        ret20 = _return_pct(bars, 20)
        rsi14 = _rsi14(bars)
        kdj = calculate_kdj(bars)
        macd = calculate_macd(bars)
        volume_ratio = _volume_ratio(bars)
        code_points = shares_by_code.get(code, ())
        flows, flow_as_of = _flows_for_code(
            code=code,
            bars=bars,
            points=code_points,
            error=share_errors.get(code),
        )
        latest_share = _latest_share(code_points, flow_as_of)
        aum_cny = latest_share.shares * close if latest_share is not None else None
        sentiment = score_sentiment(
            flow_5d_cny=flows[5].value_cny,
            aum_cny=aum_cny,
            volume_ratio=volume_ratio,
            market_breadth_pct=breadth,
            rsi14=rsi14,
            kdj_state=kdj.state,
            macd_state=macd.state,
        )
        distance_ma20 = (close / ma20 - 1) * 100
        trend = _trend(close, ma20, ma60, ma20_rising)
        action = _action(trend, ret1, distance_ma20, sentiment.score)
        theme = _theme_for(
            context, str(metadata["sector"]), str(metadata.get("market", "CN"))
        )
        row = dict(metadata)
        row.update(
            {
                "date": bars[-1].date.isoformat(),
                "close": close,
                "ma20": ma20,
                "ma60": ma60,
                "ma20_rising": ma20_rising,
                "ret1_pct": ret1,
                "ret5_pct": ret5,
                "ret10_pct": ret10,
                "ret20_pct": ret20,
                "rsi14": rsi14,
                "distance_ma20_pct": distance_ma20,
                "volume_ratio": volume_ratio,
                "trend": trend,
                "action": action,
                "kdj": asdict(kdj),
                "macd": asdict(macd),
                "flows": {str(window): asdict(flow) for window, flow in flows.items()},
                "flow_as_of": flow_as_of.isoformat() if flow_as_of is not None else None,
                "aum_estimate_cny": aum_cny,
                "sentiment": asdict(sentiment),
                "policy_reason": _evidence_reason(theme["policy"]),
                "fundamental_reason": _evidence_reason(theme["fundamental"]),
                "technical_reason": _technical_reason(
                    close=close,
                    ma20=ma20,
                    ma60=ma60,
                    ma20_rising=ma20_rising,
                    ret5=ret5,
                    ret10=ret10,
                    ret20=ret20,
                    rsi14=rsi14,
                    kdj_state=kdj.state,
                    macd_state=macd.state,
                ),
                "sentiment_reason": _sentiment_reason(
                    sentiment.score,
                    sentiment.label,
                    flows,
                    volume_ratio,
                    breadth,
                    sentiment.missing_inputs,
                ),
            }
        )
        row.pop("flow_status", None)
        row.pop("reason", None)
        output_rows.append(row)
    output_rows.sort(
        key=lambda row: (
            _action_rank(str(row["action"])),
            -float(row["sentiment"]["score"]),
            -float(row["ret20_pct"]),
        )
    )
    data_dates = {row["date"] for row in output_rows}
    return {
        "title": f"{max(data_dates)} ETF精简代表池技术面审阅",
        "generated_at": generated_at.isoformat(),
        "data_date": max(data_dates),
        "flow_definition": "交易所基金份额变化 × 当日收盘价",
        "flow_price_basis": "close",
        "flow_sources": {
            "SSE": "上交所ETF规模（TOT_VOL，万份）",
            "SZSE": "深交所基金规模（份）",
        },
        "breadth_pct": breadth,
        "rows": output_rows,
    }


def _flows_for_code(
    *,
    code: str,
    bars: Sequence[DailyBar],
    points: Sequence[SharePoint],
    error: str | None,
) -> tuple[dict[int, FlowWindow], Any]:
    if error:
        return (
            {
                window: FlowWindow(window, None, "close", error)
                for window in (5, 10, 20)
            },
            None,
        )
    code_points = [point for point in points if point.code == code]
    bar_dates = {bar.date for bar in bars}
    available_dates = sorted(
        point.date for point in code_points if point.date in bar_dates
    )
    if not available_dates:
        return calculate_share_flows(code_points, bars), None
    as_of = available_dates[-1]
    eligible_bars = [bar for bar in bars if bar.date <= as_of]
    return calculate_share_flows(code_points, eligible_bars), as_of


def _market_breadth(
    rows: Sequence[Mapping[str, Any]],
    bars_by_code: Mapping[str, Sequence[DailyBar]],
    shares_by_code: Mapping[str, Sequence[SharePoint]],
    share_errors: Mapping[str, str],
) -> float:
    above_ma20: list[bool] = []
    above_ma60: list[bool] = []
    rising_ma20: list[bool] = []
    positive_5d: list[bool] = []
    positive_flow_5d: list[bool] = []
    for row in rows:
        code = str(row["code"])
        bars = bars_by_code.get(str(row["code"]), ())
        if len(bars) < 60:
            continue
        ma20 = fmean(bar.close for bar in bars[-20:])
        ma60 = fmean(bar.close for bar in bars[-60:])
        prior_ma20 = fmean(bar.close for bar in bars[-25:-5])
        above_ma20.append(bars[-1].close > ma20)
        above_ma60.append(bars[-1].close > ma60)
        rising_ma20.append(ma20 > prior_ma20)
        positive_5d.append(_return_pct(bars, 5) > 0)
        flows, _ = _flows_for_code(
            code=code,
            bars=bars,
            points=shares_by_code.get(code, ()),
            error=share_errors.get(code),
        )
        if flows[5].value_cny is not None:
            positive_flow_5d.append(flows[5].value_cny > 0)
    components = [
        sum(values) / len(values) * 100
        for values in (
            above_ma20,
            above_ma60,
            rising_ma20,
            positive_5d,
            positive_flow_5d,
        )
        if values
    ]
    return 50.0 if not components else fmean(components)


def _return_pct(bars: Sequence[DailyBar], window: int) -> float:
    return (bars[-1].close / bars[-window - 1].close - 1) * 100


def _rsi14(bars: Sequence[DailyBar]) -> float:
    changes = [right.close - left.close for left, right in zip(bars[-15:-1], bars[-14:])]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]
    average_gain = fmean(gains)
    average_loss = fmean(losses)
    if average_loss == 0:
        return 100.0 if average_gain > 0 else 50.0
    relative_strength = average_gain / average_loss
    return 100 - 100 / (1 + relative_strength)


def _volume_ratio(bars: Sequence[DailyBar]) -> float | None:
    if len(bars) < 25:
        return None
    baseline = fmean(bar.volume for bar in bars[-25:-5])
    if not math.isfinite(baseline) or baseline <= 0:
        return None
    return fmean(bar.volume for bar in bars[-5:]) / baseline


def _latest_share(
    points: Sequence[SharePoint], latest_date: Any
) -> SharePoint | None:
    matching = [point for point in points if point.date == latest_date]
    return matching[0] if len(matching) == 1 else None


def _trend(close: float, ma20: float, ma60: float, ma20_rising: bool) -> str:
    if close > ma20 > ma60 and ma20_rising:
        return "多头"
    if close < ma20 and close < ma60:
        return "空头"
    return "震荡"


def _action(trend: str, ret1: float, distance_ma20: float, sentiment: float) -> str:
    if trend == "空头":
        return "暂缓"
    if ret1 > 3 or distance_ma20 > 5 or sentiment >= 80:
        return "不追涨"
    if trend == "多头" and sentiment >= 45:
        return "技术候选"
    return "观察"


def _theme_for(
    context: Mapping[str, Any], sector: str, market: str
) -> Mapping[str, Any]:
    global_markets = {"US", "BR", "SEA", "JP", "DE"}
    theme_name = (
        "global_equity"
        if market.upper() in global_markets and "global_equity" in context["themes"]
        else context["sector_theme"][sector]
    )
    return context["themes"][theme_name]


def _evidence_reason(evidence: Mapping[str, Any]) -> str:
    label = f"{evidence['publisher']}｜{evidence['date']}｜{evidence['title']}"
    return f"{evidence['text']} [{label}]({evidence['url']})"


def _technical_reason(
    *,
    close: float,
    ma20: float,
    ma60: float,
    ma20_rising: bool,
    ret5: float,
    ret10: float,
    ret20: float,
    rsi14: float,
    kdj_state: str,
    macd_state: str,
) -> str:
    relative = "上方" if close > ma20 else "下方"
    long_relative = "上方" if close > ma60 else "下方"
    slope = "上行" if ma20_rising else "未上行"
    return (
        f"收盘价位于MA20{relative}、MA60{long_relative}，MA20{slope}；"
        f"5/10/20日涨跌幅分别为{ret5:+.2f}%/{ret10:+.2f}%/{ret20:+.2f}%，"
        f"RSI14={rsi14:.1f}，KDJ={kdj_state}，MACD={macd_state}。"
    )


def _sentiment_reason(
    score: float,
    label: str,
    flows: Mapping[int, FlowWindow],
    volume_ratio: float | None,
    breadth: float,
    missing_inputs: Sequence[str],
) -> str:
    flow_text = "/".join(_flow_reason_value(flows[window]) for window in (5, 10, 20))
    volume_text = "N/A" if volume_ratio is None else f"{volume_ratio:.2f}倍"
    missing = "无" if not missing_inputs else "、".join(missing_inputs)
    return (
        f"情绪分数{score:.1f}（{label}）；5/10/20日份额净流入为{flow_text}，"
        f"5日成交量相对前20日为{volume_text}，代表池综合宽度{breadth:.1f}%，"
        f"缺失分项：{missing}。"
    )


def _flow_reason_value(flow: FlowWindow) -> str:
    if flow.value_cny is None:
        return f"N/A({flow.reason})"
    return f"{flow.value_cny / 100_000_000:+.2f}亿"


def _action_rank(action: str) -> int:
    return {"技术候选": 0, "观察": 1, "不追涨": 2, "暂缓": 3}.get(action, 4)
