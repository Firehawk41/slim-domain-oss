import os
import sys
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Session

# A PyInstaller --onefile exe launched via a VBA Shell.Exec call inherits the
# CALLER's (Excel's) current working directory, not its own -- so the normal
# cwd-upward load_dotenv() search below would never find a .env placed next
# to the deployed exe on a network share. sys.executable in a frozen build is
# the real exe path (not a temp extraction dir), so check there explicitly
# first when frozen; load_dotenv() never overrides already-set variables, so
# this can't shadow a real environment variable, and a real dev checkout
# never has sys.frozen set, so this never affects normal `python -m` usage.
if getattr(sys, "frozen", False):
    load_dotenv(Path(sys.executable).parent / ".env")

# Load .env from the RUNNING APP's own working directory (or any parent of
# it) at import time -- usecwd=True is required here. Without it,
# find_dotenv()'s default behavior searches upward from the directory of
# the file that CALLS load_dotenv(), which is always this file
# (slim-domain/infrastructure/database.py) since the call is right here at
# module level -- so it would search slim-domain's own directory tree, not
# whichever sibling app (report-engine, Slim-LIMS, ...) actually
# imported this shared package. That silently falls back to the sqlite
# default instead of erroring, which is exactly what happened when Slim-LIMS
# first ran with a real .env sitting right next to it, confirmed via a
# reproducible test (a plain `python -c` import happened to mask the bug,
# since find_dotenv() falls back to cwd specifically when there's no
# calling __main__.__file__ -- i.e. only in that interactive/-c case).
# Variables already present in the environment take precedence over .env
# values (load_dotenv()'s default override=False).
load_dotenv(find_dotenv(usecwd=True))

# Precedence: DB_URL in .env (or real environment) > hardcoded SQLite default.
# The --db CLI flag sits above both of these — it passes a value to make_engine()
# directly, bypassing _DEFAULT_DB_URL entirely.
_DEFAULT_DB_URL: str = os.environ.get("DB_URL", "sqlite:///slim_domain.db")


class Base(DeclarativeBase):
    pass


def make_engine(url: str | None = None):
    """Return a SQLAlchemy engine.

    Precedence: url argument (--db CLI flag) > DB_URL env var (.env) > sqlite:///slim_domain.db
    """
    resolved_url = url or _DEFAULT_DB_URL
    connect_args = {}
    if make_url(resolved_url).get_backend_name() == "postgresql":
        # An unreachable Postgres server (wrong host, firewall, server down)
        # would otherwise hang this call indefinitely -- there's no VBA-side
        # force-kill anymore now that the real hook launches hidden via
        # WScript.Shell.Run instead of .Exec (see modReportEngineHook.bas),
        # so this needs to fail loudly on its own within a bounded time
        # rather than leave a hidden process running forever. sqlite has no
        # equivalent concept (a local file connect never blocks like this).
        connect_args["connect_timeout"] = 10
    # pool_pre_ping: test each pooled connection with a lightweight query
    # before handing it to a caller, transparently reconnecting if it's
    # gone stale. Confirmed necessary the hard way: Slim-LIMS caches
    # services (and their sessions) for a server's entire lifetime --
    # reads never touch the connection again after the initial cache
    # build, but the new customer/chemical resolution feature's writes
    # do, and a Postgres restart (even a routine one, unrelated to this
    # app) kills every existing connection out from under a long-running
    # process. Without this, that surfaced as a confusing
    # PendingRollbackError deep inside an INSERT, not an obviously
    # connection-related error.
    return create_engine(resolved_url, connect_args=connect_args, pool_pre_ping=True)


def make_session(engine) -> Session:
    return Session(engine)
