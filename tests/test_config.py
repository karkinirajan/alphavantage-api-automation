import pytest

from alphavantage_dashboard.config import ConfigError, Settings

MINIMAL = {"ALPHAVANTAGE_API_KEY": "demo-av-key", "SECRET_KEY": "0123456789abcdef"}


def test_defaults():
    s = Settings.from_env(MINIMAL)
    assert s.public_url == "http://localhost:5004" and not s.cookie_secure
    assert s.database_url == "sqlite:///dashboard.db" and s.base_url == "https://www.alphavantage.co/query"
    assert (s.market_status_ttl, s.movers_ttl, s.daily_ttl, s.notice_ttl) == (600.0, 3600.0, 3600.0, 60.0)


def test_secrets_are_not_in_the_repr():
    text = repr(Settings.from_env(MINIMAL))
    assert "demo-av-key" not in text and "0123456789abcdef" not in text and "public_url" in text


@pytest.mark.parametrize("missing", ["ALPHAVANTAGE_API_KEY", "SECRET_KEY"])
def test_a_missing_required_variable_is_named(missing):
    with pytest.raises(ConfigError, match=missing):
        Settings.from_env({k: v for k, v in MINIMAL.items() if k != missing})


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"SECRET_KEY": "short"}, "at least 16"),
        ({"PUBLIC_URL": "localhost:5004"}, "PUBLIC_URL"),
        ({"ALPHAVANTAGE_BASE_URL": "ftp://x"}, "ALPHAVANTAGE_BASE_URL"),
        ({"REQUEST_TIMEOUT": "0"}, "REQUEST_TIMEOUT"),
        ({"REQUEST_TIMEOUT": "soon"}, "REQUEST_TIMEOUT"),
        ({"DAILY_TTL": "-1"}, "DAILY_TTL"),
        ({"MOVERS_TTL": "nan"}, "MOVERS_TTL"),
    ],
)
def test_invalid_values_are_rejected(change, message):
    with pytest.raises(ConfigError, match=message):
        Settings.from_env({**MINIMAL, **change})


def test_overrides_are_read():
    s = Settings.from_env(
        {**MINIMAL, "PUBLIC_URL": "https://dash.example.test/", "MARKET_STATUS_TTL": "5", "NOTICE_TTL": "0",
         "ALPHAVANTAGE_BASE_URL": "http://127.0.0.1:9/query", "REQUEST_TIMEOUT": "3"}
    )  # fmt: skip
    assert s.public_url == "https://dash.example.test" and s.cookie_secure
    assert (s.market_status_ttl, s.notice_ttl, s.request_timeout) == (5.0, 0.0, 3.0)
    assert s.base_url == "http://127.0.0.1:9/query"
