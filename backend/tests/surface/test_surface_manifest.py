"""Output files + GIS-format manifest, on SYNTHETIC rows."""

import csv
import hashlib
import pytest

from georgist import surface_manifest as sm
from georgist import surface_rent as sr

from .test_surface_output import _row


def test_manifest_mirrors_gis_format(cfg, band, tmp_path):
    breach = sr.reconciliation_check(module_rents={"surface": (10**9,) * 3}, observed_total_value_gbp=1.0, gross_yield_value=0.05)
    rows = [_row(cfg, band), _row(cfg, band, code="S01013402", reconciliation=breach)]
    entries = sm.write_outputs(rows, tmp_path, source="SYNTHETIC", licence="synthetic-test-only")
    with (tmp_path / "manifest.csv").open() as f:
        reader = csv.DictReader(f)
        assert tuple(reader.fieldnames) == sm.MANIFEST_COLUMNS
        man = {r["file"]: r for r in reader}
    assert man["surface_rent_dz_internal.csv"]["rows"] == "2" and man["surface_rent_dz_internal.csv"]["publish_level"] == "internal"
    pub = man["surface_rent_dz_public.csv"]
    assert pub["rows"] == "1" and pub["publish_level"] == "public_zone" and pub["key"] == "(code, vintage)"
    assert pub["zone_vintage"] == "DZ2011" and pub["owner"] == "valuation"
    for e in entries:
        assert hashlib.sha256((tmp_path / e["file"]).read_bytes()).hexdigest() == man[e["file"]]["sha256"]
    header = (tmp_path / "surface_rent_dz_public.csv").read_text().splitlines()[0].split(",")
    assert not set(header) & set(sr.INTERNAL_ONLY_COLUMNS)


def test_epc_rows_carry_licence_and_attribution(tmp_path, cfg, band):
    from .test_surface_output import _row
    with pytest.raises(ValueError):  # EPC-built row without the rollup licence text
        _row(cfg, band, extra_tags=("epc_all_time",))
    row = _row(cfg, band, extra_tags=("epc_all_time",), licence=sm.epc_licence("synthetic-test-only"))
    assert "Royal Mail" in row["licence"] and row["code"] and row["vintage"] == 2011
    sm.write_outputs([row], tmp_path, source="SYNTHETIC", licence="synthetic-test-only")
    with (tmp_path / "manifest.csv").open() as f:
        man = list(csv.DictReader(f))
    for m in man:
        assert sm.EPC_ROLLUP_LICENCE in m["licence"]
        for credit in ("Open Government Licence", "NRS data", "PAF", "Royal Mail", "OS data"):
            assert credit in m["attribution"]
        assert m["key"] == "(code, vintage)"
    header = (tmp_path / "surface_rent_dz_internal.csv").read_text().splitlines()[0].split(",")
    assert header[:2] == ["code", "vintage"] and "zone_code" not in header


def test_declared_key_must_be_real_columns(tmp_path):
    with pytest.raises(ValueError):
        sm.write_internal_table([{"zone_code": "S01013401"}], tmp_path, name="x_SYNTHETIC.csv", columns=["zone_code"],
                                source="SYNTHETIC", licence="synthetic")
