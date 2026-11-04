# Alpha Vantage and the request limit

## The three calls

| Page or endpoint | Alpha Vantage function | Kept for |
|---|---|---|
| `/` (market status) | `MARKET_STATUS` | 10 minutes (`MARKET_STATUS_TTL`) |
| `/` (top movers) | `TOP_GAINERS_LOSERS` | 1 hour (`MOVERS_TTL`); Alpha Vantage updates it once a day |
| `/api/candles`, `/api/compare` | `TIME_SERIES_DAILY` (compact: the latest 100 days) | 1 hour per symbol (`DAILY_TTL`) |

The free key allows 25 requests a day, so a chart of a new symbol costs one request and a comparison two (the
chart and the comparison share the entry of a symbol they have in common).

## What can come back instead of data

Alpha Vantage answers HTTP 200 even when it has no data. The client reads three kinds of answer:

| Answer | Treated as | HTTP status of the JSON API | Remembered |
|---|---|---|---|
| a body with `Error Message` | "no data for that request" (an unknown symbol, or a bad call) | 404 | `NOTICE_TTL` (60 s) |
| a body with `Note` or `Information` | a notice instead of data: the daily limit may be used up, or the function needs a premium key | 503 | `NOTICE_TTL` |
| a network error, a non-200 status, something that is not JSON or not the expected shape | an upstream failure | 502 | not remembered |

Remembering a notice for a minute keeps a page that is opened ten times from asking ten times. The notice's own
words are written to the log (one line, cut to 200 characters, with the key replaced by `***`) and are not shown to
users, because the same words can mean a rate limit or a premium-only function and the documentation does not say
how to tell them apart.

## The key is in the URL

Alpha Vantage takes the key only as the `apikey` query parameter. That puts it in every request URL, and the
`httpx` library writes `HTTP Request: GET <url>` to its log at INFO level. A test found this: with INFO logging
the key was written to the log. The client therefore sets the `httpx` and `httpcore` loggers to WARNING itself, so
the key stays out of the log of any application that uses it, and error messages carry the exception's class name
only (never its text, which holds the URL).

## The cache is per process

Each gunicorn worker keeps its own cache, so two workers spend twice the allowance. The Docker image runs one
worker with four threads (`WEB_CONCURRENCY`, `WEB_THREADS`); the cache is guarded by a lock.

## Premium

`outputsize=full` (25+ years of history) and the realtime and delayed `entitlement` options of the movers are
premium features according to Alpha Vantage's documentation. None of them is used.
