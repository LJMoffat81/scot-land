"""Common Good land — OGL PostGIS overlay + linked registers.

OGL council open layers (Highland sites/buildings) load into PostGIS via
``etl.ingest_common_good``. Non-OGL sources (Fife OS INSPIRE EUL) stay linked
only — the former Fife-only catalog row is folded into this layer. Place cards
report on-point hits only from PostGIS, never invented.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from layers.common_good_spatial import is_loaded, query_point, row_count, source_meta

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "data" / "config" / "common_good.yaml"

NATIONAL_GAP = (
    "No single national Common Good polygon layer — coverage is council-by-council."
)


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
                "ingest": source.get("ingest", True),
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


def place_common_good(
    council_code: str | None = None,
    *,
    lat: float | None = None,
    lng: float | None = None,
) -> dict[str, Any]:
    """Place-card block: PostGIS hit when loaded; else linked register / gap."""
    register = _register_for(council_code)
    spatial_sources = _spatial_sources_for(council_code)
    spatial = spatial_sources[0] if spatial_sources else None
    point: dict[str, Any] | None = None
    if lat is not None and lng is not None:
        point = query_point(lat, lng)

    on_point = bool(point and point.get("ok") and point.get("intersects"))
    loaded = is_loaded()
    if on_point or loaded or register or spatial:
        status = "live" if loaded else "linked"
        reason = (
            "OGL Common Good polygons loaded in PostGIS (partial council coverage)."
            if loaded
            else (
                "Statutory Common Good register / spatial metadata linked for this "
                "council. PostGIS overlay not loaded yet — on-point geometry is not "
                "claimed without ingest."
            )
        )
    else:
        status = "gap"
        reason = (
            f"{NATIONAL_GAP} No verified open register URL for this council "
            "in data/config/common_good.yaml."
        )
    return {
        "status": status,
        "on_this_point": on_point if point and point.get("ok") else None,
        "sites": (point or {}).get("sites") or [],
        "reason": reason,
        "register": register,
        "spatial": spatial,
        "spatial_sources": spatial_sources,
        "national_gap": NATIONAL_GAP,
        "postgis_loaded": loaded,
        "source": (point or {}).get("source") or source_meta().get("attribution"),
    }


def common_good_payload() -> dict[str, Any]:
    """Public JSON: registers, OGL spatial sources, PostGIS load status."""
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
    ogl_sources = [
        s for s in spatial_sources if str(s.get("licence") or "").upper().startswith("OGL")
    ]
    guidance = national.get("guidance") or {}
    meta = source_meta()
    loaded = is_loaded()
    return {
        "ok": True,
        "checked": data.get("checked"),
        "status": "live" if loaded else (national.get("status") or "linked"),
        "national_gap": national.get("gap") or NATIONAL_GAP,
        "note": (
            f"{len(registers)} of 32 councils have a verified open Common Good "
            "register or spatial-metadata link. OGL Highland sites/buildings load "
            "into PostGIS; Fife OS INSPIRE EUL titles are linked only (former "
            "Fife-only catalog row folded in). Spatial Hub assets stay login-gated."
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
        "ogl_spatial_source_count": len(ogl_sources),
        "gaps": list(data.get("gaps") or []),
        "map_overlay": {
            "status": "live" if loaded else "linked",
            "endpoint": "/layers/open/common-good",
            "postgis_table": "common_good_sites",
            "postgis_rows": row_count() if loaded else 0,
            "licence": meta.get("licence"),
            "source_url": meta.get("source_url"),
            "reason": (
                None
                if loaded
                else (
                    "PostGIS common_good_sites empty — run "
                    "`python -m etl.ingest_common_good --from-config` "
                    "(OGL sources only). API returns 503 until loaded."
                )
            ),
        },
    }


def catalog_layer() -> dict[str, Any]:
    payload = common_good_payload()
    meta = source_meta()
    ogl = [
        s
        for s in payload.get("spatial_sources") or []
        if str(s.get("licence") or "").upper().startswith("OGL")
    ]
    catalog_url = (ogl[0].get("catalog_url") if ogl else None) or meta.get("source_url")
    return {
        "id": "common_good",
        "group": "ownership",
        "status": "live",
        "label": "Common Good land",
        "description": (
            "OGL council open layers in PostGIS (Highland sites/buildings). "
            f"{payload['register_count']} verified register links. "
            "Fife indicative titles folded in as linked OS INSPIRE EUL — not ingested. "
            "Ownership-context (who/outline) — not a LayersPanel toggle, not a rent row. "
            "Partial coverage; bbox API returns 503 when PostGIS unloaded."
        ),
        "endpoint": "/layers/open/common-good",
        "stats_endpoint": "/api/common-good.json",
        "licence": meta.get("licence"),
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
        ),
        "source_url": catalog_url,
        "minzoom": 8,
        "gaps": payload.get("gaps") or [],
        "ledger_role": "ownership-context",
        "ledger_row": None,
        "ui_surface": "ledger",
    }
