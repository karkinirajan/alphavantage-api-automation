# Alpha Vantage dashboard

A small Flask dashboard on the [Alpha Vantage](https://www.alphavantage.co/) API. It shows which markets are open,
the top gainers, losers and most actively traded US tickers, and charts of a stock's daily prices: candlesticks,
closing price, daily high and low, and a comparison of two symbols. Visitors can register and sign in.

## Contents

1. [Features](#features)
2. [Quickstart](#quickstart)
3. [Configuration](#configuration)
4. [Pages and API](#pages-and-api)
5. [The Alpha Vantage free key](#the-alpha-vantage-free-key)
6. [Project structure](#project-structure)
7. [Testing](#testing)
8. [Docker](#docker)
9. [Versions](#versions)
10. [License](#license)

More detail: [Alpha Vantage and the request limit](docs/alpha-vantage.md) and [The data model](docs/data-model.md).

## Features

* Market status and top movers on the home page; when Alpha Vantage gives nothing the page **says so** and shows
  no numbers of its own (the first version filled in made-up gainers and losers as if they were real).
* Four charts drawn as SVG by a short script of this project: no chart library, nothing loaded from another site.
  Rising candles are hollow and falling ones filled, so they differ by more than colour; the candle colours are
  adjustable; every chart has a text description and a tooltip per day.
* Answers are cached (market status 10 minutes, movers and daily prices 1 hour), because the free key allows only
  25 requests a day.
* The API key is read from the environment and kept out of logs, error messages, pages and the database.
* Accounts: sign-up, log-in, profile; hashed passwords, CSRF protection, log-out by POST.
* Strict Content-Security-Policy, HttpOnly / SameSite session cookies. The server never runs in debug mode.

## Quickstart

You need [uv](https://docs.astral.sh/uv/) and an Alpha Vantage API key (free).

```bash
uv sync
cp .env.example .env                  # then fill it in (git-ignored, read from the current directory)
python -c "import secrets; print(secrets.token_urlsafe(32))"   # -> SECRET_KEY
uv run alphavantage-dashboard init-db # creates the tables (the app also creates them on start)
uv run alphavantage-dashboard run     # development server on http://127.0.0.1:5004
```

`.env.example` sets `ALPHAVANTAGE_API_KEY=demo`, the key used in Alpha Vantage's own documentation examples. What
the `demo` key can access is not stated in the documentation pages that were read; use your own key for real data.

## Configuration

Environment variables (`.env.example` lists them; a test keeps that file complete):

| Variable | Default | Meaning |
|---|---|---|
| `ALPHAVANTAGE_API_KEY` | required | your Alpha Vantage key |
| `SECRET_KEY` | required | signs the session cookie, 16+ characters; it must stay the same between restarts |
| `PUBLIC_URL` | `http://localhost:5004` | where users reach the app; `https://` makes the cookie `Secure` |
| `DATABASE_URL` | `sqlite:///dashboard.db` | SQLAlchemy URL |
| `REQUEST_TIMEOUT` | `20` | seconds to wait for Alpha Vantage |
| `MARKET_STATUS_TTL`, `MOVERS_TTL`, `DAILY_TTL` | `600`, `3600`, `3600` | seconds an answer is kept before Alpha Vantage is asked again |
| `NOTICE_TTL` | `60` | seconds a rate-limit notice or an unknown-symbol answer is remembered |
| `ALPHAVANTAGE_BASE_URL` | the Alpha Vantage URL | for tests and local fakes |

## Pages and API

| Path | What |
|---|---|
| `/` | market status and top movers |
| `/charts` | the four charts, with a symbol box, two colour pickers and a comparison box |
| `/api/candles?symbol=IBM` | JSON: the daily candles of a symbol, oldest first (the latest 100 days) |
| `/api/compare?a=IBM&b=MSFT` | JSON: the daily closes of two symbols |
| `/signup`, `/login`, `/logout` (POST), `/profile` | accounts |
| `/healthz` | `{"status": "ok"}` |

The JSON API answers `400` for a malformed symbol (letters, digits, dots and dashes, up to 15 characters; checked
before anything is sent to Alpha Vantage), `404` for a symbol Alpha Vantage has no data for, `503` when Alpha Vantage
sent a notice instead of data (a rate limit, or a premium-only function) and `502` when it could not be reached or
answered something unexpected. Error texts never include the key, the request URL or Alpha Vantage's own wording.

## The Alpha Vantage free key

Alpha Vantage's support page says the free key allows **25 API requests per day**. The home page needs two
requests, a chart one, a comparison two: without a cache a handful of page views would use the day's allowance.
Answers are therefore kept in memory (see the TTL settings), and a notice is remembered for a minute so that the
API is not asked again at once. The cache is **per process**: run one worker with threads (the Docker image does).
The `outputsize=full` option of the daily series is premium-only, so the charts show the latest 100 days.

## Project structure

```
src/alphavantage_dashboard/
  config.py         settings from the environment (the key and the secret kept out of repr)
  alphavantage.py   the client: market_status(), movers(), daily(symbol); the cache; errors; no key in logs
  models.py         User
  views.py          pages, JSON API, accounts, CSRF          app.py  application factory, security headers
  cli.py            alphavantage-dashboard run | init-db
  templates/, static/ (style.css, charts.js, logo.png)
tests/              a fake Alpha Vantage, unit and flow tests
docs/               Alpha Vantage notes, data model (erd.png), brand/ (the other logo variants)
```

## Testing

```bash
uv run pytest -q -W error --cov
uv run ruff check . && uv run ruff format --check .
```

140 tests, 98 % line and branch coverage. Tests use an in-process fake Alpha Vantage (`tests/fake_alphavantage.py`),
so they need no key and no network. **No live Alpha Vantage call has been made with this code**: there was no key
of its own, only demo values. The app was also run under gunicorn against a local fake Alpha Vantage over HTTP and
in a real browser (screenshots of every page and chart, keyboard order, contrast, overflow, both themes).

## Docker

```bash
docker build -t alphavantage-dashboard .
docker run -p 8000:8000 --env-file .env -v dashboard-data:/data alphavantage-dashboard   # PUBLIC_URL must match
```

The image runs gunicorn with one worker and four threads as an unprivileged user, creates the tables on start,
keeps the SQLite file in the `/data` volume and contains no `.env`.

## Versions

Python 3.13, Flask 3.1, httpx 0.28. Details in [VERSIONS.md](VERSIONS.md); what changed from the first version in
[work-done.md](work-done.md).

## License

MIT, see [LICENSE](LICENSE).
