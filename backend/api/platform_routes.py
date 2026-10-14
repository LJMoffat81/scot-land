"""Open land platform HTTP routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from agr.export_stamp import with_stamp
from georgist import db
from georgist.ledger import ledger_catalog, ledger_zone_payload, resolve_ledger_zone
from georgist.place_stack import (
    is_zone_code,
    lookup_zone_publication_status,
    place_hectare_stack,
)
from layers.common_good import common_good_payload
from layers.crofting import crofting_payload
from layers.dz_context import build_metrics_payload
from layers.ldp import coverage_summary as ldp_coverage
from layers.ldp import query_bbox as ldp_bbox
from layers.open_stats import (
    catalog_json,
    public_land_json,
    vdl_json,
)
from layers.ledger import ledger_payload
from layers.platform import place_context, platform_catalog
from layers.registers import registers_payload
from layers.data_zones import query_bbox as data_zones_bbox
from layers.flood import query_bbox as flood_bbox
from layers.hydro import query_bbox as hydro_bbox
from layers.hla import query_bbox as hla_bbox
from layers.public_land import query_bbox as public_land_bbox
from layers.sepa_car import query_bbox as sepa_car_bbox
from layers.naturescot import LayerUnavailable as NatureScotUnavailable
from layers.naturescot import query_designations_bbox as naturescot_designations_bbox
from layers.naturescot import query_sssi_bbox as sssi_bbox
from layers.scotwind import LayerUnavailable as ScotwindUnavailable
from layers.scotwind import query_bbox as scotwind_bbox
from layers.repd_onshore_wind import query_bbox as repd_onshore_wind_bbox
from layers.vdl import query_bbox as vdl_bbox
from layers.community_ownership import LayerUnavailable as CommunityOwnershipUnavailable
from layers.community_ownership import query_bbox as community_ownership_bbox
from layers.woodland import LayerUnavailable as WoodlandUnavailable
from layers.woodland import query_native_woodland_bbox, query_nfi_bbox
from layers.ces_aquaculture import query_bbox as ces_aquaculture_bbox
from layers.crown_estate_leases import query_bbox as crown_estate_leases_bbox
from layers.repd import query_bbox as repd_bbox
from layers.lca import LayerUnavailable as LcaUnavailable
from layers.lca import query_bbox as lca_bbox

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


@router.get("/layers/open/dz-context")
def layer_open_dz_context(
    vintage: int = Query(default=2011, description="Data Zone vintage: 2011 or 2022"),
) -> JSONResponse:
    """Data Zone house prices, SIMD and population density (OGL context).

    Attributes always load from the staged GIS metrics table. Zone polygons are
    included only when ``dz_boundaries`` is loaded — never invented. No modelled
    AGR £ is attached.
    """
    if vintage not in (2011, 2022):
        raise HTTPException(
            status_code=422,
            detail={"error": "invalid_vintage", "message": "vintage must be 2011 or 2022"},
        )
    payload = build_metrics_payload(vintage=vintage, include_geometry=True)
    if not payload.get("features"):
        raise HTTPException(
            status_code=503,
            detail=(
                "Data Zone context metrics are not available "
                "(dz_context_metrics not staged). Gaps are not filled with guesses."
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


def _scottish_waters_bounds_check(lat: float, lng: float) -> None:
    """BBox centres for ScotWind/INTOG may sit east of mainland Scotland."""
    if lat < 54.0 or lat > 62.0 or lng < -9.5 or lng > 2.0:
        raise HTTPException(
            status_code=400,
            detail="Coordinates appear to be outside Scottish waters.",
        )


@router.get("/layers/open/scotwind-intog")
def layer_open_scotwind_intog(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """ScotWind / INTOG option polygons from PostGIS (CES Spatial Hub ingest).

    Geometry + award descriptors only. **No surface rent / la-calc £.** Option-fee
    £ are HOLD (``data/config/scotwind_option_fees.yaml``) — not layer attributes.
    Returns **503** when ``ces_scotwind_intog`` is missing or empty.
    """
    _scottish_waters_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    if south >= north or west >= east:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox: require south < north and west < east",
        )
    try:
        return JSONResponse(
            scotwind_bbox(south, west, north, east, max_features=max_features)
        )
    except ScotwindUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/layers/open/repd-onshore-wind")
def layer_open_repd_onshore_wind(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """DESNZ REPD onshore wind sites (Scotland) — MW and status only.

    Natural-capital overlay from PostGIS after OGL CSV ingest. **No £ rent.**
    **503** when unloaded. Empty FeatureCollection with meta.ok=true means no
    sites in view.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = repd_onshore_wind_bbox(
        south, west, north, east, max_features=max_features
    )
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "REPD onshore wind overlay is not available: "
                f"{meta.get('error') or 'PostGIS source not loaded'}. "
                "Run python -m etl.ingest_repd_onshore_wind on the OGL CSV — "
                "gaps are not filled with guesses."
            ),
        )
    return JSONResponse(payload)


