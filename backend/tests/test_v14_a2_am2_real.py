"""V14-SPEC-A2b T24: real-file reconcile. CI ignores *_real.py (TE X1).

Fails with V14_REAL when inputs are absent (R-COMMON / K17). No pytest.skip.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.build_v14_primary_2023 import main as primary_main

pytestmark = pytest.mark.real

# §10 Pass 2 stub run outputs (labelled for Methods Auditor T24).
REAL_B2 = Path("/workspace/b2q/specA_dryrun/out_probe/b2.json")
REAL_DRC = Path("/workspace/b2q/specA_dryrun/out_probe/drc.json")
CENSUS = Path(
    "/workspace/scotland-rules/v14_run_prep/am2/am2_census_2023_not_scored.csv"
)
# Frozen am2 census sha256 (V14-SPEC-A2b); prefix 6062e2d8.
CENSUS_SHA256 = (
    "6062e2d8b4ce558880e610ee60597dd6ca70853b05903e587d377fe34427e65c"
)


def _require_real(path: Path) -> None:
    if not path.is_file():
        pytest.fail(f"V14_REAL: ERROR: {path}: expected present, got absent")


def test_t24_real_reconcile(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """T24: real b2 + DRC + census -> 730 not_scored; priced 6246."""
    _require_real(REAL_B2)
    _require_real(REAL_DRC)
    _require_real(CENSUS)
    census_sha = hashlib.sha256(CENSUS.read_bytes()).hexdigest()
    assert census_sha.startswith("6062e2d8")
    assert census_sha == CENSUS_SHA256
    primary = tmp_path / "primary_estimates_2023.json"
    builder = tmp_path / "builder_output_2023.json"
    not_scored = tmp_path / "not_scored_2023.json"
    rc = primary_main(
        [
            "--b2-out",
            str(REAL_B2),
            "--drc",
            str(REAL_DRC),
            "--primary-out",
            str(primary),
            "--builder-out",
            str(builder),
            "--not-scored-out",
            str(not_scored),
            "--reconcile-census",
            str(CENSUS),
        ]
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert (
        "not_scored suppressed_price=680 no_sales=0 no_2023_row=44 absent_from_file=6\n"
        in out
    )
    assert "zones=6246\n" in out
    payload = json.loads(not_scored.read_text(encoding="utf-8"))
    assert payload["denominator"] == 6246
    assert payload["counts"] == {
        "suppressed_price": 680,
        "no_sales": 0,
        "no_2023_row": 44,
        "absent_from_file": 6,
    }
    assert len(payload["not_scored"]) == 730
