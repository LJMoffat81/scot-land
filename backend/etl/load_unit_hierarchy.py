"""ARCH-4a + PLACES-LADDER: Populate and validate ref.unit and ref.unit_hierarchy.

Loads:
- ref.unit: scotland (1), council (32), iz2022 (1,334), dz2022 (7,392), dz2011 (6,976)
- ref.unit_hierarchy:
  - dz2022 -> iz2022 (7,392, weight=1, version='2022') [PLACES-LADDER; IZ not a map level]
  - iz2022 -> council (1,334, weight=1, version='2022') [PLACES-LADDER]
  - dz2022 -> council (7,392, weight=1, version='2022') [TARGET-ARCH-1]
  - council -> scotland (32, weight=1, version='2022') [TARGET-ARCH-1]
  - dz2011 -> dz2022 (10,473, weight from dz_crosswalk_people.csv) [TARGET-ARCH-1]

Usage::

    python -m etl.load_unit_hierarchy --check
    python -m etl.load_unit_hierarchy --load
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras

REPO_ROOT = Path(__file__).resolve().parents[2]
SPINE_CSV = REPO_ROOT / "data" / "processed" / "datazones" / "zone_spine.csv"
CROSSWALK_CSV = (
    REPO_ROOT / "data" / "processed" / "datazones" / "dz_crosswalk_people.csv"
)

_DZ_RE = re.compile(r"^S01[0-9]{6}$")
_IZ_RE = re.compile(r"^S02[0-9]{6}$")
_LA_RE = re.compile(r"^S12[0-9]{6}$")
_REQ_SPINE_COLS = ("code", "vintage", "name", "iz_code", "la_code", "la_name")
_REQ_CW_COLS = ("dz2011", "dz2022", "weight", "method")
_ALLOWED_CW_METHODS = frozenset(
    {"pop_hhres_2022", "fallback_census2011_pop_terminated_postcodes"}
)


class HierarchyError(Exception):
    """Raised when unit or unit_hierarchy validation or loading fails (``HIERARCHY:`` prefix)."""


def _dsn() -> str:
    dsn = (
        os.environ.get("ARCH1_TEST_DSN")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if not dsn:
        raise HierarchyError(
            "HIERARCHY: ARCH1_TEST_DSN or DATABASE_URL not set"
        )
    return dsn


def _valid_dz_code(code: str, vintage: str) -> bool:
    if not _DZ_RE.fullmatch(code):
        return False
    if vintage == "2011":
        return "S01006506" <= code <= "S01013481"
    if vintage == "2022":
        return "S01013482" <= code <= "S01020873"
    return False


def parse_zone_spine(spine_path: Path | str = SPINE_CSV) -> dict[str, Any]:
    """Parse and validate ``zone_spine.csv``."""
    if not isinstance(spine_path, (Path, str)) or isinstance(spine_path, bool):
        raise HierarchyError("HIERARCHY: spine_path must be a Path or str")
    path = Path(spine_path)
    if not path.is_file():
        raise HierarchyError(f"HIERARCHY: zone_spine not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise HierarchyError(f"HIERARCHY: zone_spine is empty: {path}")

    reader = csv.DictReader(text.splitlines())
    fieldnames = reader.fieldnames or []
    for col in _REQ_SPINE_COLS:
        if col not in fieldnames:
            raise HierarchyError(
                f"HIERARCHY: zone_spine missing column {col!r}"
            )

    dz2011: dict[str, dict[str, str]] = {}
    dz2022: dict[str, dict[str, str]] = {}
    councils: dict[str, str] = {}
    iz2022_to_la: dict[str, str] = {}

    for idx, row in enumerate(reader, start=2):
        vintage = (row.get("vintage") or "").strip()
        if vintage not in ("2011", "2022"):
            raise HierarchyError(
                f"HIERARCHY: zone_spine row {idx}: invalid vintage {vintage!r}"
            )
        code = (row.get("code") or "").strip()
        if not _valid_dz_code(code, vintage):
            raise HierarchyError(
                f"HIERARCHY: zone_spine row {idx}: invalid code {code!r} for vintage {vintage}"
            )
        target = dz2011 if vintage == "2011" else dz2022
        if code in target:
            raise HierarchyError(
                f"HIERARCHY: zone_spine: duplicate (code, vintage) ({code!r}, {vintage})"
            )
        name = (row.get("name") or "").strip()
        la_name = (row.get("la_name") or "").strip()
        if not name or not la_name:
            raise HierarchyError(
                f"HIERARCHY: zone_spine row {idx}: empty name or la_name"
            )
        iz_code = (row.get("iz_code") or "").strip()
        if not _IZ_RE.fullmatch(iz_code):
            raise HierarchyError(
                f"HIERARCHY: zone_spine row {idx}: invalid iz_code {iz_code!r}"
            )
        la_code = (row.get("la_code") or "").strip()
        if not _LA_RE.fullmatch(la_code):
            raise HierarchyError(
                f"HIERARCHY: zone_spine row {idx}: invalid la_code {la_code!r}"
            )
        target[code] = {
            "code": code,
            "name": name,
            "iz_code": iz_code,
            "la_code": la_code,
            "la_name": la_name,
        }
        if vintage == "2022":
            prev_la_name = councils.get(la_code)
            if prev_la_name is not None and prev_la_name != la_name:
                raise HierarchyError(
                    f"HIERARCHY: council {la_code} has conflicting names: "
                    f"{prev_la_name!r} vs {la_name!r}"
                )
            councils[la_code] = la_name
            prev_la = iz2022_to_la.get(iz_code)
            if prev_la is not None and prev_la != la_code:
                raise HierarchyError(
                    f"HIERARCHY: iz2022 {iz_code} spans multiple councils: "
                    f"{prev_la} vs {la_code}"
                )
            iz2022_to_la[iz_code] = la_code

    if not dz2011 or not dz2022:
        raise HierarchyError(
            "HIERARCHY: zone_spine: missing vintage 2011 or 2022 rows"
        )
    return {
        "dz2011": dz2011,
        "dz2022": dz2022,
        "councils": councils,
        "iz2022_to_la": iz2022_to_la,
    }


def parse_crosswalk_people(
    crosswalk_path: Path | str = CROSSWALK_CSV,
    *,
    valid_dz2011: set[str],
    valid_dz2022: set[str],
) -> list[dict[str, Any]]:
    """Parse and validate ``dz_crosswalk_people.csv`` against spine codes."""
    if not isinstance(crosswalk_path, (Path, str)) or isinstance(
        crosswalk_path, bool
    ):
        raise HierarchyError("HIERARCHY: crosswalk_path must be a Path or str")
    if (
        not isinstance(valid_dz2011, set)
        or not valid_dz2011
        or not all(isinstance(x, str) and x for x in valid_dz2011)
        or not isinstance(valid_dz2022, set)
        or not valid_dz2022
        or not all(isinstance(x, str) and x for x in valid_dz2022)
    ):
        raise HierarchyError(
            "HIERARCHY: crosswalk: valid_dz2011 and valid_dz2022 must be non-empty sets of strings"
        )
    path = Path(crosswalk_path)
    if not path.is_file():
        raise HierarchyError(f"HIERARCHY: crosswalk not found: {path}")
    text = path.read_text(encoding="utf-8-sig")
    if not text.strip():
        raise HierarchyError(f"HIERARCHY: crosswalk is empty: {path}")

    reader = csv.DictReader(text.splitlines())
    fieldnames = reader.fieldnames or []
    for col in _REQ_CW_COLS:
        if col not in fieldnames:
            raise HierarchyError(
                f"HIERARCHY: crosswalk missing column {col!r}"
            )

    rows: list[dict[str, Any]] = []
    seen_pairs: set[tuple[str, str]] = set()
    weight_sums: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

    for idx, row in enumerate(reader, start=2):
        d11 = (row.get("dz2011") or "").strip()
        if d11 not in valid_dz2011:
            raise HierarchyError(
                f"HIERARCHY: crosswalk row {idx}: unknown dz2011 {d11!r}"
            )
        d22 = (row.get("dz2022") or "").strip()
        if d22 not in valid_dz2022:
            raise HierarchyError(
                f"HIERARCHY: crosswalk row {idx}: unknown dz2022 {d22!r}"
            )
        pair = (d11, d22)
        if pair in seen_pairs:
            raise HierarchyError(
                f"HIERARCHY: crosswalk: duplicate pair ({d11!r}, {d22!r})"
            )
        seen_pairs.add(pair)

        raw_w = (row.get("weight") or "").strip()
        try:
            w = Decimal(raw_w)
        except InvalidOperation as exc:
            raise HierarchyError(
                f"HIERARCHY: crosswalk row {idx}: weight must be in (0, 1], got {raw_w!r}"
            ) from exc
        if not w.is_finite() or w <= Decimal("0") or w > Decimal("1"):
            raise HierarchyError(
                f"HIERARCHY: crosswalk row {idx}: weight must be in (0, 1], got {raw_w!r}"
            )

        method = (row.get("method") or "").strip()
        if method not in _ALLOWED_CW_METHODS:
            raise HierarchyError(
                f"HIERARCHY: crosswalk row {idx}: invalid method {method!r}"
            )

        weight_sums[d11] += w
        rows.append(
            {
                "dz2011": d11,
                "dz2022": d22,
                "weight": w,
                "method": method,
            }
        )

    if not rows:
        raise HierarchyError("HIERARCHY: crosswalk has 0 rows")

    for d11 in sorted(valid_dz2011):
        total = weight_sums.get(d11, Decimal("0"))
        if abs(total - Decimal("1")) > Decimal("0.00001"):
            raise HierarchyError(
                f"HIERARCHY: crosswalk: dz2011 {d11} weights sum to {float(total):.6f}, expected 1.0"
            )
    return rows


def build_unit_hierarchy_rows(
    spine_path: Path | str = SPINE_CSV,
    crosswalk_path: Path | str = CROSSWALK_CSV,
) -> dict[str, Any]:
    """Build deterministic ``ref.unit`` and ``ref.unit_hierarchy`` row tuples."""
    spine = parse_zone_spine(spine_path)
    dz2011 = spine["dz2011"]
    dz2022 = spine["dz2022"]
    councils = spine["councils"]
    iz2022_to_la = spine["iz2022_to_la"]

    cw_rows = parse_crosswalk_people(
        crosswalk_path,
        valid_dz2011=set(dz2011.keys()),
        valid_dz2022=set(dz2022.keys()),
    )

    d2011 = date(2011, 1, 1)
    d2022 = date(2022, 1, 1)
    one = Decimal("1")

    units: list[tuple[str, str, str, str, date, date | None]] = [
        ("scotland", "scotland", "scotland", "Scotland", d2022, None),
    ]
    for la_code in sorted(councils.keys()):
        units.append(
            ("council", la_code, "scotland", councils[la_code], d2022, None)
        )
    for iz_code in sorted(iz2022_to_la.keys()):
        units.append(("iz2022", iz_code, "scotland", iz_code, d2022, None))
    for code in sorted(dz2022.keys()):
        units.append(
            ("dz2022", code, "scotland", dz2022[code]["name"], d2022, None)
        )
    for code in sorted(dz2011.keys()):
        units.append(
            ("dz2011", code, "scotland", dz2011[code]["name"], d2011, d2022)
        )

    hierarchy: list[tuple[str, str, str, str, Decimal, str, date]] = []
    # 1. PLACES-LADDER: dz2022 -> iz2022
    for code in sorted(dz2022.keys()):
        hierarchy.append(
            (
                "dz2022",
                code,
                "iz2022",
                dz2022[code]["iz_code"],
                one,
                "2022",
                d2022,
            )
        )
    # 2. PLACES-LADDER: iz2022 -> council
    for iz_code in sorted(iz2022_to_la.keys()):
        hierarchy.append(
            (
                "iz2022",
                iz_code,
                "council",
                iz2022_to_la[iz_code],
                one,
                "2022",
                d2022,
            )
        )
    # 3. TARGET-ARCH-1: dz2022 -> council
    for code in sorted(dz2022.keys()):
        hierarchy.append(
            (
                "dz2022",
                code,
                "council",
                dz2022[code]["la_code"],
                one,
                "2022",
                d2022,
            )
        )
    # 4. TARGET-ARCH-1: council -> scotland
    for la_code in sorted(councils.keys()):
        hierarchy.append(
            ("council", la_code, "scotland", "scotland", one, "2022", d2022)
        )
    # 5. TARGET-ARCH-1: dz2011 -> dz2022 crosswalk
    for cw in sorted(cw_rows, key=lambda r: (r["dz2011"], r["dz2022"])):
        hierarchy.append(
            (
                "dz2011",
                cw["dz2011"],
                "dz2022",
                cw["dz2022"],
                cw["weight"],
                cw["method"],
                d2022,
            )
        )

    counts = {
        "units_total": len(units),
        "scotland": 1,
        "council": len(councils),
        "iz2022": len(iz2022_to_la),
        "dz2022": len(dz2022),
        "dz2011": len(dz2011),
        "dz2022_to_iz2022": len(dz2022),
        "iz2022_to_council": len(iz2022_to_la),
        "dz2022_to_council": len(dz2022),
        "council_to_scotland": len(councils),
        "dz2011_to_dz2022": len(cw_rows),
        "hierarchy_total": len(hierarchy),
    }
    return {"units": units, "hierarchy": hierarchy, "counts": counts}


def _ensure_tables(cur) -> None:
    cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ref.unit (
            unit_type text NOT NULL,
            unit_id text NOT NULL,
            geography text NOT NULL,
            name text,
            valid_from date NOT NULL,
            valid_to date,
            geom geometry(MultiPolygon, 27700),
            PRIMARY KEY (unit_type, unit_id, valid_from)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ref.unit_hierarchy (
            child_type text NOT NULL,
            child_id text NOT NULL,
            parent_type text NOT NULL,
            parent_id text NOT NULL,
            weight numeric NOT NULL DEFAULT 1
                CHECK (weight > 0 AND weight <= 1),
            version text NOT NULL,
            valid_from date NOT NULL,
            PRIMARY KEY (
                child_type, child_id, parent_type, parent_id, version
            )
        )
        """
    )


