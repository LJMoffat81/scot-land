"""Crofting Register (RoC) and common grazings — OGL tabular + honest spatial gap.

Open Government Licence v3.0 sources from the Crofting Commission open-data
page (Parishes, Holdings/Crofts, Grazings). Individuals are not mirrored.

National map polygons for crofts and common grazings live on the Registers of
Scotland Crofting Register map search — public to view, not published as an
OGL redistributable WMS/WFS for this portal. Spatial Hub “Decrofted Areas”
is Restricted (login). Local council republishes (e.g. Argyll & Bute) are not
national and are not proxied here.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from georgist import db

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / "data" / "config" / "crofting.yaml"

SPATIAL_GAP = (
    "No national open (OGL) polygon layer for croft or common-grazing extents. "
    "Authoritative map extents are on the RoS Crofting Register search; "
    "Spatial Hub Decrofted Areas is Restricted — not mirrored."
)


@lru_cache(maxsize=1)
def load_crofting_config() -> dict[str, Any]:
    with CONFIG_PATH.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        raise ValueError(f"{CONFIG_PATH} must be a mapping")
    return payload


def _cfg() -> dict[str, Any]:
    return load_crofting_config()


def _table_counts() -> dict[str, int | None]:
    """Row counts when PostGIS is loaded; None when unavailable / empty schema."""
    out: dict[str, int | None] = {
        "parishes": None,
        "holdings": None,
        "grazings": None,
    }
    try:
        conn = db.connect()
    except db.DatabaseUnavailable:
        return out
    try:
        with conn.cursor() as cur:
            for key, table in (
                ("parishes", "croft_parishes"),
                ("holdings", "croft_holdings"),
                ("grazings", "common_grazings"),
            ):
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {table}")
                    out[key] = int(cur.fetchone()[0])
                except Exception:
                    conn.rollback()
                    out[key] = None
    finally:
        conn.close()
    return out


def _ingest_meta() -> list[dict[str, Any]]:
    try:
        conn = db.connect()
    except db.DatabaseUnavailable:
        return []
    try:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    SELECT dataset, source_url, licence, retrieved_at, row_count, sha256
                    FROM crofting_ingest_meta
                    ORDER BY dataset
                    """
                )
            except Exception:
                conn.rollback()
                return []
            rows = cur.fetchall()
    finally:
        conn.close()
    meta = []
    for dataset, source_url, licence, retrieved_at, row_count, sha256 in rows:
        meta.append(
            {
                "dataset": dataset,
                "source_url": source_url,
                "licence": licence,
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "retrieved_at": retrieved_at.isoformat() if retrieved_at else None,
                "row_count": row_count,
                "sha256": sha256,
            }
        )
    return meta


def crofting_payload() -> dict[str, Any]:
    """Public JSON: OGL register status, PostGIS load state, spatial gaps."""
    cfg = _cfg()
    national = cfg.get("national") or {}
    sources = cfg.get("sources") or {}
    counts = _table_counts()
    loaded = all(isinstance(counts[k], int) and counts[k] > 0 for k in ("holdings", "grazings"))
    return {
        "ok": True,
        "checked": cfg.get("checked"),
        "status": "linked",
        "licence": "OGL-3.0",
        "licence_url": national.get("licence_url")
        or "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        "open_data_url": national.get("open_data_url")
        or "https://www.crofting.scotland.gov.uk/open-data/",
        "ros_register_url": national.get("ros_register_url")
        or "https://www.crofts.ros.gov.uk/register/search",
        "ros_about_url": national.get("ros_about_url")
        or "https://www.ros.gov.uk/our-registers/crofting-register",
        "attribution": national.get("attribution")
        or (
            "Contains Crofting Commission Register of Crofts data licensed under "
            "the Open Government Licence v3.0."
        ),
        "note": (
            "Crofting Commission publishes Parishes, Holdings (crofts) and Grazings "
            "as OGL CSV downloads. This API loads those tables into PostGIS for "
            "Georgist / Valuation joins. Individuals are not ingested. Map extents "
            "are not redrawn here — see spatial_gap."
        ),
        "postgis": {
            "loaded": loaded,
            "counts": counts,
            "ingest": "python -m etl.ingest_crofting --download",
            "tables": ["croft_parishes", "croft_holdings", "common_grazings"],
            "meta": _ingest_meta(),
        },
        "sources": {
            "parishes": sources.get("parishes") or {},
            "holdings": sources.get("holdings") or {},
            "grazings": sources.get("grazings") or {},
        },
        "not_ingested": list(cfg.get("not_ingested") or ["individuals"]),
        "spatial_gap": SPATIAL_GAP,
        "gaps": list(cfg.get("gaps") or []),
        "rejected_alternatives": list(cfg.get("rejected_alternatives") or []),
        "map_overlay": {
            "status": "gap",
            "reason": SPATIAL_GAP,
        },
    }


