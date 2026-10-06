"""Wealth Engine tag vocabulary and the `surface_rent_dz` DB row contract.

Column names follow Valuation's `georgist.surface_rent.OUTPUT_COLUMNS` exactly
(valuation/surface-rent-v1 @ 687cf43), with the agreed year rename applied
(`SURFACE_COLUMNS`); the DB adds a few storage-only columns
(`DB_EXTRA_COLUMNS`). Enum VALUES follow the draft economic rules v0.4 section 2:

* `publish_level` (licence level): public_site | public_zone | internal.
* `publication_status`: ok | blocked. A block (e.g. a rules-4.2 ceiling breach)
  withholds the figure publicly but leaves `publish_level` alone, so clearing the
  block restores it.
* Diagnostic columns are internal only. Public endpoints serve an explicit
  allowlist (`PUBLIC_SURFACE_COLUMNS`), never `SELECT *`.
Mirrors backend/db/schema/001_wealth_core.sql. Pure Python: no DB, no network.

Reconciliation (rules 4.2) lives in Valuation's module:
`surface_rent.observed_total_value` (MEAN price x dwellings, same vintage) and
`surface_rent.reconciliation_check` (x GROSS yield). It is not duplicated here.
"""

from __future__ import annotations

from typing import Literal, Mapping, get_args

from georgist import surface_rent as sr
from georgist.dz_lookup import require_vintage, vintage_for_code

ValueTier = Literal["market", "proxy", "shadow"]
Quality = Literal["live", "derived", "modelled", "placeholder"]
FillMethod = Literal["observed_pooled", "shrunk_to_model", "model_filled", "no_residential", "not_applicable"]
UseBasis = Literal["existing_authorised_use", "existing_use", "best_permitted_use", "permitted_use"]
CrosswalkMethod = Literal["none", "pop_hhres_2022", "address_uprn", "value_weighted", "footprint_area"]
PublishLevel = Literal["public_site", "public_zone", "internal"]  # rules v0.4 section 2
PublicationStatus = Literal["ok", "blocked"]  # rules v0.4 section 2; separate from publish_level
PUBLISH_LEVELS: tuple[str, ...] = get_args(PublishLevel)
PUBLICATION_STATUSES: tuple[str, ...] = get_args(PublicationStatus)
PUBLIC_LEVELS: tuple[str, ...] = ("public_site", "public_zone")
ZoneVintage = Literal[2011, 2022]  # integer vintage standard (Data Zones); text labels refused
PlanningSource = Literal["hla", "svdls", "planning_app"]
GeomSource = Literal["surveyed", "ros_title", "point"]

VALUE_TIERS: tuple[str, ...] = get_args(ValueTier)
QUALITIES: tuple[str, ...] = get_args(Quality)
CROSSWALK_METHODS: tuple[str, ...] = get_args(CrosswalkMethod)

# Surface rent is crosswalked by what drives it, never by population or area (rules 11).
SURFACE_CROSSWALK_METHODS: tuple[str, ...] = ("none", "address_uprn", "value_weighted")

# Attribution-only ("of which") and policy columns: never added to measured_rent.
ATTRIBUTION_COLUMNS: tuple[str, ...] = tuple(sr.ATTRIBUTION_ONLY)
POLICY_COLUMNS: tuple[str, ...] = tuple(sr.POLICY_COLUMNS)

# Older Valuation/GIS publish vocabulary -> rules v0.4 levels. A surface row is a
# zone figure, so "public" is public_zone; "zone_total_only" is the rules' own
# definition of public_zone. "blocked" is NOT a level any more (see
# derive_publication_status). Unknown values are refused.
_PUBLISH_MAP = {
    "public": "public_zone",
    "zone_total_only": "public_zone",
    "public_zone": "public_zone",
    "public_site": "public_site",
    "internal": "internal",
}

# Tag Valuation sets on a rules-4.2 ceiling breach (b5fbbe8 also drops the level to
# 'internal'; their v0.4 work emits publication_status='blocked' instead).
BLOCK_TAGS: tuple[str, ...] = ("reconciliation_breach",)

# Rules v0.4 section 2: diagnostics may sit on the row but are internal only.
# Valuation's own list wins when present; this fallback mirrors it.
_FALLBACK_INTERNAL_ONLY = (
    "raw_residual", "rebuild_new_gbp", "remaining_factor", "drc_gbp", "drc_low_gbp", "drc_high_gbp",
    "land_value_low", "land_value_high", "typical_sale_gbp", "mean_median_ratio", "price_skew_flag",
    "rebuild_mix_basis", "floor_area_basis", "brma_mix", "yield_source", "fill_method", "proxy_tags",
)
INTERNAL_ONLY_COLUMNS: tuple[str, ...] = tuple(getattr(sr, "INTERNAL_ONLY_COLUMNS", _FALLBACK_INTERNAL_ONLY)) + (
    "model_version", "config_sha256", "source_sha256",  # DB provenance, internal
)

