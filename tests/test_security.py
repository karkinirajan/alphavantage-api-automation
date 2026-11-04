import pathlib

from alphavantage_dashboard import create_app
from alphavantage_dashboard.alphavantage import AlphaVantage
from alphavantage_dashboard.config import Settings

from .conftest import login, signup


def test_security_headers_are_on_every_response(client):
    paths = (
        "/",
        "/charts",
        "/no-such-page",
        "/login",
        "/healthz",
        "/api/candles?symbol=IBM",
        "/static/style.css",
    )
    for path in paths:
        with client.get(path) as response:  # closed: a static file response holds the file open
            h = response.headers
        assert (
            "default-src 'self'" in h["Content-Security-Policy"]
            and "frame-ancestors 'none'" in h["Content-Security-Policy"]
        ), path
        assert h["X-Content-Type-Options"] == "nosniff" and h["X-Frame-Options"] == "DENY", path
        assert h["Referrer-Policy"] == "same-origin", path


def test_pages_are_not_cached_but_static_files_keep_flasks_cache_headers(client):
    assert client.get("/profile", follow_redirects=False).headers["Cache-Control"] == "no-store"
    assert client.get("/").headers["Cache-Control"] == "no-store"
    with client.get("/static/style.css") as response:
        assert response.headers["Cache-Control"] != "no-store"


def test_the_policy_allows_no_inline_script_or_style_and_no_other_site(client):
    policy = client.get("/").headers["Content-Security-Policy"]
    assert "unsafe-inline" not in policy and "unsafe-eval" not in policy and "http" not in policy


def test_templates_use_no_inline_script_or_style_and_load_nothing_from_other_sites(app):
    """The first version loaded Bootstrap, Font Awesome and ApexCharts from CDNs, with inline code."""
    for template in pathlib.Path(app.root_path, "templates").glob("*.html"):
        text = template.read_text()
        assert " style=" not in text and "<style" not in text and " onload=" not in text, template.name
        assert "http://" not in text and "https://" not in text, template.name
        for tag in text.split("<script")[1:]:
            assert "src=" in tag.split(">")[0], template.name  # every script is a file of this site


def test_the_static_files_load_nothing_from_other_sites(app):
    for f in pathlib.Path(app.root_path, "static").glob("*"):
        if f.suffix in (".css", ".js"):
            text = f.read_text().replace(
                "http://www.w3.org/2000/svg", ""
            )  # the SVG namespace is not a request
            assert "http://" not in text and "https://" not in text and "@import" not in text, f.name


def test_the_session_cookie_is_httponly_secure_and_samesite(client):
    cookie = client.get("/login").headers["Set-Cookie"]
    assert "HttpOnly" in cookie and "Secure" in cookie and "SameSite=Lax" in cookie


def test_the_cookie_is_not_secure_when_the_site_is_plain_http_for_local_development(env, av):
    s = Settings.from_env({**env, "PUBLIC_URL": "http://localhost:5004"})
    local = create_app(s, alphavantage=AlphaVantage(s, av._client)).test_client()
    assert "Secure" not in local.get("/login").headers["Set-Cookie"]


def test_debug_mode_is_off_and_there_is_no_console(app, client):
    assert app.debug is False
    assert client.get("/console").status_code == 404


def test_error_pages_use_the_template(client):
    response = client.get("/no-such-page")
    assert response.status_code == 404 and b"<html" in response.data
    assert client.put("/login").status_code == 405


def test_an_oversized_request_is_refused(client):
    assert client.post("/signup", data={"first_name": "x" * 100_000}).status_code == 413


def test_importing_the_package_does_not_start_a_server():
    """The first version called app.run(debug=True) inside app/__init__.py."""
    import alphavantage_dashboard  # noqa: F401  (a hang here would fail the whole suite)


def test_the_secret_key_comes_from_the_settings_so_sessions_survive_a_restart(env, av):
    """It was the literal 'verysecret'."""
    s = Settings.from_env(env)
    first = create_app(s, alphavantage=av)
    second = create_app(s, alphavantage=av)
    assert first.secret_key == second.secret_key == s.secret_key and s.secret_key != "verysecret"


def test_signing_in_works_over_the_hardened_cookie(client):
    signup(client)
    assert login(client).status_code == 302
