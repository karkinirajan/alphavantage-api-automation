"""A small Alpha Vantage client: market status, top movers and daily prices, with a time-limited cache.

Alpha Vantage takes the API key only as the ``apikey`` query parameter, so the key is in every request URL.
Nothing here puts a URL, a response body or an exception message in an error or a log line: exceptions are
reported by their class name, and the answer text of Alpha Vantage is cleaned and cut before it is logged.

The first version printed the key (``print(API_KEY)``), had no timeouts, and, when the API did not answer,
showed made-up market data (AAPL up 5.4 %, ...) as if it were real. Nothing is invented here: when there is no
data, the caller is told so.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date

import httpx

from .config import Settings

logger = logging.getLogger(__name__)

SYMBOL = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,14}")
MAX_NOTICE_CHARS = 200
MAX_FIELD_CHARS = 120
MAX_ROWS = 50


class AlphaVantageError(Exception):
    """Alpha Vantage gave no data. `kind` says why; the message is safe to show."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = (
            kind  # "invalid_symbol", "not_found", "unavailable" (a notice, e.g. a rate limit) or "upstream"
        )


def normalise_symbol(raw: str) -> str:
    """The symbol in upper case, or ValueError. It goes into a URL, so the shape is checked."""
    symbol = (raw or "").strip().upper()
    if not SYMBOL.fullmatch(symbol):
        raise ValueError("A symbol is 1 to 15 letters, digits, dots or dashes.")
    return symbol


def _one_line(value: object, limit: int = MAX_FIELD_CHARS) -> str:
    """Text from the API on one line, with no control or format characters, cut short."""
    text = str(value if value is not None else "")
    kept = "".join(
        " " if c.isspace() else c for c in text if c.isspace() or not unicodedata.category(c).startswith("C")
    )
    return re.sub(r" {2,}", " ", kept).strip()[:limit]


@dataclass(frozen=True, slots=True)
class Market:
    region: str
    market_type: str
    primary_exchanges: str
    local_open: str
    local_close: str
    current_status: str
    notes: str


@dataclass(frozen=True, slots=True)
class Mover:
    ticker: str
    price: str
    change_amount: str
    change_percentage: str
    volume: str


@dataclass(frozen=True, slots=True)
class Movers:
    last_updated: str
    top_gainers: tuple[Mover, ...]
    top_losers: tuple[Mover, ...]
    most_actively_traded: tuple[Mover, ...]


@dataclass(frozen=True, slots=True)
class Candle:
    day: date
    open: float
    high: float
    low: float
    close: float
    volume: float


def keep_request_urls_out_of_logs() -> None:
    """httpx logs every request URL at INFO level, and Alpha Vantage takes the key in the URL: at INFO the key
    would be written to the log of any application that enables that level."""
    for name in ("httpx", "httpcore"):
        logger_ = logging.getLogger(name)
        # the logger's own level, not the effective one: that follows the root logger, which can change later
        if logger_.level < logging.WARNING:
            logger_.setLevel(logging.WARNING)