# What public endpoints may serve from surface_rent_dz: an explicit allowlist.
# Anything not listed (every diagnostic, and any column Valuation adds later)
# stays internal until someone adds it here on purpose.
PUBLIC_SURFACE_COLUMNS: tuple[str, ...] = (
    "code", "vintage", "valuation_date", "price_year", "evidence_year", "dwellings", "count_year",
    "dwellings_source", "vacant_share", "second_home_share",
    "measured_rent", "measured_rent_per_dwelling", "residential_land_ha", "rent_per_res_ha", "uncertainty_low", "uncertainty_high", "uncertainty",
    "infra_share", "planning_uplift", "planning_uplift_flag", "policy_rent", "policy_despec_factor",
    "value_tier", "quality", "publish_level", "publication_status", "commons_class", "net_of",
    "use_basis", "crosswalk_method", "source_id", "licence", "method",
    "negative_residual", "rebuild_status", "absent_from_ros_price_file",
)

# Valuation quality tags that the public API passes through as quality flags (read from the
# internal proxy_tags column; nothing else from proxy_tags is served). plot_bands_borrowed
# (rules v0.7): the zone had no plot-band shares and borrowed its council x urban-rural class
# shares. The API never defaults such zones to all-estate or all-one-off; it only reports it.
QUALITY_FLAG_TAGS: tuple[str, ...] = ("plot_bands_borrowed",)


def quality_flags_sql(alias: str = "") -> str:
    col = f"{alias}.proxy_tags" if alias else "proxy_tags"
    tags = ", ".join("'" + t + "'" for t in QUALITY_FLAG_TAGS)
    return f"ARRAY(SELECT t FROM unnest(COALESCE({col}, '{{}}'::text[])) AS t WHERE t IN ({tags}) ORDER BY t) AS quality_flags"


QUALITY_FLAGS_SQL = quality_flags_sql()


# Storage-only columns the DB adds to Valuation's row.
DB_EXTRA_COLUMNS: tuple[str, ...] = (
    "absent_from_ros_price_file",  # zone never appears in the RoS price file (6 DZ2011 codes)
    "planning_uplift_flag",        # why planning_uplift is NULL, e.g. pending_existing_use_proxy
    "model_version",
    "config_sha256",
    "source_sha256",
)
# Agreed names (rules section 2 + Data Zones vintage standard, Valuation fd03c4b):
#   code, vintage (integer 2011|2022), price_year (money year), evidence_year (raw sales
#   year), count_year (dwelling count year). Our column contract IS Valuation's list.
# Rows still carrying any pre-rename name are refused, never renamed.
PRE_RENAME_NAMES: tuple[str, ...] = ("zone_code", "zone_vintage", "price_base_year", "price_years",
                                     "dwelling_year", "dwelling_year_lag")
AGREED_NAMES: tuple[str, ...] = ("code", "vintage", "price_year", "evidence_year", "count_year")
SURFACE_COLUMNS: tuple[str, ...] = tuple(sr.OUTPUT_COLUMNS)
if set(PRE_RENAME_NAMES) & set(SURFACE_COLUMNS) or not set(AGREED_NAMES) <= set(SURFACE_COLUMNS):
    raise ImportError("surface_rent.OUTPUT_COLUMNS does not use the agreed names "
                      f"{AGREED_NAMES} (Valuation >= fd03c4b required)")
if "publication_status" not in SURFACE_COLUMNS:  # Valuation >= c65090f always emits it
    raise ImportError("surface_rent.OUTPUT_COLUMNS lacks publication_status (rules v0.4)")
SURFACE_DB_COLUMNS: tuple[str, ...] = SURFACE_COLUMNS + DB_EXTRA_COLUMNS
FORBIDDEN_COLUMN_TOKENS = ("rent_per_ha", "per_hectare", "per_sqm", "simd_income")


def map_publish_level(value: str) -> str:
    try:
        return _PUBLISH_MAP[value]
    except KeyError:
        raise ValueError(f"publish_level {value!r} has no rules-v0.4 mapping; not guessed") from None


