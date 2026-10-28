"""V15-CHECK4-SCORE real-file verification (S9r): live recomputation matches committed report.json."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from georgist.surface_paths import REPO_ROOT
from georgist.v14_check4_route import (
    PIN_TABLE,
    check_cancellation_identity,
    score_check4_non_gbp,
    sha256_file,
)
from scripts.build_v14_check_sources import build_check4_f8

COMMITTED_REPORT = REPO_ROOT / "data" / "processed" / "methods_code_1" / "v15_check4_score" / "report.json"
BRMA_RENTS_REAL = Path("/workspace/scot-land-valuation/yield_calibration/data/brma_rents_2010_2025.csv")
BRMA_SHARE_REAL = REPO_ROOT / "data" / "processed" / "gis" / "dz_brma_share.csv"
BEDROOM_BANDS_REAL = Path("/workspace/scotland-rules/v13_bedrooms/dz2022_bedroom_bands.csv")
CROSSWALK_REAL = Path("/workspace/scotland-rules/crosswalk/dz2011_dz2022_uprn_weights.csv")
UR6_REAL = Path("/workspace/scotland-rules/ur6/dz2011_urban_rural_6fold_2020.csv")
DRC_REAL = Path("/workspace/scotland-rules/v14_run_prep/out_v14_noprice_0ea06d11/drc.json")
NOT_SCORED_REAL = Path("/workspace/scotland-rules/v14_run_prep/am2/am2_census_2023_not_scored.csv")
PRIMARY_REAL = Path("/workspace/b2q/specA_dryrun/out_probe/primary_estimates_2023.json")


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
def test_s9r_real_check4_score_matches_committed_report() -> None:
    """S9r: live F8 + DRC Check 4 evaluation on the 6,246 priced 2023 zones matches committed report.json."""
    _require_real(COMMITTED_REPORT)
    committed = json.loads(COMMITTED_REPORT.read_text(encoding="utf-8"))
    pins = committed["pins"]

    _require_real(BRMA_RENTS_REAL, PIN_TABLE["brma_rents"])
    _require_real(BRMA_SHARE_REAL, PIN_TABLE["brma_share"])
    _require_real(BEDROOM_BANDS_REAL, PIN_TABLE["bedroom_bands"])
    _require_real(CROSSWALK_REAL, PIN_TABLE["crosswalk"])
    _require_real(UR6_REAL, PIN_TABLE["ur6"])
    _require_real(DRC_REAL, pins["drc_json"])
    _require_real(NOT_SCORED_REAL, pins["not_scored_2023"])
    _require_real(PRIMARY_REAL, pins["primary_estimates_2023"])

    ur6_map: dict[str, int] = {}
    with UR6_REAL.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            ur6_map[row["code"].strip()] = int(row["ur6_class"])

    prim_rows = json.loads(PRIMARY_REAL.read_text(encoding="utf-8"))["zones"]
    zones = [r["zone"] for r in prim_rows]
    drc_map = json.loads(DRC_REAL.read_text(encoding="utf-8"))

    f8_payload = build_check4_f8(
        zones,
        brma_rents=BRMA_RENTS_REAL,
        brma_share=BRMA_SHARE_REAL,
        bedroom_bands=BEDROOM_BANDS_REAL,
        crosswalk=CROSSWALK_REAL,
        ur6=UR6_REAL,
        drc_map=drc_map,
    )
    cap_map = {r["zone"]: r for r in f8_payload["zones"]}
    assert sum(1 for r in f8_payload["zones"] if r["plus4_applied"]) == committed["coverage"]["plus4_applied_zones"]

    prim_zones = []
    for r in prim_rows:
        z = r["zone"]
        unavail = bool(r.get("unavailable") or r.get("model_failure"))
        exp_rent = float(cap_map[z]["capitalised_property"]) * 0.045 / 12.0
        cancel = check_cancellation_identity(250000.0, exp_rent, float(cap_map[z]["drc"]), yield_rate=0.045)
        assert cancel["rel_err"] <= 1e-12
        prim_zones.append(
            {
                "zone": z,
                "ur6": ur6_map[z],
                "unavailable": unavail,
                "model_failure": bool(r.get("model_failure", False)),
                "residual_land": 0.0 if unavail else float(r["land_per_home"]),
                "capitalised_land": float(cap_map[z]["capitalised_land"]),
            }
        )

    live_primary = score_check4_non_gbp(prim_zones)
    assert live_primary == committed["primary"]