class AlphaVantage:
    def __init__(
        self,
        settings: Settings,
        client: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._s = settings
        keep_request_urls_out_of_logs()
        self._client = client or httpx.Client(timeout=settings.request_timeout)
        self._clock = clock
        self._cache: dict[
            tuple, tuple[float, object]
        ] = {}  # key -> (expires at, a dict or an AlphaVantageError)
        self._lock = threading.Lock()

    # -- the request, cached
    def _call(self, function: str, ttl: float, **params: str) -> dict:
        key = (function, tuple(sorted(params.items())))
        now = self._clock()
        with self._lock:
            hit = self._cache.get(key)
            if hit and hit[0] > now:
                if isinstance(hit[1], AlphaVantageError):
                    raise hit[1]
                return hit[1]  # type: ignore[return-value]
        try:
            body = self._fetch(function, params)
        except AlphaVantageError as exc:
            if exc.kind in ("unavailable", "not_found"):  # remembered briefly: asking again would not help
                with self._lock:
                    self._cache[key] = (now + self._s.notice_ttl, exc)
            raise
        with self._lock:
            self._cache[key] = (now + ttl, body)
        return body

    def _loggable(self, text: object) -> str:
        """Text of Alpha Vantage's answer as it may be logged: one line, cut short, without the API key."""
        return _one_line(text, MAX_NOTICE_CHARS).replace(self._s.alphavantage_api_key, "***")

    def _fetch(self, function: str, params: dict[str, str]) -> dict:
        try:
            response = self._client.get(
                self._s.base_url,
                params={"function": function, **params, "apikey": self._s.alphavantage_api_key},
            )
        except httpx.HTTPError as exc:
            raise AlphaVantageError(
                "upstream", f"Alpha Vantage could not be reached ({type(exc).__name__})."
            ) from None
        if response.status_code != 200:
            raise AlphaVantageError("upstream", f"Alpha Vantage answered HTTP {response.status_code}.")
        try:
            body = response.json()
        except ValueError:
            raise AlphaVantageError(
                "upstream", "Alpha Vantage answered something that is not JSON."
            ) from None
        if not isinstance(body, dict):
            raise AlphaVantageError("upstream", "Alpha Vantage answered something unexpected.")
        if "Error Message" in body:
            logger.info(
                "Alpha Vantage reported an error for %s: %s",
                function,
                self._loggable(body["Error Message"]),
            )
            raise AlphaVantageError("not_found", "Alpha Vantage has no data for that request.")
        for notice_key in ("Note", "Information"):
            if notice_key in body:
                logger.warning(
                    "Alpha Vantage sent a notice for %s: %s",
                    function,
                    self._loggable(body[notice_key]),
                )
                raise AlphaVantageError(
                    "unavailable",
                    "Alpha Vantage sent a notice instead of data: the daily request limit may be used up, "
                    "or the function needs a premium key. Try again later.",
                )
        return body

    # -- the three things the dashboard shows
    def market_status(self) -> list[Market]:
        body = self._call("MARKET_STATUS", self._s.market_status_ttl)
        rows = body.get("markets")
        if not isinstance(rows, list):
            raise AlphaVantageError("upstream", "Alpha Vantage answered no market list.")
        return [
            Market(
                region=_one_line(r.get("region")),
                market_type=_one_line(r.get("market_type")),
                primary_exchanges=_one_line(r.get("primary_exchanges")),
                local_open=_one_line(r.get("local_open")),
                local_close=_one_line(r.get("local_close")),
                current_status=_one_line(r.get("current_status")),
                notes=_one_line(r.get("notes")),
            )
            for r in rows
            if isinstance(r, dict)
        ]

    def movers(self) -> Movers:
        body = self._call("TOP_GAINERS_LOSERS", self._s.movers_ttl)

        def rows(name: str) -> tuple[Mover, ...]:
            raw = body.get(name)
            if not isinstance(raw, list):
                return ()
            return tuple(
                Mover(
                    ticker=_one_line(r.get("ticker"), 20),
                    price=_one_line(r.get("price"), 30),
                    change_amount=_one_line(r.get("change_amount"), 30),
                    change_percentage=_one_line(r.get("change_percentage"), 30),
                    volume=_one_line(r.get("volume"), 30),
                )
                for r in raw[:MAX_ROWS]
                if isinstance(r, dict)
            )

        result = Movers(
            last_updated=_one_line(body.get("last_updated"), 60),
            top_gainers=rows("top_gainers"),
            top_losers=rows("top_losers"),
            most_actively_traded=rows("most_actively_traded"),
        )
        if not (result.top_gainers or result.top_losers or result.most_actively_traded):
            raise AlphaVantageError("upstream", "Alpha Vantage answered no movers.")
        return result

    def daily(self, symbol: str) -> list[Candle]:
        """The daily candles of `symbol` (the latest 100: the free key's 'compact' size), oldest first."""
        symbol = normalise_symbol(symbol)
        body = self._call("TIME_SERIES_DAILY", self._s.daily_ttl, symbol=symbol)
        series = body.get("Time Series (Daily)")
        if not isinstance(series, dict):
            raise AlphaVantageError("upstream", "Alpha Vantage answered no daily series.")
        candles = []
        for day, values in series.items():
            try:
                candles.append(
                    Candle(
                        day=date.fromisoformat(str(day)),
                        open=float(values["1. open"]),
                        high=float(values["2. high"]),
                        low=float(values["3. low"]),
                        close=float(values["4. close"]),
                        volume=float(values.get("5. volume", 0)),
                    )
                )
            except (KeyError, TypeError, ValueError):
                continue  # one malformed day does not spoil the others
        if not candles:
            raise AlphaVantageError("upstream", "Alpha Vantage answered no usable daily prices.")
        return sorted(candles, key=lambda c: c.day)
