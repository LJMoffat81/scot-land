"""Local data locations for the surface-rent module (CI-safe: no machine paths in the repo).

Resolution order for each named directory:
1. environment variable `SCOT_LAND_<NAME>_DIR` (e.g. SCOT_LAND_DATAZONES_DIR);
2. `data/config/surface.local.yaml` (gitignored), key `paths: {<name>: /abs/dir}`;
3. the repo-relative default under `data/external/` (normally absent on CI, so data tests skip).
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_OVERRIDE = REPO_ROOT / "data" / "config" / "surface.local.yaml"
DEFAULTS = {
    "datazones": "data/external/datazones",   # Scot-LAND Data Zones processed tables
    "gis": "data/external/gis",               # Scot-LAND GIS processed outputs
    "raw": "data/external/raw",               # downloaded public sources (RoS, NRS, HPI, SGUR)
    "valuation_out": "data/external/out",     # internal illustrative outputs (never committed)
    # Full OS Open UPRN DZ2011→DZ2022 weights (GIS handoff; not committed).
    # Env: SCOT_LAND_DZ_UPRN_CROSSWALK_DIR. Files: dz2011_dz2022_uprn_weights.csv,
    # dz_crosswalk_zero_uprn.csv (column names dz2011/dz2022 or *_code).
    "dz_uprn_crosswalk": "data/external/dz_crosswalk_uprn",
}


def _local() -> dict:
    if LOCAL_OVERRIDE.exists():
        with LOCAL_OVERRIDE.open(encoding="utf-8") as fh:
            return (yaml.safe_load(fh) or {}).get("paths") or {}
    return {}


def data_dir(name: str) -> Path:
    if name not in DEFAULTS:
        raise KeyError(f"unknown data dir {name!r}; one of {sorted(DEFAULTS)}")
    env = os.environ.get(f"SCOT_LAND_{name.upper()}_DIR")
    if env:
        return Path(env)
    loc = _local().get(name)
    if loc:
        return Path(loc)
    return REPO_ROOT / DEFAULTS[name]


def expand(template: str) -> str:
    """Expand `{datazones_dir}`-style placeholders used in surface.yaml."""
    return template.format(**{f"{k}_dir": str(data_dir(k)) for k in DEFAULTS})
