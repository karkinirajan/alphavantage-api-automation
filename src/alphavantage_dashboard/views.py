"""Routes: the market pages and their JSON API, and the user accounts."""

from __future__ import annotations

import hmac
import re
import secrets
from functools import wraps
from urllib.parse import urlsplit

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import check_password_hash, generate_password_hash

from .alphavantage import AlphaVantageError, normalise_symbol
from .app import Services
from .extensions import db
from .models import User

bp = Blueprint("web", __name__)

USERNAME = re.compile(r"^[A-Za-z0-9_.-]{3,40}$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD, MAX_PASSWORD = 10, 128  # the upper bound keeps the password hash cheap to refuse to compute
NAME_MAX = 100
SUGGESTED_SYMBOLS = ("IBM", "MSFT", "GOOG")  # the three the first version offered
DEFAULT_COMPARISON = ("IBM", "MSFT")
# Checked when the account does not exist, so that "no such account" takes as long as "wrong password"
_DUMMY_HASH = generate_password_hash("not-a-real-password")
# How an Alpha Vantage failure is told to the browser
_STATUS = {"not_found": 404, "unavailable": 503, "upstream": 502}


def services() -> Services:
    return current_app.extensions["dashboard"]


# -- sessions and CSRF
def current_user() -> User | None:
    if "user" not in g:
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id else None
    return g.user


def csrf_token() -> str:
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_urlsafe(32)
    return session["csrf_token"]


def safe_next(target: str | None) -> str | None:
    """Only a path on this site: an absolute or protocol-relative address would be an open redirect."""
    if not target or "\\" in target:
        return None
    parts = urlsplit(target)
    if parts.scheme or parts.netloc or not target.startswith("/") or target.startswith("//"):
        return None
    return target


@bp.app_context_processor
def template_globals():
    return {"csrf_token": csrf_token, "user": current_user()}


@bp.before_app_request
def check_csrf():
    """Every POST (sign-in included) must carry the session's token, as a form field or a header."""
    if request.method == "POST":
        expected = session.get("csrf_token", "")
        got = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
        if not expected or not hmac.compare_digest(expected, got):
            abort(400, "The form has expired. Go back, reload the page and try again.")


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("web.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapper


# -- the market pages
@bp.get("/")
def index():
    """Market status and the top movers. When Alpha Vantage gives nothing, the page says so, with no numbers
    of its own (the first version filled in made-up gainers and losers, as if they were real)."""
    av = services().alphavantage
    markets = movers = market_error = movers_error = None
    try:
        markets = av.market_status()
    except AlphaVantageError as exc:
        market_error = str(exc)
    try:
        movers = av.movers()
    except AlphaVantageError as exc:
        movers_error = str(exc)
    return render_template(
        "index.html", markets=markets, movers=movers, market_error=market_error, movers_error=movers_error
    )


@bp.get("/charts")
def charts():
    return render_template("charts.html", symbols=SUGGESTED_SYMBOLS, comparison=DEFAULT_COMPARISON)


def _symbol_arg(name: str, default: str) -> str:
    try:
        return normalise_symbol(request.args.get(name, default))
    except ValueError as exc:
        abort(400, str(exc))
        raise AssertionError from exc  # unreachable: abort() raises


def _failure(exc: AlphaVantageError):
    return jsonify(error=str(exc)), _STATUS.get(exc.kind, 502)


@bp.errorhandler(400)
def api_bad_request(error):
    """A bad request to the JSON API is JSON; anywhere else it is the error page."""
    if request.path.startswith("/api/"):
        return jsonify(error=error.description), 400
    return render_template("error.html", code=400, title="Bad request", message=error.description), 400


@bp.get("/api/candles")
def api_candles():
    symbol = _symbol_arg("symbol", "IBM")
    try:
        candles = services().alphavantage.daily(symbol)
    except AlphaVantageError as exc:
        return _failure(exc)
    return jsonify(
        symbol=symbol,
        candles=[
            {"t": c.day.isoformat(), "o": c.open, "h": c.high, "l": c.low, "c": c.close, "v": c.volume}
            for c in candles
        ],
    )


@bp.get("/api/compare")
def api_compare():
    first = _symbol_arg("a", DEFAULT_COMPARISON[0])
    second = _symbol_arg("b", DEFAULT_COMPARISON[1])
    series = {}
    try:
        for key, symbol in (("a", first), ("b", second)):
            series[key] = {
                "symbol": symbol,
                "closes": [
                    {"t": c.day.isoformat(), "c": c.close} for c in services().alphavantage.daily(symbol)
                ],
            }
    except AlphaVantageError as exc:
        return _failure(exc)
    return jsonify(series)


@bp.get("/healthz")
def healthz():
    return jsonify(status="ok")


# -- accounts
@bp.route("/login", methods=["GET", "POST"])
def login():
    target = safe_next(request.values.get("next"))
    if request.method == "GET":
        return render_template("login.html", next=target)
    name = request.form.get("login", "").strip().lower()
    password = request.form.get("password", "")[:MAX_PASSWORD]
    user = (
        db.session.scalar(select(User).where(or_(User.username == name, User.email == name)))
        if name
        else None
    )
    correct = check_password_hash(user.password_hash if user else _DUMMY_HASH, password)
    if user is None or not correct:
        flash("Invalid login credentials", "error")
        return render_template("login.html", next=target), 401
    session.clear()  # a new session at sign-in: nothing planted before it survives
    session["user_id"] = user.id
    return redirect(target or url_for("web.profile"))


def _signup_problems(form) -> list[str]:
    problems = []
    if not USERNAME.match(form["username"]):
        problems.append("The username must be 3 to 40 letters, digits, dots, dashes or underscores.")
    if len(form["email"]) > 120 or not EMAIL.match(form["email"]):
        problems.append("Enter a valid email address.")
    for label, key in (("first name", "first_name"), ("last name", "last_name")):
        if not form[key] or len(form[key]) > NAME_MAX:
            problems.append(f"The {label} is required (up to {NAME_MAX} characters).")
    if not MIN_PASSWORD <= len(form["password"]) <= MAX_PASSWORD:
        problems.append(f"The password must be {MIN_PASSWORD} to {MAX_PASSWORD} characters.")
    return problems


@bp.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "GET":
        return render_template("signup.html", form={})
    form = {
        "email": request.form.get("email", "").strip().lower(),
        "username": request.form.get("username", "").strip(),
        "first_name": request.form.get("first_name", "").strip(),
        "last_name": request.form.get("last_name", "").strip(),
        "password": request.form.get("password", ""),
    }
    problems = _signup_problems(form)
    if not problems:
        form["username"] = form["username"].lower()
        taken = db.session.scalar(
            select(func.count())
            .select_from(User)
            .where(or_(User.username == form["username"], User.email == form["email"]))
        )
        if taken:
            problems.append("Username or email already in use.")
    if problems:
        for problem in problems:
            flash(problem, "error")
        form.pop("password")
        return render_template("signup.html", form=form), 400
    user = User(**{k: v for k, v in form.items() if k != "password"})
    user.password_hash = generate_password_hash(form["password"])
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:  # two sign-ups with the same name at the same moment
        db.session.rollback()
        flash("Username or email already in use.", "error")
        form.pop("password")
        return render_template("signup.html", form=form), 400
    flash("Registration successful. Please log in.", "info")
    return redirect(url_for("web.login"))


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("web.index"))


@bp.get("/profile")
@login_required
def profile():
    return render_template("profile.html")
