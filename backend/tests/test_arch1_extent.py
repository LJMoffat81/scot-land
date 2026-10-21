"""ARCH-1a extent load / close_slivers tests X1–X5, U4."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import psycopg2
import pytest

from etl.build_scotland_extent import ExtentError, load_only

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "arch1"
SQL_DIR = Path(__file__).resolve().parents[1] / "etl" / "sql"


def _dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN not set")
    return dsn


@pytest.fixture
def conn():
    dsn = _dsn()
    connection = psycopg2.connect(dsn)
    connection.autocommit = True
    with connection.cursor() as cur:
        cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    yield connection
    connection.close()


@pytest.fixture
def clean_ref(conn):
    with conn.cursor() as cur:
        cur.execute("CREATE SCHEMA IF NOT EXISTS ref")
        cur.execute("DROP TABLE IF EXISTS ref.extent_buf50_sub CASCADE")
        cur.execute("DROP TABLE IF EXISTS ref.extent_sub CASCADE")
        cur.execute("DROP TABLE IF EXISTS ref.extent CASCADE")
        cur.execute("DROP TABLE IF EXISTS ref.unit_hierarchy CASCADE")
        cur.execute("DROP TABLE IF EXISTS ref.unit CASCADE")
        cur.execute("DROP FUNCTION IF EXISTS ref.close_slivers(geometry)")
    yield conn


def test_x1_load_only_creates_tables_and_gist(clean_ref, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    # Point manifest lookup at fixture sha by copying into a temp gis folder layout.
    gis = tmp_path / "gis"
    gis.mkdir()
    src = FIXTURES / "extent_tiny.27700.geojson"
    dest = gis / "scotland_extent.27700.geojson"
    dest.write_bytes(src.read_bytes())
    sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    (gis / "manifest.csv").write_text(
        "file,owner,source,licence,attribution,publish_level,zone_vintage,key,rows,sha256,source_year\n"
        f"scotland_extent.27700.geojson,gis,fixture,OGL-3.0,test,public_zone,2011;2022,(zone),3,{sha},\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", gis / "manifest.csv"
    )
    load_only(dest)
    with clean_ref.cursor() as cur:
        cur.execute("SELECT count(*) FROM ref.extent WHERE geography='scotland'")
        assert cur.fetchone()[0] == 3
        cur.execute("SELECT count(*) FROM ref.extent_sub WHERE geography='scotland'")
        assert cur.fetchone()[0] > 0
        cur.execute(
            "SELECT count(*) FROM ref.extent_buf50_sub WHERE geography='scotland'"
        )
        assert cur.fetchone()[0] > 0
        cur.execute(
            """
            SELECT indexname FROM pg_indexes
            WHERE schemaname='ref' AND tablename='extent_sub'
              AND indexdef ILIKE '%USING gist%'
            """
        )
        names = [r[0] for r in cur.fetchall()]
        if "extent_sub_geom_idx" not in names:
            pytest.fail("missing index ref.extent_sub_geom_idx")


def test_x2_empty_file(clean_ref, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    empty = tmp_path / "scotland_extent.27700.geojson"
    empty.write_bytes(b"")
    (tmp_path / "manifest.csv").write_text(
        "file,sha256\nscotland_extent.27700.geojson," + ("ab" * 32) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", tmp_path / "manifest.csv"
    )
    with pytest.raises(ExtentError, match=r"CLIP: extent file empty:"):
        load_only(empty)


def test_x3_sha_mismatch(clean_ref, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    src = FIXTURES / "extent_tiny.27700.geojson"
    dest = tmp_path / "scotland_extent.27700.geojson"
    dest.write_bytes(src.read_bytes())
    (tmp_path / "manifest.csv").write_text(
        "file,sha256\nscotland_extent.27700.geojson," + ("0" * 64) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", tmp_path / "manifest.csv"
    )
    with pytest.raises(ExtentError, match=r"CLIP: extent sha256 mismatch"):
        load_only(dest)


def test_x4_invalid_zone_no_repair(clean_ref, monkeypatch, tmp_path):
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    src = FIXTURES / "invalid_bowtie.geojson"
    dest = tmp_path / "bad.geojson"
    dest.write_bytes(src.read_bytes())
    # No manifest row → sha check skipped; validity must still fail without make_valid.
    monkeypatch.setattr(
        "etl.build_scotland_extent.MANIFEST_PATH", tmp_path / "missing.csv"
    )
    with pytest.raises(
        ExtentError, match=r"CLIP: zone land invalid: Self-intersection"
    ):
        load_only(dest)


def test_x5_close_slivers_merges_gap(clean_ref):
    sql = (SQL_DIR / "close_slivers.sql").read_text(encoding="utf-8")
    with clean_ref.cursor() as cur:
        cur.execute(sql)
        # Two 1x1 km squares with a 0.5 m gap along x.
        cur.execute(
            """
            SELECT ST_NumGeometries(
              ref.close_slivers(
                ST_Collect(
                  ST_MakeEnvelope(0, 0, 1000, 1000, 27700),
                  ST_MakeEnvelope(1000.5, 0, 2000.5, 1000, 27700)
                )
              )
            )
            """
        )
        n = cur.fetchone()[0]
        assert n == 1


def test_u4_unit_tables_and_weight_check(clean_ref):
    """Apply the ARCH-1a migration SQL so M24 (drop CHECK) turns this red."""
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "20261021_0026_arch1_ref_layers_schemas.py"
    )
    text = migration.read_text(encoding="utf-8")
    # Extract CREATE TABLE statements from the migration module source.
    import re

    creates = re.findall(
        r'op\.execute\(\s*"""(.*?)"""\s*\)',
        text,
        flags=re.S,
    )
    assert creates, "migration has no op.execute SQL"
    with clean_ref.cursor() as cur:
        for stmt in creates:
            cur.execute(stmt)
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='ref' AND table_name='unit'
            ORDER BY ordinal_position
            """
        )
        unit_cols = [r[0] for r in cur.fetchall()]
        assert unit_cols == [
            "unit_type",
            "unit_id",
            "geography",
            "name",
            "valid_from",
            "valid_to",
            "geom",
        ]
        cur.execute(
            """
            SELECT column_name FROM information_schema.columns
            WHERE table_schema='ref' AND table_name='unit_hierarchy'
            ORDER BY ordinal_position
            """
        )
        hier_cols = [r[0] for r in cur.fetchall()]
        assert hier_cols == [
            "child_type",
            "child_id",
            "parent_type",
            "parent_id",
            "weight",
            "version",
            "valid_from",
        ]
        with pytest.raises(psycopg2.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO ref.unit_hierarchy (
                  child_type, child_id, parent_type, parent_id,
                  weight, version, valid_from
                ) VALUES ('dz2022','S01000001','council','S12000001',0,'v1','2022-01-01')
                """
            )