def load_unit_hierarchy(
    conn=None,
    *,
    spine_path: Path | str = SPINE_CSV,
    crosswalk_path: Path | str = CROSSWALK_CSV,
) -> dict[str, int]:
    """Atomically populate ``ref.unit`` and ``ref.unit_hierarchy`` in PostGIS."""
    built = build_unit_hierarchy_rows(spine_path, crosswalk_path)
    owns_conn = conn is None
    connection = conn or psycopg2.connect(_dsn())
    prev_autocommit = connection.autocommit
    try:
        connection.autocommit = False
        with connection:
            with connection.cursor() as cur:
                _ensure_tables(cur)
                cur.execute("TRUNCATE TABLE ref.unit_hierarchy, ref.unit")
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO ref.unit (
                        unit_type, unit_id, geography, name, valid_from, valid_to
                    ) VALUES %s
                    """,
                    built["units"],
                    page_size=2000,
                )
                psycopg2.extras.execute_values(
                    cur,
                    """
                    INSERT INTO ref.unit_hierarchy (
                        child_type, child_id, parent_type, parent_id,
                        weight, version, valid_from
                    ) VALUES %s
                    """,
                    built["hierarchy"],
                    page_size=2000,
                )
        return built["counts"]
    except psycopg2.Error as exc:
        raise HierarchyError(f"HIERARCHY: database error: {exc}") from exc
    finally:
        if owns_conn:
            connection.close()
        else:
            connection.autocommit = prev_autocommit


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Offline check of zone_spine.csv and dz_crosswalk_people.csv hierarchy rows",
    )
    parser.add_argument(
        "--load",
        action="store_true",
        help="Populate ref.unit and ref.unit_hierarchy in PostGIS",
    )
    parser.add_argument("--spine", type=Path, default=SPINE_CSV)
    parser.add_argument("--crosswalk", type=Path, default=CROSSWALK_CSV)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    if args.check == args.load:
        print(
            "HIERARCHY: specify exactly one of --check or --load",
            file=sys.stderr,
        )
        return 2
    try:
        if args.check:
            built = build_unit_hierarchy_rows(args.spine, args.crosswalk)
            print(
                json.dumps(
                    {"ok": True, **built["counts"]},
                    sort_keys=True,
                )
            )
            return 0
        counts = load_unit_hierarchy(
            spine_path=args.spine, crosswalk_path=args.crosswalk
        )
        print(json.dumps({"ok": True, **counts}, sort_keys=True))
        return 0
    except HierarchyError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
