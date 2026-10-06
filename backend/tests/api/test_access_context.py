"""GIS access context (dz_access.csv): passed through beside the figures, never used in them.

The real committed GIS file is read for the flag vocabulary and attribution; payload rows are SYNTHETIC.
"""

import csv
from collections import Counter

from georgist import attribution as at
from georgist.aggregator import access_context, build_payload
from paths import PROCESSED_DIR

SURFACE = {"code": "S01010206", "vintage": 2011, "price_year": 2025, "measured_rent": 100_000.0,
           "commons_class": "surface_residential", "value_tier": "proxy", "quality": "derived",
           "crosswalk_method": "none", "source_id": "ros_dz2011", "licence": "OGL-3.0",
           "publish_level": "public_zone"}
ACCESS = {"job_access": 1234.5, "log_job_access": 7.1185, "road_km_nearest_luc": 88.2, "nearest_luc": "Glasgow",
          "distance_method": "euclid_x1.3", "job_access_method": "network+euclid_x1.3",
          "network_component": "island_7", "flags": "off_mainland_network;luc_distance_euclid_x1.3"}
KNOWN_FLAGS = {"off_mainland_network", "luc_distance_euclid_x1.3", "job_access_partly_euclid_x1.3",
               "nearest_emp_point_gt_5km", "snap_gt_1km", "snap_skipped_tiny_component"}


def test_access_flags_and_attribution_pass_through():
    a = build_payload(SURFACE, [], [], access=ACCESS)["context"]["access"]
    assert a["status"] == "ok"
    assert a["flags"] == ["off_mainland_network", "luc_distance_euclid_x1.3"]  # verbatim, in order
    assert a["distance_method"] == "euclid_x1.3" and a["job_access"] == 1234.5
    assert [c["dataset"] for c in a["attributions"]] == ["gis/dz_access.csv"]
    assert a["source_year"] == 2023 and "OS data" in a["attributions"][0]["attribution"]


def test_access_context_never_changes_figures():
    base = build_payload(SURFACE, [], [])
    with_access = build_payload(SURFACE, [], [], access=ACCESS)
    assert with_access["totals_by_tier"] == base["totals_by_tier"]
    assert with_access["display"] == base["display"] and with_access["components"] == base["components"]
    assert with_access["attributions"] == base["attributions"]  # credit sits with the context block


def test_access_context_statuses():
    assert access_context(False)["status"] == "not_loaded"
    assert access_context(None)["status"] == "zone_missing"
    assert access_context({**ACCESS, "flags": ""})["flags"] == []
    assert build_payload(None, [], [])["context"]["access"]["status"] == "not_loaded"


def test_real_gis_access_flags_are_known_and_emp_flag_is_2022_only():
    with open(PROCESSED_DIR / "gis" / "dz_access.csv", newline="") as fh:
        rows = list(csv.DictReader(fh))
    flags = Counter(f for r in rows for f in r["flags"].split(";") if f)
    assert set(flags) <= KNOWN_FLAGS
    assert {r["vintage"] for r in rows if "nearest_emp_point_gt_5km" in r["flags"]} == {"2022"}
    assert all(("euclid_x1.3" in r["flags"]) == (r["distance_method"] == "euclid_x1.3"
                                                   or r["job_access_method"] == "network+euclid_x1.3")
               for r in rows)


def test_access_attribution_comes_from_the_manifest():
    a = at.context_attributions("access")[0]
    assert a["source"] == "manifest" and a["publish_level"] == "public_zone" and a["source_year"] == 2023
    assert "Office for National Statistics" in a["attribution"] and a["licence"].startswith("OGL v3")
