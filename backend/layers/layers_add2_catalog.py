"""LAYERS-ADD-2 catalog: open-data sweep plus council-direct sources.

Licence status follows LICENCE-ADDENDUM-1a. Spatial Hub LDP and housing land
supply stay flagged on the ADD-1 catalog. Council-direct rows are discovery
records (internal_only): they are not public switches. os_open_zoomstack is
not built (OQ1). Transport Scotland trunk/rail/ferry is omitted because it
does not add fields beyond NaPTAN and OS Roads (OQ4).
"""

from __future__ import annotations

import re
from typing import Any, Final

from layers.layer_flags import derive_public
from spatial.council_names import OFFICIAL_COUNCIL_NAMES

LICENCE_STATUSES: Final[frozenset[str]] = frozenset(
    {"ogl", "confirmed", "unconfirmed", "open_other", "prohibited"}
)
OGL_LICENCE_URL: Final[str] = (
    "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
)
OGL_ATTRIBUTION: Final[str] = (
    "Contains public sector information licensed under the Open Government "
    "Licence v3.0."
)
OS_ATTRIBUTION: Final[str] = (
    "Contains OS data © Crown copyright and database right 2026"
)
SG_ATTRIBUTION: Final[str] = (
    "Copyright Scottish Government, contains Ordnance Survey data "
    "© Crown copyright and database right 2026."
)
NRS_ATTRIBUTION: Final[str] = (
    "Contains National Records of Scotland data licensed under the Open "
    "Government Licence v3.0."
)
OFCOM_ATTRIBUTION: Final[str] = "Contains Ofcom data © Ofcom 2025"
FLS_ATTRIBUTION: Final[str] = (
    "Contains Forestry and Land Scotland data and OS data © Crown copyright "
    "and database right 2026, licensed under the Open Government Licence v3.0."
)
CES_ATTRIBUTION: Final[str] = (
    "Contains information from the Crown Estate Scotland licensed under the "
    "Open Government Licence v3.0."
)

# Not built this PR. Zoomstack waits on OQ1. Trunk/rail/ferry adds nothing
# over NaPTAN and OS Open Roads, so the row is dropped before build (OQ4).
DROPPED_LAYER_IDS: Final[dict[str, str]] = {
    "os_open_zoomstack": "OQ1 basemap not chosen; not built in this PR",
    "ts_trunk_rail_ferry": "OQ4: fields already covered by NaPTAN and OS Roads",
}

ZONE_RE: Final[re.Pattern[str]] = re.compile(r"^S01\d{6}$")
DZ2022_VINTAGE: Final[int] = 2022
DZ2022_COUNT: Final[int] = 7392
# Official 2022 range S01013482–S01020873 (6,976 of 2011 sit below this).
DZ2022_LO: Final[int] = 1_013_482
DZ2022_HI: Final[int] = 1_020_873

# Tile properties. Address, postcode, uprn, building name and dwelling
# coordinates are never on the list (A6).
TILE_PROPERTY_ALLOWLIST: Final[dict[str, frozenset[str]]] = {
    "os_open_roads": frozenset({"road_class"}),
    "os_open_greenspace": frozenset({"function_code"}),
    "os_open_rivers": frozenset({"watercourse_type"}),
    "fls_estate": frozenset({"estate_part"}),
    "ces_assets": frozenset({"asset_class"}),
}

# Aggregates that must not be served on a public route (A5).
INTERNAL_AGG_NAMES: Final[frozenset[str]] = frozenset({"agg_uprn_density"})

SMALL_SITE_MIN: Final[int] = 3
EPC_SUPPRESS_BELOW: Final[int] = 5
NO_OPEN_DATA_LABEL: Final[str] = "no open data"
BANNED_COVERAGE_LABELS: Final[frozenset[str]] = frozenset(
    {"no allocation", "none", "zero", "no data"}
)


def dz2022_zone_ids() -> list[str]:
    """Every 2022 Data Zone code in the official range (7,392)."""
    ids = [f"S{n:08d}" for n in range(DZ2022_LO, DZ2022_HI + 1)]
    if len(ids) != DZ2022_COUNT:
        raise RuntimeError(f"expected {DZ2022_COUNT} zones, got {len(ids)}")
    return ids