@router.get("/layers/open/ces-aquaculture")
def layer_open_ces_aquaculture(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """CES aquaculture seabed leases in the viewport (OGL → PostGIS).

    Natural-capital lease polygons only — attributes/status, **no £ rent**
    or fee on features; never added to Surface Rent or AGR. Ledger row 5.
    Served from PostGIS after `python -m etl.ingest_ces_aquaculture`.
    **503** when unloaded.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = ces_aquaculture_bbox(
        south, west, north, east, max_features=max_features
    )
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "CES aquaculture overlay is not available: "
                f"{meta.get('error') or 'PostGIS table missing'}. "
                "Run python -m etl.ingest_ces_aquaculture — gaps are not "
                "filled with guesses."
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


@router.get("/layers/open/flood")
def layer_open_flood(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """SEPA medium-likelihood river/coastal flood extents in the viewport (OGL).

    PostGIS only — ingest the OGL download from www2.sepa.org.uk/flooddata.
    Never uses SEPA MapServer, viewer, or live web services. Returns **503**
    when unloaded — never invents extents.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = flood_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "SEPA flood overlay is not available: "
                f"{meta.get('error') or 'upstream source failed'}. "
                "OGL Flood Maps v3.0 only — gaps are not filled with guesses."
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


@router.get("/layers/open/sssi")
def layer_open_sssi(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """NatureScot SSSI polygons (OGL-3.0). Constraint overlay — £0, no rent row."""
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    try:
        payload = sssi_bbox(south, west, north, east, max_features=max_features)
    except NatureScotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JSONResponse(payload)


@router.get("/layers/open/naturescot-designations")
def layer_open_naturescot_designations(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """NatureScot SPA/SAC/NNR polygons (OGL-3.0). Constraint overlay — £0, no rent row."""
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    try:
        payload = naturescot_designations_bbox(
            south, west, north, east, max_features=max_features
        )
    except NatureScotUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JSONResponse(payload)


@router.get("/ledger")
def natural_capital_ledger() -> dict:
    """Natural capital ledger rows + constraints (no published AGR £).

    Contract: ROWS 1–10 + nested 1a; Constraints = £0, change best use.
    Amounts are placeholders until ECONOMIC_RULES / calibration approve.
    """
    return ledger_payload()


@router.get("/layers/open/community-ownership")
def layer_open_community_ownership(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=200, ge=1, le=200),
) -> JSONResponse:
    """Community ownership asset points in the viewport (SG 2024 OGL).

    Served from PostGIS ingest of the published asset dataset (postcode
    centroids). Returns **503** when the table is missing or empty — never
    invents holdings. An empty FeatureCollection with meta.ok=true means no
    assets in view.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    if south >= north or west >= east:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox: require south < north and west < east",
        )
    try:
        payload = community_ownership_bbox(
            south, west, north, east, max_features=max_features
        )
    except CommunityOwnershipUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return JSONResponse(payload)


@router.get("/layers/open/nfi")
def layer_open_nfi(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """National Forest Inventory woodland polygons (PostGIS ingest).

    Returns **503** when ``nfi_woodland`` is missing or empty — never invents
    woodland. An empty FeatureCollection with meta.ok=true means no polygons
    in view. Ledger row 1 land-use overlay — no rent.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    try:
        payload = query_nfi_bbox(south, west, north, east, max_features=max_features)
    except WoodlandUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"National Forest Inventory overlay is not available: {exc}. "
                "Load PostGIS via python -m etl.ingest_woodland_layers — "
                "gaps are not filled with guesses."
            ),
        ) from exc
    return JSONResponse(payload)


