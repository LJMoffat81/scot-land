"""LAYERS-ADD-1 open-context layer catalog (licence-gated).

Extends the platform layer registry with the ADD-1 contract fields. Licence
rulings from LICENCE-ADDENDUM-1 / 1a override the frozen ADD-1 table where
they conflict (V&DL/green belt/schools/contaminated → ogl public; LDP/HLS →
flagged/prohibited; sepa_frm_maps → prohibited).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

from layers.layer_flags import (
    FLAG_HLS,
    FLAG_LDP,
    FLAG_SEPA_FRM,
    derive_public,
    flag_enabled,
)

SG_ATTRIBUTION = (
    "Copyright Scottish Government, contains Ordnance Survey data "
    "© Crown copyright and database right 2026."
)
SEPA_NFRA_ATTRIBUTION = (
    "©SEPA 2025; this SEPA product is licensed under the "
    "Open Government Licence version 3.0."
)
HES_ATTRIBUTION = (
    "Contains Historic Environment Scotland and OS data © Historic Environment "
    "Scotland and Crown Copyright and database right 2026, licensed under the "
    "Open Government Licence v3.0."
)
OGL_DEFAULT = (
    "Contains public sector information licensed under the Open Government "
    "Licence v3.0."
)

# Design / GIS display ids → catalog layer_id
DISPLAY_ID_BY_LAYER: Final[dict[str, str]] = {
    "simd2020_domains": "deprivation",
    "dz2022_boundaries": "dz2022",
    "naptan_stops": "stops",
    "hes_conservation_areas": "conservation",
    "hes_listed_buildings": "listed",
    "sepa_nfra_grid": "flood",
    "green_belt": "green_belt",
    "school_catchments": "school_catchments",
    "vdl": "vdl",
    "contaminated_land": "contaminated_land",
    "ldp_allocations": "ldp",
    "housing_land_supply": "hls",
}

# Tile / API property allowlists (L9). Listed buildings: category + HES link only.
# Vacant/derelict tiles are outline and fill only. Hectares stay on the Data
# Zone aggregate (agg_vdl), never as a per-site tile property.
TILE_PROPERTY_ALLOWLIST: Final[dict[str, frozenset[str]]] = {
    "naptan_stops": frozenset({"stop_type"}),
    "hes_listed_buildings": frozenset({"category", "hes_link"}),
    # `name` is the published conservation-area designation (a public name).
    "hes_conservation_areas": frozenset({"name"}),
    "sepa_nfra_grid": frozenset({"grid_id", "aad_score_res", "class"}),
    "contaminated_land": frozenset({"dz_code", "present"}),
    "housing_land_supply": frozenset({"geometry_type"}),
    "vdl": frozenset(),
    "green_belt": frozenset({"local_authority"}),
    # school_name is the published name of the school (a public institution).
    # LICENCE-ADDENDUM-1a: allowed on tiles; not a personal-data field.
    "school_catchments": frozenset({"school_name", "stage", "data_year"}),
    "ldp_allocations": frozenset({"use_class", "local_authority"}),
    "simd2020_domains": frozenset({"q", "topic"}),
    "dz2022_boundaries": frozenset({"dz_code"}),
}

# GeoJSON viewport paint. Flood risk uses sepa_nfra_grid, not the gated extent.
VIEWPORT_PAINT_LAYER_IDS: Final[frozenset[str]] = frozenset(
    {
        "access_services",
        "sepa_nfra_grid",
        "simd2020_domains",
        "hes_conservation_areas",
        "hes_listed_buildings",
        "naptan_stops",
        "green_belt",
        "school_catchments",
        "contaminated_land",
        "vdl",
    }
)

# Improvement Service / Spatial Hub sourced layers — skip when extract absent.
IS_LAYER_IDS: Final[frozenset[str]] = frozenset(
    {
        "vdl",
        "green_belt",
        "school_catchments",
        "contaminated_land",
        "ldp_allocations",
        "housing_land_supply",
    }
)

# After 1a: only these remain flagged for public surfaces.
GATED_LAYER_IDS: Final[frozenset[str]] = frozenset(
    {"sepa_frm_maps", "ldp_allocations", "housing_land_supply"}
)

LICENCE_STATUSES: Final[frozenset[str]] = frozenset(
    {"ogl", "confirmed", "unconfirmed", "open_other", "prohibited"}
)

REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "layer_id",
    "title",
    "publisher",
    "source_url",
    "service_type",
    "source_crs",
    "licence",
    "licence_status",
    "attribution",
    "group",
    "public",
    "refresh",
    "acquisition",
)


def _entry(
    *,
    layer_id: str,
    title: str,
    publisher: str,
    source_url: str,
    service_type: str,
    licence_status: str,
    attribution: str,
    group: str,
    flag_name: str | None,
    dz_aggregate: str | None,
    refresh: str,
    acquisition: str,
    licence: str = "OGL-3.0",
    source_crs: str = "EPSG:27700",
    licence_ref: str | None = None,
    minzoom: int | None = None,
    maxzoom: int | None = None,
    display_id: str | None = None,
    default_on: bool = False,
    family: str | None = None,
    caption: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    public = derive_public(licence_status, flag_name)
    row: dict[str, Any] = {
        "layer_id": layer_id,
        "title": title,
        "publisher": publisher,
        "source_url": source_url,
        "service_type": service_type,
        "source_crs": source_crs,
        "licence": licence,
        "licence_status": licence_status,
        "attribution": attribution,
        "group": group,
        "public": public,
        "flag_name": flag_name,
        "dz_aggregate": dz_aggregate,
        "refresh": refresh,
        "acquisition": acquisition,
        "display_id": display_id or DISPLAY_ID_BY_LAYER.get(layer_id),
        "default_on": default_on,
        "minzoom": minzoom,
        "maxzoom": maxzoom,
        "family": family,
        "caption": caption,
    }
    if licence_ref is not None:
        row["licence_ref"] = licence_ref
    if note is not None:
        row["note"] = note
    return row


def layers_add_entries() -> list[dict[str, Any]]:
    """Canonical ADD-1 catalog rows (licence addenda applied)."""
    year_credit_sg = SG_ATTRIBUTION
    return [
        _entry(
            layer_id="simd2020_domains",
            title="Local deprivation by topic, 2020",
            publisher="Scottish Government",
            source_url=(
                "https://www.spatialdata.gov.scot/geonetwork/srv/eng/"
                "catalog.search#/metadata/02866b0b-66e5-46ab-9b1c-d433dc3c2fae"
            ),
            service_type="WFS / download (auto)",
            licence_status="ogl",
            attribution=year_credit_sg,
            group="Places and boundaries",
            flag_name=None,
            dz_aggregate="agg_simd2020_domains",
            refresh="Static (next SIMD release)",
            acquisition="auto",
            minzoom=8,
            maxzoom=20,
            family="fill",
            caption="Scottish Government · 2020",
        ),
        _entry(
            layer_id="dz2022_boundaries",
            title="Neighbourhood lines",
            publisher="Scottish Government",
            source_url=(
                "https://www.spatialdata.gov.scot/geonetwork/srv/eng/"
                "catalog.search#/metadata/f6656adf-b720-4612-ad5c-1d13eae94c8b"
            ),
            service_type="WFS / download (auto)",
            licence_status="ogl",
            attribution=year_credit_sg,
            group="Places and boundaries",
            flag_name=None,
            dz_aggregate=None,
            refresh="Static",
            acquisition="auto",
            minzoom=10,
            maxzoom=20,
            family="context",
            caption="Scottish Government · 2022",
        ),
        _entry(
            layer_id="dz2011_boundaries",
            title="Data Zone 2011 boundaries (key only)",
            publisher="Scottish Government",
            source_url=(
                "https://www.spatialdata.gov.scot/geonetwork/srv/eng/"
                "catalog.search#/metadata/7d3e8709-98fa-4d71-867c-d5c8293823f2"
            ),
            service_type="WFS / download (auto)",
            licence_status="ogl",
            attribution=year_credit_sg,
            group="Places and boundaries",
            flag_name=None,
            dz_aggregate=None,
            refresh="Static",
            acquisition="auto",
            note="Data key only — not a visitor Layers row (GIS R4).",
        ),
        _entry(
            layer_id="naptan_stops",
            title="Bus and train stops",
            publisher="Department for Transport",
            source_url="https://beta-naptan.dft.gov.uk/",
            service_type="DfT NaPTAN CSV download (auto)",
            licence_status="ogl",
            attribution=OGL_DEFAULT,
            group="Places and boundaries",
            flag_name=None,
            dz_aggregate="agg_naptan",
            refresh="Monthly",
            acquisition="auto",
            minzoom=14,
            maxzoom=20,
            family="context",
            caption="Department for Transport · {YEAR}",
        ),
        _entry(
            layer_id="hes_conservation_areas",
            title="Conservation areas",
            publisher="Historic Environment Scotland",
            source_url="https://inspire.hes.scot/AtomService/DATA/ca_scotland.zip",
            service_type="ZIP shapefile or WFS (auto)",
            licence_status="ogl",
            attribution=HES_ATTRIBUTION,
            group="Places and boundaries",
            flag_name=None,
            dz_aggregate="agg_hes_ca",
            refresh="Quarterly",
            acquisition="auto",
            minzoom=8,
            maxzoom=20,
            family="context",
            caption="Historic Environment Scotland · {YEAR}",
            note="Tile property name is the published conservation-area designation.",
        ),
        _entry(
            layer_id="hes_listed_buildings",
            title="Listed buildings",
            publisher="Historic Environment Scotland",
            source_url="https://inspire.hes.scot/AtomService/DATA/lb_scotland.zip",
            service_type="ZIP / WFS (auto)",
            licence_status="ogl",
            attribution=HES_ATTRIBUTION,
            group="Places and boundaries",
            flag_name=None,
            dz_aggregate="agg_hes_lb",
            refresh="Quarterly",
            acquisition="auto",
            minzoom=14,
            maxzoom=20,
            family="context",
            caption="Historic Environment Scotland · {YEAR}",
            note="Tile/API properties: category + hes_link only (no address).",
        ),
        _entry(
            layer_id="sepa_nfra_grid",
            title="Flood risk (SEPA)",
            publisher="SEPA",
            source_url=(
                "https://map.sepa.org.uk/atom/NFRA/"
                "NFRA_Flood_Risk_Grid_Latest_BNG.gpkg.zip"
            ),
            service_type="GeoPackage (auto)",
            licence_status="ogl",
            attribution=SEPA_NFRA_ATTRIBUTION,
            group="Land",
            flag_name=None,
            dz_aggregate="agg_sepa_nfra",
            refresh="As SEPA republishes",
            acquisition="auto",
            minzoom=8,
            maxzoom=20,
            family="fill",
            caption="SEPA · {YEAR}",
            # Visitor paint stays OFF by default (kickoff: SEPA flood off).
            default_on=False,
        ),
        _entry(
            layer_id="sepa_frm_maps",
            title="SEPA Flood Risk Management Maps",
            publisher="SEPA",
            source_url="https://www.sepa.org.uk/environment/environmental-data/",
            service_type="View only (prohibited)",
            licence_status="prohibited",
            attribution="",
            group="Land",
            flag_name=FLAG_SEPA_FRM,
            dz_aggregate=None,
            refresh="n/a",
            acquisition="manual_drop",
            licence="prohibited",
            note='SEPA "View only" is an explicit prohibition (LICENCE-ADDENDUM-1a).',
        ),
        _entry(
            layer_id="vdl",
            title="Vacant and derelict land",
            publisher="Improvement Service Spatial Hub",
            source_url=(
                "https://data.spatialhub.scot/dataset/vacant_and_derelict_land-is"
            ),
            service_type="Spatial Hub WFS/SHP (manual_drop)",
            licence_status="ogl",
            attribution=(
                "Vacant and derelict land: Scottish Vacant and Derelict Land "
                "Survey via Improvement Service Spatial Hub. " + OGL_DEFAULT
            ),
            group="Land",
            flag_name=None,
            dz_aggregate="agg_vdl",
            refresh="Annual",
            acquisition="manual_drop",
            minzoom=10,
            maxzoom=20,
            family="context",
            caption="Improvement Service · {YEAR}",
        ),
        _entry(
            layer_id="green_belt",
            title="Green belt",
            publisher="Improvement Service Spatial Hub",
            source_url="https://data.spatialhub.scot/dataset/green_belt-is",
            service_type="Spatial Hub WFS (manual_drop)",
            licence_status="ogl",
            attribution=(
                "Green belt: Improvement Service Spatial Hub. " + OGL_DEFAULT
            ),
            group="Places and boundaries",
            flag_name=None,
            dz_aggregate="agg_green_belt",
            refresh="Annual",
            acquisition="manual_drop",
            minzoom=8,
            maxzoom=20,
            family="context",
            caption="Improvement Service · {YEAR}",
        ),
        _entry(
            layer_id="school_catchments",
            title="School catchments",
            publisher="Improvement Service Spatial Hub",
            source_url=(
                "https://data.spatialhub.scot/dataset/school_catchments-is"
            ),
            service_type="Spatial Hub WFS (manual_drop)",
            licence_status="ogl",
            attribution=(
                "School catchments: Improvement Service Spatial Hub. "
                + OGL_DEFAULT
            ),
            group="Places and boundaries",
            flag_name=None,
            dz_aggregate="agg_school_catch",
            refresh="Annual",
            acquisition="manual_drop",
            minzoom=10,
            maxzoom=20,
            family="context",
            caption="Improvement Service · council data, years vary",
            note="school_name is the published name of the school.",
        ),
        _entry(
            layer_id="contaminated_land",
            title="Contaminated land",
            publisher="Improvement Service Spatial Hub",
            source_url=(
                "https://data.spatialhub.scot/dataset/contaminated_land-is"
            ),
            service_type="Spatial Hub WFS (manual_drop)",
            licence_status="ogl",
            attribution=(
                "Contaminated land (confirmed): Improvement Service Spatial Hub. "
                + OGL_DEFAULT
            ),
            group="Land",
            flag_name=None,
            dz_aggregate="agg_contam",
            refresh="As needed",
            acquisition="manual_drop",
            minzoom=12,
            maxzoom=20,
            family="context",
            caption="Improvement Service · {YEAR}",
            note="DZ presence only — no site geometry or site_name in tiles/API.",
        ),
        _entry(
            layer_id="ldp_allocations",
            title="Planned development land",
            publisher="Improvement Service Spatial Hub",
            source_url=(
                "https://data.spatialhub.scot/dataset/local_development_plans-is"
            ),
            service_type="ZIP per council (manual_drop)",
            licence_status="prohibited",
            attribution="",
            group="Land",
            flag_name=FLAG_LDP,
            dz_aggregate="agg_ldp",
            refresh="Quarterly",
            acquisition="manual_drop",
            licence="PSGA / not commercially available",
            minzoom=10,
            maxzoom=20,
            family="context",
            caption="Improvement Service · {YEAR}",
            note="SSDI PSGA restriction — flagged OFF; roadmap only (1a).",
        ),
        _entry(
            layer_id="housing_land_supply",
            title="Land for new homes",
            publisher="Improvement Service Spatial Hub",
            source_url=(
                "https://data.spatialhub.scot/dataset/housing_land_supply-is"
            ),
            service_type="WFS/CSV (manual_drop)",
            licence_status="prohibited",
            attribution="",
            group="Land",
            flag_name=FLAG_HLS,
            dz_aggregate="agg_hls",
            refresh="Annual",
            acquisition="manual_drop",
            licence="PSGA / not commercially available",
            minzoom=10,
            maxzoom=20,
            family="context",
            caption="Improvement Service · {YEAR}",
            note="SSDI PSGA restriction — flagged OFF; roadmap only (1a).",
        ),
    ]


def layers_add_by_id() -> dict[str, dict[str, Any]]:
    return {row["layer_id"]: row for row in layers_add_entries()}


def public_layers_add_entries() -> list[dict[str, Any]]:
    """Layers that may appear on public surfaces (catalog / tiles / drawer)."""
    return [
        row
        for row in layers_add_entries()
        if row["public"] and row["layer_id"] != "dz2011_boundaries"
    ]


def waiting_for_permission_rows() -> list[dict[str, Any]]:
    """Roadmap rows: flagged and not public; exclude sepa_frm_maps entirely."""
    rows = []
    for row in layers_add_entries():
        if row["layer_id"] == "sepa_frm_maps":
            continue
        if row.get("flag_name") and not row["public"]:
            rows.append(
                {
                    "layer_id": row["layer_id"],
                    "display_id": row.get("display_id"),
                    "title": row["title"],
                    "group": row["group"],
                    "status_label": "Waiting for permission to use the data",
                    "status_label_short": "Waiting for permission",
                }
            )
    return rows


def tile_manifest(*, include_private: bool = False) -> dict[str, Any]:
    """Build the public tile endpoint list (flags OFF → no gated ids)."""
    sources: list[dict[str, Any]] = []
    for row in layers_add_entries():
        if row["layer_id"] == "sepa_frm_maps":
            continue
        if row["layer_id"] == "dz2011_boundaries":
            continue
        if not include_private and not row["public"]:
            continue
        if row["layer_id"] in IS_LAYER_IDS and not is_layer_extract_present(
            row["layer_id"]
        ):
            # Skip Improvement Service layers when the manual extract is absent.
            continue
        allow = sorted(TILE_PROPERTY_ALLOWLIST.get(row["layer_id"], frozenset()))
        sources.append(
            {
                "layer_id": row["layer_id"],
                "display_id": row.get("display_id"),
                "tile_url": f"/tiles/{row['layer_id']}/{{z}}/{{x}}/{{y}}",
                "minzoom": row.get("minzoom"),
                "maxzoom": row.get("maxzoom"),
                "property_allowlist": allow,
            }
        )
    return {"version": 1, "sources": sources}


def is_layer_extract_present(layer_id: str) -> bool:
    """True when ``data/external/<layer_id>/`` has a manifest.json (manual drop)."""
    root = Path(__file__).resolve().parents[2]
    manifest = root / "data" / "external" / layer_id / "manifest.json"
    return manifest.is_file()


def flagged_layer_ids() -> frozenset[str]:
    return frozenset(
        row["layer_id"]
        for row in layers_add_entries()
        if row.get("flag_name")
    )


def validate_entry(row: dict[str, Any]) -> list[str]:
    """Return human-readable problems for one catalog row (empty = ok)."""
    problems: list[str] = []
    for field in REQUIRED_FIELDS:
        if field not in row:
            problems.append(f"missing {field}")
        elif field not in {"flag_name", "dz_aggregate", "public"} and row[field] in (
            None,
            "",
        ):
            # attribution may be empty for prohibited rows
            if field == "attribution" and row.get("licence_status") in {
                "prohibited",
                "unconfirmed",
            }:
                continue
            if field == "public":
                continue
            problems.append(f"empty {field}")
    status = row.get("licence_status")
    if status not in LICENCE_STATUSES:
        problems.append(f"invalid licence_status={status!r}")
    expected = derive_public(
        str(status),
        row.get("flag_name"),
        flag_on=flag_enabled(row.get("flag_name")) if row.get("flag_name") else None,
        internal_only=bool(row.get("internal_only")),
    )
    if row.get("public") != expected:
        problems.append(
            f"public={row.get('public')!r} != derived {expected!r}"
        )
    return problems