def council_slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug:
        raise ValueError(f"empty council slug for {name!r}")
    return slug


def _indexed_status(indexed_licence: str) -> str:
    text = indexed_licence.strip()
    if text == "Open Government Licence 3.0":
        return "ogl"
    if text in {"", "INSPIRE End User Licence"}:
        return "open_other"
    raise ValueError(f"unmapped indexed licence {indexed_licence!r}")


def _council_attribution(name: str) -> str:
    return f"{OGL_ATTRIBUTION} {name}."


# kind, council name, item url, indexed licence text, date, partial, stale.
# Licence text is the index label only. The harvester must read licenseInfo
# on the item before any features are stored (D1).
_COUNCIL_SOURCE_ROWS: Final[tuple[tuple[str, str, str, str, str, bool, bool], ...]] = (
    (
        "ldp",
        "Argyll and Bute",
        "https://data-argyll-bute.opendata.arcgis.com/datasets/62479a00e98f484dbbfdbd78a119d71a_0",
        "",
        "2024-07-17",
        False,
        False,
    ),
    (
        "vdl",
        "Dundee City",
        "https://data.dundeecity.gov.uk/datasets/4a02de43a5dd46febc79e14207697fa5_0",
        "Open Government Licence 3.0",
        "2025-04-24",
        False,
        False,
    ),
    (
        "vdl",
        "City of Edinburgh",
        "https://data.edinburghcouncilmaps.info/datasets/e877c1ae9ee14c47b61c2f8675540667_31",
        "Open Government Licence 3.0",
        "2021-05-27",
        False,
        True,
    ),
    (
        "vdl",
        "Falkirk",
        "https://data-falkirk.opendata.arcgis.com/datasets/af6e593124b04607b3916ca0019a44e5_97",
        "Open Government Licence 3.0",
        "2024-10-17",
        False,
        False,
    ),
    (
        "vdl",
        "Glasgow City",
        "https://data.glasgow.gov.uk/datasets/f1d85a1c43a047ccbdb3838c11ff60c6_0",
        "Open Government Licence 3.0",
        "2024-07-08",
        False,
        False,
    ),
    (
        "ldp",
        "Highland",
        "https://map-highland.opendata.arcgis.com/datasets/b1872ca2e09d45f1bf632f2730113ea8_0",
        "Open Government Licence 3.0",
        "2025-04-25",
        False,
        False,
    ),
    (
        "vdl",
        "Moray",
        "https://data-moray.opendata.arcgis.com/datasets/adbde526e9144bcab7aeca4341c2e421_29",
        "Open Government Licence 3.0",
        "2024-10-24",
        False,
        False,
    ),
    (
        "ldp",
        "North Ayrshire",
        "https://maps-north-ayrshire.opendata.arcgis.com/datasets/0640a23ad6f44a909374d242f89e2918_17",
        "Open Government Licence 3.0",
        "2020-02-06",
        True,
        False,
    ),
    (
        "vdl",
        "North Ayrshire",
        "https://maps-north-ayrshire.opendata.arcgis.com/datasets/f4c91d2a83db449c97909eb6128d4cea_70",
        "Open Government Licence 3.0",
        "2022-01-21",
        False,
        False,
    ),
    (
        "vdl",
        "Perth and Kinross",
        "https://data.pkc.gov.uk/datasets/e09c5b846f2f4f979bbceb347a0d1bb0_43",
        "Open Government Licence 3.0",
        "2023-03-27",
        False,
        False,
    ),
    (
        "vdl",
        "Renfrewshire",
        "https://data-ren.opendata.arcgis.com/datasets/44395149e042462a91dceaffdd4cfdf8_3",
        "",
        "2024-11-28",
        False,
        False,
    ),
    (
        "vdl",
        "South Ayrshire",
        "https://maps-southayrshire.opendata.arcgis.com/datasets/866e3e7983424e408d8e258e42708a75_5",
        "INSPIRE End User Licence",
        "2023-10-16",
        False,
        False,
    ),
    (
        "ldp",
        "Stirling",
        "https://data.stirling.gov.uk/datasets/384d7fb9c4fa4cbdb4fe7e2278af6ac8_0",
        "",
        "2025-03-30",
        False,
        False,
    ),
    (
        "vdl",
        "Stirling",
        "https://data.stirling.gov.uk/datasets/1a8427f9b9914c72ae47ad82d16e9491_0",
        "",
        "2025-03-29",
        False,
        False,
    ),
)


