"""Publication geometry rule: modelled or proxy values and rents are zone-level only.

Laurie's rule (docs/wealth_api.md, "Publication geometry rule"):

* A modelled or proxy land value or rent is published only on zone geometry (a Data Zone).
  No public endpoint, tile or layer attaches one to sub-zone geometry: site, parcel,
  plot, UPRN or building.
* Plain shapes are fine: parcel outlines with no value or rent attached.
* A site-level figure is public only where its source is itself public at site level:
  SVDLS derelict sites, HLS housing land sites, published business rateable values.
  It must be a measured figure from that source (value tier `market`, not modelled).
* Spreading zone values down to plots is internal work: /internal only, behind
  ENABLE_INTERNAL_ENDPOINTS, never a public route.

Every public route declares a `LayerRule` (geometry_level + source_granularity + what it
carries). The declarations are validated when the app is built (an undeclared or illegal
public route stops the core app; an optional router with one is not mounted), when a
processed file is loaded (`check_manifest_entry`), and again row by row in the public
serializers (`check_site_row`, `check_zone_row`). Breaking the rule raises
`PublicationRuleError`; the API turns it into a loud 500 `publication_rule_violation`,
never a silently thinned layer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

GEOMETRY_LEVELS = ("zone", "site", "parcel", "plot", "uprn", "building")
# Private grain: never carries a public value or rent, whatever the source.
PRIVATE_GRAIN = frozenset({"parcel", "plot", "uprn", "building"})
SOURCE_GRANULARITIES = ("zone", "site")
VALUE_BASES = ("none", "measured", "modelled")

# Sources published by their owners at site level. Extending this is a rule change (docs + review).
SITE_PUBLIC_SOURCES = frozenset({"svdls", "hls", "business_rates"})
SITE_SOURCE_LABELS = {
    "svdls": "Scottish Vacant and Derelict Land Survey (derelict sites)",
    "hls": "Housing Land Supply / housing land audit sites",
    "business_rates": "Published non-domestic (business) rateable values",
}
MODELLED_TIERS = frozenset({"proxy", "shadow"})
MODELLED_QUALITY = frozenset({"modelled", "placeholder"})

# Public paths that serve no geometry and no values: exempt from declarations.
EXEMPT_PATHS = frozenset({"/health", "/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"})
INTERNAL_PREFIX = "/internal"

# Modelled council/plot AGR £ property names — never on a public route or tile until
# ECONOMIC_RULES approval. Mirrored in scripts/check_publishable.py (stdlib-only).
FORBIDDEN_PUBLIC_AGR_PROPERTIES = frozenset({
    "annual_ground_rent_plot_gbp",
    "site_rental_per_sqm_gbp",
    "site_capital_per_sqm_gbp",
    "net_contribution_plot_gbp",
    "gross_plot_liability_gbp",
    "vacant_full_agr_gbp",
    "agr_as_pct_of_price",
})

ZONE_CODE_RE = re.compile(r"^S01\d{6}$")
# Column names that carry a value or rent (manifest load-time check).
VALUE_COLUMN_RE = re.compile(r"(^|_)(rent|rents|value|values|price|prices|gbp|rv|valuation|rateable)(_|$)")


class PublicationRuleError(RuntimeError):
    """A modelled/proxy value would reach sub-zone geometry, or a declaration is missing or illegal."""

    def __init__(self, where: str, message: str):
        super().__init__(f"{where}: {message}")
        self.where = where
        self.message = message


@dataclass(frozen=True)
class LayerRule:
    geometry_level: str
    source_granularity: str
    value_basis: str  # none | measured | modelled
    sources: frozenset[str] = frozenset()  # site layers with values: the site-public sources allowed
    site_rows_from: tuple[str, ...] = ()  # zone lookups that also list site rows (checked per row)
    note: str = ""

    @property
    def carries_values(self) -> bool:
        return self.value_basis != "none"


def validate_rule(where: str, rule: LayerRule) -> LayerRule:
    """Raise unless the declaration itself obeys the rule."""
    if rule.geometry_level not in GEOMETRY_LEVELS:
        raise PublicationRuleError(where, f"geometry_level {rule.geometry_level!r} not in {GEOMETRY_LEVELS}")
    if rule.source_granularity not in SOURCE_GRANULARITIES:
        raise PublicationRuleError(where, f"source_granularity {rule.source_granularity!r} not in {SOURCE_GRANULARITIES}")
    if rule.value_basis not in VALUE_BASES:
        raise PublicationRuleError(where, f"value_basis {rule.value_basis!r} not in {VALUE_BASES}")
    if not rule.carries_values:
        if rule.sources:
            raise PublicationRuleError(where, "a layer with no values declares no value sources")
        return rule
    if rule.geometry_level in PRIVATE_GRAIN:
        raise PublicationRuleError(where, f"values or rents on {rule.geometry_level} geometry are never public "
                                   "(plain shapes only; plot spreading belongs on /internal)")
    if rule.geometry_level == "site":
        if rule.source_granularity != "site":
            raise PublicationRuleError(where, "site-level values need a source that is public at site level, "
                                       "not a zone source spread down")
        if rule.value_basis != "measured":
            raise PublicationRuleError(where, "modelled or proxy values are zone-level only")
        if not rule.sources or not rule.sources <= SITE_PUBLIC_SOURCES:
            raise PublicationRuleError(where, f"site sources {sorted(rule.sources)} must be a non-empty subset of "
                                       f"{sorted(SITE_PUBLIC_SOURCES)}")
    if rule.site_rows_from and rule.geometry_level != "zone":
        raise PublicationRuleError(where, "only zone lookups list site rows")
    return rule


# ---- Declarations: every public route, mounted or legacy -----------------------------------------------

_SITE_POINT_TABLES = ("resource_wealth", "eco_wealth")

PUBLIC_ROUTE_RULES: dict[str, LayerRule] = {
    # Wealth API (always mounted)
    "/georgist/wealth": LayerRule("zone", "zone", "modelled", site_rows_from=_SITE_POINT_TABLES,
                                  note="Data Zone surface rent; site rows from point tables are checked per row"),
    "/layers/georgist/surface-rent": LayerRule("zone", "zone", "modelled", note="Data Zone polygons only"),
    # Tax scenario tools live under /internal only (publication_status=blocked until yield calibration).
    "/layers/georgist/resource-rent": LayerRule("site", "site", "measured", sources=SITE_PUBLIC_SOURCES),
    "/layers/georgist/eco-rent": LayerRule("site", "site", "measured", sources=SITE_PUBLIC_SOURCES),
    "/layers/context/data-zones/at": LayerRule("zone", "zone", "none", note="code, vintage, name"),
    # Postcode search: a postcode centroid point (postcodes.io / ONSPD), no value or rent attached.
    "/geocode/postcode": LayerRule("site", "site", "none", note="postcode centroid lat/lng only; no values"),
    # Cadastral (always mounted): RoS INSPIRE parcel shapes only, no value attached.
    "/layers/parcels": LayerRule("parcel", "zone", "none", note="plain parcel shapes (bbox GeoJSON)"),
    "/layers/parcels/at": LayerRule("parcel", "zone", "none", note="plain parcel shape under a point"),
    "/layers/parcels/tiles/{z}/{x}/{y}.png": LayerRule("parcel", "zone", "none", note="plain parcel shapes"),
    "/layers/parcels/tiles/{z}/{x}/{y}": LayerRule("parcel", "zone", "none", note="plain parcel shapes"),
    # NRS Census 2022 Settlements / Localities (always mounted): place polygons, no rent.
    "/layers/open/settlements": LayerRule(
        "site", "site", "none", note="NRS Census 2022 settlement polygons (OGL); no rent",
    ),
    "/layers/open/localities": LayerRule(
        "site", "site", "none", note="NRS Census 2022 locality polygons (OGL); no rent",
    ),
    "/layers/open/settlements/at": LayerRule(
        "site", "site", "none", note="settlement containing a point; no rent",
    ),
    "/layers/open/localities/at": LayerRule(
        "site", "site", "none", note="locality containing a point; no rent",
    ),
    # Open-land platform router (mounted when imports + declarations succeed).
    "/layers/open/vdl": LayerRule("site", "site", "none", note="vacant/derelict survey polygons; no rent"),
    "/layers/open/hla": LayerRule(
        "site", "site", "none", note="housing land audit / supply polygons; no rent"
    ),
    "/layers/open/public-land": LayerRule("site", "site", "none", note="public/Crown holdings overlay; no rent"),
    "/layers/open/flood": LayerRule(
        "site",
        "site",
        "none",
        note="SEPA flood hazard extents (OGL); no rent",
    ),
    "/layers/open/scotwind-intog": LayerRule(
        "site",
        "site",
        "none",
        note="CES ScotWind/INTOG option polygons; ledger row 4; no rent; fees absent from open attributes",
    ),
    "/layers/open/repd-onshore-wind": LayerRule(
        "site",
        "site",
        "none",
        note="REPD onshore wind MW/status points; ledger row 3; natural-capital evidence only, no rent",
    ),
    "/layers/open/ces-aquaculture": LayerRule(
        "site",
        "site",
        "none",
        note=(
            "CES aquaculture seabed lease polygons (OGL); ledger row 5; "
            "attributes/status only — no rent or fee on features"
        ),
    ),
    "/layers/open/data-zones": LayerRule(
        "zone", "zone", "none", note="Data Zone outlines by bbox; code/name only, no rent"
    ),
    "/layers/open/dz-context": LayerRule(
        "zone",
        "zone",
        "measured",
        note="Data Zone HPI/SIMD/population density context; ledger frame row 1; no modelled AGR £",
    ),
    "/layers/open/hydro": LayerRule(
        "site",
        "site",
        "none",
        note="SEPA hydropower CAR sites (OGL); natural-capital inventory; no rent",
    ),
    "/layers/open/sepa-car": LayerRule(
        "site",
        "site",
        "none",
        note="SEPA CAR licences from public-register CSV (download-only); no rent",
    ),
    "/layers/open/ldp": LayerRule(
        "site",
        "site",
        "none",
        note="LDP allocation polygons from PostGIS; ledger nested 1a; no rent",
    ),
    "/layers/open/sssi": LayerRule(
        "site", "site", "none", note="NatureScot SSSI polygons (OGL-3.0); constraint; no rent"
    ),
    "/layers/open/naturescot-designations": LayerRule(
        "site",
        "site",
        "none",
        note="NatureScot SPA/SAC/NNR polygons (OGL-3.0); constraint; no rent",
    ),
    "/layers/open/native-woodland": LayerRule(
        "site", "site", "none", note="Native Woodland Survey polygons from PostGIS; ledger row 1; no rent"
    ),
    "/layers/open/nfi": LayerRule(
        "site", "site", "none", note="NFI woodland polygons from PostGIS; ledger row 1; no rent"
    ),
    "/layers/open/repd": LayerRule(
        "site",
        "site",
        "none",
        note="DESNZ REPD planning-site points (Scotland); ledger row 3; no modelled rent",
    ),
    "/layers/open/crown-estate-leases": LayerRule(
        "site",
        "site",
        "none",
        note="Crown Estate Scotland OGL offshore lease polygons; ledger row 4; no modelled rent",
    ),
    "/ledger": LayerRule(
        "zone",
        "zone",
        "none",
        note="Natural capital ledger skeleton; placeholders only, no published AGR £",
    ),
    "/layers/open/community-ownership": LayerRule(
        "site",
        "site",
        "none",
        note="SG community ownership OGL points from PostGIS; ownership-context; no rent",
    ),
    "/layers/open/lca": LayerRule(
        "zone",
        "zone",
        "none",
        note="Hutton LCA 1:250k capability polygons; constraint (£0); no rent",
    ),
    "/platform/place": LayerRule("site", "site", "none", note="ownership/vacant/gap card; no modelled rent"),
    "/platform/gaps": LayerRule("zone", "zone", "none", note="register gap catalogue"),
    "/api/catalog.json": LayerRule("zone", "zone", "none", note="open-data catalogue"),
    "/api/ledger.json": LayerRule(
        "zone",
        "zone",
        "none",
        note=(
            "natural capital ledger rows 1–10 (+1a), checks/excluded/benchmarks; "
            "zone optional; blocked zones empty; no public modelled £ until ECONOMIC_RULES"
        ),
    ),
    "/api/place-stack.json": LayerRule(
        "zone",
        "zone",
        "none",
        note=(
            "place per-hectare ledger stack (placeholders only); "
            "no modelled AGR £; nothing for blocked zones"
        ),
    ),
    "/api/public-land.json": LayerRule("zone", "zone", "none", note="public-land download meta"),
    "/api/vdl.json": LayerRule("zone", "zone", "none", note="VDL download meta"),
    "/api/ldp.json": LayerRule("zone", "zone", "none", note="LDP allocation coverage meta"),
    "/api/vdl-councils.json": LayerRule(
        "zone",
        "zone",
        "none",
        note="blocked public stub — vacant AGR £ not published",
    ),
    "/api/roll.json": LayerRule(
        "zone",
        "zone",
        "none",
        note="blocked public stub — council AGR roll £ not published",
    ),
    "/api/roll.csv": LayerRule(
        "zone",
        "zone",
        "none",
        note="blocked public stub — council AGR roll £ not published",
    ),
    "/api/place.json": LayerRule("site", "site", "none", note="place card download"),
    "/api/registers.json": LayerRule("zone", "zone", "none", note="registers catalogue"),
    "/api/common-good.json": LayerRule(
        "zone",
        "zone",
        "none",
        note="Common Good register links and spatial gaps; no modelled rent",
    ),
    "/api/crofting.json": LayerRule(
        "zone",
        "zone",
        "none",
        note="Crofting RoC / grazings OGL tables + spatial gaps; no modelled rent",
    ),
    "/downloads": LayerRule("zone", "zone", "none", note="download index"),
    # AGR router (optional). Shapes / metadata / search / context tiles are public.
    # Modelled residual AGR £ (plot grid, cell square, councils-agr, fiscal, validation,
    # assessment packs) lives on /internal/agr/... (auth; see api.agr_routes.internal_router).
    "/signoff": LayerRule("zone", "zone", "none", note="economist sign-off metadata"),
    "/config": LayerRule("zone", "zone", "none", note="agr.yaml public config mirror"),
    "/boundaries/councils": LayerRule("zone", "zone", "none", note="council boundary shapes"),
    "/boundaries/glasgow-ward-18": LayerRule("zone", "zone", "none", note="Ward 18 boundary shape"),
    "/layers/catalog": LayerRule("zone", "zone", "none", note="layer catalogue; no rents"),
    "/layers/councils": LayerRule(
        "zone",
        "zone",
        "none",
        note=(
            "Council outlines + open context metrics; modelled AGR £ properties "
            "scrubbed (FORBIDDEN_PUBLIC_AGR_PROPERTIES)"
        ),
    ),
    "/layers/context/urban-rural/class": LayerRule(
        "site", "site", "none", note="urban-rural class label at a point; no rent",
    ),
    "/layers/context/seabed/at": LayerRule(
        "site",
        "site",
        "none",
        note="Crown Estate lease notes at a point; published lease text, not modelled land AGR",
    ),
    "/layers/context/{layer_id}/tiles/{z}/{x}/{y}": LayerRule(
        "site", "site", "none", note="allowlisted context raster tiles; no AGR values",
    ),
    "/layers/context/{layer_id}": LayerRule(
        "site", "site", "none", note="allowlisted context feature outlines; no AGR values",
    ),
    "/sales/status": LayerRule("zone", "zone", "none", note="sales pipeline status; no rents"),
    "/postcode/{postcode}": LayerRule(
        "site",
        "site",
        "none",
        note="postcode centroid lat/lng only; modelled AGR is /internal/agr/postcode",
    ),
    "/place": LayerRule("site", "site", "none", note="place search; location only, no rent"),
    "/address": LayerRule("site", "site", "none", note="door search; location only, no rent"),
}

for _path, _rule in PUBLIC_ROUTE_RULES.items():
    validate_rule(_path, _rule)


def is_public_path(path: str) -> bool:
    return path not in EXEMPT_PATHS and not path.startswith(INTERNAL_PREFIX)


def undeclared(paths: Iterable[str]) -> list[str]:
    """Public paths with no declaration (the app must not serve these)."""
    return sorted({p for p in paths if is_public_path(p) and p not in PUBLIC_ROUTE_RULES})


def rule_for(path: str) -> LayerRule:
    try:
        return PUBLIC_ROUTE_RULES[path]
    except KeyError:
        raise PublicationRuleError(path, "public route has no geometry_level/source_granularity declaration") from None


# ---- Serializer checks ---------------------------------------------------------------------------------

def _source_key(row: Mapping[str, Any]) -> str:
    return str(row.get("source_id") or "").strip().lower()


def check_site_row(where: str, row: Mapping[str, Any], allowed: frozenset[str] = SITE_PUBLIC_SOURCES) -> None:
    """A site-geometry row about to be published with a figure: measured, from a site-public source."""
    name = row.get("name") or row.get("id") or "?"
    if row.get("value_tier") in MODELLED_TIERS or row.get("quality") in MODELLED_QUALITY:
        raise PublicationRuleError(where, f"site row {name!r} carries a {row.get('value_tier')}/{row.get('quality')} "
                                   "figure; modelled or proxy values are zone-level only")
    if _source_key(row) not in allowed:
        raise PublicationRuleError(where, f"site row {name!r} has source_id {row.get('source_id')!r}; site-level "
                                   f"figures are public only from {sorted(allowed)}")


def site_row_shows_figure(row: Mapping[str, Any]) -> bool:
    """Would the public payload show this point-table row's figure? (Same tests as aggregator._component.)"""
    from georgist.wealth_schema import PUBLIC_LEVELS

    return (row.get("quality") != "placeholder" and (row.get("publication_status") or "ok") != "blocked"
            and row.get("publish_level") in PUBLIC_LEVELS and row.get("annual_rent_gbp") is not None)


