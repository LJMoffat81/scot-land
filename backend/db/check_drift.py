"""Compare live PostGIS schema to backend/db/schema/*.sql (no drift).

Usage (after `alembic upgrade head` on a fresh DB):

    cd backend
    python -m db.check_drift

Exit 0 when every CREATE TABLE in the SQL files exists with the declared
columns; exit 1 with a report otherwise. Does not touch data/external.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from georgist import db

SCHEMA_DIR = Path(__file__).resolve().parent / "schema"
TABLE_RE = re.compile(
    r"CREATE TABLE (?:IF NOT EXISTS )?((?:[\w]+\.)?[\w]+)\s*\((.*?)\n\);",
    re.S | re.I,
)
# First token of a column line (skip constraints).
COL_RE = re.compile(r"^\s*([a-z_][a-z0-9_]*)\s+", re.I)
CONSTRAINT_PREFIXES = (
    "primary",
    "foreign",
    "unique",
    "check",
    "constraint",
    "exclude",
)
# Continuation / glue tokens inside multi-line CHECK (... OR ...) blocks.
NON_COLUMN_TOKENS = CONSTRAINT_PREFIXES + ("or", "and", "not", "in", "is", "null", "true", "false")


def expected_tables() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for sql_file in sorted(SCHEMA_DIR.glob("*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        for match in TABLE_RE.finditer(text):
            name = match.group(1).lower()
            cols: set[str] = set()
            for line in match.group(2).splitlines():
                line = line.strip().rstrip(",")
                if not line or line.startswith("(") or line.startswith(")"):
                    continue
                if line.lower().startswith(CONSTRAINT_PREFIXES):
                    continue
                m = COL_RE.match(line)
                if not m:
                    continue
                col = m.group(1).lower()
                if col in NON_COLUMN_TOKENS:
                    continue
                # Real columns are followed by a type token (text, numeric, geometry, ...).
                rest = line[m.end() :].lstrip()
                if not rest or rest.startswith("=") or rest.upper().startswith(("BETWEEN", "IN ", "AND ", "OR ")):
                    continue
                cols.add(col)
            out.setdefault(name, set()).update(cols)
    return out


def live_columns(conn, qualified: str) -> set[str] | None:
    if "." in qualified:
        schema, table = qualified.split(".", 1)
    else:
        schema, table = "public", qualified
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = %s AND table_name = %s
            """,
            (schema, table),
        )
        rows = cur.fetchall()
    if not rows:
        return None
    return {r[0].lower() for r in rows}


def check(conn) -> list[str]:
    problems: list[str] = []
    for table, cols in sorted(expected_tables().items()):
        live = live_columns(conn, table)
        if live is None:
            problems.append(f"missing table: {table}")
            continue
        missing = sorted(cols - live)
        extra_note = ""  # extras allowed (ALTER ADD from later files / ops)
        if missing:
            problems.append(f"{table}: missing columns {missing}{extra_note}")
    return problems


def main() -> int:
    try:
        conn = db.connect()
    except db.DatabaseUnavailable as exc:
        print(f"db.check_drift: database unavailable: {exc}", file=sys.stderr)
        return 2
    try:
        problems = check(conn)
    finally:
        conn.close()
    if problems:
        print("Schema drift detected:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"No drift: {len(expected_tables())} tables match db/schema/*.sql")
    return 0


if __name__ == "__main__":
    sys.exit(main())