def council_source_entries() -> list[dict[str, Any]]:
    """One internal catalog row per council-direct source. Not a public switch."""
    name_to_code = {name: code for code, name in OFFICIAL_COUNCIL_NAMES.items()}
    rows: list[dict[str, Any]] = []
    for kind, name, url, indexed, date, partial, stale in _COUNCIL_SOURCE_ROWS:
        code = name_to_code[name]
        status = _indexed_status(indexed)
        layer_id = f"{kind}_{council_slug(name)}"
        note_parts: list[str] = []
        if partial:
            note_parts.append("partial: housing additions only")
        if stale:
            note_parts.append("stale vintage")
        rows.append(
            _entry(
                layer_id=layer_id,
                title=f"{name} {'allocations' if kind == 'ldp' else 'vacant and derelict land'}",
                publisher=name,
                source_url=url,
                service_type="ArcGIS Hub feature service (auto)",
                licence_status=status,
                licence_url=url,
                attribution=_council_attribution(name),
                group="Land" if kind == "ldp" else "Places and boundaries",
                internal_only=True,
                flag_name=None,
                dz_aggregate="agg_ldp_council" if kind == "ldp" else "agg_vdl_council",
                refresh="Ad hoc",
                acquisition="auto",
                source_council=code,
                source_kind=kind,
                vintage_date=date,
                partial=partial,
                stale=stale,
                note="; ".join(note_parts) or None,
            )
        )
    return rows


