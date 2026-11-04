import datetime
import logging

import httpx
import pytest

from alphavantage_dashboard.alphavantage import (
    MAX_ROWS,
    AlphaVantage,
    AlphaVantageError,
    _one_line,
    normalise_symbol,
)

from .fake_alphavantage import API_KEY, BASE, mover


def test_a_request_has_the_function_the_symbol_and_the_key_as_query_parameters(av, av_fake):
    av.daily("ibm")
    request = av_fake.calls()[0]
    assert str(request.url).startswith(BASE + "?") and request.url.params["function"] == "TIME_SERIES_DAILY"
    assert request.url.params["symbol"] == "IBM" and request.url.params["apikey"] == API_KEY
    assert "outputsize" not in request.url.params  # compact, the only size of the free key


def test_market_status_is_read_into_plain_fields(av):
    us, uk = av.market_status()
    assert (us.region, us.market_type, us.current_status, us.local_open, us.local_close) == (
        "United States", "Equity", "open", "09:30", "16:15")  # fmt: skip
    assert uk.notes == "Holiday" and uk.primary_exchanges == "London Stock Exchange"


def test_movers_are_read_into_three_lists(av):
    m = av.movers()
    assert m.last_updated == "2026-11-03 16:16:00 US/Eastern"
    assert [r.ticker for r in m.top_gainers] == ["AAA", "BBB"] and [r.ticker for r in m.top_losers] == ["CCC"]
    assert m.most_actively_traded[0].change_percentage == "11.11%" and m.top_gainers[0].volume == "12345"


def test_at_most_a_set_number_of_rows_are_read(av, av_fake):
    av_fake.movers["top_gainers"] = [mover(f"T{i}") for i in range(200)]
    assert len(av.movers().top_gainers) == MAX_ROWS


def test_movers_without_any_row_are_an_error_not_an_empty_page(av, av_fake):
    av_fake.movers = {"last_updated": "x", "top_gainers": [], "top_losers": [], "most_actively_traded": []}
    with pytest.raises(AlphaVantageError, match="no movers") as caught:
        av.movers()
    assert caught.value.kind == "upstream"


def test_daily_candles_are_oldest_first_with_numbers(av):
    candles = av.daily("IBM")
    assert [c.day for c in candles] == sorted(c.day for c in candles) and len(candles) == 5
    assert candles[-1].day == datetime.date(2026, 11, 3)
    first = candles[0]
    assert isinstance(first.open, float) and first.low < first.open < first.high and first.volume == 5000.0


def test_a_malformed_day_is_skipped_and_an_all_malformed_series_is_an_error(av, av_fake):
    av_fake.raw = httpx.Response(200, json={"Time Series (Daily)": {
        "2026-11-03": {"1. open": "1", "2. high": "2", "3. low": "0.5", "4. close": "1.5"},
        "not-a-date": {"1. open": "1", "2. high": "2", "3. low": "0.5", "4. close": "1.5"},
        "2026-11-02": {"1. open": "x", "2. high": "2", "3. low": "0.5", "4. close": "1.5"},
        "2026-11-01": {"1. open": "1"},
    }})  # fmt: skip
    candles = av.daily("IBM")
    assert [c.day.isoformat() for c in candles] == ["2026-11-03"] and candles[0].volume == 0.0
    av_fake.raw = httpx.Response(200, json={"Time Series (Daily)": {"2026-11-03": {"1. open": "x"}}})
    with pytest.raises(AlphaVantageError, match="no usable"):
        av.daily("MSFT")


@pytest.mark.parametrize(
    "body", [{"Meta Data": {}}, {"Time Series (Daily)": ["a"]}, {"Time Series (Daily)": {}}]
)
def test_a_body_without_a_daily_series_is_an_error(av, av_fake, body):
    av_fake.raw = httpx.Response(200, json=body)
    with pytest.raises(AlphaVantageError) as caught:
        av.daily("IBM")
    assert caught.value.kind == "upstream"


@pytest.mark.parametrize(
    "bad", ["", "  ", "I B M", "../../etc", "IBM&function=X", "A" * 16, "-IBM", "^GSPC", "ИБМ"]
)
def test_a_symbol_that_could_alter_the_request_is_refused_before_any_request(av, av_fake, bad):
    with pytest.raises(ValueError, match="symbol"):
        av.daily(bad)
    assert av_fake.requests == []


@pytest.mark.parametrize("good", ["IBM", "brk.b", "AZN.L", "BF-B", "600519.SHH", " ibm\n"])
def test_real_symbols_are_accepted(good):
    assert normalise_symbol(good) == good.strip().upper()


# -- the cache
def test_an_answer_is_kept_for_its_time_to_live(av, av_fake, clock, settings):
    av.market_status()
    av.market_status()
    assert len(av_fake.calls("MARKET_STATUS")) == 1
    clock.advance(settings.market_status_ttl - 1)
    av.market_status()
    assert len(av_fake.calls("MARKET_STATUS")) == 1
    clock.advance(2)
    av.market_status()
    assert len(av_fake.calls("MARKET_STATUS")) == 2


def test_each_symbol_has_its_own_entry_and_the_symbol_is_normalised_first(av, av_fake):
    av.daily("IBM")
    av.daily("ibm")
    av.daily("MSFT")
    assert [r.url.params["symbol"] for r in av_fake.calls("TIME_SERIES_DAILY")] == ["IBM", "MSFT"]


def test_the_functions_have_their_own_lifetimes(av, av_fake, clock, settings):
    av.movers()
    av.market_status()
    clock.advance(settings.market_status_ttl + 1)  # only the market status has expired
    av.movers()
    av.market_status()
    assert len(av_fake.calls("TOP_GAINERS_LOSERS")) == 1 and len(av_fake.calls("MARKET_STATUS")) == 2


