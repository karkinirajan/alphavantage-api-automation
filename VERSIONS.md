# Versions

Exact versions of every locked package are in `uv.lock`; these are the ones that matter.

| Component | Version | Pinned in |
|---|---|---|
| Python | 3.13 (3.13.18 used for the tests) | `.python-version`, `requires-python = ">=3.13"` |
| Flask | 3.1.3 (`>=3.1`) | `pyproject.toml`, `uv.lock` |
| Flask-SQLAlchemy / SQLAlchemy | 3.1.1 / 2.1.8 | `uv.lock` |
| Werkzeug / Jinja2 | 3.1.9 / 3.1.6 | `uv.lock` (via Flask) |
| httpx | 0.28.1 (`>=0.28`) | `pyproject.toml`, `uv.lock` |
| python-dotenv / gunicorn | 1.2.4 / 26.2.0 | `uv.lock` |
| pytest / pytest-cov / ruff | 9.2.0 / 7.1.0 / 0.17.3 | dev group |
| uv | 0.13.7 locally, 0.13.6 in the Dockerfile | used to build the lock |
| Alpha Vantage API | the `query` endpoint, no version | `ALPHAVANTAGE_BASE_URL` |

27 packages are locked in all.

## Where the Alpha Vantage facts come from

Read from `https://www.alphavantage.co/documentation/` (about the first 218,000 of its 819,000 characters, which
covers the functions used here), `/support/` and `/premium/`. What those pages say:

* `TIME_SERIES_DAILY` takes `symbol`, `apikey`, and optional `outputsize` (default `compact`, "the latest 100 data
  points") and `datatype`. "The "full" outputsize is available to premium keys."
* `MARKET_STATUS` "returns the current market status (open vs. closed) of major trading venues for equities, forex,
  and cryptocurrencies around the world." `TOP_GAINERS_LOSERS` "returns the top 20 gainers, losers, and the most
  active traded tickers in the US market", updated "at the end of each trading day for all users".
* `OVERVIEW` (used by the first version's `seed.py` and `tickers.py`) is tagged as a premium function in a summary
  of the page, not verbatim.
* The free key: "25 API requests per day". No per-minute limit for it is stated.
* The key is passed as the `apikey` query parameter in every example; no header method is mentioned.

What those pages did **not** say, and what this project therefore takes from the first version's code and templates:

* the JSON key names of the three responses (`markets`, `region`, `current_status`, `top_gainers`,
  `change_percentage`, `Time Series (Daily)`, `1. open` ... `5. volume`);
* the shape of an error or a rate-limit answer. The client treats `Error Message` as "no data for that request" and
  `Note` or `Information` as a notice (a rate limit, or a premium-only function: the text is not repeated to users);
* what the `demo` key returns, and the format of London symbols (the first version used `AZN.L`).

## What the first version ran on

Unpinned: Flask, Flask-Login, Flask-Session, Flask-SQLAlchemy, Flask-WTF, requests, SQLAlchemy and WTForms (a
21-line `requirements.txt`). `app/api.py` also imported `alpha_vantage` and matplotlib, which were not listed.
The pages loaded Bootstrap 5.0.2 and an unpinned ApexCharts from jsDelivr and a Font Awesome kit script.