def _entry(
    *,
    layer_id: str,
    title: str,
    publisher: str,
    source_url: str,
    service_type: str,
    licence_status: str,
    licence_url: str,
    attribution: str,
    group: str,
    internal_only: bool,
    flag_name: str | None,
    dz_aggregate: str | None,
    refresh: str,
    acquisition: str,
    source_crs: str = "EPSG:27700",
    minzoom: int | None = None,
    aggregates_only: bool = False,
    display_only: bool = False,
    source_council: str | None = None,
    source_kind: str | None = None,
    vintage_date: str | None = None,
    partial: bool = False,
    stale: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    public = derive_public(
        licence_status,
        flag_name,
        internal_only=internal_only,
    )
    row: dict[str, Any] = {
        "layer_id": layer_id,
        "title": title,
        "publisher": publisher,
        "source_url": source_url,
        "service_type": service_type,
        "source_crs": source_crs,
        "licence": "OGL-3.0" if licence_status == "ogl" else licence_status,
        "licence_status": licence_status,
        "licence_url": licence_url,
        "attribution": attribution,
        "group": group,
        "public": public,
        "flag_name": flag_name,
        "internal_only": internal_only,
        "dz_aggregate": dz_aggregate,
        "refresh": refresh,
        "acquisition": acquisition,
        "minzoom": minzoom,
        "aggregates_only": aggregates_only,
        "display_only": display_only,
        "partial": partial,
        "stale": stale,
    }
    if source_council is not None:
        row["source_council"] = source_council
    if source_kind is not None:
        row["source_kind"] = source_kind
    if vintage_date is not None:
        row["vintage_date"] = vintage_date
    if note is not None:
        row["note"] = note
    return row


def sweep_entries() -> list[dict[str, Any]]:
    """National ADD-2 layers that this PR builds. Dropped ids are absent."""
    return [
        _entry(
            layer_id="epc_domestic",
            title="Domestic energy certificates",
            publisher="Scottish Government",
            source_url=(
                "https://statistics.gov.scot/data/domestic-energy-performance-certificates"
            ),
            service_type="7z bulk (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=OGL_ATTRIBUTION,
            group="Land",
            internal_only=False,
            flag_name=None,
            dz_aggregate="agg_epc",
            refresh="Quarterly",
            acquisition="auto",
            aggregates_only=True,
        ),
        _entry(
            layer_id="os_open_uprn",
            title="Addressable points",
            publisher="Ordnance Survey",
            source_url="https://www.ordnancesurvey.co.uk/products/os-open-uprn",
            service_type="CSV/GPKG (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=OS_ATTRIBUTION,
            group="—",
            internal_only=True,
            flag_name=None,
            dz_aggregate="agg_uprn_density",
            refresh="6-weekly",
            acquisition="auto",
        ),
        _entry(
            layer_id="ofcom_cn_fixed",
            title="Broadband",
            publisher="Ofcom",
            source_url=(
                "https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/"
                "connected-nations-20252/data-downloads-2025"
            ),
            service_type="ZIP CSV, output areas (auto)",
            licence_status="open_other",
            licence_url=(
                "https://www.ofcom.org.uk/phones-and-broadband/coverage-and-speeds/"
                "connected-nations-20252/data-downloads-2025"
            ),
            attribution=OFCOM_ATTRIBUTION,
            group="Land",
            internal_only=False,
            flag_name=None,
            dz_aggregate="agg_ofcom",
            refresh="Annual",
            acquisition="auto",
        ),
        _entry(
            layer_id="nrs_dz_pop_hh",
            title="Population and households",
            publisher="National Records of Scotland",
            source_url="https://www.nrscotland.gov.uk/statistics-and-data",
            service_type="XLSX/CSV (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=NRS_ATTRIBUTION,
            group="Places and boundaries",
            internal_only=False,
            flag_name=None,
            dz_aggregate="agg_nrs",
            refresh="Annual",
            acquisition="auto",
        ),
        _entry(
            layer_id="sg_urban_rural",
            title="Town and country",
            publisher="Scottish Government",
            source_url=(
                "https://www.gov.scot/publications/"
                "scottish-government-urban-rural-classification-2020/"
            ),
            service_type="download (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=SG_ATTRIBUTION,
            group="Places and boundaries",
            internal_only=False,
            flag_name=None,
            dz_aggregate="agg_ur",
            refresh="Biennial",
            acquisition="auto",
        ),
        _entry(
            layer_id="os_open_roads",
            title="Roads",
            publisher="Ordnance Survey",
            source_url="https://www.ordnancesurvey.co.uk/products/os-open-roads",
            service_type="GPKG (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=OS_ATTRIBUTION,
            group="Land",
            internal_only=False,
            flag_name=None,
            dz_aggregate="agg_roads",
            refresh="6-monthly",
            acquisition="auto",
            minzoom=10,
        ),
        _entry(
            layer_id="os_open_greenspace",
            title="Parks and green spaces",
            publisher="Ordnance Survey",
            source_url="https://www.ordnancesurvey.co.uk/products/os-open-greenspace",
            service_type="GPKG (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=OS_ATTRIBUTION,
            group="Places and boundaries",
            internal_only=False,
            flag_name=None,
            dz_aggregate="agg_greenspace",
            refresh="6-monthly",
            acquisition="auto",
        ),
        _entry(
            layer_id="os_open_rivers",
            title="Rivers",
            publisher="Ordnance Survey",
            source_url="https://www.ordnancesurvey.co.uk/products/os-open-rivers",
            service_type="GPKG (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=OS_ATTRIBUTION,
            group="Basemap",
            internal_only=False,
            flag_name=None,
            dz_aggregate=None,
            refresh="6-monthly",
            acquisition="auto",
            display_only=True,
        ),
        _entry(
            layer_id="fls_estate",
            title="Public forests and land",
            publisher="Forestry and Land Scotland",
            source_url=(
                "https://www.spatialdata.gov.scot/geonetwork/srv/eng/"
                "catalog.search#/metadata/cb43b17d"
            ),
            service_type="WFS/download (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=FLS_ATTRIBUTION,
            group="Places and boundaries",
            internal_only=False,
            flag_name=None,
            dz_aggregate="agg_fls",
            refresh="Annual",
            acquisition="auto",
        ),
        _entry(
            layer_id="ces_assets",
            title="Crown Estate Scotland assets",
            publisher="Crown Estate Scotland",
            source_url="https://www.crownestatescotland.com/",
            service_type="REST (auto)",
            licence_status="ogl",
            licence_url=OGL_LICENCE_URL,
            attribution=CES_ATTRIBUTION,
            group="Places and boundaries",
            internal_only=False,
            flag_name=None,
            dz_aggregate=None,
            refresh="Ad hoc",
            acquisition="auto",
            display_only=True,
        ),
    ]


def layers_add2_entries() -> list[dict[str, Any]]:
    """Sweep layers plus internal council-direct discovery rows."""
    return [*sweep_entries(), *council_source_entries()]


def public_sweep_entries() -> list[dict[str, Any]]:
    return [row for row in sweep_entries() if row["public"]]


def validate_entry(row: dict[str, Any]) -> list[str]:
    """Problems for one ADD-2 row. Empty means the row meets A1."""
    problems: list[str] = []
    if "internal_only" not in row:
        problems.append("missing internal_only")
    for field in ("licence_status", "licence_url", "attribution"):
        if field not in row or row[field] in (None, ""):
            problems.append(f"missing {field}")
    status = row.get("licence_status")
    if status not in LICENCE_STATUSES:
        problems.append(f"invalid licence_status={status!r}")
    expected = derive_public(
        str(status),
        row.get("flag_name"),
        internal_only=bool(row.get("internal_only")),
    )
    if row.get("public") != expected:
        problems.append(f"public={row.get('public')!r} != derived {expected!r}")
    if row.get("internal_only") and row.get("public"):
        problems.append("internal_only row is public")
    return problems


def tile_is_public(layer_id: str) -> bool:
    """False for UPRN, council site layers, and anything whose id names a UPRN."""
    if "uprn" in layer_id.lower():
        return False
    if layer_id.startswith(("vdl_", "ldp_")):
        return False
    if layer_id in {"contaminated_land_sites", "vdl_sites"}:
        return False
    return True


def agg_is_public(agg_name: str) -> bool:
    """Public aggregate routes never include a UPRN table."""
    if "uprn" in agg_name.lower():
        return False
    return agg_name not in INTERNAL_AGG_NAMES


def filter_tile_properties(layer_id: str, properties: dict[str, Any]) -> dict[str, Any]:
    allow = TILE_PROPERTY_ALLOWLIST.get(layer_id)
    if allow is None:
        raise KeyError(layer_id)
    extra = set(properties) - allow
    if extra:
        raise ValueError(f"{layer_id} properties outside allowlist: {sorted(extra)}")
    return {key: properties[key] for key in properties if key in allow}


def assert_zone_key(zone_id: object, dz_vintage: object) -> None:
    if not isinstance(zone_id, str) or ZONE_RE.match(zone_id) is None:
        raise ValueError(f"zone_id {zone_id!r} is not a Data Zone code")
    if dz_vintage != DZ2022_VINTAGE:
        raise ValueError(f"dz_vintage {dz_vintage!r} is not {DZ2022_VINTAGE}")


def assert_full_dz2022(rows: list[dict[str, Any]]) -> None:
    """Every 2022 zone is present once. Null and 'unknown' fail."""
    seen: set[str] = set()
    for row in rows:
        assert_zone_key(row.get("zone_id"), row.get("dz_vintage"))
        zone_id = str(row["zone_id"])
        if zone_id in seen:
            raise ValueError(f"duplicate {zone_id}")
        seen.add(zone_id)
    expected = set(dz2022_zone_ids())
    missing = expected - seen
    if missing:
        raise ValueError(f"{len(missing)} Data Zones missing")
    extra = seen - expected
    if extra:
        raise ValueError(f"zones outside the 2022 range: {sorted(extra)[:3]}")
