"""Open land platform HTTP routes."""

from __future__ import annotations

import csv
import io

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from agr.export_stamp import current_stamp, stamp_comment, with_stamp
from georgist import db
from georgist.ledger import ledger_catalog, ledger_zone_payload, resolve_ledger_zone
from georgist.place_stack import (
    is_zone_code,
    lookup_zone_publication_status,
    place_hectare_stack,
)
from layers.common_good import common_good_payload
from layers.ldp import coverage_summary as ldp_coverage
from layers.ldp import query_bbox as ldp_bbox
from layers.open_stats import (
    catalog_json,
    public_land_json,
    roll_json,
    vdl_councils_json,
    vdl_json,
)
from layers.ledger import ledger_payload
from layers.platform import place_context, platform_catalog
from layers.registers import registers_payload
from layers.data_zones import query_bbox as data_zones_bbox
from layers.hydro import query_bbox as hydro_bbox
from layers.hla import query_bbox as hla_bbox
from layers.public_land import query_bbox as public_land_bbox
from layers.sepa_car import query_bbox as sepa_car_bbox
from layers.vdl import query_bbox as vdl_bbox

router = APIRouter()


def _scotland_bounds_check(lat: float, lng: float) -> None:
    if lat < 54.5 or lat > 61.0 or lng < -8.5 or lng > -0.5:
        raise HTTPException(status_code=400, detail="Coordinates appear to be outside Scotland.")


@router.get("/layers/open/vdl")
def layer_open_vdl(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """Vacant and derelict land polygons in the viewport (OGL survey overlay).

    Returns site-level SVDLS features as published. **503** when the upstream
    open FeatureServer is unavailable — never invents sites. An empty
    FeatureCollection with meta.ok=true means no sites in view.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = vdl_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "Vacant and derelict land overlay is not available: "
                f"{meta.get('error') or 'upstream source failed'}. "
                "SVDLS survey sites only — gaps are not filled with guesses."
            ),
        )
    return JSONResponse(payload)


@router.get("/layers/open/public-land")
def layer_open_public_land(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """Public and Crown Estate holdings in the viewport (SG 2024 overlay).

    Returns 503 when the upstream open overlay is unavailable — never invents
    holdings. An empty FeatureCollection with meta.ok=true means no holdings
    in view (coverage gaps stay visible, not guessed).
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = public_land_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "Public land overlay is not available: "
                f"{meta.get('error') or 'upstream source failed'}. "
                "Five-body SG 2024 map only — gaps are not filled with guesses."
            ),
        )
    return JSONResponse(payload)


@router.get("/layers/open/data-zones")
def layer_open_data_zones(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=120, ge=1, le=120),
) -> JSONResponse:
    """2011 Data Zone boundaries in the viewport (simplified GeoJSON).

    Outlines only — code and name, no AGR £ / Surface Rent. Returns **503**
    when the upstream SG StatisticalUnits service is unavailable. An empty
    FeatureCollection with meta.ok=true means no zones in view.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = data_zones_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "Data Zone boundaries are not available: "
                f"{meta.get('error') or 'upstream source failed'}. "
                "Boundaries only — gaps are not filled with guesses."
            ),
        )
    return JSONResponse(payload)


@router.get("/layers/open/hla")
def layer_open_hla(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """Housing Land Audit / Housing Land Supply polygons in the viewport (OGL).

    Serves Spatial Hub HLA sites from PostGIS ``planning_sites`` after local
    OGL ingest. **503** when unloaded or PostGIS unavailable — never invents
    sites. An empty FeatureCollection with meta.ok=true means no sites in view.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = hla_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "Housing land audit overlay is not available: "
                f"{meta.get('error') or 'PostGIS HLA source not loaded'}. "
                "Spatial Hub OGL extract only — gaps are not filled with guesses."
            ),
        )
    return JSONResponse(payload)


