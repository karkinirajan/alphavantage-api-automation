"""Shared fixtures: demo settings (no real credential), a fake Alpha Vantage and a controllable clock."""

import pytest

from alphavantage_dashboard.alphavantage import AlphaVantage
from alphavantage_dashboard.config import Settings

from .fake_alphavantage import API_KEY, BASE, FakeAlphaVantage

SETTINGS_ENV = {
    "ALPHAVANTAGE_API_KEY": API_KEY,
    "SECRET_KEY": "demo-flask-secret-key-0123456789",
    "PUBLIC_URL": "https://dashboard.example.test",
    "ALPHAVANTAGE_BASE_URL": BASE,
}
OPTIONAL = [
    "DATABASE_URL", "REQUEST_TIMEOUT", "MARKET_STATUS_TTL", "MOVERS_TTL", "DAILY_TTL", "NOTICE_TTL",
]  # fmt: skip


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for name in [*SETTINGS_ENV, *OPTIONAL]:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def env(tmp_path):
    return {**SETTINGS_ENV, "DATABASE_URL": f"sqlite:///{tmp_path / 'test.db'}"}


@pytest.fixture
def settings(env):
    return Settings.from_env(env)


@pytest.fixture
def av_fake():
    return FakeAlphaVantage()


@pytest.fixture
def av(settings, av_fake, clock):
    return AlphaVantage(settings, av_fake.client(), clock)


@pytest.fixture
def app(settings, av):
    from alphavantage_dashboard import create_app
    from alphavantage_dashboard.extensions import db

    app = create_app(settings, alphavantage=av)
    yield app
    with app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def client(app):
    return app.test_client()


def csrf_of(client) -> str:
    """The CSRF token of the client's session (the page that shows a form creates it)."""
    with client.session_transaction() as sess:
        if "csrf_token" not in sess:
            sess["csrf_token"] = "test-csrf-token-" + "x" * 20
        return sess["csrf_token"]


def signup(
    client,
    username="alice",
    email=None,
    first_name="Alice",
    password="correct horse battery",  # noqa: S107
    **extra,
):
    return client.post(
        "/signup",
        data={
            "csrf_token": csrf_of(client), "username": username, "email": email or f"{username}@example.test",
            "first_name": first_name, "last_name": "Tester", "password": password, **extra,
        },
    )  # fmt: skip


def login(client, who="alice", password="correct horse battery", **extra):  # noqa: S107
    return client.post(
        "/login", data={"csrf_token": csrf_of(client), "login": who, "password": password, **extra}
    )


def sign_in(client, username="alice", first_name=None, password="correct horse battery"):  # noqa: S107
    """Create the account and sign in."""
    signup(client, username=username, first_name=first_name or username.title(), password=password)
    return login(client, username, password)
