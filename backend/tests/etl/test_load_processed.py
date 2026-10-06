"""Manifest loader: only listed files, checksums, row counts, declared keys, loud rejection.

All datasets here are SYNTHETIC except the test_repo_* tests, which check the committed
data/processed/gis and data/processed/datazones files against their manifests.
"""

import csv
import hashlib
import os

import pytest

from etl import load_processed as lp
from paths import PROCESSED_DIR

HEADER = list(lp.MANIFEST_COLUMNS) + ["attribution"]


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _dataset(tmp_path, files, *, name="syn", overrides=None, extra_rows=()):
    """files: {relpath: csv text}. Writes a manifest with correct sha/rows unless overridden.

    Adds the optional `key_type` column when any override uses it."""
    root = tmp_path / name
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    rows = []
    for rel, text in files.items():
        p = root / rel
        n = max(len([ln for ln in text.splitlines() if ln.strip()]) - 1, 0)
        row = {"file": rel, "owner": "test", "source": "SYNTHETIC", "licence": "synthetic-test-only",
               "publish_level": "public_zone", "zone_vintage": "2011;2022", "key": "(code, vintage)",
               "rows": str(n), "sha256": _sha(p), "attribution": "SYNTHETIC attribution"}
        row.update((overrides or {}).get(rel, {}))
        rows.append(row)
    rows += list(extra_rows)
    fields = HEADER + (["key_type"] if any("key_type" in r for r in rows) else [])
    with open(root / "manifest.csv", "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, restval="")
        w.writeheader()
        w.writerows(rows)
    return tmp_path


ZONES = "code,vintage,value\nS01006506,2011,1.5\nS01013482,2022,2.0\n"
MULTI = ("code,vintage,brma_id,household_share\n"
         "S01006805,2011,S33000001,0.9\nS01006805,2011,S33000005,0.1\n")


XWALK = ("dz2011,dz2022,people_share\n"
         "S01006506,S01013482,0.6\nS01006506,S01013483,0.4\nS01006507,S01013483,1.0\n")
XW = {"key": "(dz2011, dz2022)", "zone_vintage": "2011;2022"}


def _problems(root):
    with pytest.raises(lp.ManifestError) as exc:
        lp.validate(root)
    return "\n".join(exc.value.problems)


def test_valid_dataset_passes(tmp_path):
    entries = lp.validate(_dataset(tmp_path, {"zones.csv": ZONES}))
    assert [e.table for e in entries] == ["syn_zones"]
    assert len(entries[0].frame) == 2


def test_multi_row_key_unique_on_full_declared_key(tmp_path):
    root = _dataset(tmp_path, {"m.csv": MULTI}, overrides={"m.csv": {"key": "(code, vintage, brma_id)"}})
    assert lp.validate(root)[0].key == ("code", "vintage", "brma_id")


def test_duplicates_on_declared_key_rejected(tmp_path):
    # Same rows keyed only (code, vintage): duplicates -> rejected.
    assert "duplicate the declared key" in _problems(_dataset(tmp_path, {"m.csv": MULTI}))


def test_duplicates_on_full_multi_key_rejected(tmp_path):
    dup = MULTI + "S01006805,2011,S33000001,0.0\n"
    root = _dataset(tmp_path, {"m.csv": dup}, overrides={"m.csv": {"key": "(code, vintage, brma_id)"}})
    assert "duplicate the declared key" in _problems(root)


@pytest.mark.parametrize("key", ["(vintage, code)", "(brma_id, code, vintage)", "(code)", "",
                                 "(dz2022, dz2011)", "(dz2011)", "(code, dz2022)"])
def test_key_must_start_with_code_vintage(tmp_path, key):
    root = _dataset(tmp_path, {"z.csv": ZONES}, overrides={"z.csv": {"key": key}})
    assert "must start with (code, vintage), (dz2011, dz2022)" in _problems(root)


# --------------------------------------------------------------------------- integer vintage standard

@pytest.mark.parametrize("label", ["DZ2011", "dz2011", "2011.0", " DZ2022", "2015"])
def test_text_or_other_vintage_values_rejected_loudly(tmp_path, label):
    """vintage is the integer 2011/2022. 'DZ2011' is listed and rejected, never mapped."""
    text = f"code,vintage,value\nS01006506,{label},1.5\nS01006507,2011,1\n"
    problems = _problems(_dataset(tmp_path, {"z.csv": text}))
    assert "vintage must be the integer 2011 or 2022" in problems and label.strip() in problems
    if label.strip().upper().startswith("DZ"):
        assert "text labels like 'DZ2011' are rejected, not mapped" in problems


def test_loaded_vintage_is_integer(tmp_path):
    e = lp.validate(_dataset(tmp_path, {"z.csv": ZONES}))[0]
    assert list(e.frame["vintage"]) == [2011, 2022] and str(e.frame["vintage"].dtype) == "Int16"
    assert e.zone_vintages == (2011, 2022)


@pytest.mark.parametrize("declared", ["2011;2022", "DZ2011;DZ2022", "2022;DZ2011"])
def test_manifest_zone_vintage_declaration_normalised_to_integers(tmp_path, declared):
    """The manifest's zone_vintage is metadata (Data Zones and GIS write DZ2011;DZ2022); the data is not."""
    e = lp.validate(_dataset(tmp_path, {"z.csv": ZONES}, overrides={"z.csv": {"zone_vintage": declared}}))[0]
    assert set(e.zone_vintages) == {2011, 2022}


def test_vintage_key_type_for_per_vintage_metadata(tmp_path):
    cov = "vintage,count_year,published\n2011,2024,True\n2022,2024,True\n2022,2025,True\n"
    e = lp.validate(_dataset(tmp_path, {"cov.csv": cov}, overrides={"cov.csv": {"key": "(vintage, count_year)"}}))[0]
    assert e.key_type == "vintage" and e.key == ("vintage", "count_year")
    bad = cov.replace("2022,2025", "DZ2022,2025")
    root = _dataset(tmp_path / "b", {"cov.csv": bad}, overrides={"cov.csv": {"key": "(vintage, count_year)"}})
    assert "vintage must be the integer 2011 or 2022" in _problems(root)
    only11 = _dataset(tmp_path / "c", {"cov.csv": cov},
                      overrides={"cov.csv": {"key": "(vintage, count_year)", "zone_vintage": "2011"}})
    assert "not declared in zone_vintage" in _problems(only11)


# --------------------------------------------------------------------------- crosswalk key type

def test_crosswalk_key_type_accepted(tmp_path):
    entries = lp.validate(_dataset(tmp_path, {"dz_crosswalk_people.csv": XWALK},
                                   overrides={"dz_crosswalk_people.csv": XW}))
    assert entries[0].key_type == "crosswalk" and entries[0].key == ("dz2011", "dz2022")
    explicit = _dataset(tmp_path / "b", {"x.csv": XWALK}, overrides={"x.csv": {**XW, "key_type": "crosswalk"}})
    assert lp.validate(explicit)[0].key_type == "crosswalk"


def test_zone_files_get_zone_key_type(tmp_path):
    assert lp.validate(_dataset(tmp_path, {"z.csv": ZONES}))[0].key_type == "zone"


@pytest.mark.parametrize("bad_csv,msg", [
    ("dz2011,dz2022,s\nS01013482,S01013482,1\n", "not valid 2011 codes"),   # 2022 code in dz2011
    ("dz2011,dz2022,s\nS01006506,S01006507,1\n", "not valid 2022 codes"),   # 2011 code in dz2022
    ("dz2011,dz2022,s\nunknown,S01013482,1\n", "not valid 2011 codes"),
    ("dz2011,dz2022,s\nS01006506,S01013482,0.5\nS01006506,S01013482,0.5\n", "duplicate the declared key"),
    ("dz2011,dz2022,s\nS01006506,,1\n", "empty key values"),
    ("code,dz2022,s\nS01006506,S01013482,1\n", "not in file"),
])
def test_crosswalk_validation(tmp_path, bad_csv, msg):
    assert msg in _problems(_dataset(tmp_path, {"x.csv": bad_csv}, overrides={"x.csv": XW}))


def test_crosswalk_must_declare_both_vintages_and_agree_with_key_type(tmp_path):
    root = _dataset(tmp_path, {"x.csv": XWALK}, overrides={"x.csv": {**XW, "zone_vintage": "2011"}})
    assert "must declare zone_vintage 2011;2022" in _problems(root)
    root = _dataset(tmp_path / "b", {"x.csv": XWALK}, overrides={"x.csv": {**XW, "key_type": "zone"}})
    assert "key_type 'zone'" in _problems(root)
    root = _dataset(tmp_path / "c", {"z.csv": ZONES}, overrides={"z.csv": {"key_type": "crosswalk"}})
    assert "key_type 'crosswalk'" in _problems(root)
    root = _dataset(tmp_path / "d", {"z.csv": ZONES}, overrides={"z.csv": {"key_type": "lookup"}})
    assert "key_type 'lookup' not in" in _problems(root)


def test_sha_mismatch_rejected(tmp_path):
    root = _dataset(tmp_path, {"z.csv": ZONES}, overrides={"z.csv": {"sha256": "0" * 64}})
    assert "sha256 mismatch" in _problems(root)


def test_row_count_mismatch_rejected(tmp_path):
    root = _dataset(tmp_path, {"z.csv": ZONES}, overrides={"z.csv": {"rows": "3"}})
    assert "row count 2 != manifest rows 3" in _problems(root)


@pytest.mark.parametrize("field,value,msg", [
    ("licence", "", "licence is empty"),
    ("publish_level", "blocked", "publish_level 'blocked'"),
    ("publish_level", "public", "publish_level 'public'"),
    ("zone_vintage", "DZ2001", "zone_vintage"),
])
def test_licence_and_publish_level_required(tmp_path, field, value, msg):
    root = _dataset(tmp_path, {"z.csv": ZONES}, overrides={"z.csv": {field: value}})
    assert msg in _problems(root)


def test_bad_codes_and_undeclared_vintage_rejected(tmp_path):
    bad = "code,vintage,value\nS01016000,2011,1\nunknown,2011,2\n"
    assert "not valid for their vintage" in _problems(_dataset(tmp_path, {"z.csv": bad}))
    only11 = _dataset(tmp_path / "b", {"z.csv": ZONES}, overrides={"z.csv": {"zone_vintage": "2011"}})
    assert "not declared in zone_vintage" in _problems(only11)


def test_missing_key_column_and_empty_key_rejected(tmp_path):
    assert "not in file" in _problems(_dataset(tmp_path, {"z.csv": "code,value\nS01006506,1\n"},
                                               overrides={"z.csv": {"key": "(code, vintage)"}}))
    assert "empty key values" in _problems(_dataset(tmp_path / "b", {"z.csv": "code,vintage,v\nS01006506,,1\n"}))


def test_missing_listed_file_and_path_traversal_rejected(tmp_path):
    root = _dataset(tmp_path, {"z.csv": ZONES}, extra_rows=[
        {**{c: "x" for c in HEADER}, "file": "gone.csv", "licence": "l", "publish_level": "public_zone",
         "zone_vintage": "2011", "key": "(code, vintage)", "rows": "1", "sha256": "a" * 64},
    ])
    assert "missing" in _problems(root)
    root2 = _dataset(tmp_path / "b", {"z.csv": ZONES}, extra_rows=[{**{c: "x" for c in HEADER}, "file": "../etc.csv"}])
    assert "bad file path" in _problems(root2)


def test_manifest_missing_required_column(tmp_path):
    root = tmp_path / "syn"
    root.mkdir()
    (root / "manifest.csv").write_text("file,owner,rows,sha256\nz.csv,t,1," + "a" * 64 + "\n")
    assert "lacks required column" in _problems(tmp_path)


def test_unlisted_files_ignored(tmp_path, caplog):
    root = _dataset(tmp_path, {"z.csv": ZONES})
    (root / "syn" / "stray.csv").write_text("anything,at,all\n1,2,3\n")
    entries = lp.validate(root)
    assert [e.file for e in entries] == ["z.csv"]
    assert "stray.csv" in caplog.text


def test_extra_columns_tolerated_and_subfolders_supported(tmp_path):
    wide = "code,vintage,value,recent10_count,new_col\nS01006506,2011,1,2,x\n"
    entries = lp.validate(_dataset(tmp_path, {"alt/wide.csv": wide}))
    assert entries[0].table == "syn_alt_wide"
    assert {"recent10_count", "new_col"} <= set(entries[0].frame.columns)


def test_one_bad_file_rejects_the_whole_run(tmp_path):
    root = _dataset(tmp_path, {"good.csv": ZONES, "bad.csv": ZONES}, overrides={"bad.csv": {"rows": "9"}})
    problems = _problems(root)
    assert "bad.csv" in problems and "good.csv" not in problems


def test_cli_exit_codes(tmp_path):
    good = _dataset(tmp_path, {"z.csv": ZONES})
    assert lp.main(["--root", str(good), "--check"]) == 0
    bad = _dataset(tmp_path / "b", {"z.csv": ZONES}, overrides={"z.csv": {"rows": "5"}})
    assert lp.main(["--root", str(bad), "--check"]) == 1


def test_repo_gis_manifest_validates(caplog):
    """The committed data/processed/gis files match their manifest (checksums, rows, keys,
    integer vintages, attribution). dz_detached_plot_bands.csv is internal: skipped, never in the repo."""
    if not (PROCESSED_DIR / "gis" / "manifest.csv").is_file():
        pytest.skip("data/processed/gis not present")
    entries = lp.validate(PROCESSED_DIR, "gis")
    files = {e.file for e in entries}
    assert "dz_residential_land.csv" in files and "dz_detached_plot_bands.csv" not in files
    assert not (PROCESSED_DIR / "gis" / "dz_detached_plot_bands.csv").exists()
    rl = next(e for e in entries if e.file == "dz_residential_land.csv")
    assert rl.publish_level == "public_zone" and rl.key == ("code", "vintage") and len(rl.frame) == 14_368
    assert "Registers of Scotland" in rl.attribution
    assert all(e.attribution for e in entries)
    epc = next(e for e in entries if e.file == "epc_dz_rollup.csv")
    assert "dwellings_total_2025" in epc.frame.columns and "dwellings_nrs_2025" not in epc.frame.columns
    assert "dwellings_flag" in epc.frame.columns
    assert {e.file for e in entries} >= {"epc_dz_rollup.csv", "dz_brma_share.csv", "dz_park_overlay.csv"}
    brma = next(e for e in entries if e.file == "dz_brma_share.csv")
    assert brma.key == ("code", "vintage", "brma_id")
    assert "household_share" in brma.frame.columns  # renamed from dwelling_share by GIS
    for name in GIS_SITE_ROLLUPS:  # SVDLS / HLS rollups (public_zone, footprint_area allocation)
        e = next(e for e in entries if e.file == name)
        assert e.key == ("code", "vintage") and e.publish_level == "public_zone" and len(e.frame) == 14_368
        assert set(e.frame["crosswalk_method"]) == {"footprint_area"}
    assert not any(e.file.endswith(".gpkg") for e in entries)  # svdls_sites/hls_sites gpkg are internal


GIS_SITE_ROLLUPS = ("dz_svdls_rollup.csv", "dz_hls_rollup.csv")


# --------------------------------------------------------------------------- PostGIS

URL = os.getenv("WEALTH_TEST_DATABASE_URL", "")
needs_pg = pytest.mark.skipif(not URL, reason="WEALTH_TEST_DATABASE_URL not set")


@pytest.fixture
def pgconn(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", URL)
    from etl.migrate_to_postgis import apply_schema
    from georgist import db

    conn = db.connect()
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS processed CASCADE")
    conn.commit()
    apply_schema(conn)
    yield conn
    conn.close()


@needs_pg
def test_load_into_postgis_with_key_and_provenance(tmp_path, pgconn):
    root = _dataset(tmp_path, {"m.csv": MULTI}, overrides={"m.csv": {"key": "(code, vintage, brma_id)"}})
    assert lp.load(pgconn, lp.validate(root)) == {"syn/m.csv": 2}
    with pgconn.cursor() as cur:
        cur.execute("SELECT count(*) FROM processed.syn_m")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT key_type, key_columns, licence, publish_level FROM processed.manifest_loads "
                    "WHERE file = 'm.csv'")
        assert cur.fetchone() == ("zone", ["code", "vintage", "brma_id"], "synthetic-test-only", "public_zone")
        cur.execute("""SELECT array_agg(a.attname ORDER BY a.attnum) FROM pg_index i
                       JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                       WHERE i.indrelid = 'processed.syn_m'::regclass AND i.indisprimary""")
        assert cur.fetchone()[0] == ["code", "vintage", "brma_id"]


@needs_pg
def test_failed_validation_leaves_db_untouched(tmp_path, pgconn):
    root = _dataset(tmp_path, {"z.csv": ZONES})
    lp.load(pgconn, lp.validate(root))
    (root / "syn" / "z.csv").write_text(ZONES + "S01006507,2011,9\n")  # bytes change, manifest does not
    with pytest.raises(lp.ManifestError):
        lp.validate(root)
    with pgconn.cursor() as cur:
        cur.execute("SELECT count(*) FROM processed.syn_z")
        assert cur.fetchone()[0] == 2


@needs_pg
def test_boundary_geojson_loads_into_dz_boundaries(tmp_path, pgconn):
    import json

    fc = {"type": "FeatureCollection",
          "crs": {"type": "name", "properties": {"name": "urn:ogc:def:crs:EPSG::27700"}},
          "features": [{"type": "Feature", "properties": {"code": "S01008677", "name": "Synthetic"},
                        "geometry": {"type": "Polygon", "coordinates": [[[325000, 673000], [326000, 673000],
                                                                         [326000, 674000], [325000, 673000]]]}}]}
    root = _dataset(tmp_path, {"dz2011_boundaries.geojson": json.dumps(fc) + "\n"},
                    overrides={"dz2011_boundaries.geojson": {"rows": "1", "zone_vintage": "2011"}})
    with pgconn.cursor() as cur:
        cur.execute("TRUNCATE dz_boundaries")
    pgconn.commit()
    lp.load(pgconn, lp.validate(root))
    with pgconn.cursor() as cur:
        cur.execute("SELECT code, vintage, ST_SRID(geom) FROM dz_boundaries")
        assert cur.fetchall() == [("S01008677", 2011, 27700)]


@needs_pg
def test_crosswalk_loads_with_full_key_as_primary_key(tmp_path, pgconn):
    root = _dataset(tmp_path, {"dz_crosswalk_people.csv": XWALK}, overrides={"dz_crosswalk_people.csv": XW})
    lp.load(pgconn, lp.validate(root))
    with pgconn.cursor() as cur:
        cur.execute("SELECT count(*) FROM processed.syn_dz_crosswalk_people")
        assert cur.fetchone()[0] == 3
        cur.execute("""SELECT array_agg(a.attname ORDER BY a.attnum) FROM pg_index i
                       JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                       WHERE i.indrelid = 'processed.syn_dz_crosswalk_people'::regclass AND i.indisprimary""")
        assert cur.fetchone()[0] == ["dz2011", "dz2022"]
        cur.execute("SELECT key_type FROM processed.manifest_loads WHERE file = 'dz_crosswalk_people.csv'")
        assert cur.fetchone()[0] == "crosswalk"


@needs_pg
def test_repo_gis_dataset_loads_into_postgis(pgconn):
    """The committed GIS folder loads end to end, including the SVDLS and HLS rollups."""
    if not (PROCESSED_DIR / "gis" / "manifest.csv").is_file():
        pytest.skip("data/processed/gis not present")
    loaded = lp.load(pgconn, lp.validate(PROCESSED_DIR, "gis"))
    assert loaded["gis/dz_residential_land.csv"] == 14_368 and "gis/dz_detached_plot_bands.csv" not in loaded
    with pgconn.cursor() as cur:
        for name in GIS_SITE_ROLLUPS:
            table = "processed.gis_" + name.removesuffix(".csv")
            assert loaded[f"gis/{name}"] == 14_368
            cur.execute(f"SELECT vintage, count(*) FROM {table} GROUP BY vintage ORDER BY vintage")
            assert cur.fetchall() == [(2011, 6_976), (2022, 7_392)]
            cur.execute("SELECT key_type, key_columns, publish_level, attribution IS NOT NULL "
                        "FROM processed.manifest_loads WHERE dataset = 'gis' AND file = %s", (name,))
            assert cur.fetchone() == ("zone", ["code", "vintage"], "public_zone", True)
        # Derived display denominators (dz_denominators) with the confidence inputs.
        cur.execute("SELECT count(*), count(residential_land_ha), count(share_res_uprn_in_parcels),"
                    " count(*) FILTER (WHERE mask_too_big_parcel) FROM dz_denominators")
        n, with_ha, with_share, too_big = cur.fetchone()
        assert n == 14_368 and 0 < with_ha < n and with_share > 0 and too_big > 0
        cur.execute("SELECT residential_land_ha FROM dz_denominators WHERE code = 'S01010227' AND vintage = 2011")
        assert cur.fetchone()[0] is None  # zero-dwelling zone: area blank, never 0
        cur.execute("SELECT to_regclass('processed_internal.gis_dz_detached_plot_bands')")
        assert cur.fetchone()[0] is None


# --------------------------------------------------------------------------- Data Zones (real, committed)

DZ_FILES = {"zone_spine.csv", "dz_crosswalk_people.csv", "simd2020v2_dz2011.csv",
            "simd2020v2_access_indicators_dz2011.csv", "simd2020v2_on_dz2022.csv", "dwellings_ct_band.csv",
            "dwellings_by_year.csv", "dwellings_by_year_coverage.csv", "nrs_dwelling_mix_2011_fallback.csv",
            "dz_planning_authority.csv"}


def _need_datazones():
    if not (PROCESSED_DIR / "datazones" / "manifest.csv").is_file():
        pytest.skip("data/processed/datazones not present")


def test_repo_datazones_manifest_validates(datazones_root):
    """Data Zones' 10 CSVs: checksums, rows, integer vintages, attribution, key types incl. the
    (dz2011, dz2022) crosswalk. The committed manifest validates as is."""
    _need_datazones()
    entries = {e.file: e for e in lp.validate(datazones_root, "datazones")}
    assert set(entries) == DZ_FILES and all(e.attribution for e in entries.values())
    assert entries["dz_crosswalk_people.csv"].key_type == "crosswalk"
    assert entries["dwellings_by_year_coverage.csv"].key_type == "vintage"
    assert entries["dwellings_by_year.csv"].key == ("code", "vintage", "count_year")
    assert all(e.typed_schema == "datazones" for e in entries.values())
    assert entries["zone_spine.csv"].qualified_table == "datazones.zone_spine"
    assert set(entries["zone_spine.csv"].frame["vintage"].unique()) == {2011, 2022}


@needs_pg
def test_repo_datazones_loads_into_owner_typed_tables(pgconn, datazones_root):
    _need_datazones()
    entries = lp.validate(datazones_root, "datazones")
    for _ in range(2):  # re-runnable: one TRUNCATE + COPY per run
        loaded = lp.load(pgconn, entries)
    assert len(loaded) == 10
    with pgconn.cursor() as cur:
        cur.execute("SELECT vintage, count(*) FROM datazones.zone_spine GROUP BY 1 ORDER BY 1")
        assert cur.fetchall() == [(2011, 6976), (2022, 7392)]
        cur.execute("SELECT data_type FROM information_schema.columns WHERE table_schema = 'datazones' "
                    "AND table_name = 'dwellings_by_year' AND column_name = 'vintage'")
        assert cur.fetchone()[0] == "smallint"
        # Dwellings on 2022 zones exist only for 2024-2025.
        cur.execute("SELECT min(count_year), max(count_year) FROM datazones.dwellings_by_year WHERE vintage = 2022")
        assert cur.fetchone() == (2024, 2025)
        cur.execute("SELECT key_type, table_name FROM processed.manifest_loads WHERE file = 'dz_crosswalk_people.csv'")
        assert cur.fetchone() == ("crosswalk", "datazones.dz_crosswalk_people")
        # flags is one ';'-separated text column; '' (no flags) stays '' (FORCE_NOT_NULL), never NULL.
        cur.execute("SELECT count(*), count(flags), count(*) FILTER (WHERE flags = '') FROM datazones.zone_spine")
        assert cur.fetchone() == (14368, 14368, 14368 - 7)
        cur.execute("SELECT code FROM datazones.zone_spine"
                    " WHERE 'zero_dwellings' = ANY(string_to_array(flags, ';')) ORDER BY code")
        assert [r[0] for r in cur.fetchall()] == ["S01010206", "S01010226", "S01010227"]
        cur.execute("SELECT count(*) FROM datazones.dwellings_by_year WHERE flags IS NULL")
        assert cur.fetchone()[0] == 0


@needs_pg
def test_typed_load_refuses_owner_schema_drift(tmp_path, pgconn):
    """A datazones CSV whose columns differ from the vendored schema fails; nothing is loaded."""
    text = "code,vintage,count_year,surprise\nS01006506,2011,2025,1\n"
    root = _dataset(tmp_path, {"dwellings_by_year.csv": text}, name="datazones",
                    overrides={"dwellings_by_year.csv": {"key": "(code, vintage, count_year)"}})
    with pytest.raises(lp.ManifestError, match="owner schema drift"):
        lp.load(pgconn, lp.validate(root))


def test_public_files_need_attribution(tmp_path):
    root = _dataset(tmp_path, {"z.csv": ZONES}, overrides={"z.csv": {"attribution": ""}})
    assert "attribution is required for public_zone files" in _problems(root)
    internal = _dataset(tmp_path / "b", {"z.csv": ZONES},
                        overrides={"z.csv": {"attribution": "", "publish_level": "internal"}})
    assert lp.validate(internal, include_internal=True)[0].attribution == ""


def test_held_file_is_skipped_even_if_absent(tmp_path, monkeypatch, caplog):
    monkeypatch.setitem(lp.HELD_FILES, ("syn", "held.csv"), "SYNTHETIC hold")
    root = _dataset(tmp_path, {"z.csv": ZONES}, extra_rows=[
        {**{c: "x" for c in HEADER}, "file": "held.csv", "sha256": "b" * 64}])
    assert [e.file for e in lp.validate(root)] == ["z.csv"] and "SYNTHETIC hold" in caplog.text


def test_valuation_manifest_loads_through_etl(tmp_path, make_valuation_row):
    """Valuation fd03c4b's own manifest writer output validates in etl.load_processed."""
    from georgist import surface_manifest as sm

    rows = [make_valuation_row(250_000, code="S01008677"), make_valuation_row(260_000, code="S01008678")]
    out = tmp_path / "valuation"
    sm.write_outputs(rows, out, source="SYNTHETIC", licence="synthetic-test-only",
                     attribution="SYNTHETIC attribution")
    entries = {e.file: e for e in lp.validate(tmp_path, "valuation", include_internal=True)}
    assert set(entries) == {"surface_rent_dz_internal.csv", "surface_rent_dz_public.csv"}
    pub = entries["surface_rent_dz_public.csv"]
    assert pub.key_type == "zone" and pub.attribution == "SYNTHETIC attribution"
    assert list(pub.frame["vintage"]) == [2011, 2011]
    # Without an attribution, Valuation's public file is refused (required for public_*).
    sm.write_outputs(rows, tmp_path / "v2" / "valuation", source="SYNTHETIC", licence="synthetic-test-only")
    assert "attribution is required" in _problems(tmp_path / "v2")


def test_internal_files_skipped_by_default_and_loaded_only_into_internal_schema(tmp_path, caplog):
    """publish_level=internal rows: skipped (file need not exist) unless include_internal."""
    import logging

    caplog.set_level(logging.INFO)
    secret = {"file": "secret.csv", "owner": "test", "source": "SYNTHETIC", "licence": "synthetic-test-only",
              "publish_level": "internal", "zone_vintage": "2011", "key": "(code, vintage)", "rows": "1",
              "sha256": "0" * 64, "attribution": ""}
    root = _dataset(tmp_path, {"z.csv": ZONES}, extra_rows=[secret])
    entries = lp.validate(root)
    assert [e.file for e in entries] == ["z.csv"] and "internal, not validated" in caplog.text
    with pytest.raises(lp.ManifestError, match="secret.csv"):
        lp.validate(root, include_internal=True)  # asked for, so it must be present and valid


def test_internal_entry_targets_internal_schema(tmp_path):
    root = _dataset(tmp_path, {"z.csv": ZONES}, overrides={"z.csv": {"publish_level": "internal"}})
    (e,) = lp.validate(root, include_internal=True)
    assert e.qualified_table == f"{lp.INTERNAL_SCHEMA}.syn_z"
    assert lp.validate(root) == []
