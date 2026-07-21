#!/usr/bin/env python3.12
"""For each representative ETF, find the historical setup with highest
deterministic forward returns after multi-window drawdowns + tech signals.

Outputs JSON with current dd10/20/30/60/120 and one best-condition label.
"""

from __future__ import annotations

import argparse
import json
import math
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from src.market_data import DailyBar, MarketDataError, PublicMarketDataProvider, parse_eastmoney_bars, parse_tencent_bars, _secid, _tencent_symbol


MODULE_ROOT = Path(__file__).resolve().parent
DEFAULT_SEED = MODULE_ROOT / "reports" / "representative-technical-review-2026-07-21.json"
DEFAULT_OUT = MODULE_ROOT / "reports" / "etf68-edge-conditions-2026-07-21.json"
SHANGHAI = ZoneInfo("Asia/Shanghai")

DD_WINDOWS = (10, 20, 30, 60, 120)
FORWARD_DAYS = 10
MIN_SAMPLES = 8
BAR_LIMIT = 400


def _opener(url: str, timeout: int = 15):
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        },
    )
    return urlopen(req, timeout=timeout)


class LongHistoryProvider(PublicMarketDataProvider):
    EASTMONEY_BARS = (
        "https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        "secid={secid}&ut=7eea3edcaed734bea9cbfc24409ed989&klt=101&fqt=1&end=20500101"
        f"&lmt={BAR_LIMIT}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    )
    TENCENT_BARS = (
        "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
        f"param={{symbol}},day,,,{BAR_LIMIT},qfq"
    )

    def get_daily_bars(self, code: str) -> Sequence[DailyBar]:
        fetched_at = self.clock()
        try:
            payload = self._json(self.EASTMONEY_BARS.format(secid=_secid(code)))
            return parse_eastmoney_bars(payload, fetched_at)
        except MarketDataError:
            payload = self._json(self.TENCENT_BARS.format(symbol=_tencent_symbol(code)))
            return parse_tencent_bars(payload, code, fetched_at)


def rsi14_series(closes: list[float]) -> list[float | None]:
    out: list[float | None] = [None] * len(closes)
    for i in range(14, len(closes)):
        gains = 0.0
        losses = 0.0
        for j in range(i - 13, i + 1):
            chg = closes[j] - closes[j - 1]
            if chg >= 0:
                gains += chg
            else:
                losses -= chg
        avg_gain = gains / 14
        avg_loss = losses / 14
        if avg_loss == 0:
            out[i] = 100.0
        else:
            rs = avg_gain / avg_loss
            out[i] = 100 - 100 / (1 + rs)
    return out


def kdj_state_series(highs: list[float], lows: list[float], closes: list[float], period: int = 9) -> list[str | None]:
    out: list[str | None] = [None] * len(closes)
    k = 50.0
    d = 50.0
    for i in range(len(closes)):
        start = max(0, i - period + 1)
        window_h = max(highs[start : i + 1])
        window_l = min(lows[start : i + 1])
        rsv = 50.0 if window_h == window_l else (closes[i] - window_l) / (window_h - window_l) * 100
        prev_k, prev_d = k, d
        k = (2 * k + rsv) / 3
        d = (2 * d + k) / 3
        if i < period - 1:
            continue
        if k >= 80 and d >= 80:
            state = "超买"
        elif k <= 20 and d <= 20:
            state = "超卖"
        elif k > d and prev_k <= prev_d:
            state = "金叉"
        elif k < d and prev_k >= prev_d:
            state = "死叉"
        elif k > d:
            state = "多头"
        elif k < d:
            state = "空头"
        else:
            state = "中性"
        out[i] = state
    return out


def macd_state_series(closes: list[float]) -> list[str | None]:
    out: list[str | None] = [None] * len(closes)
    if not closes:
        return out
    ema12 = closes[0]
    ema26 = closes[0]
    dea = 0.0
    dif = 0.0
    for i, close in enumerate(closes):
        ema12 = (2 * close + 11 * ema12) / 13
        ema26 = (2 * close + 25 * ema26) / 27
        prev_dif, prev_dea = dif, dea
        dif = ema12 - ema26
        dea = (2 * dif + 8 * dea) / 10
        if i < 25:
            continue
        if dif > dea and prev_dif <= prev_dea:
            state = "金叉"
        elif dif < dea and prev_dif >= prev_dea:
            state = "死叉"
        elif dif > dea and dif > 0 and dea > 0:
            state = "零轴上多头"
        elif dif < dea and dif < 0 and dea < 0:
            state = "零轴下空头"
        else:
            state = "收敛"
        out[i] = state
    return out


def ma(values: list[float], end: int, window: int) -> float | None:
    if end + 1 < window:
        return None
    chunk = values[end - window + 1 : end + 1]
    return sum(chunk) / window


def trend_at(closes: list[float], i: int) -> str | None:
    ma20 = ma(closes, i, 20)
    ma60 = ma(closes, i, 60)
    if ma20 is None or ma60 is None or i < 24:
        return None
    ma20_prev = ma(closes, i - 5, 20)
    if ma20_prev is None:
        return None
    rising = ma20 > ma20_prev
    c = closes[i]
    if c > ma20 > ma60 and rising:
        return "多头"
    if c < ma20 and c < ma60:
        return "空头"
    return "震荡"


def drawdown_at(closes: list[float], i: int, window: int) -> float | None:
    if i + 1 < window:
        return None
    peak = max(closes[i - window + 1 : i + 1])
    if peak <= 0:
        return None
    return (peak - closes[i]) / peak * 100


def dd_bucket(dd: float | None) -> str | None:
    if dd is None:
        return None
    if dd < 3:
        return "浅回撤(<3%)"
    if dd < 8:
        return "中回撤(3-8%)"
    if dd < 15:
        return "深回撤(8-15%)"
    return "极深回撤(≥15%)"


def rsi_bucket(rsi: float | None) -> str | None:
    if rsi is None:
        return None
    if rsi < 30:
        return "RSI超卖"
    if rsi < 45:
        return "RSI偏低"
    if rsi < 55:
        return "RSI中性"
    if rsi < 70:
        return "RSI偏高"
    return "RSI超买"


@dataclass
class ConditionStats:
    n: int = 0
    wins: int = 0
    sum_ret: float = 0.0
    sum_sq: float = 0.0

    def add(self, ret: float) -> None:
        self.n += 1
        if ret > 0:
            self.wins += 1
        self.sum_ret += ret
        self.sum_sq += ret * ret

    @property
    def mean(self) -> float:
        return self.sum_ret / self.n if self.n else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def std(self) -> float:
        if self.n < 2:
            return 0.0
        mean = self.mean
        var = max(0.0, self.sum_sq / self.n - mean * mean)
        return math.sqrt(var)

    @property
    def deterministic_score(self) -> float:
        """Lower confidence bound of mean forward return (确定性收益)."""
        if self.n < MIN_SAMPLES:
            return float("-inf")
        return self.mean - self.std / math.sqrt(self.n)


def analyze_code(code: str, name: str, bars: Sequence[DailyBar]) -> dict[str, Any]:
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    n = len(closes)

    rsi_s = rsi14_series(closes)
    kdj_s = kdj_state_series(highs, lows, closes)
    macd_s = macd_state_series(closes)

    # current drawdowns
    last = n - 1
    current_dd = {f"dd{w}": round(drawdown_at(closes, last, w) or 0.0, 2) for w in DD_WINDOWS}

    stats: dict[str, ConditionStats] = defaultdict(ConditionStats)
    # start when we have 120d history + indicators; end when forward window exists
    start_i = max(120, 60, 26)
    for i in range(start_i, n - FORWARD_DAYS):
        fwd = (closes[i + FORWARD_DAYS] / closes[i] - 1) * 100
        dds = {w: drawdown_at(closes, i, w) for w in DD_WINDOWS}
        # dominant drawdown window = largest current dd among windows
        valid = [(w, dds[w]) for w in DD_WINDOWS if dds[w] is not None]
        if not valid:
            continue
        dom_w, dom_dd = max(valid, key=lambda x: x[1] or 0.0)
        bucket = dd_bucket(dom_dd)
        rsi_b = rsi_bucket(rsi_s[i])
        kdj = kdj_s[i]
        macd = macd_s[i]
        trend = trend_at(closes, i)
        if not all([bucket, rsi_b, kdj, macd, trend]):
            continue

        # Candidate conditions (interpretable composites + key single factors)
        candidates = [
            f"近{dom_w}日{bucket}+{rsi_b}",
            f"近{dom_w}日{bucket}+KDJ{kdj}",
            f"近{dom_w}日{bucket}+MACD{macd}",
            f"近{dom_w}日{bucket}+趋势{trend}",
            f"近{dom_w}日{bucket}+{rsi_b}+KDJ{kdj}",
            f"{rsi_b}+KDJ{kdj}+MACD{macd}",
            f"趋势{trend}+{rsi_b}",
        ]
        # Also tag deep-drawdown specific windows independently when that window is deep
        for w in DD_WINDOWS:
            dd = dds[w]
            if dd is not None and dd >= 8:
                candidates.append(f"近{w}日回撤≥8%+{rsi_b}")
                candidates.append(f"近{w}日回撤≥8%+KDJ{kdj}")

        for label in candidates:
            stats[label].add(fwd)

    best_label = None
    best_score = float("-inf")
    best_stat: ConditionStats | None = None
    for label, st in stats.items():
        score = st.deterministic_score
        if score > best_score:
            best_score = score
            best_label = label
            best_stat = st

    if best_label is None or best_stat is None:
        edge = "样本不足，暂无稳健优势条件"
        detail = None
    else:
        edge = (
            f"{best_label}｜样本{best_stat.n}｜胜率{best_stat.win_rate*100:.0f}%"
            f"｜此后{FORWARD_DAYS}日均{best_stat.mean:+.2f}%｜确定性{best_score:+.2f}%"
        )
        detail = {
            "condition": best_label,
            "samples": best_stat.n,
            "win_rate_pct": round(best_stat.win_rate * 100, 1),
            "avg_fwd_ret_pct": round(best_stat.mean, 2),
            "deterministic_score_pct": round(best_score, 2),
            "forward_days": FORWARD_DAYS,
        }

    # top3 for debugging / canvas
    ranked = sorted(
        ((lab, st) for lab, st in stats.items() if st.n >= MIN_SAMPLES),
        key=lambda x: x[1].deterministic_score,
        reverse=True,
    )[:3]
    top3 = [
        {
            "condition": lab,
            "samples": st.n,
            "win_rate_pct": round(st.win_rate * 100, 1),
            "avg_fwd_ret_pct": round(st.mean, 2),
            "deterministic_score_pct": round(st.deterministic_score, 2),
        }
        for lab, st in ranked
    ]

    return {
        "code": code,
        "name": name,
        "bars": n,
        **current_dd,
        "best_edge": edge,
        "best_detail": detail,
        "top3": top3,
        "current_tech": {
            "rsi14": None if rsi_s[last] is None else round(rsi_s[last], 1),
            "kdj": kdj_s[last],
            "macd": macd_s[last],
            "trend": trend_at(closes, last),
        },
    }


def collect_bars(codes: list[str], provider: LongHistoryProvider, workers: int = 8):
    bars_by_code: dict[str, Sequence[DailyBar]] = {}
    errors: dict[str, str] = {}

    def one(code: str):
        try:
            return code, provider.get_daily_bars(code), None
        except Exception as exc:
            reason = getattr(exc, "reason", None) or type(exc).__name__
            return code, None, str(reason)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = [pool.submit(one, c) for c in codes]
        for fut in as_completed(futs):
            code, bars, err = fut.result()
            if err or bars is None:
                errors[code] = err or "empty"
            else:
                bars_by_code[code] = bars
            time.sleep(0.02)
    return bars_by_code, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=Path, default=DEFAULT_SEED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--workers", type=int, default=6)
    args = parser.parse_args()

    seed = json.loads(args.seed.read_text(encoding="utf-8"))
    rows = seed["rows"]
    meta = {str(r["code"]): str(r["name"]) for r in rows}
    codes = list(meta)

    provider = LongHistoryProvider(
        calendar_provider=object(),
        catalyst_provider=object(),
        opener=_opener,
        clock=lambda: datetime.now(timezone.utc),
    )
    bars_by_code, errors = collect_bars(codes, provider, workers=args.workers)
    if errors:
        # retry failed once serially
        for code, reason in list(errors.items()):
            try:
                time.sleep(0.3)
                bars_by_code[code] = provider.get_daily_bars(code)
                errors.pop(code, None)
            except Exception as exc:
                errors[code] = getattr(exc, "reason", None) or str(exc)

    if errors:
        raise RuntimeError(f"bar_fetch_failed:{errors}")

    results = []
    for code in codes:
        results.append(analyze_code(code, meta[code], bars_by_code[code]))

    payload = {
        "generated_at": datetime.now(SHANGHAI).isoformat(),
        "data_date": seed.get("data_date") or seed.get("rows", [{}])[0].get("date"),
        "methodology": {
            "dd_windows": list(DD_WINDOWS),
            "forward_days": FORWARD_DAYS,
            "min_samples": MIN_SAMPLES,
            "score": "mean_fwd_ret - std/sqrt(n)",
            "bar_limit": BAR_LIMIT,
            "note": "确定性收益=历史同条件下前瞻收益均值的保守下界；非实盘保证。",
        },
        "rows": results,
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output} rows={len(results)}")
    # preview a few
    for r in results[:5]:
        print(r["code"], r["name"], r["best_edge"][:80])
    # Archive canvas + JSON for this data_date
    try:
        from save_snapshot import main as save_snapshot_main
        import sys as _sys

        day = str(payload.get("data_date") or "")
        argv = _sys.argv[:]
        _sys.argv = ["save_snapshot.py"] + ([f"--date={day}"] if day else [])
        try:
            save_snapshot_main()
        finally:
            _sys.argv = argv
    except Exception as exc:  # noqa: BLE001 — snapshot must not fail the analysis
        print(f"snapshot_archive_skipped:{exc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