# -- what Alpha Vantage can say instead of data
@pytest.mark.parametrize("key", ["Note", "Information"])
def test_a_notice_instead_of_data_is_an_unavailable_error_that_does_not_repeat_the_notice(av, av_fake, key):
    av_fake.notice_key = key
    av_fake.notice = f"Thank you for using Alpha Vantage! Our limit is 25 requests per day. apikey={API_KEY}"
    with pytest.raises(AlphaVantageError) as caught:
        av.movers()
    assert (
        caught.value.kind == "unavailable"
        and "25 requests" not in str(caught.value)
        and API_KEY not in str(caught.value)
    )
    assert "premium" in str(caught.value)  # the same words can mean a rate limit or a premium-only function


def test_a_notice_is_remembered_briefly_so_the_api_is_not_asked_again_at_once(av, av_fake, clock, settings):
    av_fake.notice = "rate limit"
    for _ in range(3):
        with pytest.raises(AlphaVantageError):
            av.movers()
    assert len(av_fake.calls()) == 1
    av_fake.notice = None
    clock.advance(settings.notice_ttl + 1)
    assert (
        av.movers().top_gainers
    )  # asked again once the notice has expired, and the data is kept from then on
    assert len(av_fake.calls()) == 2


def test_an_unknown_symbol_is_not_found_and_the_notice_text_is_not_shown(av, av_fake):
    av_fake.unknown_symbols = {"NOPE"}
    with pytest.raises(AlphaVantageError) as caught:
        av.daily("NOPE")
    assert caught.value.kind == "not_found" and "SECRET" not in str(caught.value)
    with pytest.raises(AlphaVantageError):
        av.daily("NOPE")
    assert len(av_fake.calls()) == 1  # remembered


def test_a_wrong_key_is_reported_without_echoing_it(settings, av_fake, clock):
    from dataclasses import replace

    other = AlphaVantage(replace(settings, alphavantage_api_key="another-key-value"), av_fake.client(), clock)
    with pytest.raises(AlphaVantageError) as caught:
        other.market_status()
    assert "another-key-value" not in str(caught.value) and API_KEY not in str(caught.value)


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_http_errors_name_the_status_and_nothing_else(av, av_fake, status):
    av_fake.http_status = status
    with pytest.raises(AlphaVantageError) as caught:
        av.market_status()
    assert (
        caught.value.kind == "upstream"
        and str(status) in str(caught.value)
        and API_KEY not in str(caught.value)
    )


@pytest.mark.parametrize(
    "answer",
    [
        httpx.Response(200, text="<html>nope</html>"),
        httpx.Response(200, json=["a", "list"]),
        httpx.Response(200, json={"markets": "no"}),
    ],
)
def test_unexpected_answers_are_upstream_errors(av, av_fake, answer):
    av_fake.raw = answer
    with pytest.raises(AlphaVantageError) as caught:
        av.market_status()
    assert caught.value.kind == "upstream"


def test_upstream_errors_are_not_remembered(av, av_fake):
    av_fake.http_status = 500
    with pytest.raises(AlphaVantageError):
        av.market_status()
    av_fake.http_status = 200
    assert av.market_status()  # asked again at once, and it worked


def test_a_network_failure_names_only_its_kind_never_the_url_or_the_key(settings, clock):
    def boom(request):
        raise httpx.ConnectError(f"cannot reach {request.url}")

    broken = AlphaVantage(settings, httpx.Client(transport=httpx.MockTransport(boom)), clock)
    with pytest.raises(AlphaVantageError) as caught:
        broken.daily("IBM")
    assert (
        "ConnectError" in str(caught.value)
        and API_KEY not in str(caught.value)
        and "alphavantage" not in str(caught.value)
    )


def test_the_notice_is_logged_but_the_key_never_is(av, av_fake, caplog):
    av_fake.notice = f"Limit reached for apikey={API_KEY}. Premium plans remove it."
    with caplog.at_level(logging.DEBUG), pytest.raises(AlphaVantageError):
        av.movers()
    assert "Limit reached for apikey=***. Premium" in caplog.text and API_KEY not in caplog.text


def test_an_error_text_is_logged_without_the_key_too(av, av_fake, caplog):
    av_fake.unknown_symbols = {"NOPE"}
    with caplog.at_level(logging.DEBUG), pytest.raises(AlphaVantageError):
        av.daily("NOPE")
    assert "Invalid API call for NOPE" in caplog.text and API_KEY not in caplog.text


def test_text_from_the_api_is_one_clean_line():
    nasty = "Closed\n\x1b[31mred\x1b[0m‮​  now " + "x" * 300
    line = _one_line(nasty, 40)
    assert "\n" not in line and "\x1b" not in line and "‮" not in line and "​" not in line and len(line) <= 40
    assert _one_line(None) == "" and _one_line(12.5) == "12.5"


def test_api_text_in_the_market_status_is_cleaned(av, av_fake):
    av_fake.markets[0]["notes"] = "Early\nclose\x1b[2J"
    assert av.market_status()[0].notes == "Early close[2J"


def test_the_http_library_does_not_log_request_urls_which_hold_the_key(av, av_fake, caplog):
    """httpx logs 'HTTP Request: GET <url>' at INFO, and the key is in the URL."""
    with caplog.at_level(logging.DEBUG):
        av.daily("IBM")
    assert "HTTP Request" not in caplog.text and API_KEY not in caplog.text
    assert logging.getLogger("httpx").level >= logging.WARNING
