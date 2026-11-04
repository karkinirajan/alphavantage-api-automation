# Work done on alphavantage-api-automation (branch `chore/modernize`)

Local commit only; nothing was pushed. The first version was a Flask prototype of a stock-trading simulator on the
Alpha Vantage API: market pages that worked in part, user accounts, and a lot of scaffolding that never ran. It is
rebuilt as a small tested dashboard that keeps what worked and says plainly what it dropped.

## Read this first: rotate or decide

They are in the git history (7 commits, 2024-03-07 to 2025-02-09), not in the new code.

| What | Where in history | Do |
|---|---|---|
| **Alpha Vantage API key** (one value) | `app/api.py` and `app/seed.py`, in all 6 code commits | request a new key (they are free) and stop using this one |
| **Flask `SECRET_KEY` = `verysecret`** | `app/config.py`, in all 6 code commits | a guessable value: sessions of any deployment that used it can be forged. Use a new `SECRET_KEY` |
| **Personal data of 4 people**: names, emails and password hashes (5 people in one earlier commit) | `instance/database.db`, committed in 5 commits (`4b3196c` to `2465a62`) | the hashes are Werkzeug password hashes: weak passwords can be recovered offline. Consider telling the users and having them change the password wherever they reused it. The file stays on disk, untracked |
| 3 session files | `flask_session/`, 9 to 252 bytes each, committed in 6 commits | session ids of 2024; they have long expired. Not read |
| `.DS_Store` | all 6 code commits | macOS folder metadata (file names on the author's machine); harmless |

Rewriting the 7-commit history with `git filter-repo` is possible after the key and the secret are replaced; only you
can push it.

## What was there

* 7 commits (2024-03-07 five times, 2024-04-26, 2025-02-09), 43 tracked files, about 1,500 lines. A one-line README
  and a 21-line `requirements.txt` (Flask, Flask-Login, Flask-Session, Flask-SQLAlchemy, Flask-WTF, requests,
  SQLAlchemy, WTForms).
* `app/` with `__init__.py`, `config.py`, `dbs.py` (13 models), `routes.py` (308 lines), `forms.py`, `api.py`,
  `seed.py`, `tickers.py`, 11 templates, a 292-line stylesheet, one small script and nine logo and arrow images;
  `run.py`; an ERD image; two empty-ish `apiData.txt` files (2 and 0 bytes); the committed database (4 users, every
  other table empty) and three session files.

## Findings in the first version

| Where | What was wrong |
|---|---|
| `app/__init__.py` | `app.run(debug=True)` was **executed at import time**: importing the package (as `run.py` did, or any test or WSGI server would) started a Werkzeug debug server, whose console allows code execution to whoever can reach it |
| `app/routes.py` home page | `print(API_KEY)` on every request; `requests.get` **without a timeout**; and `top_gainers_losers_data["top_gainers"]` raised `KeyError` when Alpha Vantage sent its rate-limit notice, so the home page was a 500 error exactly when the 25-a-day allowance ran out |
| `app/routes.py` home page | when the API gave nothing, it **filled in made-up data and showed it as real**: a gainers and losers list (AAPL +5.4 %, MSFT +4.8 %, ...), most-active volumes, and four markets with open and closed status |
| `app/routes.py` accounts | `form.validate_on_submit` and `form.validate` were used **without parentheses** (always true), so no form was ever validated, and no CSRF token was ever checked; `GET /logout`; the register check turned a missing user into the string `"None"`, so nobody could register that name; `/profile` ended in a `.filter` that was never called |
| `app/routes.py` | `User.get(...)` does not exist (the first `user_loader` was overridden by the second); `/chart` rendered a template that does not exist (a 500 error); `/portfolio` and `/settings` were empty or placeholder pages |
| `app/config.py` | `SECRET_KEY='verysecret'`, and sessions kept in files in a tracked `flask_session/` directory |
| `app/api.py`, `app/seed.py` | the Alpha Vantage key written in both. `api.py` needs `alpha_vantage` and matplotlib (not in `requirements.txt`) and plots on import; `seed.py` could not run (it opened a dictionary as a file, indexed a list with a string, and wrote one column per row) |
| `app/tickers.py` | `fetch_data_from_api` built a URL and returned nothing |
| `app/dbs.py` | 13 models; only `user` was ever used. `wallet_funds` was never set |
| templates | Bootstrap 5.0.2, **a Font Awesome kit script** and an **unpinned ApexCharts** (the latest on every page view) from CDNs; inline scripts and styles; `home.html` was a page of a different project (a basket, products, banners) with no route and no images |
| `.gitignore`, repo | the database, three session files and `.DS_Store` were tracked; README of one line |

## What was done, file by file

| First version | Now |
|---|---|
| `app/__init__.py`, `app/config.py`, `run.py` | `src/alphavantage_dashboard/app.py` (factory, headers), `config.py`, `cli.py` (`run`, `init-db`, never in debug mode), `__init__.py` |
| `app/routes.py` | `views.py` (pages, JSON API, accounts, CSRF) and `alphavantage.py` (the client: timeouts, cache, errors, no key in logs) |
| `app/dbs.py` (13 models) | `models.py` (`User` only); the rest are described in `docs/data-model.md` |
| `app/forms.py` (WTForms), Flask-Login, Flask-Session, Flask-WTF | plain form handling with a CSRF token in the session and Flask's signed session cookie |
| `app/api.py`, `app/seed.py`, `app/tickers.py` | removed: none of them could run, and the client covers what they were reaching for (the daily series) |
| `app/templates/*` (11) | `templates/` (7 pages) rewritten without CDNs or inline code; `home.html` removed |
| `app/static/stylesheet.css`, `functions.js` | `static/style.css` (light and dark), `static/charts.js` (four SVG charts) |
| 9 images | the logo the app used is `static/logo.png`; the 8 others were referenced nowhere (checked) and moved to `docs/brand/`; the ERD is `docs/erd.png` |
| `instance/database.db`, `flask_session/*`, `.DS_Store`, 2 x `apiData.txt` | untracked (the database and sessions stay on disk) or removed |
| `requirements.txt` | `pyproject.toml` + `uv.lock` (Python 3.13; 5 direct dependencies) |
| `README.md` | rewritten |
| (new) | `.env.example`, `.gitignore`, `Dockerfile`, `.dockerignore`, `.github/workflows/ci.yml`, `VERSIONS.md`, `docs/` (2 pages), 140 tests |

### Behaviour that differs from the first version

* **No invented data.** When Alpha Vantage gives nothing the page says that the movers or the market status are not
  available. The first version showed made-up numbers.
* Answers are cached (10 minutes for the market status, 1 hour for movers and daily prices) because the free key
  allows 25 requests a day; a notice is remembered for a minute.
* The JSON endpoints are `/api/candles?symbol=` (was `/candlestick`) and `/api/compare?a=&b=` (was
  `/stock-data?symbol_us=&symbol_uk=`); the charts page is `/charts` (was `/chart`, which was a 500 error).
* The comparison chart sets both series to 100 on the first day. The first version plotted the raw closes of the
  two symbols on one axis, which cannot work for prices on different scales (its defaults were a US and a UK stock).
* The scatter chart (which plotted a low and a high per day) is now a high-low bar chart; the candle colours default
  to the theme's blue and orange instead of fixed colours, and rising candles are hollow.
* The `/portfolio` and `/settings` pages, the wallet placeholder, the search box and the gear menu are gone (they
  led nowhere). The light/dark choice follows the operating system instead of a `localStorage` setting.
* Accounts: first and last name instead of `fname`/`lname`; passwords of 10 to 128 characters; usernames and emails
  stored in lower case and compared without regard to case; log-out is a POST with a CSRF token; a failed log-in is a
  401; signing in goes to the profile. **The database file of the first version is not compatible and was not
  migrated.**
* Alpha Vantage's market data pages are public, as before; only the profile needs a login.

## Verified (commands actually run)

| Check | Result |
|---|---|
| `pytest -q -W error --cov` | 140 passed (warnings are errors); 98 % line and branch coverage |
| mutation check | 34 defects reintroduced one at a time (no CSRF check, an open redirect, a password stored in clear, a symbol that is not validated, a cache that never expires or is never used, a notice not recognised, notices or upstream failures remembered wrongly, the key not redacted from logged text, `httpx` allowed to log URLs, the exception text in an error, candles not sorted, API text not escaped or cleaned, a CDN script added, debug server, ...): the suite failed for all 34; files restored afterwards |
| `ruff check`, `ruff format --check` | pass (rules `E F I B UP SIM S BLE RUF`). The generic "long literal next to a key or password name" pattern of the hygiene test is applied outside `tests/` only, because the tests use obvious demo values; real-key shapes (`sk-`, `AKIA`, `AIza`, `apikey=...`) are checked in every file |
| the app under `gunicorn` against a local fake Alpha Vantage over HTTP | home page, caching (two page views: one call per function), 100-day candles oldest first, the 400/404/503 statuses of the API, sign-up, log-in, profile, 405 for GET log-out and 400 without a token, security headers; **no plaintext password and no API key in the database**, and none in a gunicorn log of 171 lines at debug level (the check fails if the log is empty) |
| real browser (Chromium via Playwright): light and dark, 375/768/1280 px | all pages and the four charts looked at. Counted: 100 candles, 100 line points, 100 high-low bars and 2 comparison lines; error states (unknown symbol, notice, bad comparison) and recovery; the colour picker redraws without a new request; keyboard order; text contrast at least 4.5:1, chart marks and field outlines at least 3:1. Found and fixed: the comparison legend covered a line, chart text was about 5 px tall on a phone (charts were drawn at a fixed width and scaled down; they are now drawn at their box's width and redrawn on resize), and control labels wrapped away from their inputs |
| `docker build --no-cache`, then run | image 235 MB, user `app`, `/healthz` ok, tables in `/data`, home page, API and `charts.js` served, no `.env` inside, a log of 12 lines with no key |
| secret scan of the tree being committed | no credential; history scan produced the list above |

### A leak found while testing

`httpx`, the HTTP library, logs `HTTP Request: GET <url>` at INFO level, and Alpha Vantage takes the key in the URL.
A test showed the key in the log as soon as INFO logging was on. The client now sets the `httpx` and `httpcore`
loggers to WARNING by itself (on the logger's own level, because the effective level follows the root logger and
can change later), and the same test guards it.

## Not verified

* **No live Alpha Vantage call was made**: no key of its own, only demo values and fakes. The JSON key names of the
  three responses are taken from the first version's code and templates: the documentation text that was read does
  not show a sample response. The exact shape of an error or rate-limit answer is also not in what was read, so the
  client handles `Error Message`, `Note` and `Information` defensively. About the first 218,000 of the documentation
  page's 819,000 characters were read.
* What the `demo` key returns, and the format of London symbols (the first version's default `AZN.L`), are unknown.
  The comparison now defaults to IBM and MSFT.
* GitHub Actions has not run (the same commands were run locally).

## Questions for the owner

1. The data model describes a **stock-trading simulator** (wallet, orders, portfolio). Is it still wanted? It was
   not built and its tables are gone; `docs/erd.png` is where to start.
2. Should the market pages require a login? They did not before.
3. Which symbols should the charts page suggest? The first version offered IBM, MSFT and GOOG, and a US-against-UK
   comparison.
4. The four people whose emails and password hashes are in the history: do they need to be told?
5. Is a premium key planned? It would allow the full price history and the realtime movers.
