"""Validated, injectable market data for the ETF scanner.

The scanner consumes the ``MarketDataProvider`` protocol rather than making
network calls.  ``PublicMarketDataProvider`` is the optional standard-library
adapter for the documented Eastmoney and Tencent endpoints; tests inject local
fixture providers.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Mapping, Optional, Protocol, Sequence
from urllib.request import urlopen
from zoneinfo import ZoneInfo


QUOTE_MAX_AGE = timedelta(minutes=15)
SUPPORTING_DATA_MAX_AGE = timedelta(hours=24)
MAX_QUOTE_PRICE_DISAGREEMENT = 0.003
MAX_PREVIOUS_CLOSE_DISAGREEMENT = 0.003
MAX_TURNOVER_DISAGREEMENT = 0.10
MAX_QUOTE_BAR_DISAGREEMENT = 0.003
MIN_COMMON_RETURN_DATES = 21
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class MarketDataError(ValueError):
    """A fail-closed data-quality error with a stable machine-readable reason."""

    def __init__(self, reason: str, source_timestamp: Optional[datetime] = None):
        super().__init__(reason)
        self.reason = reason
        self.source_timestamp = source_timestamp


@dataclass(frozen=True)
class Quote:
    source: str
    price: float
    previous_close: float
    turnover_cny: float
    timestamp: datetime
    aum_cny: Optional[float] = None
    premium_pct: Optional[float] = None


@dataclass(frozen=True)
class ValidatedQuote:
    code: str
    current_price: float
    previous_close: float
    turnover_cny: float
    source_timestamp: datetime
    sources: tuple[str, ...]
    quotes: tuple[Quote, ...]


@dataclass(frozen=True)
class DailyBar:
    date: date
    open: float
    close: float
    high: float
    low: float
    volume: float
    turnover_cny: float
    source: str
    timestamp: datetime


@dataclass(frozen=True)
class TimedMetric:
    value: float
    source: str
    timestamp: datetime


@dataclass(frozen=True)
class TradingCalendarState:
    session_date: date
    is_trading_session: bool
    source: str
    timestamp: datetime


@dataclass(frozen=True)
class BenchmarkCalendarState:
    latest_completed_session_date: date
    source: str
    timestamp: datetime


@dataclass(frozen=True)
class CatalystEvidence:
    source: str
    reference: str
    event_timestamp: datetime
    collected_at: datetime


@dataclass(frozen=True)
class CatalystSnapshot:
    primary_confirmed: bool
    corroborated: bool
    adverse: bool
    primary_evidence: CatalystEvidence
    corroboration_evidence: CatalystEvidence


# Compatibility import for callers that used the former public type name.  The
# constructor is intentionally the stricter structured-evidence constructor.
CatalystConfirmation = CatalystSnapshot


@dataclass(frozen=True)
class MarketSnapshot:
    code: str
    market: str
    benchmark: str
    current_price: float
    previous_close: float
    quotes: tuple[Quote, ...]
    bars: tuple[DailyBar, ...]
    benchmark_bars: tuple[DailyBar, ...]
    aum_cny: float
    premium_pct: float
    aum_metric: TimedMetric
    premium_metric: TimedMetric
    catalyst: CatalystSnapshot
    session_date: date
    trading_calendar: TradingCalendarState
    benchmark_calendar: BenchmarkCalendarState
    observed_at: datetime
    source_timestamp: datetime
    sources: tuple[str, ...]

    @property
    def benchmark_session_date(self) -> date:
        return self.benchmark_calendar.latest_completed_session_date


class MarketDataProvider(Protocol):
    """Provider contract covering every independently injectable data input."""

    def get_current_quotes(self, code: str) -> Sequence[Any]: ...
    def get_daily_bars(self, code: str) -> Sequence[Any]: ...
    def get_aum(self, code: str) -> Any: ...
    def get_premium(self, code: str) -> Any: ...
    def get_benchmark_bars(self, benchmark: str) -> Sequence[Any]: ...
    def get_trading_calendar(self, session_date: date) -> Any: ...
    def get_benchmark_calendar(
        self, benchmark: str, market: str, as_of_date: date
    ) -> Any: ...
    def get_catalyst(self, code: str) -> Any: ...


def parse_eastmoney_quote(payload: Mapping[str, Any], fetched_at: datetime) -> Quote:
    """Parse an Eastmoney quote using the documented integer scales."""
    try:
        data = payload["data"]
        if not isinstance(data, Mapping):
            raise TypeError
        return Quote(
            source="eastmoney",
            price=_positive(data["f43"], "malformed_eastmoney_quote") / 1000,
            previous_close=_positive(data["f60"], "malformed_eastmoney_quote") / 1000,
            turnover_cny=_nonnegative(data["f48"], "malformed_eastmoney_quote"),
            timestamp=_timestamp(fetched_at, "malformed_eastmoney_timestamp"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, MarketDataError):
            raise
        raise MarketDataError("malformed_eastmoney_quote") from exc


def parse_tencent_quote(body: str) -> Quote:
    """Parse Tencent's GBK-decoded tilde-delimited ETF response."""
    try:
        quoted = body.split('="', 1)[1].rsplit('"', 1)[0]
        fields = quoted.split("~")
        if len(fields) <= 82:
            raise ValueError
        timestamp = datetime.strptime(fields[30], "%Y%m%d%H%M%S").replace(
            tzinfo=SHANGHAI_TZ
        )
        market_values = [
            _optional_number(fields[index]) for index in (44, 45)
        ]
        market_values = [value for value in market_values if value is not None and value > 0]
        aum_cny = max(market_values) * 100_000_000 if market_values else None
        premium = _optional_number(fields[77])
        return Quote(
            source="tencent",
            price=_positive(fields[3], "malformed_tencent_quote"),
            previous_close=_positive(fields[4], "malformed_tencent_quote"),
            turnover_cny=_nonnegative(fields[57], "malformed_tencent_quote") * 10_000,
            timestamp=timestamp,
            aum_cny=aum_cny,
            premium_pct=premium,
        )
    except (IndexError, TypeError, ValueError) as exc:
        if isinstance(exc, MarketDataError):
            raise
        raise MarketDataError("malformed_tencent_quote") from exc


