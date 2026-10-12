"""Common Good land — linked open registers and honest national gap.

There is no single open national Common Good spatial layer. This module
surfaces verified council register landing pages and documents the one
known indicative spatial source (Fife) without redistributing OS INSPIRE
EUL geometries. Place cards never invent an on-point hit.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "data" / "config" / "common_good.yaml"

NATIONAL_GAP = "No single open national Common Good spatial layer."


@lru_cache(maxsize=1)
def load_common_good() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{CONFIG_PATH} must be a mapping")
    return payload


def _register_for(code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    registers = load_common_good().get("registers") or {}
    row = registers.get(code)
    if not isinstance(row, dict) or not row.get("url"):
        return None
    return {
        "council_code": code,
        "name": row.get("name"),
        "url": row["url"],
        "label": row.get("label") or "Common Good register",
        "kind": row.get("kind") or "register",
        "note": row.get("note"),
    }


def _spatial_for(code: str | None) -> dict[str, Any] | None:
    if not code:
        return None
    for source in load_common_good().get("spatial_sources") or []:
        if not isinstance(source, dict):
            continue
        if source.get("council_code") != code:
            continue
        return {
            "id": source.get("id"),
            "council_code": code,
            "council_name": source.get("council_name"),
            "status": source.get("status") or "linked",
            "kind": source.get("kind"),
            "label": source.get("label"),
            "metadata_url": source.get("metadata_url"),
            "feature_server": source.get("feature_server"),
            "licence": source.get("licence"),
            "vintage_note": source.get("vintage_note"),
            "host_note": source.get("host_note"),
            "feature_count_observed": source.get("feature_count_observed"),
            "gaps": list(source.get("gaps") or []),
        }
    return None


def place_common_good(council_code: str | None = None) -> dict[str, Any]:
    """Place-card block: link register when known; never claim a spatial hit."""
    register = _register_for(council_code)
    spatial = _spatial_for(council_code)
    if register or spatial:
        status = "linked"
        reason = (
            "Statutory Common Good register / spatial metadata linked for this "
            "council. No national open spatial layer — on-point geometry is not "
            "claimed here."
        )
    else:
        status = "gap"
        reason = (
            f"{NATIONAL_GAP} No verified open register URL for this council "
            "in data/config/common_good.yaml."
        )
    return {
        "status": status,
        "on_this_point": None,
        "reason": reason,
        "register": register,
        "spatial": spatial,
        "national_gap": NATIONAL_GAP,
    }


def common_good_payload() -> dict[str, Any]:
    """Public JSON describing what is openly linkable and what remains a gap."""
    data = load_common_good()
    national = data.get("national") or {}
    registers = []
    for code, row in sorted((data.get("registers") or {}).items()):
        if not isinstance(row, dict) or not row.get("url"):
            continue
        registers.append(
            {
                "council_code": code,
                "name": row.get("name"),
                "url": row["url"],
                "label": row.get("label"),
                "kind": row.get("kind") or "register",
                "note": row.get("note"),
            }
        )
    spatial_sources = []
    for source in data.get("spatial_sources") or []:
        if not isinstance(source, dict):
            continue
        spatial_sources.append(
            {
                "id": source.get("id"),
                "council_code": source.get("council_code"),
                "council_name": source.get("council_name"),
                "status": source.get("status") or "linked",
                "kind": source.get("kind"),
                "label": source.get("label"),
                "metadata_url": source.get("metadata_url"),
                "feature_server": source.get("feature_server"),
                "licence": source.get("licence"),
                "vintage_note": source.get("vintage_note"),
                "host_note": source.get("host_note"),
                "feature_count_observed": source.get("feature_count_observed"),
                "gaps": list(source.get("gaps") or []),
            }
        )
    guidance = national.get("guidance") or {}
    return {
        "ok": True,
        "checked": data.get("checked"),
        "status": national.get("status") or "linked",
        "national_gap": national.get("gap") or NATIONAL_GAP,
        "note": (
            f"{len(registers)} of 32 councils have a verified open Common Good "
            "register or spatial-metadata link in this file. There is no national "
            "open polygon layer. Fife indicative titles are linked under OS INSPIRE "
            "EUL and are not mirrored here. Spatial Hub assets stay login-gated."
        ),
        "guidance": {
            "url": guidance.get("url"),
            "label": guidance.get("label"),
            "note": guidance.get("note"),
        },
        "registers": registers,
        "register_count": len(registers),
        "council_count": 32,
        "spatial_sources": spatial_sources,
        "gaps": list(data.get("gaps") or []),
        "map_overlay": {
            "status": "gap",
            "reason": (
                "No national open Common Good WMS/WFS under a redistributable "
                "open licence. Fife FeatureServer is linked only; TLS was expired "
                "when checked and geometries are not proxied (OS INSPIRE EUL)."
            ),
        },
    }


def catalog_layer() -> dict[str, Any]:
    payload = common_good_payload()
    fife = next(
        (
            s
            for s in payload.get("spatial_sources") or []
            if s.get("council_code") == "S12000047"
        ),
        None,
    )
    return {
        "id": "common_good",
        "group": "ownership",
        "status": "linked",
        "label": "Common Good registers",
        "description": (
            f"{payload['register_count']} verified council register / metadata "
            "links. No national open spatial layer. Fife indicative Common Good "
            "Titles exist under OS INSPIRE EUL — linked, not mirrored."
        ),
        "endpoint": "/api/common-good.json",
        "source_url": (fife or {}).get("metadata_url")
        or (payload.get("guidance") or {}).get("url"),
        "gaps": payload.get("gaps") or [],
    }
