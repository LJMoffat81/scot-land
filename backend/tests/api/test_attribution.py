"""Attribution from manifest `attribution` columns: every public view carries its datasets' credits."""

import pytest

from georgist import attribution as at
from paths import PROCESSED_DIR



def test_epc_attribution_comes_from_the_manifest_column():
    """GIS manifest `attribution` is the source (no README scraping, no pinned copy)."""
    if not (PROCESSED_DIR / "gis" / "manifest.csv").is_file():
        pytest.skip("data/processed/gis not present")
    at.dataset_attribution.cache_clear()
    a = at.dataset_attribution(*at.EPC_ROLLUP)
    assert a["source"] == "manifest" and a["publish_level"] == "public_zone"
    assert "non-commercial" in a["licence"].lower() and a["use_restriction"] == at.NON_COMMERCIAL
    assert "Royal Mail" in a["attribution"]
    assert not hasattr(at, "PINNED") and not hasattr(at, "_ATTRIBUTION_RE")


def test_missing_manifest_attribution_refused(tmp_path):
    (tmp_path / "gis").mkdir()
    (tmp_path / "gis" / "manifest.csv").write_text(
        "file,licence,publish_level,attribution\nepc_dz_rollup.csv,OGL v3,public_zone,\n")
    with pytest.raises(at.AttributionMissing) as exc:
        at.dataset_attribution(*at.EPC_ROLLUP, root=str(tmp_path))
    assert exc.value.datasets == ["gis/epc_dz_rollup.csv"]
    with pytest.raises(at.AttributionMissing):
        at.dataset_attribution(*at.EPC_ROLLUP, root=str(tmp_path / "nowhere"))


def test_count_datasets_credited_only_when_their_view_is_shown(monkeypatch):
    fake = {ds: {"dataset": "/".join(ds), "licence": "L", "attribution": "A", "publish_level": "public_zone",
                 "source": "manifest"} for ds in (at.EPC_ROLLUP, at.DZ_DWELLINGS, at.DZ_SPINE,
                                                                     at.GIS_RESIDENTIAL_LAND, at.GIS_PLOT_BANDS)}
    monkeypatch.setattr(at, "dataset_attribution", lambda d, f, root=None: fake[(d, f)])
    assert [a["dataset"] for a in at.attributions_for("surface_rent")] == ["gis/epc_dz_rollup.csv",
                                                                          "gis/dz_detached_plot_bands.csv"]
    shown = at.attributions_for("surface_rent", ["per_residential_hectare", "per_dwelling", "per_resident"])
    assert [a["dataset"] for a in shown] == ["gis/epc_dz_rollup.csv", "gis/dz_detached_plot_bands.csv",
                                             "gis/dz_residential_land.csv",
                                             "datazones/dwellings_by_year.csv", "datazones/zone_spine.csv"]


def test_unknown_dataset_refused(tmp_path):
    with pytest.raises(at.AttributionMissing):
        at.dataset_attribution("gis", "nope.csv", root=str(tmp_path))


def test_wealth_payload_carries_epc_attribution_with_surface():
    from georgist.aggregator import build_payload

    surface = {"code": "S01008677", "vintage": 2011, "price_year": 2025, "measured_rent": 1.0,
               "value_tier": "proxy", "quality": "derived", "publish_level": "public_zone",
               "publication_status": "ok"}
    p = build_payload(surface, [], [])
    assert [a["dataset"] for a in p["attributions"]] == ["gis/epc_dz_rollup.csv", "gis/dz_detached_plot_bands.csv"]
    assert "Royal Mail" in p["attributions"][0]["attribution"]
    assert "non-commercial" in p["attributions"][0]["licence"]
    assert build_payload(None, [], [])["attributions"] == []  # no EPC-derived figure, no credit needed


@pytest.mark.parametrize("ds", [at.GIS_RESIDENTIAL_LAND, at.GIS_PLOT_BANDS])
def test_parcel_based_files_carry_ros_credit_under_ogl(ds):
    """Both parcel-based GIS files: RoS credit wording and OGL v3 pass through unchanged."""
    a = at.dataset_attribution(*ds)
    assert a["source"] == "manifest" and a["publish_level"] == "public_zone"
    assert "Registers of Scotland" in a["attribution"] and "OS data" in a["attribution"]
    assert a["licence"].startswith("OGL v3")


def test_wealth_payload_credits_residential_land_when_that_view_is_shown():
    from georgist.aggregator import build_payload

    surface = {"code": "S01008677", "vintage": 2011, "price_year": 2025, "measured_rent": 1000.0,
               "value_tier": "proxy", "quality": "derived", "publish_level": "public_zone",
               "publication_status": "ok"}
    p = build_payload(surface, [], [], denominators={"residential_land_ha": 10.0})
    assert "gis/dz_residential_land.csv" in [a["dataset"] for a in p["attributions"]]
    assert "gis/dz_residential_land.csv" not in [a["dataset"] for a in build_payload(surface, [], [])["attributions"]]