def derive_publication_status(row: Mapping) -> str:
    """ok | blocked. Valuation's own `publication_status` wins; else a block tag or legacy 'blocked' level."""
    status = row.get("publication_status")
    if status is not None:
        if status not in PUBLICATION_STATUSES:
            raise ValueError(f"bad publication_status {status!r}")
        return status
    tags = row.get("proxy_tags") or ()
    if row.get("publish_level") == "blocked" or any(t in tags for t in BLOCK_TAGS):
        return "blocked"
    return "ok"


def publicly_served(row: Mapping) -> bool:
    """Rules v0.4 section 2: public level, not blocked, not a placeholder."""
    return (
        row.get("publish_level") in PUBLIC_LEVELS
        and row.get("publication_status", "ok") == "ok"
        and row.get("quality") != "placeholder"
    )


def public_surface_view(row: Mapping) -> dict:
    """Only allowlisted columns. Never contains a diagnostic."""
    return {k: row[k] for k in PUBLIC_SURFACE_COLUMNS if k in row}


def check_crosswalk(method: str, *, surface: bool = True) -> str:
    allowed = SURFACE_CROSSWALK_METHODS if surface else CROSSWALK_METHODS
    if method not in allowed:
        raise ValueError(f"crosswalk_method {method!r} not allowed here (allowed: {allowed})")
    return method


def to_db_row(
    row: Mapping,
    *,
    absent_from_ros_price_file: bool = False,
    model_version: str | None = None,
    config_sha256: str | None = None,
    source_sha256: Mapping | None = None,
) -> dict:
    """A Valuation `build_output_row` dict plus DB-only columns, validated against the enums.

    Only the agreed names are accepted (code, vintage, price_year, evidence_year, count_year).
    A row still carrying a pre-rename name (zone_code, price_base_year, dwelling_year, ...) is
    refused, never silently renamed.
    """
    old = sorted(set(PRE_RENAME_NAMES) & set(row))
    if old:
        raise ValueError(f"row uses pre-rename column(s) {old}: the agreed names are {AGREED_NAMES}")
    if set(row) != set(SURFACE_COLUMNS) or len(row) != len(SURFACE_COLUMNS):
        missing, extra = set(SURFACE_COLUMNS) - set(row), set(row) - set(SURFACE_COLUMNS)
        raise ValueError(f"row is not a surface_rent.build_output_row result (missing {sorted(missing)}, "
                         f"extra {sorted(extra)})")
    if row["price_year"] is None:
        raise ValueError("price_year (money year) is required")
    vintage = require_vintage(row["vintage"], "vintage")  # 'DZ2011' is refused, never mapped
    if vintage_for_code(row["code"]) != vintage:
        raise ValueError(f"code {row['code']!r} is not a {vintage} data zone code")
    if row["value_tier"] not in VALUE_TIERS:
        raise ValueError(f"bad value_tier {row['value_tier']!r}")
    if row["quality"] not in QUALITIES:
        raise ValueError(f"bad quality {row['quality']!r}")
    if row["fill_method"] not in get_args(FillMethod):
        raise ValueError(f"bad fill_method {row['fill_method']!r}")
    if row["use_basis"] not in get_args(UseBasis):
        raise ValueError(f"bad use_basis {row['use_basis']!r}")
    check_crosswalk(row["crosswalk_method"], surface=True)
    status = derive_publication_status(row)
    out = {c: row[c] for c in SURFACE_COLUMNS}
    if row["publish_level"] == "blocked":
        # Pre-v0.4 rows lost their licence level when blocked; the most cautious level is kept.
        out["publish_level"] = "internal"
    else:
        out["publish_level"] = map_publish_level(row["publish_level"])
    out["publication_status"] = status
    out.update({
        "absent_from_ros_price_file": bool(absent_from_ros_price_file),
        "planning_uplift_flag": "pending_existing_use_proxy" if row["planning_uplift"] is None else None,
        "model_version": model_version,
        "config_sha256": config_sha256,
        "source_sha256": dict(source_sha256) if source_sha256 is not None else None,
    })
    assert tuple(out) == SURFACE_DB_COLUMNS
    return out


def per_person(value_gbp: float, value_vintage: int, population: int, population_vintage: int) -> float:
    """Per-person figures divide by SAME-vintage population only (rules 2). Vintages are integers."""
    if require_vintage(value_vintage) != require_vintage(population_vintage):
        raise ValueError(f"vintage mismatch: value {value_vintage} vs population {population_vintage}")
    if not population or population <= 0:
        raise ValueError("population must be positive")
    return value_gbp / population