def place_crofting(_council_code: str | None = None) -> dict[str, Any]:
    """Place-card block: link OGL register + RoS map; never invent on-point geometry."""
    cfg = _cfg()
    national = cfg.get("national") or {}
    counts = _table_counts()
    return {
        "status": "linked",
        "on_this_point": None,
        "reason": (
            "OGL Register of Crofts / Grazings tables are linked (and loaded into "
            "PostGIS when ingested). National croft and common-grazing polygons "
            "are not openly redistributable here — confirm extents on the RoS "
            "Crofting Register map."
        ),
        "licence": "OGL-3.0",
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
        "open_data_url": national.get("open_data_url"),
        "ros_register_url": national.get("ros_register_url"),
        "postgis_counts": counts,
        "spatial_gap": SPATIAL_GAP,
    }


def catalog_crofting_register() -> dict[str, Any]:
    payload = crofting_payload()
    holdings = (payload.get("sources") or {}).get("holdings") or {}
    return {
        "id": "crofting_register",
        "group": "ownership",
        "status": "linked",
        "label": "Crofting Register (RoC)",
        "description": (
            "Crofting Commission Register of Crofts — OGL-3.0 lists only "
            "(holdings CSV → PostGIS). No boundary polygons. Never ingest List "
            "of Individuals. Constraint (Limits use (not a money value), no rent "
            "row) — changes best use only. Map extents: RoS Crofting Register "
            "search (not OGL redistributable). No LayersPanel toggle."
        ),
        "endpoint": "/api/crofting.json",
        "licence": "OGL-3.0",
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
        "source_url": holdings.get("source_url") or payload.get("open_data_url"),
        "gaps": payload.get("gaps") or [],
        "lists_only": True,
        "boundaries": False,
        "ledger_role": "constraint",
        "ledger_row": None,
        "ui_surface": "ledger",
    }


def catalog_common_grazings() -> dict[str, Any]:
    payload = crofting_payload()
    grazings = (payload.get("sources") or {}).get("grazings") or {}
    return {
        "id": "common_grazings",
        "group": "ownership",
        "status": "linked",
        "label": "Common grazings",
        "description": (
            "Crofting Commission List of Grazings — OGL-3.0 lists only "
            "(extent ha → PostGIS). No national OGL polygon overlay; RoS "
            "Crofting Register map holds definitive common-land extents. "
            "Constraint (Limits use (not a money value), no rent row). "
            "No LayersPanel toggle."
        ),
        "endpoint": "/api/crofting.json",
        "licence": "OGL-3.0",
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
        "source_url": grazings.get("source_url") or payload.get("open_data_url"),
        "gaps": [
            "No national OGL common-grazing polygon WMS/WFS for redistribution",
            "Spatial Hub Decrofted Areas is Restricted — not an alternative map layer",
        ],
        "lists_only": True,
        "boundaries": False,
        "ledger_role": "constraint",
        "ledger_row": None,
        "ui_surface": "ledger",
    }
