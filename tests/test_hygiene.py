"""Things that went wrong in the first version and must not come back."""

import ast
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "alphavantage_dashboard"


def git_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    return [p for p in out.split("\0") if p]


def tracked_text_files():
    suffixes = (".py", ".html", ".md", ".toml", ".yml", ".example", ".css", ".js")
    files = [ROOT / p for p in git_files() if p.endswith(suffixes) and p != "uv.lock"]
    return [f for f in files if f.exists()] or [f for f in ROOT.rglob("*.py") if ".venv" not in f.parts]


def test_no_credentials_in_the_tree():
    """Real-key shapes are looked for everywhere. A long literal next to a name like `key` or `password` is
    looked for outside tests only: the tests use obvious demo values (to prove they are never echoed)."""
    shapes = {
        "an OpenAI key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"),
        "an AWS access key id": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
        "a Google API key": re.compile(r"\bAIza[0-9A-Za-z_-]{30,}"),
        "a key written in a URL": re.compile(r"(?i)apikey=[A-Za-z0-9]{10,}(?![A-Za-z0-9{])"),
    }
    named = re.compile(r"""(?i)(api_?key|secret|token|passw\w*)\w*\s*[=:]\s*['"][A-Za-z0-9_/+-]{16,}['"]""")
    found = []
    for f in tracked_text_files():
        if f.name == "test_hygiene.py":
            continue
        text = f.read_text(errors="ignore")
        relative = f.relative_to(ROOT)
        found += [f"{relative}: {label}" for label, p in shapes.items() if p.search(text)]
        if relative.parts[0] != "tests" and named.search(text):
            found.append(f"{relative}: a long literal assigned to a key/secret/token name")
    assert found == []


def test_no_database_session_file_or_env_file_is_tracked():
    def is_local_state(path: str) -> bool:
        return (
            path.endswith((".db", ".sqlite3", ".DS_Store"))
            or path.split("/")[-1] == ".env"
            or path.startswith(("instance/", "flask_session/"))
        )

    assert [p for p in git_files() if is_local_state(p)] == []


def test_a_server_is_started_only_by_the_cli_and_never_in_debug_mode():
    for f in SRC.rglob("*.py"):
        text = f.read_text()
        assert "debug=True" not in text, f.name
        if f.name != "cli.py":
            assert ".run(" not in text, f.name


def test_no_print_calls_and_no_blocking_requests_library():
    """The first version printed the API key. (Looked for in the code, not in comments that explain it.)"""
    for f in SRC.rglob("*.py"):
        tree = ast.parse(f.read_text())
        calls = [
            n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
        ]
        assert "print" not in calls or f.name == "cli.py", f.name
        imported = {
            a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
        }
        imported |= {
            n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module
        }
        assert "requests" not in imported, f.name
    assert "httpx.Client(timeout=settings.request_timeout)" in (SRC / "alphavantage.py").read_text()


def test_the_api_key_is_used_by_the_client_only():
    users = [f.name for f in SRC.rglob("*.py") if "alphavantage_api_key" in f.read_text()]
    assert sorted(users) == ["alphavantage.py", "config.py"]


def test_the_leftover_template_of_another_project_is_gone():
    """home.html was an e-commerce page (a basket, products, banners) with no route and no images."""
    assert not (SRC / "templates" / "home.html").exists()


def test_env_example_lists_every_variable_the_settings_read():
    source = (SRC / "config.py").read_text()
    read = set(re.findall(r"""(?:get|_number)\(\s*(?:environ,\s*)?["']([A-Z][A-Z0-9_]+)["']""", source))
    read |= set(re.findall(r'"([A-Z][A-Z0-9_]+)"', re.search(r"missing = \[.*?\]", source, re.S).group(0)))
    documented = set(re.findall(r"^#?\s*([A-Z][A-Z0-9_]+)=", (ROOT / ".env.example").read_text(), re.M))
    assert {"ALPHAVANTAGE_API_KEY", "SECRET_KEY", "PUBLIC_URL", "DATABASE_URL", "DAILY_TTL"} <= read
    assert sorted(read - documented) == []
