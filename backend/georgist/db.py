"""PostGIS connection for the Wealth Engine. Configured only from the environment.

Either `DATABASE_URL` (postgresql://user:pass@host:5432/db) or the standard libpq
variables `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`. There are no
defaults for credentials. If nothing is configured, or the server cannot be
reached, callers get `DatabaseUnavailable` with a reason. They must surface it
(HTTP 503), never substitute zeros.
"""

from __future__ import annotations

import os
import re
from contextlib import contextmanager
from typing import Any, Iterator

CONNECT_TIMEOUT_S = int(os.getenv("DB_CONNECT_TIMEOUT", "3"))
_PG_VARS = ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE")


class DatabaseUnavailable(RuntimeError):
    """The Wealth database is not configured, not reachable, or lacks the schema."""

    def __init__(self, reason: str, detail: str = ""):
        self.reason = reason
        self.detail = _scrub(detail)
        super().__init__(f"{reason}: {self.detail}" if self.detail else reason)


def _scrub(text: str) -> str:
    """Remove anything that looks like a password from an error message."""
    text = re.sub(r"(postgres(?:ql)?://[^:/@\s]+:)[^@\s]+@", r"\1***@", text)
    return re.sub(r"(password\s*=\s*)\S+", r"\1***", text, flags=re.IGNORECASE)


def database_configured() -> bool:
    if os.getenv("DATABASE_URL", "").strip():
        return True
    return bool(os.getenv("PGHOST", "").strip() and os.getenv("PGDATABASE", "").strip())


def connection_kwargs() -> dict[str, Any]:
    """libpq connection arguments from the environment. Raises if unconfigured."""
    url = os.getenv("DATABASE_URL", "").strip()
    if url:
        return {"dsn": url, "connect_timeout": CONNECT_TIMEOUT_S}
    if database_configured():
        # libpq reads PG* itself; pass nothing secret explicitly.
        return {"dsn": "", "connect_timeout": CONNECT_TIMEOUT_S}
    raise DatabaseUnavailable(
        "not_configured",
        "set DATABASE_URL, or PGHOST and PGDATABASE (plus PGUSER/PGPASSWORD)",
    )


def connect():
    """Open a psycopg2 connection or raise `DatabaseUnavailable`."""
    kwargs = connection_kwargs()
    try:
        import psycopg2
    except ImportError as exc:  # pragma: no cover - requirements include it
        raise DatabaseUnavailable("driver_missing", str(exc)) from exc
    try:
        return psycopg2.connect(**kwargs)
    except psycopg2.Error as exc:
        raise DatabaseUnavailable("connection_failed", str(exc).strip()) from exc


@contextmanager
def cursor(dict_rows: bool = True) -> Iterator[Any]:
    """Read cursor. Query errors (missing table, bad SQL) become `DatabaseUnavailable`."""
    conn = connect()
    try:
        import psycopg2
        from psycopg2 import extras

        factory = extras.RealDictCursor if dict_rows else None
        try:
            with conn.cursor(cursor_factory=factory) as cur:
                yield cur
            conn.commit()
        except psycopg2.errors.UndefinedTable as exc:
            conn.rollback()
            raise DatabaseUnavailable(
                "schema_missing",
                f"{str(exc).strip()} — apply backend/db/schema/*.sql",
            ) from exc
        except psycopg2.Error as exc:
            conn.rollback()
            raise DatabaseUnavailable("query_failed", str(exc).strip()) from exc
    finally:
        conn.close()


def db_status() -> dict[str, Any]:
    """Cheap status for /health. Never raises."""
    if not database_configured():
        return {"status": "unavailable", "reason": "not_configured"}
    try:
        with cursor(dict_rows=False) as cur:
            cur.execute("SELECT postgis_lib_version()")
            version = cur.fetchone()[0]
        return {"status": "ok", "postgis": str(version) if version else None}
    except DatabaseUnavailable as exc:
        return {"status": "unavailable", "reason": exc.reason, "detail": exc.detail}
    except Exception as exc:  # health must never 500
        return {"status": "unavailable", "reason": "error", "detail": _scrub(str(exc))}
