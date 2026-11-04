"""An in-process Alpha Vantage: answers the three functions the dashboard uses and records what it got."""

from __future__ import annotations

import datetime
import hashlib

import httpx

BASE = "https://alphavantage.example.test/query"
API_KEY = "demo-av-key"


def candles(symbol: str, days: int = 5) -> dict:
    """Deterministic daily prices, newest first like the real API (the numbers are made up for the tests)."""
    seed = int(hashlib.sha256(symbol.encode()).hexdigest(), 16) % 50 + 100
    end = datetime.date(2026, 11, 3)
    out = {}
    for i in range(days):
        day = end - datetime.timedelta(days=i)
        base = seed + (days - i)
        out[day.isoformat()] = {
            "1. open": f"{base:.4f}", "2. high": f"{base + 2:.4f}", "3. low": f"{base - 1:.4f}",
            "4. close": f"{base + 1:.4f}", "5. volume": str(1000 * (i + 1)),
        }  # fmt: skip
    return out


def mover(ticker: str, price: str = "10.00") -> dict:
    return {
        "ticker": ticker,
        "price": price,
        "change_amount": "1.00",
        "change_percentage": "11.11%",
        "volume": "12345",
    }


class FakeAlphaVantage:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self.unknown_symbols: set[str] = set()
        self.notice: str | None = None  # a "Note"/"Information" text sent instead of data
        self.notice_key = "Information"
        self.http_status = 200
        self.raw: httpx.Response | None = None  # answer with this instead of anything else
        self.markets = [
            {
                "market_type": "Equity",
                "region": "United States",
                "primary_exchanges": "NASDAQ, NYSE, AMEX, BATS",
                "local_open": "09:30",
                "local_close": "16:15",
                "current_status": "open",
                "notes": "",
            },
            {
                "market_type": "Equity",
                "region": "United Kingdom",
                "primary_exchanges": "London Stock Exchange",
                "local_open": "08:00",
                "local_close": "16:30",
                "current_status": "closed",
                "notes": "Holiday",
            },
        ]
        self.movers = {
            "metadata": "Top gainers, losers, and most actively traded US tickers",
            "last_updated": "2026-11-03 16:16:00 US/Eastern",
            "top_gainers": [mover("AAA"), mover("BBB")],
            "top_losers": [mover("CCC")],
            "most_actively_traded": [mover("DDD")],
        }

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))

    def calls(self, function: str | None = None) -> list[httpx.Request]:
        return [r for r in self.requests if function is None or r.url.params.get("function") == function]

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.raw is not None:
            return self.raw
        if self.http_status != 200:
            return httpx.Response(self.http_status, text=f"error for {request.url}")
        params = request.url.params
        if params.get("apikey") != API_KEY:
            return httpx.Response(
                200, json={"Error Message": f"the parameter apikey is invalid: {params.get('apikey')}"}
            )
        if self.notice is not None:
            return httpx.Response(200, json={self.notice_key: self.notice})
        function = params.get("function")
        if function == "MARKET_STATUS":
            return httpx.Response(
                200, json={"endpoint": "Global Market Open & Close Status", "markets": self.markets}
            )
        if function == "TOP_GAINERS_LOSERS":
            return httpx.Response(200, json=self.movers)
        if function == "TIME_SERIES_DAILY":
            symbol = params.get("symbol", "")
            if symbol in self.unknown_symbols:
                return httpx.Response(
                    200, json={"Error Message": f"Invalid API call for {symbol}. SECRET detail"}
                )
            return httpx.Response(
                200, json={"Meta Data": {"2. Symbol": symbol}, "Time Series (Daily)": candles(symbol)}
            )
        return httpx.Response(200, json={"Error Message": "unknown function"})
