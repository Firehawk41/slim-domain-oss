"""A PyInstaller --onefile exe launched via VBA's Shell.Exec inherits the
CALLER's (Excel's) cwd, not its own -- so a .env placed next to the deployed
exe on a network share would never be found by a plain cwd-upward
load_dotenv() search. infrastructure.database checks next to sys.executable
first when sys.frozen is set. Each test reloads the module under a patched
sys.frozen/sys.executable since the check runs at import time.
"""

import importlib
import sys

import infrastructure.database as database_module


def _reload_with(monkeypatch, tmp_path, frozen: bool) -> None:
    if frozen:
        monkeypatch.setattr(sys, "frozen", True, raising=False)
        monkeypatch.setattr(sys, "executable", str(tmp_path / "slim-report-engine.exe"), raising=False)
    else:
        monkeypatch.delattr(sys, "frozen", raising=False)
    importlib.reload(database_module)


def test_frozen_exe_loads_env_from_exe_directory(monkeypatch, tmp_path) -> None:
    (tmp_path / ".env").write_text("DB_URL=postgresql://examplelab@LAB-SERVER/report_engine\n")
    monkeypatch.delenv("DB_URL", raising=False)

    _reload_with(monkeypatch, tmp_path, frozen=True)

    assert database_module._DEFAULT_DB_URL == "postgresql://examplelab@LAB-SERVER/report_engine"


def test_frozen_exe_falls_through_when_no_env_next_to_exe(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DB_URL", raising=False)

    _reload_with(monkeypatch, tmp_path, frozen=True)  # no .env written in tmp_path

    assert database_module._DEFAULT_DB_URL == "sqlite:///slim_domain.db"


def test_non_frozen_is_unaffected(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("DB_URL", raising=False)

    _reload_with(monkeypatch, tmp_path, frozen=False)

    assert database_module._DEFAULT_DB_URL == "sqlite:///slim_domain.db"


def test_postgres_engine_gets_a_connect_timeout(monkeypatch) -> None:
    captured = {}

    def fake_create_engine(url, connect_args=None, **kwargs):
        captured["connect_args"] = connect_args
        return object()

    monkeypatch.setattr(database_module, "create_engine", fake_create_engine)

    database_module.make_engine("postgresql+psycopg2://user:pw@example.invalid/db")

    assert captured["connect_args"] == {"connect_timeout": 10}


def test_sqlite_engine_gets_no_connect_timeout() -> None:
    engine = database_module.make_engine("sqlite:///:memory:")
    conn = engine.connect()  # would raise TypeError if connect_timeout were passed to sqlite3.connect
    conn.close()


def test_unreachable_postgres_fails_within_timeout() -> None:
    """192.0.2.1 is RFC 5737 TEST-NET-1 -- reserved for documentation/testing,
    never routable, so connections to it are silently dropped (blackholed)
    rather than immediately rejected, which is what actually exercises
    connect_timeout instead of just hitting a fast "no route" error.
    """
    import time

    from sqlalchemy.exc import OperationalError

    engine = database_module.make_engine("postgresql+psycopg2://user:pw@192.0.2.1/db")
    start = time.monotonic()
    try:
        with engine.connect():
            pass
    except OperationalError:
        pass
    elapsed = time.monotonic() - start
    assert elapsed < 15  # the 10s connect_timeout, plus slack -- not an indefinite hang
