"""ARCH-3 (Batch A): GIS-cleared official OGL-3.0 registry layers, SRID-aware postgis_table adapter, and Batch A exclusion guards."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

from etl.run_layer import run_layer
from layers.parked_check import (
    BATCH_A_EXCLUDED_REGISTRY_IDS,
    ParkedGuardError,
    check_parked_guards,
)
from layers.registry.loader import REGISTRY_DIR, RegistryError, load_registry

_HELPERS_PATH = (
    Path(__file__).resolve().parent / "fixtures" / "arch2" / "helpers.py"
)
_spec = importlib.util.spec_from_file_location("arch2_helpers_3", _HELPERS_PATH)
assert _spec and _spec.loader
_helpers = importlib.util.module_from_spec(_spec)
sys.modules["arch2_helpers_3"] = _helpers
_spec.loader.exec_module(_helpers)

connect = _helpers.connect
drop_layer_tables = _helpers.drop_layer_tables
load_tiny_extent = _helpers.load_tiny_extent

BATCH_A_GO_SPECS: dict[str, dict[str, Any]] = {
    "ces-aquaculture": {
        "table": "ces_aquaculture_leases",
        "id_field": "id",
        "clip": "land+sea",
        "geometry": "polygon",
        "unit": "none",
        "vintage": "2026",
        "attribution": (
            "Contains public sector information, licensed under the Open Government "
            "Licence v3.0, from Crown Estate Scotland."
        ),
    },
    "crown-estate-leases": {
        "table": "crown_estate_leases",
        "id_field": "id",
        "clip": "sea",
        "geometry": "polygon",
        "unit": "none",
        "vintage": "2026",
        "attribution": (
            "Contains public sector information, licensed under the Open Government "
            "Licence v3.0, from Crown Estate Scotland."
        ),
    },
    "scotwind-intog": {
        "table": "ces_scotwind_intog",
        "id_field": "id",
        "clip": "sea",
        "geometry": "polygon",
        "unit": "none",
        "vintage": "2026",
        "attribution": (
            "Contains information from the Crown Estate Scotland licensed under the "
            "Open Government Licence v3.0."
        ),
    },
    "repd": {
        "table": "repd_sites",
        "id_field": "ref_id",
        "clip": "land+sea",
        "geometry": "point",
        "unit": "point",
        "vintage": "REPD Q2 2026 (2026-07)",
        "attribution": (
            "Contains public sector information licensed under the Open Government "
            "Licence v3.0 from the Department for Energy Security and Net Zero."
        ),
    },
    "repd-onshore-wind": {
        "table": "repd_onshore_wind",
        "id_field": "ref_id",
        "clip": "land",
        "geometry": "point",
        "unit": "point",
        "vintage": "REPD Q2 2026 (2026-07)",
        "attribution": (
            "Contains public sector information licensed under the Open Government "
            "Licence v3.0. Renewable Energy Planning Database © DESNZ / Crown copyright."
        ),
    },
    "naturescot-sssi": {
        "table": "naturescot_sssi",
        "id_field": "pa_code",
        "clip": "land+sea",
        "geometry": "polygon",
        "unit": "none",
        "vintage": "2026",
        "attribution": (
            "Contains NatureScot information licensed under the Open Government Licence "
            "v3.0. Contains OS data © Crown copyright and database right 2026."
        ),
    },
    "naturescot-designations": {
        "table": "naturescot_designations",
        "id_field": "site_key",
        "clip": "land+sea",
        "geometry": "polygon",
        "unit": "none",
        "vintage": "NNR rev 2026-09-17",
        "attribution": (
            "Contains NatureScot information licensed under the Open Government Licence "
            "v3.0. Contains OS data © Crown copyright and database right 2026."
        ),
    },
    "sepa-flood": {
        "table": "sepa_flood",
        "id_field": "object_id",
        "clip": "land+sea",
        "geometry": "polygon",
        "unit": "none",
        "vintage": "Flood Maps v3.0 (rev 2025-02-25)",
        "attribution": (
            "© SEPA 2025; this SEPA product is licensed under the Open Government "
            "Licence v3.0."
        ),
    },
    "hydro-sites": {
        "table": "hydro_sites",
        "id_field": "lic_no",
        "clip": "land",
        "geometry": "point",
        "unit": "point",
        "vintage": "SEPA ATOM feed (2018-08-01)",
        "attribution": (
            "Contains public sector information licensed under the Open Government "
            "Licence v3.0. © SEPA."
        ),
    },
    "sepa-car": {
        "table": "sepa_car_licences",
        "id_field": "authorisation_no",
        "clip": "land+sea",
        "geometry": "point",
        "unit": "point",
        "vintage": "2026",
        "attribution": (
            "Contains public sector information licensed under the Open Government "
            "Licence v3.0. © Scottish Environment Protection Agency."
        ),
    },
    "nfi": {
        "table": "nfi_woodland",
        "id_field": "feature_id",
        "clip": "land",
        "geometry": "polygon",
        "unit": "none",
        "vintage": "NFI Scotland 2025",
        "attribution": (
            "© Forestry Commission copyright. Contains Ordnance Survey data © Crown "
            "copyright and database right 2026. Licensed under the Open Government "
            "Licence v3.0."
        ),
    },
    "native-woodland": {
        "table": "native_woodland",
        "id_field": "feature_id",
        "clip": "land",
        "geometry": "polygon",
        "unit": "none",
        "vintage": "NWSS national survey",
        "attribution": (
            "Native Woodland Survey of Scotland. © Scottish Forestry / Forestry "
            "Commission. Contains Ordnance Survey data © Crown copyright and database "
            "right 2026. Licensed under the Open Government Licence v3.0."
        ),
    },
}


def _dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        raise RuntimeError("ARCH1_TEST_DSN not set")
    return dsn


@pytest.fixture
def conn():
    _dsn()
    connection = connect()
    yield connection
    connection.close()


def test_arch3_12_batch_a_entries_registered_and_match_gis_signoff() -> None:
    entries = load_registry(REGISTRY_DIR)
    assert len(entries) == 19
    for lid, spec in sorted(BATCH_A_GO_SPECS.items()):
        assert lid in entries, f"missing Batch A registry entry {lid}"
        raw = entries[lid].raw
        assert raw["licence"] == "OGL-3.0"
        assert raw["serve"]["mode"] == "pmtiles"
        assert raw["clip"] == spec["clip"]
        assert raw["geometry"] == spec["geometry"]
        assert raw["unit"] == spec["unit"]
        assert raw["vintage"] == spec["vintage"]
        assert raw["attribution"] == spec["attribution"]
        assert raw["source"]["type"] == "postgis_table"
        assert raw["source"]["table"] == spec["table"]
        assert raw["source"]["id_field"] == spec["id_field"]
        if spec["geometry"] == "polygon":
            assert raw["clip_keep_all"] is False
        for field in raw.get("keep_fields") or []:
            assert "gbp" not in field.lower()
            assert "fee" not in field.lower()
            assert "postcode" not in field.lower()


@pytest.mark.parametrize("bad_vintage", [None, True, False, 2026, 2026.0, "", [], {}])
def test_registry_schema_rejects_bad_vintage(
    tmp_path: Path, bad_vintage: Any
) -> None:
    base = yaml.safe_load(
        (REGISTRY_DIR / "ces-aquaculture.yaml").read_text(encoding="utf-8")
    )
    base["id"] = "x"
    base["vintage"] = bad_vintage
    (tmp_path / "x.yaml").write_text(
        yaml.safe_dump(base, sort_keys=False), encoding="utf-8"
    )
    with pytest.raises(RegistryError, match=r"^REGISTRY: x: \$\.vintage: "):
        load_registry(tmp_path)


@pytest.mark.parametrize(
    "excluded_id",
    sorted(BATCH_A_EXCLUDED_REGISTRY_IDS),
)
def test_check_parked_guards_rejects_excluded_batch_a_ids(
    excluded_id: str,
) -> None:
    with pytest.raises(
        ParkedGuardError,
        match=rf"^PARKED: excluded Batch A source '{excluded_id}' must not appear in registry$",
    ):
        check_parked_guards(
            entries={excluded_id: {"source": {"type": "postgis_table"}}}
        )


def test_all_12_batch_a_entries_run_layer_ingest_and_clip(
    conn, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("ARCH1_TEST_DSN", _dsn())
    all_lids = tuple(sorted(BATCH_A_GO_SPECS.keys()))
    drop_layer_tables(conn, *all_lids)
    load_tiny_extent(conn, monkeypatch, tmp_path)

    entries = load_registry(REGISTRY_DIR)
    table_names = [BATCH_A_GO_SPECS[lid]["table"] for lid in all_lids]

    with conn.cursor() as cur:
        for tname in table_names:
            cur.execute(f"DROP TABLE IF EXISTS public.{tname} CASCADE")

        for lid in all_lids:
            raw = entries[lid].raw
            tname = raw["source"]["table"]
            id_field = raw["source"]["id_field"]
            keep_fields = raw.get("keep_fields") or []
            geom_kind = raw["geometry"]
            clip_mode = raw["clip"]

            extra_cols = []
            seen_cols = {id_field, "publication_status", "geom"}
            for col in keep_fields:
                if col not in seen_cols:
                    extra_cols.append(f"{col} TEXT")
                    seen_cols.add(col)
            col_sql = ",\n                ".join(
                [f"{id_field} TEXT PRIMARY KEY", "publication_status TEXT NOT NULL DEFAULT 'ok'"]
                + extra_cols
                + [
                    "geom GEOMETRY(Point, 4326) NOT NULL"
                    if geom_kind == "point"
                    else "geom GEOMETRY(MultiPolygon, 4326) NOT NULL"
                ]
            )
            cur.execute(f"CREATE TABLE public.{tname} ({col_sql})")

            # Tiny extent has land square x=0..10000, y=0..10000 and sea square x=0..20000, y=0..20000 (in EPSG:27700).
            if geom_kind == "point":
                in_geom = "ST_Transform(ST_SetSRID(ST_MakePoint(5000, 5000), 27700), 4326)"
                out_geom = "ST_Transform(ST_SetSRID(ST_MakePoint(50000, 50000), 27700), 4326)"
            else:
                if clip_mode == "sea":
                    # Inside sea (12000..14000, 2000..4000), plus one outside (50000..52000, 50000..52000)
                    in_geom = "ST_Multi(ST_Transform(ST_MakeEnvelope(12000, 2000, 14000, 4000, 27700), 4326))"
                else:
                    # Inside land (2000..4000, 2000..4000)
                    in_geom = "ST_Multi(ST_Transform(ST_MakeEnvelope(2000, 2000, 4000, 4000, 27700), 4326))"
                out_geom = "ST_Multi(ST_Transform(ST_MakeEnvelope(50000, 50000, 52000, 52000, 27700), 4326))"

            cur.execute(
                f"INSERT INTO public.{tname} ({id_field}, publication_status, geom) VALUES "
                f"('IN_1', 'ok', {in_geom}), ('OUT_1', 'ok', {out_geom})"
            )
    conn.commit()

    try:
        for lid in all_lids:
            res = run_layer(lid, conn=conn)
            assert res["id"] == lid
            assert res["before"] == 2
            assert res["after"] == 1
            assert res["outside"] == 0
    finally:
        drop_layer_tables(conn, *all_lids)
        with conn.cursor() as cur:
            for tname in table_names:
                cur.execute(f"DROP TABLE IF EXISTS public.{tname} CASCADE")
        conn.commit()
