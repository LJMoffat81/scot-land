"""Common Good land — linked open registers and honest national gap.

There is no single open national Common Good spatial layer. This module
surfaces verified council register landing pages and documents indicative
spatial sources (Highland licence unconfirmed; Fife OS INSPIRE EUL) without
loading or storing outlines. Place cards never invent an on-point hit.
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


def _spatial_sources_for(code: str | None = None) -> list[dict[str, Any]]:
    out = []
    for source in load_common_good().get("spatial_sources") or []:
        if not isinstance(source, dict):
            continue
        if code and source.get("council_code") != code:
            continue
        out.append(
            {
                "id": source.get("id"),
                "council_code": source.get("council_code"),
                "council_name": source.get("council_name"),
                "status": source.get("status") or "linked",
                "kind": source.get("kind"),
                "label": source.get("label"),
                "catalog_url": source.get("catalog_url") or source.get("metadata_url"),
                "metadata_url": source.get("metadata_url"),
                "open_data_url": source.get("open_data_url"),
                "feature_server": source.get("feature_server"),
                "licence": source.get("licence"),
                "ingest": source.get("ingest", False),
                "vintage_note": source.get("vintage_note"),
                "host_note": source.get("host_note"),
                "feature_count_observed": source.get("feature_count_observed"),
                "gaps": list(source.get("gaps") or []),
            }
        )
    return out


def _spatial_for(code: str | None) -> dict[str, Any] | None:
    rows = _spatial_sources_for(code)
    return rows[0] if rows else None


def place_common_good(council_code: str | None = None) -> dict[str, Any]:
    """Place-card block: link register when known; never claim a spatial hit."""
    register = _register_for(council_code)
    spatial_sources = _spatial_sources_for(council_code)
    spatial = spatial_sources[0] if spatial_sources else None
    if register or spatial:
        status = "linked"
        reason = (
            "Statutory Common Good register / spatial metadata linked for this "
            "council. No national open spatial layer — on-point geometry is not "
            "claimed here. Highland FeatureServers are link-only (licence "
            "unconfirmed); Fife is OS INSPIRE EUL linked only."
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
        "spatial_sources": spatial_sources,
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
    spatial_sources = _spatial_sources_for()
    guidance = national.get("guidance") or {}
    return {
        "ok": True,
        "checked": data.get("checked"),
        "status": national.get("status") or "linked",
        "national_gap": national.get("gap") or NATIONAL_GAP,
        "note": (
            f"{len(registers)} of 32 councils have a verified open Common Good "
            "register or spatial-metadata link in this file. There is no national "
            "open polygon layer. Highland FeatureServers are link-only (licence "
            "unconfirmed — not OGL). Fife indicative titles are linked under OS "
            "INSPIRE EUL and are not mirrored here. Spatial Hub assets stay "
            "login-gated."
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
                "No national open Common Good WMS/WFS under a confirmed "
                "redistributable open licence. Highland FeatureServers are "
                "link-only (licence unconfirmed); Fife FeatureServer is linked "
                "only under OS INSPIRE EUL — geometries are not loaded or stored."
            ),
        },
    }


def catalog_layer() -> dict[str, Any]:
    payload = common_good_payload()
    highland = next(
        (
            s
            for s in payload.get("spatial_sources") or []
            if s.get("council_code") == "S12000017"
        ),
        None,
    )
    fife = next(
        (
            s
            for s in payload.get("spatial_sources") or []
            if s.get("council_code") == "S12000047"
        ),
        None,
    )
    source_url = (
        (highland or {}).get("catalog_url")
        or (fife or {}).get("metadata_url")
        or (fife or {}).get("catalog_url")
        or (payload.get("guidance") or {}).get("url")
    )
    return {
        "id": "common_good",
        "group": "ownership",
        "status": "linked",
        "label": "Common Good registers",
        "description": (
            f"{payload['register_count']} verified council register / metadata "
            "links. No national open spatial layer. Highland FeatureServers are "
            "link-only (licence unconfirmed — not OGL). Fife indicative titles "
            "under OS INSPIRE EUL — linked, not mirrored. Ownership-context "
            "(who/outline) — not a LayersPanel toggle, not a rent row."
        ),
        "endpoint": "/api/common-good.json",
        "licence": (
            "unconfirmed (Highland FeatureServers linked only); "
            "OS Public Sector End User Licence - INSPIRE (Fife linked only)"
        ),
        "source_url": source_url,
        "gaps": payload.get("gaps") or [],
        "ledger_role": "ownership-context",
        "ledger_row": None,
        "ui_surface": "ledger",
    }