def parse_eastmoney_bars(
    payload: Mapping[str, Any], fetched_at: datetime
) -> list[DailyBar]:
    """Parse Eastmoney's documented daily kline CSV fields."""
    try:
        rows = payload["data"]["klines"]
        if not isinstance(rows, list):
            raise TypeError
        timestamp = _timestamp(fetched_at, "malformed_eastmoney_timestamp")
        parsed = []
        for row in rows:
            fields = row.split(",")
            if len(fields) < 7:
                raise ValueError
            parsed.append(
                DailyBar(
                    date=date.fromisoformat(fields[0]),
                    open=_positive(fields[1], "malformed_eastmoney_bars"),
                    close=_positive(fields[2], "malformed_eastmoney_bars"),
                    high=_positive(fields[3], "malformed_eastmoney_bars"),
                    low=_positive(fields[4], "malformed_eastmoney_bars"),
                    volume=_nonnegative(fields[5], "malformed_eastmoney_bars"),
                    turnover_cny=_nonnegative(fields[6], "malformed_eastmoney_bars"),
                    source="eastmoney",
                    timestamp=timestamp,
                )
            )
        return _bars(parsed, "missing_eastmoney_bars")
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        if isinstance(exc, MarketDataError):
            raise
        raise MarketDataError("malformed_eastmoney_bars") from exc


def collect_market_snapshot(
    record: Mapping[str, Any],
    provider: MarketDataProvider,
    *,
    as_of: datetime,
) -> MarketSnapshot:
    """Collect one fail-closed snapshot from independently injectable inputs."""
    as_of = _shanghai_timestamp(as_of, "invalid_as_of_timestamp")
    try:
        code = str(record["code"])
        market = str(record["market"])
        benchmark = str(record["tracking_index"])
    except KeyError as exc:
        raise MarketDataError("missing_instrument_metadata") from exc

    calendar = collect_trading_session(provider, as_of)
    if calendar.is_trading_session is not True:
        raise MarketDataError("not_trading_session", calendar.timestamp)

    validated_quote = collect_current_quote(code, provider, as_of=as_of)

    bars = tuple(_bars(provider.get_daily_bars(code), "missing_daily_bars"))
    benchmark_bars = tuple(
        _bars(provider.get_benchmark_bars(benchmark), "missing_benchmark_bars")
    )
    _ordered_bars(bars)
    _ordered_bars(benchmark_bars)

    if market.upper() == "CN":
        benchmark_calendar = BenchmarkCalendarState(
            latest_completed_session_date=calendar.session_date,
            source=calendar.source,
            timestamp=calendar.timestamp,
        )
    else:
        getter = getattr(provider, "get_benchmark_calendar", None)
        if not callable(getter):
            raise MarketDataError("missing_benchmark_calendar")
        benchmark_calendar = _benchmark_calendar(
            getter(benchmark, market, calendar.session_date)
        )
        _fresh(
            benchmark_calendar.timestamp,
            as_of,
            SUPPORTING_DATA_MAX_AGE,
            "stale_benchmark_calendar",
        )

    aum = _metric(provider.get_aum(code), "missing_aum")
    premium = _metric(
        provider.get_premium(code), "missing_premium", allow_negative=True
    )
    catalyst = _catalyst(provider.get_catalyst(code))
    _validate_catalyst_freshness(catalyst, as_of)
    for timestamp, reason in (
        (aum.timestamp, "stale_aum"),
        (premium.timestamp, "stale_premium"),
        *((bar.timestamp, "stale_daily_bars") for bar in bars),
        *((bar.timestamp, "stale_benchmark_bars") for bar in benchmark_bars),
    ):
        _fresh(timestamp, as_of, SUPPORTING_DATA_MAX_AGE, reason)

    timestamps = [
        *(quote.timestamp for quote in validated_quote.quotes),
        *(bar.timestamp for bar in bars),
        *(bar.timestamp for bar in benchmark_bars),
        aum.timestamp,
        premium.timestamp,
        calendar.timestamp,
        benchmark_calendar.timestamp,
        *_catalyst_timestamps(catalyst),
    ]
    sources = (
        {quote.source for quote in validated_quote.quotes}
        | {bar.source for bar in bars}
        | {bar.source for bar in benchmark_bars}
        | {
        aum.source,
        premium.source,
        calendar.source,
        benchmark_calendar.source,
        catalyst.primary_evidence.source,
        catalyst.corroboration_evidence.source,
        }
    )
    return validate_market_snapshot(
        MarketSnapshot(
            code=code,
            market=market,
            benchmark=benchmark,
            current_price=validated_quote.current_price,
            previous_close=validated_quote.previous_close,
            quotes=validated_quote.quotes,
            bars=bars,
            benchmark_bars=benchmark_bars,
            aum_cny=aum.value,
            premium_pct=premium.value,
            aum_metric=aum,
            premium_metric=premium,
            catalyst=catalyst,
            session_date=calendar.session_date,
            trading_calendar=calendar,
            benchmark_calendar=benchmark_calendar,
            observed_at=as_of,
            source_timestamp=min(timestamps),
            sources=tuple(sorted(sources)),
        )
    )


