"""Settings, read from the environment.

The Flask secret key was the literal ``verysecret`` and the Alpha Vantage key was written in ``api.py`` and
``seed.py``. Nothing secret is written in the code now, and secrets are kept out of ``repr`` so they do not
reach logs.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://www.alphavantage.co/query"


class ConfigError(Exception):
    """A setting is missing or invalid. The message names the variable, never its value."""


def _number(environ: Mapping[str, str], name: str, default: float, *, minimum: float = 0.0) -> float:
    raw = environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        raise ConfigError(f"{name} must be a number") from None
    if value < minimum or value != value:  # the second test rejects NaN
        raise ConfigError(f"{name} must be at least {minimum:g}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    # repr=False on every secret: a Settings object ends up in logs and tracebacks
    alphavantage_api_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    public_url: str = "http://localhost:5004"
    database_url: str = "sqlite:///dashboard.db"
    base_url: str = DEFAULT_BASE_URL
    request_timeout: float = 20.0
    # Alpha Vantage's free key allows 25 requests a day, so answers are kept for a while
    market_status_ttl: float = 600.0
    movers_ttl: float = 3600.0  # Alpha Vantage updates the movers once a day, at the end of the trading day
    daily_ttl: float = 3600.0
    notice_ttl: float = (
        60.0  # how long a rate-limit notice is remembered, so that it is not asked again at once
    )

    @property
    def cookie_secure(self) -> bool:
        return self.public_url.startswith("https://")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        environ = os.environ if environ is None else environ

        def get(name: str) -> str:
            return environ.get(name, "").strip()

        missing = [n for n in ("ALPHAVANTAGE_API_KEY", "SECRET_KEY") if not get(n)]
        if missing:
            raise ConfigError("Missing environment variables: " + ", ".join(missing))
        if len(get("SECRET_KEY")) < 16:
            raise ConfigError("SECRET_KEY must be at least 16 characters")
        public_url = (get("PUBLIC_URL") or "http://localhost:5004").rstrip("/")
        if not public_url.startswith(("http://", "https://")):
            raise ConfigError("PUBLIC_URL must start with http:// or https://")
        base_url = get("ALPHAVANTAGE_BASE_URL") or DEFAULT_BASE_URL
        if not base_url.startswith(("http://", "https://")):
            raise ConfigError("ALPHAVANTAGE_BASE_URL must start with http:// or https://")
        return cls(
            alphavantage_api_key=get("ALPHAVANTAGE_API_KEY"),
            secret_key=get("SECRET_KEY"),
            public_url=public_url,
            database_url=get("DATABASE_URL") or "sqlite:///dashboard.db",
            base_url=base_url,
            request_timeout=_number(environ, "REQUEST_TIMEOUT", 20.0, minimum=1),
            market_status_ttl=_number(environ, "MARKET_STATUS_TTL", 600.0),
            movers_ttl=_number(environ, "MOVERS_TTL", 3600.0),
            daily_ttl=_number(environ, "DAILY_TTL", 3600.0),
            notice_ttl=_number(environ, "NOTICE_TTL", 60.0),
        )
