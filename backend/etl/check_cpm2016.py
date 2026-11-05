"""M6b-tiles: fail-closed CPM 2016 preconditions (raw table + clipped layer).

``check_cpm2016_raw`` runs from ``run_layer.PRECONDITIONS`` before fetch.
``check_cpm2016_clipped`` runs at the start of ``tiles.build`` so a direct
tile command cannot skip ``run_layer``.

National pin ``GPKG_FEATURE_COUNT`` stays ``None`` until Laurie's PC; fixture
tests monkeypatch it to the stub count (8) before calling ``run_layer``.
Never use WFS ``439700`` as that pin. Never assert post-clip count == raw pin.
"""

from __future__ import annotations

from typing import Any

from etl.check_dz2011_boundaries import PrecheckError
from georgist.cpm2016_rules import ALLOWED_IMPORTANCE, GPKG_FEATURE_COUNT

PREFIX = "CPM2016-PRECHECK: REFUSED: "
LAYER_ID = "carbon-peatland"
RAW_TABLE = "carbon_peatland"
OFFICIAL = sorted(ALLOWED_IMPORTANCE)


def _refuse(field: str, expected: Any, got: Any) -> PrecheckError:
    return PrecheckError(f"{PREFIX}{field}: expected {expected}, got {got}")


def _refuse_msg(message: str) -> PrecheckError:
    return PrecheckError(f"{PREFIX}{message}")


def check_cpm2016_raw(conn) -> None:
    """Fail-closed checks on pre-clip ``carbon_peatland`` (raw ingest table)."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'public' AND table_name = %s
            )
            """,
            (RAW_TABLE,),
        )
        if not cur.fetchone()[0]:
            raise _refuse("table", RAW_TABLE, "absent")

        cur.execute(f"SELECT count(*) FROM {RAW_TABLE}")
        n = int(cur.fetchone()[0])
        if n == 0:
            raise _refuse("rows", "at least 1", 0)

        pin = GPKG_FEATURE_COUNT
        if pin is None:
            raise _refuse("GPKG_FEATURE_COUNT", "pinned integer", None)
        if n != int(pin):
            raise _refuse("GPKG_FEATURE_COUNT", pin, n)

        cur.execute(f"SELECT DISTINCT ST_SRID(geom) FROM {RAW_TABLE}")
        srids = sorted(int(r[0]) for r in cur.fetchall())
        if srids != [27700]:
            actual = srids[0] if len(srids) == 1 else srids
            raise _refuse("SRID", 27700, actual)

        cur.execute(
            f"""
            SELECT importance IS NULL AS is_null, importance
            FROM {RAW_TABLE}
            """
        )
        present: set[int] = set()
        for is_null, importance in cur.fetchall():
            if is_null or importance is None:
                raise _refuse_msg(
                    "IMPORTANCE: expected integer code in "
                    f"{OFFICIAL}, got None"
                )
            code = int(importance)
            if code not in ALLOWED_IMPORTANCE:
                raise _refuse_msg(
                    "IMPORTANCE: expected integer code in "
                    f"{OFFICIAL}, got {code}"
                )
            present.add(code)

        if 1 not in present or 2 not in present:
            raise _refuse(
                "classes 1 and 2",
                "both present",
                sorted(present),
            )


def check_cpm2016_clipped(conn) -> None:
    """Fail-closed checks on post-clip ``layers."carbon-peatland"``."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT EXISTS (
              SELECT 1 FROM information_schema.tables
              WHERE table_schema = 'layers' AND table_name = %s
            )
            """,
            (LAYER_ID,),
        )
        if not cur.fetchone()[0]:
            raise _refuse("table", f'layers."{LAYER_ID}"', "absent")

        cur.execute(f'SELECT count(*) FROM layers."{LAYER_ID}"')
        n = int(cur.fetchone()[0])
        if n == 0:
            raise _refuse("rows", "at least 1", 0)

        cur.execute(f'SELECT DISTINCT ST_SRID(geom) FROM layers."{LAYER_ID}"')
        srids = sorted(int(r[0]) for r in cur.fetchall())
        if srids != [27700]:
            actual = srids[0] if len(srids) == 1 else srids
            raise _refuse("SRID", 27700, actual)

        cur.execute(
            f"""
            SELECT props->>'importance' AS importance
            FROM layers."{LAYER_ID}"
            """
        )
        present: set[int] = set()
        for (raw,) in cur.fetchall():
            if raw is None or str(raw).strip() == "":
                raise _refuse_msg(
                    "IMPORTANCE: expected integer code in "
                    f"{OFFICIAL}, got None"
                )
            try:
                code = int(str(raw).strip())
            except ValueError as exc:
                raise _refuse_msg(
                    "IMPORTANCE: expected integer code in "
                    f"{OFFICIAL}, got None"
                ) from exc
            if code not in ALLOWED_IMPORTANCE:
                raise _refuse_msg(
                    "IMPORTANCE: expected integer code in "
                    f"{OFFICIAL}, got {code}"
                )
            present.add(code)

        if 1 not in present or 2 not in present:
            raise _refuse(
                "classes 1 and 2",
                "both present",
                sorted(present),
            )