def collect_trading_session(
    provider: MarketDataProvider, as_of: datetime
) -> TradingCalendarState:
    """Return authoritative Shanghai session state after fail-closed validation."""
    observed_at = _shanghai_timestamp(as_of, "invalid_as_of_timestamp")
    requested_session_date = observed_at.date()
    calendar = _calendar(provider.get_trading_calendar(requested_session_date))
    _fresh(
        calendar.timestamp,
        observed_at,
        SUPPORTING_DATA_MAX_AGE,
        "stale_calendar",
    )
    if calendar.session_date != requested_session_date:
        raise MarketDataError("session_date_conflict", calendar.timestamp)
    return calendar


def collect_current_quote(
    code: str,
    provider: MarketDataProvider,
    *,
    as_of: datetime,
) -> ValidatedQuote:
    """Validate fresh Eastmoney/Tencent agreement without needing catalysts."""
    as_of = _shanghai_timestamp(as_of, "invalid_as_of_timestamp")
    return _validate_quotes(code, provider.get_current_quotes(code), as_of)


def _validate_quotes(
    code: str, raw_quotes: Any, as_of: datetime
) -> ValidatedQuote:
    """Normalize and cross-check the two independent quote sources."""
    if raw_quotes is None:
        raise MarketDataError("missing_current_quotes")
    try:
        iterator = iter(raw_quotes)
    except TypeError as exc:
        raise MarketDataError("malformed_quote") from exc
    quotes = [_quote(item) for item in iterator]
    if not quotes:
        raise MarketDataError("missing_current_quotes")
    by_source = {quote.source.lower(): quote for quote in quotes}
    if "eastmoney" not in by_source or "tencent" not in by_source:
        raise MarketDataError("missing_independent_quote")
    eastmoney = by_source["eastmoney"]
    tencent = by_source["tencent"]
    for quote in (eastmoney, tencent):
        _fresh(quote.timestamp, as_of, QUOTE_MAX_AGE, "stale_quote")
    midpoint = _quote_average(eastmoney.price, tencent.price)
    if abs(eastmoney.price - tencent.price) / midpoint > MAX_QUOTE_PRICE_DISAGREEMENT:
        raise MarketDataError(
            "quote_price_conflict", min(eastmoney.timestamp, tencent.timestamp)
        )
    previous_close_midpoint = _quote_average(
        eastmoney.previous_close, tencent.previous_close
    )
    if (
        abs(eastmoney.previous_close - tencent.previous_close)
        / previous_close_midpoint
        > MAX_PREVIOUS_CLOSE_DISAGREEMENT
    ):
        raise MarketDataError(
            "quote_previous_close_conflict",
            min(eastmoney.timestamp, tencent.timestamp),
        )
    turnover_midpoint = _quote_average(
        eastmoney.turnover_cny, tencent.turnover_cny
    )
    if (
        _relative_difference(eastmoney.turnover_cny, tencent.turnover_cny)
        > MAX_TURNOVER_DISAGREEMENT
    ):
        raise MarketDataError(
            "quote_turnover_conflict", min(eastmoney.timestamp, tencent.timestamp)
        )
    return ValidatedQuote(
        code=code,
        current_price=midpoint,
        previous_close=previous_close_midpoint,
        turnover_cny=turnover_midpoint,
        source_timestamp=min(eastmoney.timestamp, tencent.timestamp),
        sources=tuple(sorted((eastmoney.source, tencent.source))),
        quotes=tuple(sorted((eastmoney, tencent), key=lambda quote: quote.source)),
    )