@router.get("/layers/open/native-woodland")
def layer_open_native_woodland(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """Native Woodland Survey of Scotland polygons (PostGIS ingest).

    Returns **503** when ``native_woodland`` is missing or empty — never invents
    survey polygons. An empty FeatureCollection with meta.ok=true means none
    in view. Ledger row 1 land-use overlay — no rent.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    try:
        payload = query_native_woodland_bbox(
            south, west, north, east, max_features=max_features
        )
    except WoodlandUnavailable as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                f"Native Woodland Survey overlay is not available: {exc}. "
                "Load PostGIS via python -m etl.ingest_woodland_layers — "
                "gaps are not filled with guesses."
            ),
        ) from exc
    return JSONResponse(payload)


@router.get("/layers/open/repd")
def layer_open_repd(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """DESNZ REPD Scotland planning-site points in the viewport (OGL).

    Served from PostGIS after `python -m etl.ingest_repd`. **503** when the
    table is missing or empty — never invents sites. Empty FeatureCollection
    with meta.ok=true means no sites in view. Ledger row 3 — no £ rent.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = repd_bbox(south, west, north, east, max_features=max_features)
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "REPD overlay is not available: "
                f"{meta.get('error') or 'PostGIS table missing or empty'}. "
                "Load the OGL quarterly extract with python -m etl.ingest_repd."
            ),
        )
    return JSONResponse(payload)


