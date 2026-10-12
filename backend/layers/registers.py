"""Per-council official register landing pages.

Source file: data/config/registers.yaml
Only council-specific URLs that were HTTP 200 on an official domain are
stored as scope=council. Other councils fall back to national ePlanning.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
REGISTERS_PATH = REPO_ROOT / "data" / "config" / "registers.yaml"

NATIONAL_PLANNING_NOTE = (
    "Council-specific public-access page not confirmed in this file. "
    "Use national ePlanning or Tell Me Scotland."
)


@lru_cache(maxsize=1)
def load_registers() -> dict[str, Any]:
    with REGISTERS_PATH.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    councils = payload.get("councils") or {}
    if len(councils) != 32:
        raise ValueError(
            f"{REGISTERS_PATH} must list 32 councils, found {len(councils)}"
        )
    return payload


def _planning_link(national: dict[str, Any], council: dict[str, Any]) -> dict[str, Any]:
    planning = council.get("planning") or {}
    eplanning = (national.get("eplanning") or {})
    tellme = (national.get("tellme_scotland") or {})
    if planning.get("scope") == "council" and planning.get("url"):
        return {
            "scope": "council",
            "url": planning["url"],
            "label": "View planning applications",
            "national_eplanning": eplanning.get("url"),
            "tellme_scotland": tellme.get("url"),
        }
    return {
        "scope": "national",
        "url": eplanning.get("url"),
        "label": eplanning.get("label") or "ePlanning Scotland",
        "note": NATIONAL_PLANNING_NOTE,
        "tellme_scotland": tellme.get("url"),
    }


def registers_for_council(code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    data = load_registers()
    council = (data.get("councils") or {}).get(code)
    if not council:
        return None
    national = data.get("national") or {}
    land_map = council.get("land_map")
    return {
        "code": code,
        "name": council.get("name"),
        "planning": _planning_link(national, council),
        "common_good": {
            "url": None,
            "note": "No single open national Common Good spatial file. Statutory LA register.",
        },
        "cat": {
            "url": (national.get("spatial_hub_cat") or {}).get("url"),
            "label": "Spatial Hub CAT register",
            "note": (national.get("spatial_hub_cat") or {}).get("note"),
        },
        "land_map": land_map,
        "scotlis": national.get("scotlis"),
        "la_ownership": {
            "status": "gap",
            "url": (national.get("spatial_hub_la_own") or {}).get("url"),
            "note": (national.get("spatial_hub_la_own") or {}).get("note"),
        },
    }


def registers_payload() -> dict[str, Any]:
    data = load_registers()
    national = data.get("national") or {}
    councils = []
    for code, council in sorted((data.get("councils") or {}).items()):
        councils.append(
            {
                "code": code,
                "name": council.get("name"),
                "planning": _planning_link(national, council),
                "land_map": council.get("land_map"),
            }
        )
    council_specific = sum(
        1 for row in councils if (row.get("planning") or {}).get("scope") == "council"
    )
    return {
        "ok": True,
        "checked": "2026-09-01",
        "note": (
            f"{council_specific} of 32 councils have a verified official planning "
            "view page in this file. Others use national ePlanning. "
            "Common Good has no national spatial file. Spatial Hub CAT/assets "
            "require login. LA ownership is not open."
        ),
        "national": national,
        "councils": councils,
        "council_specific_planning": council_specific,
        "council_count": len(councils),
    }
