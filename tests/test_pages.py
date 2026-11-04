import json

import pytest

from .fake_alphavantage import API_KEY


def test_the_home_page_shows_the_movers_and_the_market_status(client):
    page = client.get("/").get_data(as_text=True)
    for text in ("Top gainers", "Top losers", "Most actively traded", "AAA", "CCC", "DDD", "11.11%", "12345"):
        assert text in page
    assert "Updated 2026-11-03 16:16:00 US/Eastern" in page
    assert (
        "United States" in page and "NASDAQ, NYSE, AMEX, BATS" in page and "09:30" in page and "16:15" in page
    )
    assert ">Open<" in page and ">Closed<" in page  # the status is text, not only colour


def test_text_from_the_api_is_escaped(client, av_fake):
    av_fake.markets[0]["notes"] = "<script>alert(1)</script>"
    av_fake.movers["top_gainers"][0]["ticker"] = "<img src=x onerror=alert(1)>"
    page = client.get("/").get_data(as_text=True)
    assert "<script>alert(1)" not in page and "<img src=x" not in page and "&lt;script&gt;" in page


def test_when_the_api_sends_a_notice_the_page_says_so_and_shows_no_numbers_of_its_own(client, av_fake):
    """The first version replaced missing data with made-up gainers and losers (AAPL +5.4 %, ...)."""
    av_fake.notice = "Our standard API rate limit is 25 requests per day."
    page = client.get("/").get_data(as_text=True)
    assert client.get("/").status_code == 200
    assert (
        "The top movers are not available right now" in page
        and "The market status is not available right now" in page
    )
    for invented in ("AAPL", "MSFT", "5.4%", "NFLX", "BAC", "HSBC"):
        assert invented not in page
    assert "<table" not in page and "25 requests" not in page  # the notice text itself is not repeated


def test_one_part_can_fail_while_the_other_is_shown(client, av_fake):
    av_fake.movers = {"last_updated": "x", "top_gainers": [], "top_losers": [], "most_actively_traded": []}
    page = client.get("/").get_data(as_text=True)
    assert "The top movers are not available right now" in page and "United States" in page


def test_a_missing_list_is_said_not_hidden(client, av_fake):
    av_fake.movers["top_losers"] = []
    page = client.get("/").get_data(as_text=True)
    assert "No data for top losers" in page and "AAA" in page


def test_the_api_is_asked_once_however_often_the_page_is_opened(client, av_fake):
    for _ in range(4):
        client.get("/")
    assert len(av_fake.calls("MARKET_STATUS")) == 1 and len(av_fake.calls("TOP_GAINERS_LOSERS")) == 1


def test_the_key_is_never_in_a_page(client, app):
    for path in ("/", "/charts", "/login", "/api/candles?symbol=IBM"):
        assert API_KEY not in client.get(path).get_data(as_text=True), path


# -- the charts page
def test_the_charts_page_has_its_controls_and_one_external_script_file_of_its_own(client):
    page = client.get("/charts").get_data(as_text=True)
    for ident in (
        'id="symbol"',
        'id="bullish"',
        'id="bearish"',
        'id="first"',
        'id="second"',
        'id="candles"',
        'id="compare"',
    ):
        assert ident in page
    assert 'value="IBM"' in page and 'value="MSFT"' in page and '<option value="GOOG">' in page
    assert 'data-candles-url="/api/candles"' in page and 'data-compare-url="/api/compare"' in page
    assert page.count("<script") == 1 and 'src="/static/charts.js"' in page


# -- the JSON API
def test_candles_come_oldest_first_with_numbers(client):
    data = client.get("/api/candles?symbol=ibm").get_json()
    assert data["symbol"] == "IBM"
    days = [c["t"] for c in data["candles"]]
    assert days == sorted(days) and len(days) == 5 and days[-1] == "2026-11-03"
    first = data["candles"][0]
    assert (
        set(first) == {"t", "o", "h", "l", "c", "v"}
        and first["l"] < first["o"] < first["h"]
        and first["v"] == 5000.0
    )


def test_the_default_symbol_is_ibm(client, av_fake):
    assert client.get("/api/candles").get_json()["symbol"] == "IBM"
    assert av_fake.calls("TIME_SERIES_DAILY")[0].url.params["symbol"] == "IBM"


@pytest.mark.parametrize("bad", ["", "I B M", "../etc", "IBM&function=OVERVIEW", "A" * 16, "%00"])
def test_a_bad_symbol_is_a_400_json_and_no_request_is_made(client, av_fake, bad):
    response = client.get("/api/candles", query_string={"symbol": bad})
    assert response.status_code == 400 and "symbol" in response.get_json()["error"]
    assert av_fake.requests == []


def test_an_unknown_symbol_is_a_404_without_the_api_text(client, av_fake):
    av_fake.unknown_symbols = {"NOPE"}
    response = client.get("/api/candles?symbol=NOPE")
    assert response.status_code == 404 and "SECRET" not in response.get_data(as_text=True)


def test_a_notice_is_a_503(client, av_fake):
    av_fake.notice = "limit"
    response = client.get("/api/candles?symbol=IBM")
    assert response.status_code == 503 and "premium" in response.get_json()["error"]


@pytest.mark.parametrize("status", [401, 500])
def test_an_upstream_failure_is_a_502_that_leaks_nothing(client, av_fake, status):
    av_fake.http_status = status
    response = client.get("/api/candles?symbol=IBM")
    assert response.status_code == 502 and API_KEY not in response.get_data(as_text=True)
    assert "alphavantage" not in response.get_data(as_text=True)


def test_a_comparison_has_both_series(client):
    data = client.get("/api/compare?a=ibm&b=msft").get_json()
    assert (data["a"]["symbol"], data["b"]["symbol"]) == ("IBM", "MSFT")
    assert all(set(point) == {"t", "c"} for point in data["a"]["closes"] + data["b"]["closes"])
    assert [p["t"] for p in data["a"]["closes"]] == sorted(p["t"] for p in data["a"]["closes"])


def test_the_comparison_defaults_and_shares_the_cache_with_the_chart(client, av_fake):
    data = client.get("/api/compare").get_json()
    assert (data["a"]["symbol"], data["b"]["symbol"]) == ("IBM", "MSFT")
    client.get("/api/candles?symbol=IBM")
    assert len(av_fake.calls("TIME_SERIES_DAILY")) == 2  # IBM and MSFT, once each


def test_a_comparison_with_one_bad_symbol_fails_as_a_whole(client, av_fake):
    assert client.get("/api/compare?a=IBM&b=../x").status_code == 400
    av_fake.unknown_symbols = {"NOPE"}
    assert client.get("/api/compare?a=IBM&b=NOPE").status_code == 404


def test_api_errors_are_json_and_page_errors_are_html(client):
    assert client.get("/api/candles?symbol=!!").content_type.startswith("application/json")
    page = client.get("/no-such-page")
    assert (
        page.status_code == 404
        and page.content_type.startswith("text/html")
        and b"Page not found" in page.data
    )


def test_the_json_is_valid_for_every_endpoint(client):
    for path in ("/api/candles?symbol=IBM", "/api/compare?a=IBM&b=MSFT", "/healthz"):
        json.loads(client.get(path).get_data(as_text=True))