def check_site_rows(where: str, rows: Iterable[Mapping[str, Any]]) -> None:
    rule = rule_for(where)
    allowed = rule.sources or SITE_PUBLIC_SOURCES
    for r in rows:
        if site_row_shows_figure(r):
            check_site_row(where, r, allowed)


def check_zone_row(where: str, row: Mapping[str, Any]) -> None:
    """A row about to be drawn on a zone-level layer must be keyed by a real Data Zone code."""
    code = str(row.get("code") or "")
    if not ZONE_CODE_RE.match(code):
        raise PublicationRuleError(where, f"zone layer row keyed {code!r}, not a Data Zone code")


def check_router(module_name: str, paths: Iterable[str]) -> None:
    missing = undeclared(paths)
    if missing:
        raise PublicationRuleError(module_name, f"public route(s) without a publication declaration: {missing}")


# ---- Load-time check for processed files --------------------------------------------------------------

def value_columns(columns: Iterable[str]) -> list[str]:
    return [c for c in columns if VALUE_COLUMN_RE.search(str(c).lower())]


# Key columns that identify sub-zone geometry (a zone key extended by one of these is not zone-level).
SUB_ZONE_KEY_RE = (
    ("uprn", re.compile(r"(^|_)uprn(_|$)")),
    ("building", re.compile(r"(^|_)(building|toid)(_|$)")),
    ("plot", re.compile(r"(^|_)plot(_id)?$")),
    ("parcel", re.compile(r"(^|_)(parcel|inspire|title)(_id)?$")),
    ("site", re.compile(r"(^|_)site(_id|_ref)?$")),
)