@router.get("/layers/open/crown-estate-leases")
def layer_open_crown_estate_leases(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=80, ge=1, le=80),
) -> JSONResponse:
    """Crown Estate Scotland offshore lease polygons in the viewport (OGL).

    Served from PostGIS after `python -m etl.ingest_crown_estate_leases`.
    Offshore wind / wave / tidal / CCS only. **503** when missing/empty —
    never invents leases. Ledger row 4 — no £ rent.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    payload = crown_estate_leases_bbox(
        south, west, north, east, max_features=max_features
    )
    meta = payload.get("meta") or {}
    if meta.get("ok") is False:
        raise HTTPException(
            status_code=503,
            detail=(
                "Crown Estate Scotland leases overlay is not available: "
                f"{meta.get('error') or 'PostGIS table missing or empty'}. "
                "Load OGL Spatial Hub themes with "
                "python -m etl.ingest_crown_estate_leases."
            ),
        )
    return JSONResponse(payload)



@router.get("/layers/open/lca")
def layer_open_lca(
    south: float = Query(..., description="BBox south latitude"),
    west: float = Query(..., description="BBox west longitude"),
    north: float = Query(..., description="BBox north latitude"),
    east: float = Query(..., description="BBox east longitude"),
    max_features: int = Query(default=200, ge=1, le=200),
) -> JSONResponse:
    """Land Capability for Agriculture polygons in the viewport (PostGIS ingest).

    James Hutton Institute Open Data Licence (accepted; not OGL-3.0; PSI clause
    under OGL v2.0). Returns **503** when ``lca_agriculture`` is missing or
    empty — never invents capability polygons. An empty FeatureCollection with
    meta.ok=true means no polygons in view. Ledger constraint (£0) — changes
    best use only.
    """
    _scotland_bounds_check((south + north) / 2.0, (west + east) / 2.0)
    if south >= north or west >= east:
        raise HTTPException(
            status_code=400,
            detail="Invalid bbox: require south < north and west < east",
        )
    try:
        return JSONResponse(
            lca_bbox(south, west, north, east, max_features=max_features)
        )
    except LcaUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc



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
    """Blocked: vacant-land residual AGR £ is not a public download."""
    del scenario  # signature kept for clients that still pass ?scenario=
    raise HTTPException(
        status_code=403,
        detail={
            "message": "Modelled vacant-land AGR £ is not published on public routes.",
            "publication_status": "blocked",
        },
    )


@router.get("/api/roll.json")
def api_roll(scenario: str = Query(default="full_agr")) -> dict:
    """Blocked: council AGR roll £ is not a public download."""
    del scenario
    raise HTTPException(
        status_code=403,
        detail={
            "message": "Modelled council AGR roll £ is not published on public routes.",
            "publication_status": "blocked",
        },
    )


@router.get("/api/roll.csv")
def api_roll_csv(scenario: str = Query(default="full_agr")) -> dict:
    """Blocked: council AGR roll £ is not a public download."""
    del scenario
    raise HTTPException(
        status_code=403,
        detail={
            "message": "Modelled council AGR roll £ is not published on public routes.",
            "publication_status": "blocked",
        },
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


@router.get("/api/crofting.json")
def api_crofting() -> dict:
    """Crofting Commission OGL Register of Crofts + grazings; spatial gaps honest."""
    return with_stamp(crofting_payload())


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
                "id": "sssi_overlay",
                "label": "NatureScot SSSI overlay (this API)",
                "licence": "OGL-3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "endpoint": "/layers/open/sssi",
                "url": "https://opendata.nature.scot/maps/sites-of-special-scientific-interest",
                "note": "PostGIS bbox after local OGL ingest; 503 when unloaded.",
            },
            {
                "id": "naturescot_designations_overlay",
                "label": "NatureScot SPA/SAC/NNR overlay (this API)",
                "licence": "OGL-3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "endpoint": "/layers/open/naturescot-designations",
                "url": "https://opendata.nature.scot/",
                "note": "PostGIS bbox after local OGL ingest; 503 when unloaded.",
            },
            {
                "id": "lca_overlay",
                "label": "Land Capability for Agriculture overlay (this API)",
                "licence": (
                    "James Hutton Institute Open Data Licence "
                    "(not OGL-3.0; PSI clause under OGL v2.0)"
                ),
                "licence_url": (
                    "https://www.hutton.ac.uk/wp-content/uploads/2024/05/"
                    "The-James-Hutton-Institute-Open-Data-Licence-download.pdf"
                ),
                "endpoint": "/layers/open/lca",
                "url": (
                    "https://www.hutton.ac.uk/sites/default/files/files/soils/"
                    "downloads/Hutton_LCA250K_OpenData.zip"
                ),
                "note": (
                    "PostGIS ingest of Hutton LCA 1:250k. Ledger constraint (£0) — "
                    "not a rent or title. Redistribution / derived data on equivalent "
                    "Hutton terms with required attribution. 503 when unloaded."
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
                "id": "dz_context",
                "label": "Data Zone HPI / SIMD / population density",
                "licence": "OGL v3.0",
                "endpoint": "/layers/open/dz-context",
                "note": "Ledger-frame surface inputs for row 1; no modelled AGR £",
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
                "id": "scotwind_intog",
                "label": "ScotWind / INTOG option polygons (this API)",
                "licence": "OGL-3.0",
                "licence_url": (
                    "https://www.nationalarchives.gov.uk/doc/"
                    "open-government-licence/version/3/"
                ),
                "attribution": (
                    "Contains information from the Crown Estate Scotland licensed "
                    "under the Open Government Licence v3.0"
                ),
                "endpoint": "/layers/open/scotwind-intog",
                "url": (
                    "https://crown-estate-scotland-spatial-hub-coregis.hub.arcgis.com/"
                    "datasets/coregis::scotwind-offers-crown-estate-scotland/about"
                ),
                "note": (
                    "PostGIS ingest of CES ScotWind Offers + INTOG Application Areas. "
                    "Polygons only. Option-fee £ HOLD in data/config/scotwind_option_fees.yaml. "
                    "Does not add to surface rent."
                ),
            },
            {
                "id": "common_good",
                "label": "Common Good registers (verified links)",
                "licence": (
                    "council pages; Highland FeatureServers licence unconfirmed "
                    "(linked only); Fife OS INSPIRE EUL metadata — links only"
                ),
                "endpoint": "/api/common-good.json",
                "note": (
                    "No national open spatial layer. Highland and Fife "
                    "FeatureServers are linked only — not loaded or stored. "
                    "Spatial Hub assets stay login-gated."
                ),
            },
            {
                "id": "crofting_register",
                "label": "Crofting Register of Crofts (OGL CSV → PostGIS)",
                "licence": "OGL-3.0",
                "endpoint": "/api/crofting.json",
                "url": "https://www.crofting.scotland.gov.uk/open-data/",
                "note": (
                    "Parishes / Holdings / Grazings under OGL. Individuals not "
                    "ingested. Map extents: RoS Crofting Register search (linked)."
                ),
            },
            {
                "id": "common_grazings",
                "label": "Common grazings (OGL CSV → PostGIS)",
                "licence": "OGL-3.0",
                "endpoint": "/api/crofting.json",
                "url": "https://www.crofting.scotland.gov.uk/open-data/",
                "note": (
                    "List of Grazings with extent (ha). No national OGL polygon "
                    "overlay — Spatial Hub Decrofted Areas is Restricted."
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
