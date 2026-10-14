"""Official Intermediate Zone names (NRS/SG, OGL v3).

Lookup table: ``data/reference/intermediate_zone_names.csv`` built from
ScotGov/StatisticalUnits IntermediateZoneCent2011 (layer 8) and
IntermediateZoneCent2022 (layer 13). Never invent names.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOOKUP_PATH = REPO_ROOT / "data" / "reference" / "intermediate_zone_names.csv"


@lru_cache(maxsize=1)
def _table() -> dict[tuple[str, int], str]:
    if not LOOKUP_PATH.is_file():
        return {}
    out: dict[tuple[str, int], str] = {}
    with LOOKUP_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            code = (row.get("code") or "").strip()
            name = (row.get("name") or "").strip()
            try:
                vintage = int(row.get("vintage") or "")
            except ValueError:
                continue
            if code and name and vintage in (2011, 2022):
                out[(code, vintage)] = name
    return out


def iz_name(code: str | None, vintage: int | None) -> str | None:
    """Official IZ name for ``(code, vintage)``, or None when unknown."""
    if not code or vintage is None:
        return None
    try:
        vin = int(vintage)
    except (TypeError, ValueError):
        return None
    return _table().get((str(code).strip(), vin))