def implied_geometry_level(key: tuple[str, ...]) -> str:
    for level, pattern in SUB_ZONE_KEY_RE:
        if any(pattern.search(k.lower()) for k in key):
            return level
    return "zone"


def check_manifest_entry(*, geometry_level: str, source_granularity: str, site_source: str,
                         publish_level: str, key: tuple[str, ...], columns: Iterable[str]) -> list[str]:
    """Problems for one manifest row (empty list = fine). Internal files are exempt (never served)."""
    problems: list[str] = []
    if geometry_level not in GEOMETRY_LEVELS:
        return [f"geometry_level {geometry_level!r} not in {GEOMETRY_LEVELS}"]
    if source_granularity not in SOURCE_GRANULARITIES:
        return [f"source_granularity {source_granularity!r} not in {SOURCE_GRANULARITIES}"]
    implied = implied_geometry_level(key)
    if implied != "zone" and geometry_level == "zone":
        problems.append(f"key {key} identifies {implied} geometry; declare geometry_level {implied!r}")
        geometry_level = implied
    elif tuple(key) == ("code", "vintage") and geometry_level != "zone":
        problems.append(f"keyed (code, vintage) but declares geometry_level {geometry_level!r}")
    if publish_level == "internal":
        return problems
    vals = value_columns(columns)
    if not vals or geometry_level == "zone":
        return problems
    if geometry_level in PRIVATE_GRAIN:
        problems.append(f"{geometry_level}-level file carries value/rent column(s) {vals}; values on sub-zone "
                        "geometry are internal only")
    elif source_granularity != "site" or site_source not in SITE_PUBLIC_SOURCES:
        problems.append(f"site-level value column(s) {vals} need source_granularity 'site' and site_source in "
                        f"{sorted(SITE_PUBLIC_SOURCES)} (got {source_granularity!r}, {site_source!r})")
    return problems