def validate_market_snapshot(value: Any) -> MarketSnapshot:
    """Normalize and fail closed on directly constructed market snapshots."""
    if not isinstance(value, MarketSnapshot):
        raise MarketDataError("malformed_snapshot")
    code = _nonempty_text(value.code, "malformed_snapshot")
    market = _nonempty_text(value.market, "malformed_snapshot")
    benchmark = _nonempty_text(value.benchmark, "malformed_snapshot")
    current_price = _positive(value.current_price, "malformed_snapshot")
    previous_close = _positive(value.previous_close, "malformed_snapshot")
    aum_cny = _nonnegative(value.aum_cny, "malformed_snapshot")
    premium_pct = _number(value.premium_pct, "malformed_snapshot")
    session_date = value.session_date
    if not isinstance(session_date, date) or isinstance(session_date, datetime):
        raise MarketDataError("malformed_snapshot")
    observed_at = _timestamp(value.observed_at, "malformed_snapshot")
    source_timestamp = _timestamp(value.source_timestamp, "malformed_snapshot")
    if observed_at.astimezone(SHANGHAI_TZ).date() != session_date:
        raise MarketDataError(
            "observation_session_date_conflict", source_timestamp
        )

    validated_quote = _validate_quotes(code, value.quotes, observed_at)
    quotes = validated_quote.quotes
    bars = tuple(_bars(value.bars, "missing_daily_bars"))
    benchmark_bars = tuple(
        _bars(value.benchmark_bars, "missing_benchmark_bars")
    )
    if len(bars) < 2:
        raise MarketDataError("insufficient_bars")
    _ordered_bars(bars)
    _ordered_bars(benchmark_bars)
    aum_metric = _metric(value.aum_metric, "missing_aum")
    premium_metric = _metric(
        value.premium_metric, "missing_premium", allow_negative=True
    )
    catalyst = _catalyst(value.catalyst)
    _validate_catalyst_freshness(catalyst, observed_at)
    trading_calendar = _calendar(value.trading_calendar)
    benchmark_calendar = _benchmark_calendar(value.benchmark_calendar)
    for timestamp, reason in (
        *((bar.timestamp, "stale_daily_bars") for bar in bars),
        *((bar.timestamp, "stale_benchmark_bars") for bar in benchmark_bars),
        (aum_metric.timestamp, "stale_aum"),
        (premium_metric.timestamp, "stale_premium"),
        (trading_calendar.timestamp, "stale_calendar"),
        (benchmark_calendar.timestamp, "stale_benchmark_calendar"),
    ):
        _fresh(timestamp, observed_at, SUPPORTING_DATA_MAX_AGE, reason)

    if not isinstance(value.sources, (list, tuple)) or not value.sources:
        raise MarketDataError("malformed_snapshot")
    sources = tuple(_source_text(source) for source in value.sources)
    if benchmark_calendar.source not in sources:
        raise MarketDataError(
            "benchmark_calendar_source_missing", source_timestamp
        )
    component_sources = (
        tuple(quote.source for quote in quotes)
        + tuple(bar.source for bar in bars)
        + tuple(bar.source for bar in benchmark_bars)
        + (
            aum_metric.source,
            premium_metric.source,
            catalyst.primary_evidence.source,
            catalyst.corroboration_evidence.source,
            trading_calendar.source,
            benchmark_calendar.source,
        )
    )
    if any(source not in sources for source in component_sources):
        raise MarketDataError("snapshot_source_missing", source_timestamp)
    if source_timestamp > benchmark_calendar.timestamp:
        raise MarketDataError(
            "benchmark_calendar_timestamp_conflict", source_timestamp
        )
    component_timestamps = (
        tuple(quote.timestamp for quote in quotes)
        + tuple(bar.timestamp for bar in bars)
        + tuple(bar.timestamp for bar in benchmark_bars)
        + (
            aum_metric.timestamp,
            premium_metric.timestamp,
            *_catalyst_timestamps(catalyst),
            trading_calendar.timestamp,
            benchmark_calendar.timestamp,
        )
    )
    if source_timestamp != min(component_timestamps):
        raise MarketDataError("source_timestamp_conflict", source_timestamp)

    if trading_calendar.is_trading_session is not True:
        raise MarketDataError("not_trading_session", source_timestamp)
    if trading_calendar.session_date != session_date:
        raise MarketDataError("session_date_conflict", source_timestamp)
    if bars[-1].date != session_date:
        raise MarketDataError("session_date_conflict", source_timestamp)
    if benchmark_bars[-1].date > session_date:
        raise MarketDataError("future_benchmark_bar", source_timestamp)
    if benchmark_calendar.latest_completed_session_date > session_date:
        raise MarketDataError("future_benchmark_session", source_timestamp)
    if (
        market.upper() == "CN"
        and benchmark_calendar.latest_completed_session_date != session_date
    ):
        raise MarketDataError("benchmark_session_date_conflict", source_timestamp)
    if (
        benchmark_bars[-1].date
        != benchmark_calendar.latest_completed_session_date
    ):
        raise MarketDataError("benchmark_session_date_conflict", source_timestamp)
    if not math.isclose(
        current_price,
        validated_quote.current_price,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise MarketDataError("quote_snapshot_price_conflict", source_timestamp)
    if not math.isclose(
        previous_close,
        validated_quote.previous_close,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise MarketDataError(
            "quote_snapshot_previous_close_conflict", source_timestamp
        )
    if not math.isclose(
        aum_cny, aum_metric.value, rel_tol=1e-12, abs_tol=1e-12
    ):
        raise MarketDataError("aum_metric_conflict", source_timestamp)
    if not math.isclose(
        premium_pct,
        premium_metric.value,
        rel_tol=1e-12,
        abs_tol=1e-12,
    ):
        raise MarketDataError("premium_metric_conflict", source_timestamp)
    if (
        _relative_difference(current_price, bars[-1].close)
        > MAX_QUOTE_BAR_DISAGREEMENT
    ):
        raise MarketDataError("quote_bar_price_conflict", source_timestamp)
    if (
        _relative_difference(previous_close, bars[-2].close)
        > MAX_QUOTE_BAR_DISAGREEMENT
    ):
        raise MarketDataError("previous_close_bar_conflict", source_timestamp)

    normalized = MarketSnapshot(
        code=code,
        market=market,
        benchmark=benchmark,
        current_price=current_price,
        previous_close=previous_close,
        quotes=quotes,
        bars=bars,
        benchmark_bars=benchmark_bars,
        aum_cny=aum_cny,
        premium_pct=premium_pct,
        aum_metric=aum_metric,
        premium_metric=premium_metric,
        catalyst=catalyst,
        session_date=session_date,
        trading_calendar=trading_calendar,
        benchmark_calendar=benchmark_calendar,
        observed_at=observed_at,
        source_timestamp=source_timestamp,
        sources=sources,
    )
    common_bar_window(normalized)
    return normalized


def common_bar_window(
    snapshot: MarketSnapshot,
) -> tuple[tuple[DailyBar, ...], tuple[DailyBar, ...]]:
    """Return the latest 21 ETF/benchmark bars sharing completed dates."""
    etf_by_date = {bar.date: bar for bar in snapshot.bars}
    benchmark_by_date = {bar.date: bar for bar in snapshot.benchmark_bars}
    common_dates = sorted(etf_by_date.keys() & benchmark_by_date.keys())
    if len(common_dates) < MIN_COMMON_RETURN_DATES:
        raise MarketDataError(
            "insufficient_common_bar_dates", snapshot.source_timestamp
        )
    window_dates = common_dates[-MIN_COMMON_RETURN_DATES:]
    return (
        tuple(etf_by_date[bar_date] for bar_date in window_dates),
        tuple(benchmark_by_date[bar_date] for bar_date in window_dates),
    )


class PublicMarketDataProvider:
    """Default public endpoint adapter with injectable I/O and non-market inputs."""

    EASTMONEY_QUOTE = "https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f43,f44,f45,f46,f47,f48,f60,f169,f170"
    EASTMONEY_BARS = "https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&ut=7eea3edcaed734bea9cbfc24409ed989&klt=101&fqt=1&end=20500101&lmt=120&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61"
    TENCENT_QUOTE = "https://qt.gtimg.cn/q={symbol}"

    def __init__(
        self,
        *,
        calendar_provider: Any,
        catalyst_provider: Any,
        benchmark_codes: Optional[Mapping[str, str]] = None,
        opener: Callable[..., Any] = urlopen,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self.calendar_provider = calendar_provider
        self.catalyst_provider = catalyst_provider
        self.benchmark_codes = dict(benchmark_codes or {})
        self.opener = opener
        self.clock = clock

    def get_current_quotes(self, code: str) -> Sequence[Quote]:
        fetched_at = self.clock()
        east = parse_eastmoney_quote(
            self._json(self.EASTMONEY_QUOTE.format(secid=_secid(code))), fetched_at
        )
        tencent = parse_tencent_quote(
            self._text(self.TENCENT_QUOTE.format(symbol=_tencent_symbol(code)), "gbk")
        )
        return [east, tencent]

    def get_daily_bars(self, code: str) -> Sequence[DailyBar]:
        fetched_at = self.clock()
        payload = self._json(self.EASTMONEY_BARS.format(secid=_secid(code)))
        return parse_eastmoney_bars(payload, fetched_at)

    def get_aum(self, code: str) -> TimedMetric:
        quote = self._tencent(code)
        if quote.aum_cny is None:
            raise MarketDataError("missing_aum", quote.timestamp)
        return TimedMetric(quote.aum_cny, quote.source, quote.timestamp)

    def get_premium(self, code: str) -> TimedMetric:
        quote = self._tencent(code)
        if quote.premium_pct is None:
            raise MarketDataError("missing_premium", quote.timestamp)
        return TimedMetric(quote.premium_pct, quote.source, quote.timestamp)

    def get_benchmark_bars(self, benchmark: str) -> Sequence[DailyBar]:
        code = self.benchmark_codes.get(benchmark, benchmark)
        return self.get_daily_bars(code)

    def get_trading_calendar(self, session_date: date) -> Any:
        return self.calendar_provider.get_trading_calendar(session_date)

    def get_benchmark_calendar(
        self, benchmark: str, market: str, as_of_date: date
    ) -> Any:
        getter = getattr(self.calendar_provider, "get_benchmark_calendar", None)
        if not callable(getter):
            raise MarketDataError("missing_benchmark_calendar")
        return getter(benchmark, market, as_of_date)

    def get_catalyst(self, code: str) -> Any:
        return self.catalyst_provider.get_catalyst(code)

    def _tencent(self, code: str) -> Quote:
        return parse_tencent_quote(
            self._text(self.TENCENT_QUOTE.format(symbol=_tencent_symbol(code)), "gbk")
        )

    def _json(self, url: str) -> Mapping[str, Any]:
        try:
            return json.loads(self._bytes(url).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MarketDataError("malformed_public_response") from exc

    def _text(self, url: str, encoding: str) -> str:
        try:
            return self._bytes(url).decode(encoding)
        except UnicodeDecodeError as exc:
            raise MarketDataError("malformed_public_response") from exc

    def _bytes(self, url: str) -> bytes:
        try:
            with self.opener(url, timeout=10) as response:
                return response.read()
        except Exception as exc:
            raise MarketDataError("public_endpoint_unavailable") from exc


def _quote(value: Any) -> Quote:
    if isinstance(value, Quote):
        source = value.source
        price = value.price
        previous_close = value.previous_close
        turnover_cny = value.turnover_cny
        timestamp = value.timestamp
        aum_cny = value.aum_cny
        premium_pct = value.premium_pct
    elif isinstance(value, Mapping):
        try:
            source = value["source"]
            price = value["price"]
            previous_close = value["previous_close"]
            turnover_cny = value["turnover_cny"]
            timestamp = value["timestamp"]
            aum_cny = value.get("aum_cny")
            premium_pct = value.get("premium_pct")
        except KeyError as exc:
            raise MarketDataError("malformed_quote") from exc
    else:
        raise MarketDataError("malformed_quote")
    normalized_aum = _optional_number(aum_cny)
    if normalized_aum is not None and normalized_aum < 0:
        raise MarketDataError("malformed_quote")
    return Quote(
        source=_source_text(source),
        price=_positive(price, "malformed_quote"),
        previous_close=_positive(previous_close, "malformed_quote"),
        turnover_cny=_nonnegative(turnover_cny, "malformed_quote"),
        timestamp=_timestamp(timestamp, "missing_quote_timestamp"),
        aum_cny=normalized_aum,
        premium_pct=_optional_number(premium_pct),
    )


def _bars(values: Any, missing_reason: str) -> list[DailyBar]:
    if values is None:
        raise MarketDataError(missing_reason)
    try:
        iterator = iter(values)
    except TypeError as exc:
        raise MarketDataError("malformed_daily_bar") from exc
    parsed = []
    for value in iterator:
        if isinstance(value, DailyBar):
            bar_date = value.date
            open_price = value.open
            close = value.close
            high = value.high
            low = value.low
            volume = value.volume
            turnover_cny = value.turnover_cny
            source = value.source
            timestamp = value.timestamp
        elif isinstance(value, Mapping):
            try:
                bar_date = value["date"]
                open_price = value["open"]
                close = value["close"]
                high = value["high"]
                low = value["low"]
                volume = value["volume"]
                turnover_cny = value["turnover_cny"]
                source = value["source"]
                timestamp = value["timestamp"]
            except KeyError as exc:
                raise MarketDataError("malformed_daily_bar") from exc
        else:
            raise MarketDataError("malformed_daily_bar")
        try:
            if isinstance(bar_date, str):
                bar_date = date.fromisoformat(bar_date)
            if not isinstance(bar_date, date) or isinstance(bar_date, datetime):
                raise ValueError
            bar = DailyBar(
                date=bar_date,
                open=_positive(open_price, "malformed_daily_bar"),
                close=_positive(close, "malformed_daily_bar"),
                high=_positive(high, "malformed_daily_bar"),
                low=_positive(low, "malformed_daily_bar"),
                volume=_nonnegative(volume, "malformed_daily_bar"),
                turnover_cny=_nonnegative(turnover_cny, "malformed_daily_bar"),
                source=_source_text(source),
                timestamp=_timestamp(timestamp, "missing_bar_timestamp"),
            )
            if bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close):
                raise MarketDataError("malformed_daily_bar")
            parsed.append(bar)
        except (KeyError, TypeError, ValueError) as exc:
            if isinstance(exc, MarketDataError):
                raise
            raise MarketDataError("malformed_daily_bar") from exc
    if not parsed:
        raise MarketDataError(missing_reason)
    return parsed


def _ordered_bars(bars: Sequence[DailyBar]) -> None:
    if any(left.date >= right.date for left, right in zip(bars, bars[1:])):
        raise MarketDataError("conflicting_daily_bar_order")


def _metric(
    value: Any, missing_reason: str, *, allow_negative: bool = False
) -> TimedMetric:
    if value is None:
        raise MarketDataError(missing_reason)
    if isinstance(value, TimedMetric):
        metric_value = value.value
        source = value.source
        timestamp = value.timestamp
    elif isinstance(value, Mapping):
        try:
            metric_value = value["value"]
            source = value["source"]
            timestamp = value["timestamp"]
        except KeyError as exc:
            raise MarketDataError("malformed_metric") from exc
    else:
        raise MarketDataError("malformed_metric")
    normalized_value = (
        _number(metric_value, "malformed_metric")
        if allow_negative
        else _nonnegative(metric_value, "malformed_metric")
    )
    return TimedMetric(
        value=normalized_value,
        source=_source_text(source),
        timestamp=_timestamp(timestamp, "missing_metric_timestamp"),
    )


def _calendar(value: Any) -> TradingCalendarState:
    if value is None:
        raise MarketDataError("missing_trading_calendar")
    if isinstance(value, TradingCalendarState):
        session_date = value.session_date
        is_session = value.is_trading_session
        source = value.source
        timestamp = value.timestamp
    elif isinstance(value, Mapping):
        try:
            session_date = value["session_date"]
            is_session = value["is_trading_session"]
            source = value["source"]
            timestamp = value["timestamp"]
        except KeyError as exc:
            raise MarketDataError("malformed_trading_calendar") from exc
    else:
        raise MarketDataError("malformed_trading_calendar")
    try:
        if isinstance(session_date, str):
            session_date = date.fromisoformat(session_date)
        if not isinstance(session_date, date) or isinstance(session_date, datetime):
            raise ValueError
        if not isinstance(is_session, bool):
            raise ValueError
        return TradingCalendarState(
            session_date=session_date,
            is_trading_session=is_session,
            source=_source_text(source),
            timestamp=_timestamp(timestamp, "missing_calendar_timestamp"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, MarketDataError):
            raise
        raise MarketDataError("malformed_trading_calendar") from exc


def _benchmark_calendar(value: Any) -> BenchmarkCalendarState:
    if value is None:
        raise MarketDataError("missing_benchmark_calendar")
    if isinstance(value, BenchmarkCalendarState):
        latest_session_date = value.latest_completed_session_date
        source = value.source
        timestamp = value.timestamp
    elif isinstance(value, Mapping):
        try:
            latest_session_date = value["latest_completed_session_date"]
            source = value["source"]
            timestamp = value["timestamp"]
        except KeyError as exc:
            raise MarketDataError("malformed_benchmark_calendar") from exc
    else:
        raise MarketDataError("malformed_benchmark_calendar")
    try:
        if isinstance(latest_session_date, str):
            latest_session_date = date.fromisoformat(latest_session_date)
        if not isinstance(latest_session_date, date) or isinstance(
            latest_session_date, datetime
        ):
            raise ValueError
        return BenchmarkCalendarState(
            latest_completed_session_date=latest_session_date,
            source=_source_text(source),
            timestamp=_timestamp(timestamp, "missing_benchmark_calendar_timestamp"),
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, MarketDataError):
            raise
        raise MarketDataError("malformed_benchmark_calendar") from exc


def _catalyst(value: Any) -> CatalystSnapshot:
    if value is None:
        raise MarketDataError("missing_catalyst")
    if isinstance(value, CatalystSnapshot):
        fields = [value.primary_confirmed, value.corroborated, value.adverse]
        primary_value = value.primary_evidence
        corroboration_value = value.corroboration_evidence
    elif isinstance(value, Mapping):
        try:
            fields = [
                value[key]
                for key in ("primary_confirmed", "corroborated", "adverse")
            ]
        except KeyError as exc:
            raise MarketDataError("malformed_catalyst") from exc
        if "primary_evidence" not in value or "corroboration_evidence" not in value:
            raise MarketDataError("missing_catalyst_evidence")
        primary_value = value["primary_evidence"]
        corroboration_value = value["corroboration_evidence"]
    else:
        raise MarketDataError("malformed_catalyst")
    try:
        if not all(isinstance(item, bool) for item in fields):
            raise ValueError
        primary_evidence = _catalyst_evidence(primary_value)
        corroboration_evidence = _catalyst_evidence(corroboration_value)
        if (
            primary_evidence.source.casefold()
            == corroboration_evidence.source.casefold()
        ):
            raise MarketDataError("catalyst_sources_not_independent")
        if (
            primary_evidence.reference.casefold()
            == corroboration_evidence.reference.casefold()
        ):
            raise MarketDataError("catalyst_references_not_independent")
        return CatalystSnapshot(
            primary_confirmed=fields[0],
            corroborated=fields[1],
            adverse=fields[2],
            primary_evidence=primary_evidence,
            corroboration_evidence=corroboration_evidence,
        )
    except (KeyError, TypeError, ValueError) as exc:
        if isinstance(exc, MarketDataError):
            raise
        raise MarketDataError("malformed_catalyst") from exc


def _catalyst_evidence(value: Any) -> CatalystEvidence:
    if isinstance(value, CatalystEvidence):
        source = value.source
        reference = value.reference
        event_timestamp = value.event_timestamp
        collected_at = value.collected_at
    elif isinstance(value, Mapping):
        source = value.get("source")
        reference = value.get("reference")
        event_timestamp = value.get("event_timestamp")
        collected_at = value.get("collected_at")
    else:
        raise MarketDataError("malformed_catalyst_evidence")
    return CatalystEvidence(
        source=_source_text(source),
        reference=_nonempty_text(reference, "missing_catalyst_reference"),
        event_timestamp=_timestamp(
            event_timestamp, "missing_catalyst_event_timestamp"
        ),
        collected_at=_timestamp(
            collected_at, "missing_catalyst_collection_timestamp"
        ),
    )


def _catalyst_timestamps(value: CatalystSnapshot) -> tuple[datetime, ...]:
    return (
        value.primary_evidence.event_timestamp,
        value.primary_evidence.collected_at,
        value.corroboration_evidence.event_timestamp,
        value.corroboration_evidence.collected_at,
    )


def _validate_catalyst_freshness(
    value: CatalystSnapshot, as_of: datetime
) -> None:
    for label, evidence in (
        ("primary", value.primary_evidence),
        ("corroboration", value.corroboration_evidence),
    ):
        _fresh(
            evidence.collected_at,
            as_of,
            SUPPORTING_DATA_MAX_AGE,
            f"stale_{label}_catalyst_collection",
        )
        _fresh(
            evidence.event_timestamp,
            as_of,
            SUPPORTING_DATA_MAX_AGE,
            f"stale_{label}_catalyst_event",
        )
        if evidence.event_timestamp > evidence.collected_at:
            raise MarketDataError(
                "catalyst_event_after_collection", evidence.event_timestamp
            )


def _fresh(timestamp: datetime, as_of: datetime, max_age: timedelta, reason: str) -> None:
    timestamp = _timestamp(timestamp, reason)
    as_of = _timestamp(as_of, "invalid_as_of_timestamp")
    if timestamp > as_of + timedelta(minutes=1) or as_of - timestamp > max_age:
        raise MarketDataError(reason, timestamp)


def _timestamp(value: Any, reason: str) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise MarketDataError(reason) from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MarketDataError(reason)
    try:
        if value.utcoffset() is None:
            raise MarketDataError(reason)
    except MarketDataError:
        raise
    except Exception as exc:
        raise MarketDataError(reason) from exc
    return value


def _shanghai_timestamp(value: Any, reason: str) -> datetime:
    return _timestamp(value, reason).astimezone(SHANGHAI_TZ)


def _source_text(source: Any) -> str:
    if not isinstance(source, str) or not source.strip():
        raise MarketDataError("missing_source")
    return source.strip()


def _nonempty_text(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MarketDataError(reason)
    return value.strip()


def _relative_difference(left: float, right: float) -> float:
    if left == right:
        return 0.0
    midpoint = (abs(left) + abs(right)) / 2
    return math.inf if midpoint == 0 else abs(left - right) / midpoint


def _quote_average(left: float, right: float) -> float:
    return _number((left + right) / 2, "malformed_quote_aggregate")


def _positive(value: Any, reason: str) -> float:
    number = _number(value, reason)
    if number <= 0:
        raise MarketDataError(reason)
    return number


def _nonnegative(value: Any, reason: str) -> float:
    number = _number(value, reason)
    if number < 0:
        raise MarketDataError(reason)
    return number


def _number(value: Any, reason: str) -> float:
    if isinstance(value, bool):
        raise MarketDataError(reason)
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise MarketDataError(reason) from exc
    if not math.isfinite(number):
        raise MarketDataError(reason)
    return number


def _optional_number(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    return _number(value, "malformed_optional_number")


def _secid(code: str) -> str:
    if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
        raise MarketDataError("invalid_security_code")
    market = 0 if code.startswith(("1", "3", "399")) else 1
    return f"{market}.{code}"


def _tencent_symbol(code: str) -> str:
    secid = _secid(code)
    return ("sz" if secid.startswith("0.") else "sh") + code