@router.get("/layers/open/hydro")
def layer_open_hydro(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """SEPA hydropower CAR sites in the viewport (OGL → PostGIS).

    Natural-capital site inventory only — **no £ rent**. Served from PostGIS
    after `python -m etl.ingest_hydro_sites`. **503** when unloaded.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = hydro_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "Hydropower sites overlay is not available: "
                f"{meta.get('error') or 'PostGIS table missing'}. "
                "Load the OGL ATOM shapefile with python -m etl.ingest_hydro_sites."
            ),
        )
    return JSONResponse(payload)


@router.get("/layers/open/sepa-car")
def layer_open_sepa_car(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """SEPA CAR licences in the viewport (MapServer 194/195 → PostGIS).

    Ingest loads Open/SEPA_Reference layers into PostGIS with
    `python -m etl.ingest_sepa_car`. This route serves **PostGIS only —
    never proxies MapServer**. **No £ rent**. **503** until loaded.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = sepa_car_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "SEPA CAR licences overlay is not available: "
                f"{meta.get('error') or 'PostGIS table missing'}. "
                "Run python -m etl.ingest_sepa_car to load MapServer "
                "layers 194/195 into PostGIS (API never proxies MapServer)."
            ),
        )
    return JSONResponse(payload)


@router.get("/layers/open/ldp")
def layer_open_ldp(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """LDP allocation polygons in the viewport (PostGIS, OGL ingest).

    Returns **503** when ``ldp_allocations`` is not loaded — never invents
    missing authorities. An empty FeatureCollection with meta.ok=true means
    no allocations in view (national fragmentation stays visible).
    Feeds ledger nested row 1a (planning) — no £ rent.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = ldp_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "LDP allocations overlay is not available: "
                f"{meta.get('error') or 'PostGIS layer not loaded'}. "
                "OGL Spatial Hub / authority packs only — gaps are not filled with guesses."
            ),
        )
    return JSONResponse(payload)


@router.get("/ledger")
def natural_capital_ledger() -> dict:
    """Natural capital ledger rows + constraints (no published AGR £).

    Contract: ROWS 1–10 + nested 1a; Constraints = £0, change best use.
    Amounts are placeholders until ECONOMIC_RULES / calibration approve.
    """
    return ledger_payload()


@router.get("/platform/place")
def platform_place(
    lat: float = Query(..., ge=-90, le=90),
    lng: float = Query(..., ge=-180, le=180),
    postcode: str | None = Query(default=None),
) -> dict:
    """Public place card for one clicked spot (place_card_v1).

    Council, data zone, intersecting layers, and official links.
    No modelled AGR £ — residual plot rent stays on /internal/agr/*.
    """
    _scotland_bounds_check(lat, lng)
    return place_context(lat, lng, postcode=postcode)


@router.get("/platform/gaps")
def platform_gaps() -> dict:
    """Visible register gaps — first-class product, not hidden."""
    catalog = platform_catalog()
    return {
        "brief": catalog["brief"],
        "gaps": [layer for layer in catalog["layers"] if layer["status"] in ("gap", "linked")],
        "live": [layer for layer in catalog["layers"] if layer["status"] == "live"],
        "policy": catalog["data_policy"],
    }


@router.get("/api/catalog.json")
def api_catalog() -> dict:
    return with_stamp(catalog_json())


@router.get("/api/ledger.json")
def api_ledger(
    zone_id: str | None = Query(
        default=None,
        description="Optional Data Zone code (e.g. S01008677). Zone-level stack; "
        "blocked zones return published=false with empty rows.",
    ),
    vintage: str | None = Query(
        default=None,
        description="Optional vintage 2011 or 2022 when zone_id is set.",
    ),
) -> dict:
    """Natural capital ledger: rows 1–10 (+1a), checks, excluded, benchmarks.

    National catalog when zone_id is omitted. With zone_id, returns the
    zone-level stack (nothing published for blocked zones). No map-panel
    layer dump and no modelled plot £ until ECONOMIC_RULES is approved.
    """
    if zone_id is None:
        return with_stamp(ledger_catalog())

    vin: int | None = None
    if vintage is not None:
        text = vintage.strip()
        if text not in ("2011", "2022"):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_vintage",
                    "vintage": vintage,
                    "message": "vintage must be the integer 2011 or 2022.",
                },
            )
        vin = int(text)
    try:
        resolve_ledger_zone(zone_id, vin)
    except ValueError as exc:
        code = str(exc)
        raise HTTPException(
            status_code=422,
            detail={
                "error": code,
                "zone_id": zone_id,
                "vintage": vin,
                "message": (
                    "zone_id must be a Scottish data zone code like S01012345; "
                    "vintage must match the code's 2011/2022 range."
                ),
            },
        ) from exc
    try:
        return with_stamp(ledger_zone_payload(zone_id, vin))
    except db.DatabaseUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "wealth_database_unavailable",
                "reason": exc.reason,
                "detail": exc.detail,
                "message": (
                    "Zone ledger needs the wealth database to check publication_status; "
                    "nothing was estimated."
                ),
            },
        ) from exc


@router.get("/api/place-stack.json")
def api_place_stack(
    zone: str | None = Query(default=None, description="Data Zone code (S01…)"),
    lat: float | None = Query(default=None, ge=-90, le=90),
    lng: float | None = Query(default=None, ge=-180, le=180),
) -> dict:
    """Place view per-hectare stack (Natural capital ledger).

    Zone grain only. Nested 1a indented (never added). Shadow stack separate.
    Oil & gas + benchmarks outside. Nothing for blocked zones. Public amounts
    are placeholders — no modelled AGR £ until ECONOMIC_RULES / calibration.
    """
    zone_code = (zone or "").strip().upper() or None
    zone_name: str | None = None
    if not zone_code:
        if lat is None or lng is None:
            raise HTTPException(
                status_code=400,
                detail="Provide zone= (Data Zone) or lat= and lng=.",
            )
        _scotland_bounds_check(lat, lng)
        from layers.platform import _data_zone_at

        dz = _data_zone_at(lat, lng)
        if dz.get("status") != "ok" or not dz.get("code"):
            raise HTTPException(
                status_code=404,
                detail=dz.get("note") or "No Data Zone at this point.",
            )
        zone_code = str(dz["code"]).strip().upper()
        zone_name = dz.get("name")
    if not is_zone_code(zone_code):
        raise HTTPException(
            status_code=422,
            detail=f"zone {zone_code!r} is not a Data Zone code.",
        )
    status = lookup_zone_publication_status(zone_code)
    return with_stamp(
        place_hectare_stack(
            zone_code,
            zone_name=zone_name,
            publication_status=status,
        )
    )


@router.get("/api/public-land.json")
def api_public_land() -> dict:
    return with_stamp(public_land_json())


@router.get("/api/vdl.json")
def api_vdl() -> dict:
    return with_stamp(vdl_json())


@router.get("/api/ldp.json")
def api_ldp() -> dict:
    """LDP allocation coverage meta — authorities loaded into PostGIS + honest gaps."""
    return with_stamp(ldp_coverage())


@router.get("/api/vdl-councils.json")
def api_vdl_councils(
    scenario: str = Query(default="full_agr"),
) -> dict:
    return with_stamp(vdl_councils_json(scenario))


@router.get("/api/roll.json")
def api_roll(scenario: str = Query(default="full_agr")) -> dict:
    return with_stamp(roll_json(scenario))


@router.get("/api/roll.csv")
def api_roll_csv(scenario: str = Query(default="full_agr")) -> PlainTextResponse:
    payload = roll_json(scenario)
    rows = payload.get("councils") or []
    comment = stamp_comment(current_stamp())
    cache = {"Cache-Control": "public, max-age=300"}
    if not rows:
        return PlainTextResponse(
            comment + "\n", media_type="text/csv", headers=cache
        )
    fields = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return PlainTextResponse(
        comment + "\n" + buf.getvalue(), media_type="text/csv", headers=cache
    )


@router.get("/api/place.json")
def api_place(
    pc: str | None = Query(default=None),
    lat: float | None = Query(default=None),
    lng: float | None = Query(default=None),
) -> dict:
    """Place card download (place_card_v1). No modelled AGR £."""
    result: dict = {}
    if pc:
        import httpx

        from api.common import _load_postcode_api_url

        normalised = pc.replace(" ", "").upper()
        api_url = _load_postcode_api_url()
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(f"{api_url}/{normalised}")
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Postcode lookup failed: {exc}") from exc
        if response.status_code != 200:
            raise HTTPException(status_code=404, detail="Postcode not found.")
        result = (response.json() or {}).get("result") or {}
        lat = float(result["latitude"])
        lng = float(result["longitude"])
        pc = result.get("postcode") or pc
    if lat is None or lng is None:
        raise HTTPException(status_code=400, detail="Provide pc= or lat= and lng=.")
    _scotland_bounds_check(lat, lng)
    council_code = None
    council_name = None
    if pc:
        codes = result.get("codes") if isinstance(result.get("codes"), dict) else None
        if isinstance(codes, dict):
            council_code = codes.get("admin_district")
        council_name = result.get("admin_district")
    card = place_context(
        lat,
        lng,
        postcode=pc,
        council_code=council_code,
        council_name=council_name,
    )
    # Defence in depth: public download must never carry residual plot AGR £.
    card.pop("agr", None)
    return with_stamp(card)


@router.get("/api/registers.json")
def api_registers() -> dict:
    return with_stamp(registers_payload())


@router.get("/api/common-good.json")
def api_common_good() -> dict:
    """Verified Common Good register links and spatial gaps — research / education."""
    return with_stamp(common_good_payload())


@router.get("/downloads")
def open_downloads() -> dict:
    """Index of freely licensed layers and official sources."""
    return with_stamp({
        "note": (
            "Only openly licensed material is offered here. "
            "Spatial Hub login layers are listed as sources, not mirrored."
        ),
        "items": [
            {
                "id": "vdl_register",
                "label": "SVDLS site register",
                "licence": "OGL-3.0",
                "url": "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
            },
            {
                "id": "vdl_overlay",
                "label": "VDL map overlay (this API)",
                "licence": "OGL-3.0",
                "endpoint": "/layers/open/vdl",
            },
            {
                "id": "hydro_sites",
                "label": "SEPA hydropower sites (this API)",
                "licence": "OGL-3.0",
                "url": (
                    "https://www.data.gov.uk/dataset/"
                    "5750f8e5-d51b-4e75-a8d6-403a0d1ded81/hydropower_sites"
                ),
                "endpoint": "/layers/open/hydro",
                "note": "PostGIS after ATOM ingest. value_tier=proxy. No £ rent.",
            },
            {
                "id": "sepa_car",
                "label": "SEPA CAR licences (this API)",
                "licence": "OGL-3.0",
                "url": "https://www.sepa.org.uk/environment/environmental-data/",
                "endpoint": "/layers/open/sepa-car",
                "note": (
                    "MapServer 194/195 → PostGIS via python -m etl.ingest_sepa_car; "
                    "API never proxies. value_tier=market. No £ rent."
                ),
            },
            {
                "id": "data_zone_boundaries",
                "label": "Data Zone boundaries overlay (this API)",
                "licence": "OGL v3.0 — Scottish Government / OS",
                "endpoint": "/layers/open/data-zones",
                "note": "Simplified GeoJSON by bbox. Outlines only — no AGR £.",
            },
            {
                "id": "ldp_allocations",
                "label": "LDP allocations (PostGIS / this API)",
                "licence": "OGL-3.0",
                "endpoint": "/layers/open/ldp",
                "url": "https://data.spatialhub.scot/dataset/local_development_plans-is",
                "note": (
                    "Fragmented national Spatial Hub pack. City of Edinburgh missing. "
                    "OGL authority FeatureServers (e.g. Highland) ingested into PostGIS. "
                    "Planning extents, not a title."
                ),
            },
            {
                "id": "council_agr",
                "label": "Council AGR metrics GeoJSON",
                "licence": "research estimate + OGL inputs",
                "endpoint": "/layers/councils",
            },
            {
                "id": "inspire_parcels",
                "label": "ROS INSPIRE cadastral parcels",
                "licence": "OGL-3.0",
                "url": "https://www.ros.gov.uk/open-data",
                "endpoint": "/layers/parcels",
                "note": (
                    "PostGIS Index Polygons ingest. 503 when table empty; "
                    "CI may load a synthetic fixture only."
                ),
            },
            {
                "id": "common_good",
                "label": "Common Good registers (verified links)",
                "licence": "council pages + Fife OS INSPIRE EUL metadata — links only",
                "endpoint": "/api/common-good.json",
                "note": (
                    "No national open spatial layer. Fife indicative titles are "
                    "linked, not mirrored. Spatial Hub assets stay login-gated."
                ),
            },
            {
                "id": "scotlis",
                "label": "ScotLIS official titles",
                "licence": "ROS service",
                "url": "https://scotlis.ros.gov.uk/",
            },
        ],
    })
