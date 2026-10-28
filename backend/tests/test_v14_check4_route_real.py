"""CHECK4-ROUTE real-file verification (Q12r + Addendum 5 1e-12 cancellation identity across 6,246 zones).

Fails with V14_REAL when any pinned input file is absent (R-COMMON / K17). No pytest.skip.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from georgist.v14_check4_route import (
    BRMA_NAME_DISCLOSURE,
    PIN_TABLE,
    capitalised_by_zone,
    check_cancellation_identity,
    load_brma_rents_2025,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
BRMA_RENTS_REAL = Path("/workspace/scot-land-valuation/yield_calibration/data/brma_rents_2010_2025.csv")
BRMA_SHARE_REAL = REPO_ROOT / "data" / "processed" / "gis" / "dz_brma_share.csv"
BEDROOM_BANDS_REAL = Path("/workspace/scotland-rules/v13_bedrooms/dz2022_bedroom_bands.csv")
CROSSWALK_REAL = Path("/workspace/scotland-rules/crosswalk/dz2011_dz2022_uprn_weights.csv")
UR6_REAL = Path("/workspace/scotland-rules/ur6/dz2011_urban_rural_6fold_2020.csv")
DRC_REAL = Path("/workspace/scotland-rules/v14_run_prep/out_v14_noprice_0ea06d11/drc.json")
NOT_SCORED_REAL = Path("/workspace/scotland-rules/v14_run_prep/am2/am2_census_2023_not_scored.csv")

DRC_SHA256 = "0a939b46a6f5e4dc51c1d2218218d91eabba78c302c7010bd395354324cf0175"
NOT_SCORED_SHA256 = "6062e2d8b4ce558880e610ee60597dd6ca70853b05903e587d377fe34427e65c"


def _require_real(path: Path, expected_sha: str | None = None) -> Path:
    if not path.is_file():
        pytest.fail(f"V14_REAL: ERROR: {path}: expected present, got absent")
    if expected_sha is not None:
        actual = sha256_file(path)
        if actual != expected_sha:
            pytest.fail(
                f"V14_REAL: REFUSED: {path.name} sha256: expected {expected_sha}, got {actual}"
            )
    return path


@pytest.mark.real
def test_q12r_real_6246_zones_f8_and_addendum5_cancellation() -> None:
    """Q12r: 6,246 complete priced 2023 zones, 18 BRMAs x 4 bands, 1,101 plus4_applied, 1e-12 cancellation."""
    _require_real(BRMA_RENTS_REAL, PIN_TABLE["brma_rents"])
    _require_real(BRMA_SHARE_REAL, PIN_TABLE["brma_share"])
    _require_real(BEDROOM_BANDS_REAL, PIN_TABLE["bedroom_bands"])
    _require_real(CROSSWALK_REAL, PIN_TABLE["crosswalk"])
    _require_real(UR6_REAL, PIN_TABLE["ur6"])
    _require_real(DRC_REAL, DRC_SHA256)
    _require_real(NOT_SCORED_REAL, NOT_SCORED_SHA256)

    rents = load_brma_rents_2025(BRMA_RENTS_REAL, PIN_TABLE)
    assert len(rents) == 18
    assert all(len(v) == 4 for v in rents.values())

    drc_map = json.loads(DRC_REAL.read_text(encoding="utf-8"))
    assert len(drc_map) == 6976
    with NOT_SCORED_REAL.open(encoding="utf-8") as f:
        not_scored = {r["zone"].strip() for r in csv.DictReader(f)}
    assert len(not_scored) == 730

    priced_zones = sorted(set(drc_map.keys()) - not_scored)
    assert len(priced_zones) == 6246

    res = capitalised_by_zone(
        priced_zones,
        brma_rents_path=BRMA_RENTS_REAL,
        brma_share_path=BRMA_SHARE_REAL,
        bedroom_bands_path=BEDROOM_BANDS_REAL,
        crosswalk_path=CROSSWALK_REAL,
        ur6_path=UR6_REAL,
        drc_map=drc_map,
        pins=PIN_TABLE,
    )
    assert res["disclosure"]["brma_name_map"] == BRMA_NAME_DISCLOSURE
    zones_out = res["zones"]
    assert len(zones_out) == 6246

    plus4_count = 0
    for z, zrow in zones_out.items():
        assert zrow["capitalised_property"] > 0.0
        assert zrow["capitalised_property_unadjusted"] > 0.0
        b_sum = sum(zrow["bedroom_shares"].values())
        assert abs(b_sum - 1.0) <= 1e-5
        if zrow["plus4_applied"]:
            plus4_count += 1
            assert zrow["ur6"] in (5, 6)
            assert zrow["capitalised_property"] > zrow["capitalised_property_unadjusted"]
        else:
            assert abs(zrow["capitalised_property"] - zrow["capitalised_property_unadjusted"]) <= 1e-12

        # Verify Addendum 5 building-cost cancellation identity to <= 1e-12 using a synthetic reference price
        # (no real sale price read)
        cancel = check_cancellation_identity(
            250000.0,
            zrow["expected_monthly_rent"],
            zrow["drc"],
            yield_rate=0.045,
        )
        assert cancel["rel_err"] <= 1e-12
        assert abs(cancel["capitalised_land"] - zrow["capitalised_land"]) <= 1e-9

    assert plus4_count == 1101
