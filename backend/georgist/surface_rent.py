"""Residual surface land rent: pure functions.

Spec: docs/surface_rent_spec.md. Rules: scotland-rules/ECONOMIC_RULES.md v0.6 (Georgist draft).

MEAN price (RoS, data zone) minus the MEAN depreciated rebuild cost of the same
homes (sold mix where available) gives a residual land value. A land yield (BRMA x urban-rural
class, gross rent/price less config deductions) turns it into measured rent.

Rules applied here:
- 6.2 / tier: every land value is a PROXY.
- 6.2: rebuild £/m² must be configured, never defaulted. v1 uses an
  OPEN_ESTIMATE band (low/central/high), and the band is carried through.
- 6.3: `raw_residual` is stored as computed, negatives included. The published
  value is floored at 0 and flagged `negative_residual`.
- 6.4: yields come from config or evidence. Land yield should come out below
  gross yield, and is flagged otherwise.
- 6.7: no income, employment or deprivation drivers.
- 4.3: `infra_share` and `planning_uplift` are breakdowns. They cannot be totalled.
- 13: policy de-speculation sits in `policy_rent`, never in `measured_rent`.
- 11: surface crosswalk uses address_uprn or value_weighted. Never area, never population.
- 4.2: zone ceiling uses MEAN price x dwellings on the SAME vintage.
- 6.1: MEAN for anything that adds up; zone total = (mean P - mean DRC) x count,
  per-home = total / count. Median is display only (`typical_sale_gbp`) plus a
  small-sample skew flag. Rebuild mix basis is stamped (sold | all_stock).
- 1: land yield IS r - g (one config number). Separate r, g only in scenario
  runs, asserted to satisfy r - g = land_yield.
- 2 / 4.2: raw RoS prices keep their sales year as `evidence_year`; they are
  moved to `price_year` only through a RECORDED index (council UK HPI, tag
  `indexed_council_hpi`). price_year == rebuild price base == dwelling
  count_year (dwellings join on price_year), and dwellings are on the price
  vintage. A missing count year is flagged, never filled from another year.
  Totals refuse rows with differing price_year.
- 6.1: a suppressed zone is filled by the model, never copied from a neighbour.

Nothing here reads the database or the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import yaml

METHOD = "residual_drc_surface_v1"
VALUE_TIER = "proxy"
CONFIG_PATH = Path(__file__).resolve().parents[2] / "data" / "config" / "surface.yaml"

RATE_BASES = ("bcis_median_type", "bcis_median_type_override", "bcis_median_all_rows", "generic_estate",
              "one_off_detached", "generic_detached")  # rules 6.2 v0.7
REBUILD_EXTRA_TYPES = ("detached_estate", "detached_one_off")  # rules 6.2 v0.7: estate (volume-builder) and one-off detached rates
ONEOFF_RATE_TYPES = ("detached_one_off", "detached")  # rate for the non-estate detached share (detached = generic blend)
DWELLING_TYPES = (
    "detached",
    "semi_detached",
    "terraced",
    "flat_purpose_built",
    "flat_conversion",
    "other",
)
SCENARIOS = ("low", "central", "high")  # DRC scenarios: low = low rebuild x short life x low floor -> HIGH land (rules 6.2 v0.6 corners)
FILL_METHODS = ("observed_pooled", "shrunk_to_model", "model_filled", "no_residential", "not_applicable")

# Rules v0.7: zones with zero dwellings get NO residential surface rent (null, never 0), whatever RoS says.
ZERO_DWELLINGS_FLAG = "zero_dwellings"
ZERO_DWELLINGS_FALLBACK = ("S01010206", "S01010226", "S01010227")  # DZ2011 demolished Glasgow estates (Data Zones dwellings_by_year)
SAMPLE_PURPOSES = ("model_fit", "yield_calibration", "fill_donor", "holdout")
POP_MISMATCH_FLAG = "pop_dwellings_mismatch"   # Data Zones zone_spine flag (e.g. S01011598): per-resident figures hidden
QUALITY = ("live", "derived", "modelled", "placeholder")
REBUILD_MIX_BASES = ("sold", "all_stock")  # rules 6.1
PUBLISH_LEVELS = ("public_site", "public_zone", "internal")  # rules 2: licence level
PUBLICATION_STATUSES = ("ok", "blocked")  # rules 2 (v0.4): separate from publish_level; 4.2 breach -> blocked
DWELLING_YEAR_POLICIES = ("strict", "lag_allowed")  # lag_allowed pending Georgist ruling; default strict

# Rules 2 (v0.4): required on every row; a row missing any is rejected.
REQUIRED_FIELDS = (
    "commons_class", "value_tier", "quality", "uncertainty_low", "uncertainty_high", "net_of", "use_basis",
    "crosswalk_method", "publish_level", "source_id", "licence", "price_year",
)
# Rules 2 (v0.4): diagnostics may sit on the row but are internal only, never served publicly.
INTERNAL_ONLY_COLUMNS = (
    "raw_residual", "rebuild_new_gbp", "remaining_factor", "drc_gbp", "drc_low_gbp", "drc_high_gbp", "drc_swing_gbp",
    "land_value_low", "land_value_high", "typical_sale_gbp", "mean_median_ratio", "price_skew_flag",
    "rebuild_mix_basis", "floor_area_basis", "brma_mix", "yield_source", "fill_method", "proxy_tags",
)
FLOOR_AREA_BASES = ("mean", "median", "default")
RES_LAND_LOW_CONFIDENCE = ("weak_match", "mask_too_big", "uprn_exceeds")  # GIS dz_residential_land quality
RES_LAND_SOURCES = ("gis_residential_land", "settlement_area")  # rules 6.4 v0.5; never whole-zone area
CROSSWALK_METHODS = ("none", "pop_hhres_2022", "address_uprn", "value_weighted", "footprint_area")
REBUILD_STATUSES_USABLE = ("OPEN_ESTIMATE", "LICENSED")

ATTRIBUTION_ONLY = ("infra_share", "planning_uplift")  # rules 4.3
POLICY_COLUMNS = ("policy_rent", "policy_despec_factor")  # rules 13
from georgist.surface_zones import VINTAGES, validate_code, vintage_int  # noqa: E402

SUMMABLE = ("measured_rent",)

OUTPUT_COLUMNS = (
    "code",
    "vintage",
    "valuation_date",
    "price_year",
    "ur6_class",
    "ur8_class",
    "dwellings",
    "sales_n_pooled",
    "evidence_year",
    "evidence_years",
    "price_measure",
    "price_gbp",
    "price_indexed_gbp",
    "price_index_series",
    "price_index_factor",
    "typical_sale_gbp",
    "mean_median_ratio",
    "price_skew_flag",
    "count_year",
    "count_year_lag",
    "dwellings_source",
    "vacant_share",
    "second_home_share",
    "rebuild_status",
    "rebuild_mix_basis",
    "floor_area_basis",
    "rebuild_new_gbp",
    "remaining_factor",
    "drc_gbp",
    "drc_low_gbp",
    "drc_high_gbp",
    "drc_swing_gbp",
    "raw_residual",
    "negative_residual",
    "land_value",
    "land_value_low",
    "land_value_high",
    "land_value_zone_total",
    "yield_gross",
    "yield_land",
    "yield_source",
    "brma_mix",
    "measured_rent_per_dwelling",
    "measured_rent_per_resident",
    "measured_rent",
    "residential_land_ha",
    "rent_per_res_ha",
    "uncertainty_low",
    "uncertainty_high",
    "uncertainty",
    "infra_share",
    "planning_uplift",
    "policy_despec_factor",
    "policy_rent",
    "value_tier",
    "quality",
    "fill_method",
    "publish_level",
    "publication_status",
    "commons_class",
    "net_of",
    "use_basis",
    "crosswalk_method",
    "source_id",
    "licence",
    "proxy_tags",
    "method",
)
AREA_TOKENS = ("per_ha", "per_hectare", "per_sqm", "per_m2", "_ha", "hectare", "area")


class PendingSourceError(RuntimeError):
    """A required parameter is unsourced. A run must not proceed."""


class ForbiddenDriverError(ValueError):
    """A driver breaks the exclusion rule (6.7)."""


class AttributionOnlyError(ValueError):
    """Attempt to total a breakdown or policy column (rules 4.3, 13)."""


class VintageMismatchError(ValueError):
    """Price and dwelling counts are on different geography vintages (rules 4.2)."""


class YearMismatchError(ValueError):
    """Price and dwelling counts are for different years (rules 2)."""


class YieldIdentityError(ValueError):
    """Scenario r and g do not satisfy r - g = land_yield (rules 1)."""


# --------------------------------------------------------------------------- config


def load_config(path: Path | str = CONFIG_PATH) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)["surface_rent"]


def rebuild_uplift(config: Mapping, price_year: int | None = None) -> float:
    """Factor taking the rebuild band from its price base to `price_year`.

    Rules 2: price minus rebuild only at the same price year. A year with no
    sourced factor raises; it is never assumed to be 1.0.
    """
    rebuild = config.get("rebuild") or {}
    factors = (rebuild.get("uplift") or {}).get("factor_by_price_year") or {}
    year = int(price_year) if price_year is not None else int(str(rebuild["valuation_date"])[:4])
    if year not in {int(k) for k in factors}:
        raise PendingSourceError(f"no rebuild uplift factor to price_year {year} (rebuild.uplift.factor_by_price_year)")
    return float({int(k): v for k, v in factors.items()}[year])


def rebuild_price_base_year(config: Mapping) -> int:
    return int(str(config["rebuild"]["price_base"])[:4])


def rebuild_band(config: Mapping, price_year: int | None = None) -> dict[str, dict[str, float]]:
    """{type: {low, central, high}} £/m² at `price_year`. Raises if pending, incomplete or unordered.

    There is deliberately no default. OPEN_ESTIMATE is usable but is carried
    into every row as `rebuild_status` and as the uncertainty band.
    """
    rebuild = config.get("rebuild") or {}
    status = rebuild.get("status")
    if status not in REBUILD_STATUSES_USABLE:
        raise PendingSourceError(f"surface_rent.rebuild.status is {status!r}; need one of {REBUILD_STATUSES_USABLE}")
    if not rebuild.get("sources"):
        raise PendingSourceError("rebuild.sources must list the evidence")
    table = rebuild.get("gbp_per_m2") or {}
    if "rate_basis" in rebuild:
        rate_basis(config)  # rules 6.2 v0.7: every rate declares its basis
    uplift = rebuild_uplift(config, price_year)
    out: dict[str, dict[str, float]] = {}
    for t in DWELLING_TYPES:
        cell = table.get(t)
        if not isinstance(cell, Mapping) or any(not isinstance(cell.get(s), (int, float)) for s in SCENARIOS):
            raise PendingSourceError(f"rebuild £/m² band missing for {t}")
        if not cell["low"] <= cell["central"] <= cell["high"]:
            raise ValueError(f"rebuild band for {t} not ordered low <= central <= high")
        out[t] = {s: float(cell[s]) * uplift for s in SCENARIOS}
    for t in REBUILD_EXTRA_TYPES:  # optional procurement-route rates (rules 6.2 v0.7)
        cell = table.get(t)
        if cell is None:
            continue
        if any(not isinstance(cell.get(s), (int, float)) for s in SCENARIOS) or not cell["low"] <= cell["central"] <= cell["high"]:
            raise ValueError(f"rebuild band for {t} incomplete or not ordered")
        out[t] = {s: float(cell[s]) * uplift for s in SCENARIOS}
    return out


def rebuild_rates(config: Mapping, scenario: str = "central", price_year: int | None = None) -> dict[str, float]:
    if scenario not in SCENARIOS:
        raise ValueError(f"scenario must be one of {SCENARIOS}")
    return {t: band[scenario] for t, band in rebuild_band(config, price_year).items()}


def derive_rebuild_band(rebuild_cfg: Mapping) -> dict[str, dict[str, int]]:
    """Recompute the published band from base rows x factors (audit of the derivation)."""
    loc = rebuild_cfg["factors"]["location_scotland"]
    on = rebuild_cfg["factors"]["on_costs"]
    out: dict[str, dict[str, int]] = {}
    for t, spec in rebuild_cfg["base_rows_gbp_per_m2"].items():
        rows = spec["rows"] if isinstance(spec, Mapping) else spec
        base = {"low": min(rows), "central": sum(rows) / len(rows), "high": max(rows)}
        if isinstance(spec, Mapping) and "high_override" in spec:
            base["high"] = spec["high_override"]
        out[t] = {s: round(base[s] * loc[s] * on[s]) for s in SCENARIOS}
    return out


def region_factor(config: Mapping, council_code: str | None) -> float:
    factors = (config.get("rebuild") or {}).get("region_factors") or {}
    if "default" not in factors:
        raise PendingSourceError("rebuild.region_factors.default must be explicit")
    return float(factors.get(council_code or "", factors["default"]))


def validate_drivers(drivers: Iterable[str], config: Mapping) -> list[str]:
    """Reject any driver whose name matches an excluded (endogenous) concept."""
    forbidden = [s.lower() for s in (config.get("drivers") or {}).get("forbidden_substrings", [])]
    if not forbidden:
        raise ValueError("drivers.forbidden_substrings must be configured")
    drivers = list(drivers)
    bad = [d for d in drivers if any(s in d.lower() for s in forbidden)]
    if bad:
        raise ForbiddenDriverError(f"excluded drivers (rule 6.7): {bad}")
    return drivers


# --------------------------------------------------------------------------- price


@dataclass(frozen=True)
class YearPrice:
    """One RoS zone-year. mean/median None = suppressed (absent row), not zero."""

    year: int
    sales_n: int | None
    mean_gbp: float | None
    median_gbp: float | None


@dataclass(frozen=True)
class PooledPrice:
    price_gbp: float | None
    sales_n: int
    years: str | None
    measure: str
    tags: tuple[str, ...]
    evidence_year: int | None = None  # sales year the pooled price is expressed in (latest RoS year, or index_to_year)


def _measure_value(obs: YearPrice, measure: str) -> float | None:
    if measure == "mean":
        value = obs.mean_gbp
    elif measure == "median":
        value = obs.median_gbp
    else:
        raise ValueError(f"price measure must be mean or median, got {measure!r}")
    if value is None or value <= 0:
        return None
    return float(value)


def pool_prices(
    observations: Sequence[YearPrice],
    *,
    latest_year: int,
    measure: str,
    pool_years: int,
    pool_years_max: int,
    n_min: int,
    index_factor: Mapping[int, float] | None = None,
    index_to_year: int | None = None,
) -> PooledPrice:
    """Count-weighted pool of indexed zone prices over a window that widens once.

    For the MEAN this is exact: Σ n·mean / Σ n is the pooled mean. With
    `index_factor`, prices are expressed in `index_to_year` (required);
    otherwise in `latest_year`, and every pooled year must equal it.
    """
    if index_factor is not None and index_to_year is None:
        raise ValueError("index_to_year is required with index_factor (rules 2: stated evidence_year)")
    evidence_year = int(index_to_year) if index_factor is not None else int(latest_year)
    for window in (pool_years, pool_years_max):
        first = latest_year - window + 1
        total_n, weighted = 0, 0.0
        used: list[int] = []
        for obs in observations:
            if not (first <= obs.year <= latest_year):
                continue
            value = _measure_value(obs, measure)
            if value is None or not obs.sales_n:
                continue
            if index_factor is None:
                if obs.year != latest_year:
                    raise ValueError("pooling several years needs index_factor (rules 2: no mixing price years unindexed)")
                factor = 1.0
            elif obs.year in index_factor:
                factor = float(index_factor[obs.year])
            else:
                raise KeyError(f"no index factor for {obs.year}")
            total_n += int(obs.sales_n)
            weighted += int(obs.sales_n) * value * factor
            used.append(obs.year)
        if total_n >= n_min:
            tags = [f"pooled_{window}y"]
            if measure == "median" and len(used) > 1:
                tags.append("pooled_median_approx")
            return PooledPrice(weighted / total_n, total_n, f"{min(used)}-{max(used)}", measure, tuple(tags), evidence_year)
    return PooledPrice(None, 0, None, measure, ("suppressed_all_years",), evidence_year)


def price_skew_flag(mean_gbp: float | None, median_gbp: float | None, sales_n: int, skew_cfg: Mapping) -> tuple[float | None, bool]:
    """Rules 6.1 robustness flag: mean/median unusually high in a small-sales zone."""
    if not mean_gbp or not median_gbp or median_gbp <= 0:
        return None, False
    ratio = float(mean_gbp) / float(median_gbp)
    flag = int(sales_n) < int(skew_cfg["small_sales_n_below"]) and ratio >= float(skew_cfg["mean_median_ratio_min"])
    return ratio, flag


# --------------------------------------------------------------------------- dwellings (Data Zones)


@dataclass(frozen=True)
class DwellingCount:
    count: int | None
    year: int
    vintage: str
    tags: tuple[str, ...] = ()
    source: str = "unspecified"
    vacant_share: float | None = None        # rules 6.4 (v0.5): reported alongside, never changes rent
    second_home_share: float | None = None


def dwellings_for(
    counts: Mapping[tuple[str, str, int], int], code: str, vintage: str, year: int, *, source: str = "unspecified",
    source_tags: Sequence[str] = (),
) -> DwellingCount:
    """Exact (code, vintage, year) lookup. A missing year is flagged, NEVER filled from the nearest year."""
    key = (code, vintage, int(year))
    if key in counts and counts[key] is not None:
        v = counts[key]
        if isinstance(v, Mapping):  # {"dwellings_total", "vacant_share", "second_home_share"}
            return DwellingCount(int(v["dwellings_total"]), int(year), vintage, tuple(source_tags), source,
                                 v.get("vacant_share"), v.get("second_home_share"))
        return DwellingCount(int(v), int(year), vintage, tuple(source_tags), source)
    return DwellingCount(None, int(year), vintage, ("dwellings_missing_year",) + tuple(source_tags), source)


# --------------------------------------------------------------------------- price indexation (UK HPI)


HPI_TYPES = ("detached", "semi_detached", "terraced", "flat")


@dataclass(frozen=True)
class CouncilHPI:
    """UK HPI points for one council area. base = annual mean of monthly index in the
    raw price year; target = the month matching the rebuild price base."""

    council_code: str
    base_period: str
    target_period: str
    base_index: Mapping[str, float]   # keys: all + HPI_TYPES
    target_index: Mapping[str, float]
    base_price: Mapping[str, float]   # UK HPI average price by type in the base period (value weights)


@dataclass(frozen=True)
class IndexedPrice:
    price_raw_gbp: float | None
    evidence_year: int          # RoS sales year of the raw price
    price_indexed_gbp: float | None
    price_year: int             # year the indexed price is expressed in (= rebuild price base)
    factor: float
    series: str
    tags: tuple[str, ...] = ()


def hpi_factor(hpi: CouncilHPI, type_mix: Mapping[str, float] | None) -> tuple[float, str, tuple[str, ...]]:
    """Council UK HPI factor base -> target.

    By property type where a zone type mix is given: value-weighted (Laspeyres)
    f = Σ s_t·P_t·f_t / Σ s_t·P_t with council base average prices P_t, so the
    zone's MEAN price moves as its own mix would. Otherwise the all-dwellings index.
    """
    tags = ["indexed_council_hpi"]
    w = {t: float(type_mix.get(t, 0.0)) for t in HPI_TYPES} if type_mix else {}
    usable = all(t in hpi.base_index and t in hpi.target_index and t in hpi.base_price for t in HPI_TYPES)
    if w and sum(w.values()) > 0 and usable:
        num = sum(w[t] * hpi.base_price[t] * hpi.target_index[t] / hpi.base_index[t] for t in HPI_TYPES)
        den = sum(w[t] * hpi.base_price[t] for t in HPI_TYPES)
        series = f"UKHPI council {hpi.council_code} type indices (value-weighted by zone type mix), {hpi.base_period} mean -> {hpi.target_period}"
        return num / den, series, tuple(tags + ["hpi_by_property_type"])
    if "all" not in hpi.base_index or "all" not in hpi.target_index:
        raise PendingSourceError(f"no all-dwellings UK HPI for {hpi.council_code}")
    series = f"UKHPI council {hpi.council_code} all-dwellings index, {hpi.base_period} mean -> {hpi.target_period}"
    return hpi.target_index["all"] / hpi.base_index["all"], series, tuple(tags + ["hpi_all_dwellings"])


def index_price(
    pooled: PooledPrice, *, price_year: int, factor: float | None = None, series: str | None = None,
    tags: Sequence[str] = (), extreme_log_abs: float | None = None,
) -> IndexedPrice:
    """Move the raw pooled MEAN price from its evidence_year to price_year through a recorded index.

    The raw price is never altered. If evidence_year == price_year no index is
    needed (factor 1, series 'none'); otherwise factor and series are required.
    """
    import math

    if pooled.evidence_year is None:
        raise ValueError("pooled price has no evidence_year")
    if int(pooled.evidence_year) != int(price_year):
        if factor is None or not series or series == "none":
            raise YearMismatchError(
                f"evidence_year {pooled.evidence_year} != price_year {price_year} and no recorded index"
            )
    else:
        factor, series = (1.0, "none") if factor is None else (factor, series or "none")
    if factor <= 0:
        raise ValueError("index factor must be positive")
    out_tags = list(tags)
    if extreme_log_abs is not None and abs(math.log(factor)) > float(extreme_log_abs):
        out_tags.append("index_factor_extreme")
    indexed = pooled.price_gbp * factor if pooled.price_gbp is not None else None
    return IndexedPrice(pooled.price_gbp, int(pooled.evidence_year), indexed, int(price_year), float(factor), series, tuple(out_tags))


def assert_base_alignment(
    *, price_year: int, rebuild_base_year: int, dwelling_year: int, price_vintage: str, dwelling_vintage: str,
    policy: str = "strict", max_lag_years: int = 0,
) -> int:
    """Rules 2 / 4.2: index base == rebuild price base; dwellings on the same vintage.

    policy 'strict' (default): dwelling count_year == price_year.
    policy 'lag_allowed' (pending Georgist ruling): dwelling_year may be the latest
    PUBLISHED year up to `max_lag_years` before the base, never after it and never
    extrapolated. Returns the lag in years (0 when aligned).
    """
    if price_vintage != dwelling_vintage:
        raise VintageMismatchError(f"price on {price_vintage} but dwellings on {dwelling_vintage}")
    if int(price_year) != int(rebuild_base_year):
        raise YearMismatchError(f"price_year {price_year} != rebuild price base {rebuild_base_year}")
    if policy not in DWELLING_YEAR_POLICIES:
        raise ValueError(f"dwelling year policy must be one of {DWELLING_YEAR_POLICIES}")
    lag = int(price_year) - int(dwelling_year)
    if lag == 0:
        return 0
    if policy == "strict" or lag < 0 or lag > int(max_lag_years):
        raise YearMismatchError(
            f"dwelling count_year {dwelling_year} vs price_year {price_year} (policy {policy}, max lag {max_lag_years})"
        )
    return lag


def assert_same_year_vintage(*, price_year: int, price_vintage: str, dwelling_year: int, dwelling_vintage: str) -> None:
    if price_vintage != dwelling_vintage:
        raise VintageMismatchError(f"price on {price_vintage} but dwellings on {dwelling_vintage}")
    if int(price_year) != int(dwelling_year):
        raise YearMismatchError(f"price_year {price_year} != dwelling_year {dwelling_year}")


def observed_total_value(
    *, mean_price_gbp: float, dwellings: int, price_vintage: str, dwellings_vintage: str,
    price_year: int, dwellings_year: int, measure: str = "mean",
) -> float:
    """Rules 4.2: zone observed total = MEAN price x dwelling count, same vintage and year.

    `price_year` is the year the price is EXPRESSED in: pass the indexed
    price with its price_year (see `index_price`), never the evidence_year.
    """
    if measure != "mean":
        raise ValueError("ceiling total must use the MEAN price (mean x count is the total)")
    assert_same_year_vintage(price_year=price_year, price_vintage=price_vintage, dwelling_year=dwellings_year, dwelling_vintage=dwellings_vintage)
    return float(mean_price_gbp) * int(dwellings)


# --------------------------------------------------------------------------- rebuild


@dataclass(frozen=True)
class MixComponent:
    """Share of the zone's (sold) stock of one dwelling type, with EPC attributes."""

    dwelling_type: str
    share: float
    floor_area_m2: float
    age_band: str


def choose_rebuild_mix(
    sold_mix: Sequence[MixComponent] | None, stock_mix: Sequence[MixComponent] | None, *, sold_records: int, min_sold_records: int
) -> tuple[Sequence[MixComponent], str]:
    """Rules 6.1: rebuild mix should match the homes that sold. Falls back to the stock, flagged."""
    if sold_mix and sold_records >= int(min_sold_records):  # sold proxy: EPCs from the last 10 years (rules 6.1)
        return sold_mix, "sold"
    if stock_mix:
        return stock_mix, "all_stock"
    raise ValueError("no dwelling mix (sold or stock)")


def epc_coverage_tags(coverage: float | None) -> tuple[str, ...]:
    """Rules 6.1 (v0.4): EPC coverage > 100% (certificates surviving demolition) ->
    use the recent-certificate mix only, and flag."""
    return ("epc_coverage_over_100_recent_only",) if coverage is not None and coverage > 1.0 else ()


# ---- EPC rollup (GIS epc_dz_rollup.csv) -> rebuild inputs

EPC_AGE_COLUMNS = {  # rollup column suffix -> config age band label
    "pre1919": "before 1919", "1919_1929": "1919-1929", "1930_1949": "1930-1949", "1950_1964": "1950-1964",
    "1965_1975": "1965-1975", "1976_1983": "1976-1983", "1984_1991": "1984-1991", "1992_1998": "1992-1998",
    "1999_2002": "1999-2002", "2003_2007": "2003-2007", "2008_on": "2008 onwards",
}


@dataclass(frozen=True)
class ZoneRebuildInputs:
    type_shares: Mapping[str, float]       # over DWELLING_TYPES, sums to 1
    age_shares: Mapping[str, float] | None  # over config age bands, sums to 1; None -> default remaining factor
    floor_area_m2: float
    floor_area_basis: str                   # mean | median | default
    mix_basis: str                          # sold | all_stock
    source: str                             # epc_recent10 | epc_all_time | nrs2017
    tags: tuple[str, ...]
    area_by_group: Mapping[str, float] | None = None  # {'house': m2, 'flat': m2} means where published
    estate_fraction: float | None = None    # share of post-1980 detached homes taking the estate rate (None = pending)
    estate_bands: tuple[str, ...] = ()      # EPC age bands counted as post-1980
    oneoff_type: str = "detached"           # rate type for the non-estate detached share once a split is attached

    def area_for(self, dwelling_type: str) -> float:
        g = self.area_by_group or {}
        if dwelling_type.startswith("flat") and "flat" in g:
            return float(g["flat"])
        if dwelling_type in ("detached", "detached_estate", "detached_one_off", "semi_detached", "terraced") and "house" in g:
            return float(g["house"])
        return float(self.floor_area_m2)


def _f(row: Mapping, key: str) -> float | None:
    v = row.get(key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v else v  # NaN -> None


def epc_type_shares(row: Mapping, prefix: str = "") -> dict[str, float] | None:
    """EPC property-type and built-form MARGINALS -> rebuild types.

    flats + maisonettes -> flat_purpose_built (conversions not identified);
    park homes + unknown type -> other; houses + bungalows split detached /
    semi / terraced (mid, end, enclosed) in proportion to the built-form shares
    with unknown built form dropped. The rollup has no type x form cross-tab,
    and built form is recorded for flats too, so this is an approximation.
    """
    g = lambda k: _f(row, f"{prefix}{k}")  # noqa: E731
    keys = ("pt_house_share", "pt_flat_share", "pt_bungalow_share", "pt_maisonette_share", "pt_park_home_share", "pt_unknown_share")
    if any(g(k) is None for k in keys):
        return None
    flat = g("pt_flat_share") + g("pt_maisonette_share")
    other = g("pt_park_home_share") + g("pt_unknown_share")
    house = g("pt_house_share") + g("pt_bungalow_share")
    det = g("bf_detached_share") or 0.0
    semi = g("bf_semi_detached_share") or 0.0
    terr = sum(g(k) or 0.0 for k in ("bf_mid_terrace_share", "bf_end_terrace_share",
                                     "bf_enclosed_mid_terrace_share", "bf_enclosed_end_terrace_share"))
    known = det + semi + terr
    out = dict.fromkeys(DWELLING_TYPES, 0.0)
    out["flat_purpose_built"] = flat
    if known > 0:
        out["detached"], out["semi_detached"], out["terraced"] = (house * det / known, house * semi / known, house * terr / known)
        out["other"] = other
    else:
        out["other"] = other + house
    total = sum(out.values())
    if total <= 0:
        return None
    return {t: v / total for t, v in out.items()}


def epc_age_shares(row: Mapping, prefix: str = "") -> dict[str, float] | None:
    vals = {label: _f(row, f"{prefix}age_{suffix}_share") or 0.0 for suffix, label in EPC_AGE_COLUMNS.items()}
    total = sum(vals.values())  # unknown band dropped, known bands renormalised
    return {k: v / total for k, v in vals.items()} if total > 0 else None


def nrs2017_type_shares(row: Mapping) -> dict[str, float] | None:
    vals = {"detached": _f(row, "type_detached") or 0.0, "semi_detached": _f(row, "type_semi_detached") or 0.0,
            "terraced": _f(row, "type_terraced") or 0.0, "flat_purpose_built": _f(row, "type_flat") or 0.0,
            "other": _f(row, "type_unknown") or 0.0}
    total = sum(vals.values())
    if total <= 0:
        return None
    out = dict.fromkeys(DWELLING_TYPES, 0.0)
    out.update({k: v / total for k, v in vals.items()})
    return out


EPC_PRIMARY = ("all_time", "recent10")


def zone_rebuild_inputs(
    epc_row: Mapping | None, nrs2017_row: Mapping | None, *, default_area_m2: float, min_tfa_n: int = 5,
    primary: str = "all_time",
) -> ZoneRebuildInputs:
    """Rebuild inputs for one DZ2011 zone.

    Mix source (team decision 2026-10-06): the all-certificate EPC columns are
    primary (73% coverage); `recent10_` (54%) is the sensitivity
    (primary='recent10'). Zones with EPC coverage > 100% use recent10 whatever
    the primary (rules 6.1: recent certificates only), flagged. If the chosen
    family is suppressed, the other family is used, flagged. Last resort: NRS
    2017 DZ2011 type mix + default floor area, flagged.

    Floor area (rules v0.4/0.5: MEAN for totals): house mean (House+Bungalow) for
    detached/semi/terraced, flat mean (Flat+Maisonette) for flats, each only with
    >= min_tfa_n certificates; else the zone mean `tfa_mean_m2`; else the stated
    default (tagged). A median is used only if the rollup has no mean column at
    all (older rollup), tagged floor_area_basis=median (biased low).
    """
    if primary not in EPC_PRIMARY:
        raise ValueError(f"primary must be one of {EPC_PRIMARY}")
    tags: list[str] = []
    if epc_row is not None:
        cov = _f(epc_row, "coverage_share")
        cov_tags = epc_coverage_tags(cov)
        tags += list(cov_tags)
        fams = [("", "epc_all_time", "all_stock"), ("recent10_", "epc_recent10", "sold")]
        if primary == "recent10" or cov_tags:
            fams.reverse()
        for i, (prefix, source, basis) in enumerate(fams):
            if str(epc_row.get(f"{prefix}suppressed", "False")) in ("True", "true", "1"):
                continue
            types = epc_type_shares(epc_row, prefix)
            if types is None:
                continue
            t = tags + ["epc_mix_marginal_approx", "epc_flats_as_purpose_built", source]
            if i > 0:
                t.append(f"{source}_fallback")
            if basis == "all_stock":
                t.append("rebuild_mix_all_stock")
            has_mean_col = f"{prefix}tfa_mean_m2" in epc_row
            n = _f(epc_row, f"{prefix}tfa_n") or 0
            mean = _f(epc_row, f"{prefix}tfa_mean_m2") if n >= min_tfa_n else None
            groups: dict[str, float] = {}
            if has_mean_col:
                for g in ("house", "flat"):
                    gm, gn = _f(epc_row, f"{prefix}tfa_mean_{g}_m2"), _f(epc_row, f"{prefix}tfa_n_{g}") or 0
                    if gm is not None and gn >= min_tfa_n:
                        groups[g] = gm
                if groups:
                    t.append("floor_area_by_house_flat")
                if mean is not None:
                    area, fab = mean, "mean"
                else:
                    area, fab = float(default_area_m2), "mean"
                    t.append("floor_area_default")
                t.append("floor_area_basis=mean")
            else:
                median = _f(epc_row, f"{prefix}tfa_median_m2")
                if median is None:
                    continue
                area, fab = median, "median"
                t += ["floor_area_basis=median", "floor_area_median_biased_low"]
            return ZoneRebuildInputs(types, epc_age_shares(epc_row, prefix), float(area), fab, basis, source, tuple(t),
                                     groups or None)
    if nrs2017_row is not None:
        types = nrs2017_type_shares(nrs2017_row)
        if types is not None:
            ages = epc_age_shares(epc_row, "") if epc_row is not None else None
            return ZoneRebuildInputs(types, ages, float(default_area_m2), "default", "all_stock", "nrs2017",
                                     tuple(tags + ["rebuild_mix_nrs2017_fallback", "floor_area_default", "floor_area_basis=default"]))
    raise ValueError("no EPC or NRS 2017 mix for zone")


def rate_basis(config: Mapping) -> dict[str, str]:
    """Rules 6.2 v0.7 `rate_basis` per rebuild rate type; every configured rate must declare one from RATE_BASES."""
    rb = dict((config.get("rebuild") or {}).get("rate_basis") or {})
    rates = (config.get("rebuild") or {}).get("gbp_per_m2") or {}
    missing = [t for t in rates if t not in rb]
    bad = {t: v for t, v in rb.items() if v not in RATE_BASES}
    if missing or bad:
        raise ValueError(f"rebuild.rate_basis missing {missing} / invalid {bad}; allowed {RATE_BASES}")
    if rb.get("detached_estate", "generic_estate") != "generic_estate":
        raise ValueError("detached_estate must carry rate_basis generic_estate (rules 6.2 v0.7)")
    if rb.get("detached_one_off", "one_off_detached") != "one_off_detached":
        raise ValueError("detached_one_off must carry rate_basis one_off_detached (a published one-off row)")
    return rb


def zone_flag_sets(spine_rows: Iterable[Mapping] | None = None, *, fallback_zero: Iterable[str] = ZERO_DWELLINGS_FALLBACK,
                   vintage: int = 2011) -> dict:
    """Zero-dwelling and pop/dwellings-mismatch codes from Data Zones zone_spine `flags`.

    zero_dwellings WINS: a zone carrying both (S01010227) is zero_dwellings only (not applicable),
    never a per-resident case. With no spine the zero-dwelling set falls back to the tested codes and
    the mismatch set is empty (source spine_missing)."""
    if spine_rows is None:
        return {"zero_dwellings": frozenset(fallback_zero), "pop_dwellings_mismatch": frozenset(), "source": "fallback_codes"}
    zero, mism = set(), set()
    for r in spine_rows:
        if vintage_int(r.get("vintage")) != vintage:
            continue
        flags = str(r.get("flags") or "").split(";")
        if ZERO_DWELLINGS_FLAG in flags:
            zero.add(str(r["code"]))
        elif POP_MISMATCH_FLAG in flags:
            mism.add(str(r["code"]))
    return {"zero_dwellings": frozenset(zero), "pop_dwellings_mismatch": frozenset(mism), "source": "zone_spine"}


def zero_dwellings_codes(spine_rows: Iterable[Mapping] | None = None, *, fallback: Iterable[str] = ZERO_DWELLINGS_FALLBACK,
                         vintage: int = 2011) -> tuple[frozenset[str], str]:
    """Codes flagged zero_dwellings. Read from Data Zones zone_spine `flags` when the spine carries the
    flag for any zone of this vintage; otherwise the tested fallback codes. Returns (codes, source)."""
    if spine_rows is not None:
        hit = set()
        for r in spine_rows:
            if vintage_int(r.get("vintage")) != vintage:
                continue
            flags = str(r.get("flags") or "")
            if ZERO_DWELLINGS_FLAG in flags.split(";"):
                hit.add(str(r["code"]))
        if hit:
            return frozenset(hit), "zone_spine"
    return frozenset(str(c) for c in fallback), "fallback_codes"


def sample_for(purpose: str, rows, zero_codes: Iterable[str] = ZERO_DWELLINGS_FALLBACK):
    """Single choke point (Georgist v0.7 extension): zero-dwelling zones' sales never enter model fitting,
    yield calibration, fill donors or holdout samples. `rows` is a mapping keyed by code or a sequence of
    dicts with `code`; rows with dwellings == 0 or a zero_dwellings flag are also dropped."""
    if purpose not in SAMPLE_PURPOSES:
        raise ValueError(f"purpose must be one of {SAMPLE_PURPOSES}")
    zc = set(zero_codes)

    def bad(code, r):
        if str(code) in zc:
            return True
        if isinstance(r, Mapping):
            if r.get("dwellings") is not None and r.get("dwellings") == 0:
                return True
            if ZERO_DWELLINGS_FLAG in str(r.get("flags") or "").split(";") or ZERO_DWELLINGS_FLAG in (r.get("tags") or ()):
                return True
        return False

    if isinstance(rows, Mapping):
        return {k: v for k, v in rows.items() if not bad(k, v)}
    return [r for r in rows if not bad(r.get("code") if isinstance(r, Mapping) else r, r)]


def per_resident(value: float | None, population: float | None, flags: str | Iterable[str] | None) -> float | None:
    """Per-resident figure, HIDDEN (None) where Data Zones sets pop_dwellings_mismatch, or with no population."""
    fl = flags.split(";") if isinstance(flags, str) else list(flags or ())
    if POP_MISMATCH_FLAG in fl or ZERO_DWELLINGS_FLAG in fl or value is None or not population or population <= 0:
        return None
    return float(value) / float(population)


def tag_epc_overcount(inp: "ZoneRebuildInputs", epc_row: Mapping | None, *, threshold: float,
                      flag_column: str = "res_uprn_exceeds_dwellings") -> "ZoneRebuildInputs":
    """Old certificates on demolished stock bias EPC floor area and age. Tag them PROXY where certificates
    exceed 2025 homes by more than `threshold` (config, 1.25). Uses GIS's `res_uprn_exceeds_dwellings` flag
    when the rollup carries it; otherwise the coverage ratio of the certificate family actually used for
    floor area and age (recent10_coverage_share for epc_recent10, coverage_share for all-time and for the
    NRS-2017 fallback, whose ages come from the all-time family)."""
    if epc_row is None:
        return inp
    flag = epc_row.get(flag_column) if flag_column in epc_row else None
    if flag is not None and flag == flag and str(flag) != "":
        over = str(flag).strip().lower() in ("true", "1", "yes")
        basis = flag_column
    else:
        col = "recent10_coverage_share" if inp.source == "epc_recent10" else "coverage_share"
        cov = _f(epc_row, col)
        over = cov is not None and cov > threshold
        basis = col
    if not over:
        return inp
    t = ("epc_overcount_proxy", f"epc_overcount_basis={basis}", "age_proxy_epc_overcount")
    if inp.source.startswith("epc_"):
        t += ("floor_area_proxy_epc_overcount",)
    return ZoneRebuildInputs(inp.type_shares, inp.age_shares, inp.floor_area_m2, inp.floor_area_basis, inp.mix_basis,
                             inp.source, inp.tags + t, inp.area_by_group, inp.estate_fraction, inp.estate_bands, inp.oneoff_type)


ESTATE_MODES = ("plot_bands", "gis_bands", "epc_age_upper_bound", "pending")   # gis_bands = legacy alias of plot_bands


def estate_fraction(estate_row: Mapping | None, estate_cfg: Mapping, *, mid_weight: float | None = None) -> tuple[float | None, tuple[str, ...]]:
    """Weighted estate share of detached homes from GIS parcel-band shares (Georgist guard; rules 3b273073: all ages).

    Not a hard cut-off: weight 1 for parcels < 0.05 ha (estate), 0 for > 0.1 ha
    (one-off), `band_weights.mid` (default 0.5) for 0.05-0.1 ha. Shares blank (zone
    with < 5 such homes) or no row -> None with tag estate_share_pending. Plot size
    only selects the rebuild RATE; it is never a land-value driver.
    """
    cols = estate_cfg["columns"]
    if estate_row is None:
        return None, ("estate_share_pending",)
    vals = {b: _f(estate_row, cols[b]) for b in ("lt", "mid", "gt")}
    if any(v is None for v in vals.values()) or sum(vals.values()) <= 0:
        return None, ("estate_share_pending", "estate_share_blank_lt5_homes")
    w = dict(estate_cfg["band_weights"])
    if mid_weight is not None:
        w["mid"] = float(mid_weight)
    tot = sum(vals.values())
    e = sum(float(w[b]) * vals[b] for b in vals) / tot
    src = estate_row.get("_plot_bands_source", "filled")
    src_tag = {"filled": "plot_bands_filled", "borrowed": "plot_bands_borrowed",
               "borrowed_national": "plot_bands_borrowed_national"}[src]
    tags = ("estate_share_gis", "estate_split_all_ages", src_tag, f"estate_mid_weight={w['mid']}", "rate_basis=generic_estate")
    return min(1.0, max(0.0, e)), tags


PLOT_BAND_SOURCES = ("filled", "borrowed", "borrowed_national")


def borrow_plot_bands(rows: Mapping[str, Mapping], zone_meta: Mapping[str, tuple], estate_cfg: Mapping) -> dict[str, dict]:
    """Rules 22c35eba: zones with blank all_ages plot-band shares never default to the one-off rate or to
    all-estate. They borrow the DWELLING-WEIGHTED (matched detached homes, `columns.n_matched`) all_ages
    shares of their own council x UR6 cell (`plot_bands_borrowed`); if that cell has no filled zone,
    the UR6 class nationally (`plot_bands_borrowed_national`). Borrowed rows carry no median parcel
    size (no own plot evidence). `zone_meta`: code -> (council_code, ur6_class) for every zone to value.
    Returns code -> row with `_plot_bands_source` in PLOT_BAND_SOURCES."""
    cols = estate_cfg["columns"]
    bands = ("lt", "mid", "gt")
    ncol = cols.get("n_matched")

    def filled(r):
        if r is None:
            return None
        v = {b: _f(r, cols[b]) for b in bands}
        return v if all(x is not None for x in v.values()) and sum(v.values()) > 0 else None

    acc_cell: dict[tuple, list] = {}
    acc_ur6: dict[int, list] = {}
    out: dict[str, dict] = {}
    for code, (council, ur6) in zone_meta.items():
        r = rows.get(code)
        v = filled(r)
        if v is None:
            continue
        w = (_f(r, ncol) if ncol else None) or 1.0
        for key, acc in (((council, int(ur6)), acc_cell), (int(ur6), acc_ur6)):
            a = acc.setdefault(key, [0.0, {b: 0.0 for b in bands}, 0])
            a[0] += w
            a[2] += 1
            for b in bands:
                a[1][b] += w * v[b]
        out[code] = {**dict(r), "_plot_bands_source": "filled"}
    for code, (council, ur6) in zone_meta.items():
        if code in out:
            continue
        for key, acc, src in (((council, int(ur6)), acc_cell, "borrowed"), (int(ur6), acc_ur6, "borrowed_national")):
            a = acc.get(key)
            if a and a[0] > 0:
                out[code] = {"code": code, **{cols[b]: a[1][b] / a[0] for b in bands}, "_plot_bands_source": src,
                             "_borrow_cell": str(key), "_borrow_n_zones": a[2]}
                break
    return out


def with_estate(inp: "ZoneRebuildInputs", estate_cfg: Mapping, *, mode: str = "pending", estate_row: Mapping | None = None,
                mid_weight: float | None = None) -> "ZoneRebuildInputs":
    """Attach the estate split.

    `plot_bands` (main, rules 3b273073): GIS dz_detached_plot_bands all_ages shares split EVERY detached
    home, whatever its age; blank shares fall back to pending. `epc_age_upper_bound`: SENSITIVITY,
    all post-1980 detached take the estate rate, no plot evidence. `pending`: all detached at
    rebuild.gbp_per_m2.detached, tagged estate_share_pending."""
    if mode not in ESTATE_MODES:
        raise ValueError(f"estate mode must be one of {ESTATE_MODES}")
    bands = tuple(estate_cfg["post_1980_bands"])
    if mode in ("plot_bands", "gis_bands"):
        e, tags = estate_fraction(estate_row, estate_cfg, mid_weight=mid_weight)
        if e is None:  # rules 22c35eba: never fall back to one-off or all-estate; borrow first
            raise PendingSourceError("blank plot-band shares: run borrow_plot_bands (council x UR6, then UR6 national) first")
        bands = ALL_AGES  # no age gating on the main path
    elif mode == "epc_age_upper_bound":
        e, tags = 1.0, ("estate_upper_bound_epc_age_only", "rate_basis=generic_estate")
    else:
        e, tags = None, ("estate_share_pending",)
    oneoff = "detached"
    if e is not None:
        oneoff = estate_cfg.get("oneoff_rate_type", "detached")
        if oneoff not in ONEOFF_RATE_TYPES:
            raise ValueError(f"estate.oneoff_rate_type must be one of {ONEOFF_RATE_TYPES}")
        tags = tuple(tags) + (f"oneoff_rate={oneoff}",)
    return ZoneRebuildInputs(inp.type_shares, inp.age_shares, inp.floor_area_m2, inp.floor_area_basis, inp.mix_basis,
                             inp.source, inp.tags + tuple(tags), inp.area_by_group, e, bands, oneoff)


ALL_AGES = ("*",)


def _zone_mix(inp: "ZoneRebuildInputs") -> list["MixComponent"]:
    e = inp.estate_fraction or 0.0
    mix = []
    for t, st in inp.type_shares.items():
        if st <= 0:
            continue
        for a, sa in inp.age_shares.items():
            if sa <= 0:
                continue
            split = inp.estate_fraction is not None
            oo = inp.oneoff_type if split else "detached"
            if t == "detached" and e > 0 and (inp.estate_bands == ALL_AGES or a in inp.estate_bands):
                mix.append(MixComponent("detached_estate", st * sa * e, inp.area_for("detached_estate"), a))
                if e < 1:
                    mix.append(MixComponent(oo, st * sa * (1 - e), inp.area_for(oo), a))
            elif t == "detached" and split:
                mix.append(MixComponent(oo, st * sa, inp.area_for(oo), a))
            else:
                mix.append(MixComponent(t, st * sa, inp.area_for(t), a))
    tot = sum(c.share for c in mix)
    return [MixComponent(c.dwelling_type, c.share / tot, c.floor_area_m2, c.age_band) for c in mix]


def oneoff_detached_share(inp: "ZoneRebuildInputs") -> float:
    """Share of the zone's dwellings drawing the one-off (or, when pending, the blended) detached rate (diagnostic only)."""
    if not inp.age_shares:
        return inp.type_shares.get("detached", 0.0)
    return sum(c.share for c in _zone_mix(inp) if c.dwelling_type in ("detached", "detached_one_off"))


def zone_rebuild_band(
    inp: ZoneRebuildInputs, *, band: Mapping[str, Mapping[str, float]], depreciation: Mapping, valuation_year: int,
    region: float = 1.0, default_remaining_factor: float | None = None,
) -> dict[str, "RebuildResult"]:
    """Mean DRC per dwelling for low/central/high rebuild from zone mix x age x floor area.

    Floor area per type: house mean for detached/semi/terraced, flat mean for
    flats, zone mean otherwise. Type and age are taken as independent within
    the zone (the rollup has no cross-tab).
    """
    if inp.age_shares is None:
        if default_remaining_factor is None:
            raise PendingSourceError("zone has no age mix and no default_remaining_factor")
        out = {}
        for s in SCENARIOS:
            new = sum(inp.type_shares[t] * inp.area_for(t) * band[t][s] for t in inp.type_shares) * region
            out[s] = RebuildResult(new, new * default_remaining_factor, default_remaining_factor)
        return out
    mix = _zone_mix(inp)
    return depreciated_rebuild_band(mix, band=band, depreciation=depreciation, valuation_year=valuation_year, region=region)


SWING_PARAMS = ("rebuild", "life_years", "remaining_min")


def zone_drc_at(inp: "ZoneRebuildInputs", *, band, depreciation, valuation_year: int, rebuild: str = "central",
                life: str = "central", floor: str = "central", region: float = 1.0,
                default_remaining_factor: float | None = None) -> "RebuildResult":
    """DRC per dwelling at one explicit setting of each parameter (no corner logic)."""
    fixed = {t: {s: b[rebuild] for s in SCENARIOS} for t, b in band.items()}
    dep = {**depreciation_at(depreciation, life=life, floor=floor), "band_combination": {"rule": "corner"}}
    return zone_rebuild_band(inp, band=fixed, depreciation=dep, valuation_year=valuation_year, region=region,
                             default_remaining_factor=default_remaining_factor)["central"]


def one_at_a_time_drc(inp: "ZoneRebuildInputs", **kw) -> dict[str, float]:
    """Rules 6.2 v0.7: each parameter's swing, low and high with the others central.
    Keys '<param>_<low|high>' -> DRC per dwelling (internal diagnostic)."""
    out = {"central": zone_drc_at(inp, **kw).drc_gbp}
    for p in SWING_PARAMS:
        for lvl in ("low", "high"):
            arg = {"rebuild": "rebuild", "life_years": "life", "remaining_min": "floor"}[p]
            out[f"{p}_{lvl}"] = zone_drc_at(inp, **{**kw, arg: lvl}).drc_gbp
    return out


@dataclass(frozen=True)
class RebuildResult:
    rebuild_new_gbp: float
    drc_gbp: float
    remaining_factor: float  # DRC / rebuild_new (mix-weighted)


DEPRECIATION_PARAMS = ("life_years", "remaining_min")
BAND_COMBINATION_RULES = ("corner",)
# DRC scenario -> which end of each input band it takes. DRC rises with rebuild
# £/m2, with building life (slower write-down) and with the remaining-value floor,
# so the HIGHEST DRC (= LOWEST land value) is high rebuild x long life x high floor.
CORNERS = {
    "low": {"rebuild": "low", "life_years": "low", "remaining_min": "low"},       # land_value_high
    "central": {"rebuild": "central", "life_years": "central", "remaining_min": "central"},
    "high": {"rebuild": "high", "life_years": "high", "remaining_min": "high"},    # land_value_low
}


def depreciation_param(depreciation: Mapping, key: str, level: str = "central") -> float:
    """A depreciation input at `level` (low|central|high). Scalars are the central
    value with no band (older configs); bands are {low, central, high}, low <= central <= high."""
    v = depreciation[key]
    if isinstance(v, Mapping):
        lo, c, hi = (float(v[k]) for k in SCENARIOS)
        if not lo <= c <= hi:
            raise ValueError(f"depreciation.{key} band must satisfy low <= central <= high, got {dict(v)}")
        return float(v[level])
    return float(v)


def band_corners(depreciation: Mapping) -> dict[str, dict[str, str]]:
    """Validated corner map (rules 6.2 v0.6). Only corner combination is supported:
    the two extremes of the land value band are the joint extremes of rebuild cost,
    life and floor. A config that pairs them the other way round is rejected,
    because DRC is monotone increasing in all three."""
    comb = depreciation.get("band_combination", {"rule": "corner"})
    rule = comb.get("rule", "corner") if isinstance(comb, Mapping) else comb
    if rule not in BAND_COMBINATION_RULES:
        raise ValueError(f"band_combination {rule!r} not supported; use one of {BAND_COMBINATION_RULES}")
    corners = {s: dict(CORNERS[s]) for s in SCENARIOS}
    if isinstance(comb, Mapping):
        for name, s in (("drc_low_land_high", "low"), ("drc_high_land_low", "high")):
            if name in comb and dict(comb[name]) != CORNERS[s]:
                raise ValueError(f"band_combination.{name} must be {CORNERS[s]} (DRC rises with rebuild, life and floor)")
    return corners


def depreciation_at(depreciation: Mapping, level: str = "central", *, life: str | None = None, floor: str | None = None) -> dict:
    """Scalar depreciation config at a band level (life/floor may be set separately for sensitivity runs)."""
    out = dict(depreciation)
    out["life_years"] = depreciation_param(depreciation, "life_years", life or level)
    out["remaining_min"] = depreciation_param(depreciation, "remaining_min", floor or level)
    return out


def remaining_factor(age_band: str, valuation_year: int, depreciation: Mapping) -> float:
    midpoints = depreciation["age_band_midpoint_year"]
    if age_band not in midpoints:
        raise KeyError(f"unknown EPC age band {age_band!r}; add it to config")
    life = depreciation_param(depreciation, "life_years")
    floor = depreciation_param(depreciation, "remaining_min")
    age = max(0.0, valuation_year - float(midpoints[age_band]))
    return max(floor, 1.0 - age / life)


def depreciated_rebuild(
    mix: Sequence[MixComponent],
    *,
    rates_gbp_per_m2: Mapping[str, float],
    depreciation: Mapping,
    valuation_year: int,
    region: float,
    share_tolerance: float = 1e-6,
) -> RebuildResult:
    """Mix-weighted rebuild cost new and depreciated replacement cost per dwelling."""
    if not mix:
        raise ValueError("dwelling mix is empty")
    total_share = sum(c.share for c in mix)
    if abs(total_share - 1.0) > share_tolerance:
        raise ValueError(f"mix shares sum to {total_share}, not 1")
    rc_new = drc = 0.0
    for c in mix:
        if c.dwelling_type not in rates_gbp_per_m2:
            raise PendingSourceError(f"no rebuild rate for {c.dwelling_type}")
        if c.floor_area_m2 <= 0 or c.share < 0:
            raise ValueError(f"bad mix component {c}")
        new = c.floor_area_m2 * float(rates_gbp_per_m2[c.dwelling_type]) * region
        rc_new += c.share * new
        drc += c.share * new * remaining_factor(c.age_band, valuation_year, depreciation)
    return RebuildResult(rc_new, drc, drc / rc_new if rc_new else 0.0)


def depreciated_rebuild_band(
    mix: Sequence[MixComponent],
    *,
    band: Mapping[str, Mapping[str, float]],
    depreciation: Mapping,
    valuation_year: int,
    region: float,
) -> dict[str, RebuildResult]:
    """Low / central / high DRC by CORNER combination (rules 6.2 v0.6).

    Keyed by DRC scenario: `high` = high rebuild £/m2 x long life x high floor
    (the highest DRC, i.e. `land_value_low`); `low` = low rebuild x short life x
    low floor (`land_value_high`). Because DRC is monotone increasing in all
    three inputs these two corners are the exact extremes over the input box.
    A depreciation config with scalar life/floor gives the rebuild band alone.
    """
    corners = band_corners(depreciation)
    out = {}
    for s in SCENARIOS:
        c = corners[s]
        out[s] = depreciated_rebuild(
            mix,
            rates_gbp_per_m2={t: b[c["rebuild"]] for t, b in band.items()},
            depreciation=depreciation_at(depreciation, life=c["life_years"], floor=c["remaining_min"]),
            valuation_year=valuation_year,
            region=region,
        )
    return out


# --------------------------------------------------------------------------- residual


@dataclass(frozen=True)
class Residual:
    raw_residual: float
    land_value: float
    negative_residual: bool
    tags: tuple[str, ...]


def residual_land_value(price_gbp: float, drc_gbp: float) -> Residual:
    """Rules 6.3: raw kept (may be negative); published floored at 0 and flagged."""
    raw = float(price_gbp) - float(drc_gbp)
    if raw < 0:
        return Residual(raw, 0.0, True, ("negative_residual",))
    return Residual(raw, raw, False, ())


@dataclass(frozen=True)
class ResidualBand:
    central: Residual
    land_value_low: float   # = P - DRC(high rebuild), floored
    land_value_high: float  # = P - DRC(low rebuild), floored
    raw_by_rebuild: dict[str, float]
    tags: tuple[str, ...]


def residual_band(price_gbp: float, rebuilds: Mapping[str, RebuildResult]) -> ResidualBand:
    raw = {s: float(price_gbp) - rebuilds[s].drc_gbp for s in SCENARIOS}
    central = residual_land_value(price_gbp, rebuilds["central"].drc_gbp)
    tags = list(central.tags)
    if raw["high"] < 0 and not central.negative_residual:
        tags.append("negative_under_high_rebuild")
    return ResidualBand(central, max(0.0, raw["high"]), max(0.0, raw["low"]), raw, tuple(tags))


@dataclass(frozen=True)
class LandValue:
    land_value: float | None
    fill_method: str
    tags: tuple[str, ...]


def resolve_land_value(
    *,
    dwellings: int,
    observed: Residual | None,
    sales_n: int,
    model_gbp: float | None,
    n_min: int,
    n_full: int,
    shrinkage_k: float,
    absent_from_price_file: bool = False,
    zero_dwellings: bool = False,
) -> LandValue:
    """Choose observed, shrunk or model value. Never borrows a neighbour's value.

    A zone absent from the RoS price file (Data Zones flag absent_from_ros_price_file)
    is a no-price zone: model-filled when a model value exists, otherwise land value
    None with tag model_fill_pending. Never zero.
    """
    if zero_dwellings:  # rules v0.7: overrides any RoS price (S01010227 still has price rows)
        return LandValue(None, "not_applicable", (ZERO_DWELLINGS_FLAG, "not_applicable"))
    if absent_from_price_file:
        if model_gbp is None:
            return LandValue(None, "model_filled", ("absent_from_ros_price_file", "model_fill_pending"))
        return LandValue(max(0.0, model_gbp), "model_filled", ("absent_from_ros_price_file", "model_filled"))
    if dwellings <= 0:
        return LandValue(None, "no_residential", ("no_residential",))
    if observed is not None and sales_n >= n_full:
        return LandValue(observed.land_value, "observed_pooled", observed.tags)
    if observed is not None and sales_n >= n_min:
        if model_gbp is None:
            return LandValue(observed.land_value, "observed_pooled", observed.tags + ("thin_no_model",))
        k = float(shrinkage_k)
        blended = (sales_n * observed.land_value + k * model_gbp) / (sales_n + k)
        return LandValue(max(0.0, blended), "shrunk_to_model", observed.tags + ("shrunk_to_model",))
    if model_gbp is None:
        raise ValueError("thin or suppressed zone needs a model estimate (no neighbour copy)")
    tags = ("model_filled",) + (("negative_residual",) if model_gbp < 0 else ())
    return LandValue(max(0.0, model_gbp), "model_filled", tags)


# --------------------------------------------------------------------------- yield


def configured_land_yield(yield_cfg: Mapping) -> float:
    """Rules 1: config stores ONE figure, the land yield (= r - g). No r or g outside scenarios."""
    stray = {"r", "g", "discount_rate", "growth_rate"} & set(yield_cfg)
    if stray:
        raise YieldIdentityError(f"yield config must not set {sorted(stray)}; r and g belong in scenario runs only")
    if "land_yield" not in yield_cfg:
        raise PendingSourceError("yield.land_yield must be configured")
    return float(yield_cfg["land_yield"])


def scenario_r_g(scenario: Mapping, land_yield_value: float, *, tol: float = 1e-9) -> tuple[float, float]:
    """Scenario runs only: return (r, g) after asserting r - g == land_yield."""
    r, g = float(scenario["r"]), float(scenario["g"])
    if abs((r - g) - float(land_yield_value)) > tol:
        raise YieldIdentityError(f"scenario r - g = {r - g} != land_yield {land_yield_value}")
    return r, g


def capital_value(rent_gbp: float, land_yield_value: float, scenario: Mapping | None = None) -> float:
    """Rules 1: V = R / (r - g) = R / land_yield. Derived only; never an input to totals."""
    if scenario is not None:
        scenario_r_g(scenario, land_yield_value)
    if land_yield_value <= 0:
        raise ValueError("land yield must be positive to capitalise")
    return float(rent_gbp) / float(land_yield_value)


def gross_yield(monthly_rent_gbp: float, price_gbp: float) -> float:
    if price_gbp <= 0:
        raise ValueError("price must be positive")
    return 12.0 * float(monthly_rent_gbp) / float(price_gbp)


def mix_weighted(values: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Weighted mean of e.g. rent by bedroom size over the same mix as prices."""
    total = sum(weights.values())
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    missing = set(weights) - set(values)
    if missing:
        raise KeyError(f"no value for {sorted(missing)}")
    return sum(values[k] * w for k, w in weights.items()) / total


def _central(v) -> float:
    """Central value of a scalar or {low, central, high} band."""
    return float(v["central"]) if isinstance(v, Mapping) else float(v)


def land_yield(gross: float, *, building_share: float, deductions: Mapping, life_years: float) -> float:
    """y_land = g·(1−void)·(1−running) − (1/life)·(DRC/P). May be ≤ 0; caller flags."""
    void = float(deductions["void"])
    running = float(deductions["running_costs"])
    if deductions.get("building_depreciation") != "from_life_years":
        raise ValueError(f"unsupported building_depreciation rule {deductions.get('building_depreciation')!r}")
    if not 0 <= building_share <= 1:
        raise ValueError("building_share must be in [0, 1]")
    return gross * (1 - void) * (1 - running) - building_share / _central(life_years)


def rent_route_land_value(
    *, monthly_rent_gbp: float, drc_gbp: float, y_land: float, deductions: Mapping, life_years: float
) -> float | None:
    """Rules 12.1 route 2: (net rent − building's share of rent) / land yield.

    Building's share = DRC × (y_land + 1/life). Shares the rebuild assumption
    with the sales route. If rent and y_land come from the same cell as the
    price, this route is algebraically identical to P − DRC.
    """
    if y_land <= 0:
        return None
    net = 12.0 * monthly_rent_gbp * (1 - float(deductions["void"])) * (1 - float(deductions["running_costs"]))
    land_rent = net - drc_gbp * (y_land + 1.0 / _central(life_years))
    return land_rent / y_land


@dataclass(frozen=True)
class YieldCell:
    brma_id: str
    ur6_class: int
    y_land: float
    source: str  # 'cell' | 'brma_wide' | 'config_fallback'
    tags: tuple[str, ...] = ()
    y_gross: float | None = None


def cell_price_evidence(zones: Iterable[Mapping], *, cell_of, zero_codes: Iterable[str] = ZERO_DWELLINGS_FALLBACK) -> dict:
    """Yield calibration price evidence per cell: {cell: {price_n, mean_price}} (sales-weighted).
    Zero-dwelling zones' sales are excluded (rules v0.7 via sample_for('yield_calibration')).
    Each zone: {code, sales_n, price_gbp, dwellings?}; `cell_of(zone) -> cell key or None`."""
    acc: dict = {}
    for z in sample_for("yield_calibration", list(zones), zero_codes):
        c, n, pr = cell_of(z), int(z.get("sales_n") or 0), z.get("price_gbp")
        if c is None or n <= 0 or pr is None:
            continue
        a = acc.setdefault(c, [0, 0.0])
        a[0] += n
        a[1] += n * float(pr)
    return {c: {"price_n": n, "mean_price": tot / n} for c, (n, tot) in acc.items()}


def resolve_cell_yield(
    *,
    brma_id: str,
    ur6_class: int,
    cell_y: float | None,
    prs_n: int,
    price_n: int,
    brma_wide_y: float | None,
    yield_cfg: Mapping,
    cell_gross: float | None = None,
) -> YieldCell:
    """Cell land yield with class cap vs BRMA-wide value and a fallback chain."""
    lo, hi = (float(x) for x in yield_cfg["class_cap"])
    fallback = configured_land_yield(yield_cfg)
    tags: list[str] = []
    if cell_gross is not None and cell_y is not None and cell_y >= cell_gross:
        tags.append("land_yield_not_below_gross")  # rules 6.4
    thin = prs_n < int(yield_cfg["prs_min_records"]) or price_n < int(yield_cfg["price_min_sales"])
    if cell_y is not None and not thin:
        if brma_wide_y is not None and brma_wide_y > 0:
            capped = min(max(cell_y, lo * brma_wide_y), hi * brma_wide_y)
            if capped != cell_y:
                return YieldCell(brma_id, ur6_class, capped, "cell", tuple(tags + ["yield_class_capped"]), cell_gross)
        return YieldCell(brma_id, ur6_class, cell_y, "cell", tuple(tags), cell_gross)
    if brma_wide_y is not None:
        return YieldCell(brma_id, ur6_class, brma_wide_y, "brma_wide", tuple(tags + ["yield_fallback:brma"]), cell_gross)
    return YieldCell(brma_id, ur6_class, float(fallback), "config_fallback", tuple(tags + ["yield_fallback:config"]), cell_gross)


@dataclass(frozen=True)
class ZoneYield:
    y_land: float
    source: str
    brma_mix: dict[str, float]
    tags: tuple[str, ...] = field(default_factory=tuple)
    y_low: float | None = None   # from BRMA share half-widths (rules 6.4 v0.5); None = no spread
    y_high: float | None = None


def brma_dwelling_shares(
    household_rows: Sequence[Mapping], bound_rows: Sequence[Mapping], *, tolerance: float = 1e-6,
) -> tuple[dict[str, float], dict[str, float], str]:
    """Dwelling shares for ONE zone (rules 6.4, v0.5).

    household_rows: that zone's rows of GIS dz_brma_share.csv (household_share).
    bound_rows: that zone's rows of alt/dz_brma_share_dwelling_bounds.csv.
    A zone wholly in one BRMA gets share 1 (occupancy can't move it). A split
    zone uses `share_mid` with `share_halfwidth`. `household_share` is NEVER
    used as a dwelling share for a split zone: missing bounds raise.
    Returns (shares, halfwidths, basis).
    """
    brmas = {r["brma_id"] for r in household_rows}
    if len(brmas) == 1:
        return {next(iter(brmas)): 1.0}, {next(iter(brmas)): 0.0}, "single_brma"
    if not bound_rows:
        raise ValueError("split zone without dwelling bounds; household_share must not stand in for dwellings")
    mid = {r["brma_id"]: float(r["share_mid"]) for r in bound_rows}
    hw = {r["brma_id"]: float(r["share_halfwidth"]) for r in bound_rows}
    if set(mid) != brmas:
        raise ValueError(f"bounds BRMAs {sorted(mid)} != household BRMAs {sorted(brmas)}")
    if abs(sum(mid.values()) - 1.0) > tolerance:
        raise ValueError("share_mid must sum to 1 per zone")
    return mid, hw, "share_mid_bounds"


def _extreme_yield(shares: Mapping[str, float], hw: Mapping[str, float], y: Mapping[str, float], high: bool) -> float:
    lo = {b: max(0.0, shares[b] - hw.get(b, 0.0)) for b in shares}
    up = {b: min(1.0, shares[b] + hw.get(b, 0.0)) for b in shares}
    w, rest = dict(lo), 1.0 - sum(lo.values())
    for b in sorted(shares, key=lambda k: y[k], reverse=high):
        add = min(up[b] - w[b], max(rest, 0.0))
        w[b] += add
        rest -= add
    return sum(w[b] * y[b] for b in shares)

def blend_zone_yield(
    shares: Mapping[str, float], cells: Mapping[str, YieldCell], *, tolerance: float = 1e-6,
    halfwidths: Mapping[str, float] | None = None,
) -> ZoneYield:
    """Zone yield = Σ_b share(z,b) × y_land(b, class_z). Shares (dwelling share_mid) must sum to 1.

    With `halfwidths`, the yield range over all share vectors within ±halfwidth
    (summing to 1) gives y_low / y_high for the uncertainty band.
    """
    total = sum(shares.values())
    if abs(total - 1.0) > tolerance:
        raise ValueError(f"dz_brma_share sums to {total}, not 1")
    if any(s < 0 for s in shares.values()):
        raise ValueError("negative dz_brma_share")
    missing = set(shares) - set(cells)
    if missing:
        raise KeyError(f"no yield cell for BRMA {sorted(missing)}")
    y = sum(shares[b] * cells[b].y_land for b in shares)
    tags = sorted({t for b in shares for t in cells[b].tags})
    sources = sorted({cells[b].source for b in shares if shares[b] > 0})
    if y <= 0:
        tags.append("yield_nonpositive")
    y_low = y_high = None
    if halfwidths and any(v > 0 for v in halfwidths.values()):
        yb = {b: cells[b].y_land for b in shares}
        y_low, y_high = _extreme_yield(shares, halfwidths, yb, False), _extreme_yield(shares, halfwidths, yb, True)
        tags.append("brma_share_bounds_in_band")
    return ZoneYield(y, "+".join(sources), dict(shares), tuple(tags), y_low, y_high)


# --------------------------------------------------------------------------- reconciliation (4.2)


@dataclass(frozen=True)
class Reconciliation:
    ok: bool
    ceiling_rent_gbp: float
    modules_low_gbp: float
    modules_central_gbp: float
    detail: dict


def reconciliation_check(
    *, module_rents: Mapping[str, tuple[float, float, float]], observed_total_value_gbp: float, gross_yield_value: float,
    tolerance: float = 0.0,
) -> Reconciliation:
    """Σ standalone module rents must not exceed zone rent evidence within the band.

    module_rents: {commons_class: (low, central, high)} £/yr, crosswalked to the
    price vintage. Ceiling rent = observed total value (mean×count) × gross yield.
    Breach when the LOW end of the module sum exceeds the ceiling.
    """
    ceiling = float(observed_total_value_gbp) * float(gross_yield_value)
    low = sum(v[0] for v in module_rents.values())
    central = sum(v[1] for v in module_rents.values())
    ok = low <= ceiling * (1 + tolerance)
    return Reconciliation(ok, ceiling, low, central, {"classes": sorted(module_rents)})


# --------------------------------------------------------------------------- output


def uncertainty_level(value: float | None, low: float | None, high: float | None, cfg: Mapping) -> str:
    if value is None or low is None or high is None or value <= 0:
        return "high"
    width = (high - low) / value
    if width <= float(cfg["low_max"]):
        return "low"
    if width <= float(cfg["medium_max"]):
        return "medium"
    return "high"


EXCLUDE_FROM_TOTALS_TAGS = ("dwellings_missing_year",)


def build_output_row(
    *,
    code: str,
    vintage: str,
    valuation_date: date | str,
    ur6_class: int | None,
    ur8_class: int | None,
    dwellings: DwellingCount,
    pooled: PooledPrice,
    indexed: IndexedPrice,
    typical_sale_gbp: float | None,
    rebuild_mix_basis: str,
    rebuilds: Mapping[str, RebuildResult] | None,
    band: ResidualBand | None,
    land: LandValue,
    zone_yield: ZoneYield | None,
    gross_yield_value: float | None,
    config: Mapping,
    source_id: str,
    licence: str,
    crosswalk_method: str = "none",
    net_of: Sequence[str] = (),
    model_interval: tuple[float, float] | None = None,
    infra_share: float | None = None,
    reconciliation: Reconciliation | None = None,
    extra_tags: Sequence[str] = (),
    floor_area_basis: str | None = None,
    residential_land_ha: float | None = None,
    residential_land_source: str | None = None,
    drc_swing: Mapping[str, float] | None = None,
    population: float | None = None,
    zone_flags: str | Iterable[str] | None = None,
    residential_land_low_confidence: Iterable[str] = (),
) -> dict:
    """One `surface_rent_dz` row (rules 6.1: mean for anything that adds up).

    `land` is the INDEXED mean price minus mean DRC per dwelling, both at
    price_year (= rebuild price base = dwelling count_year). The zone total is that
    times the dwelling count; per-dwelling rent is the zone total divided by
    the count. The median only appears as `typical_sale_gbp` (display).
    """
    if crosswalk_method not in CROSSWALK_METHODS:
        raise ValueError(f"crosswalk_method {crosswalk_method!r} not in {CROSSWALK_METHODS}")
    if crosswalk_method not in config["crosswalk_allowed_surface"]:
        raise ValueError(f"surface rent may not be crosswalked by {crosswalk_method!r} (rules 11)")
    bad_net = set(net_of) - set(config["net_of_allowed"])
    if bad_net:
        raise ValueError(f"net_of values not allowed: {sorted(bad_net)}")
    if land.fill_method not in FILL_METHODS:
        raise ValueError(f"bad fill_method {land.fill_method}")
    if pooled.measure != "mean":
        raise ValueError("rent and totals use the MEAN price (rules 6.1); median is display only")
    if rebuild_mix_basis not in REBUILD_MIX_BASES:
        raise ValueError(f"rebuild_mix_basis must be one of {REBUILD_MIX_BASES}")
    if isinstance(vintage, bool) or not isinstance(vintage, int) or vintage not in VINTAGES:
        raise ValueError(f"vintage must be the integer 2011 or 2022, got {vintage!r}")
    validate_code(code, vintage)
    if dwellings.vintage != vintage:
        raise VintageMismatchError(f"price on {vintage} but dwellings on {dwellings.vintage}")
    if residential_land_ha is not None:
        if residential_land_source not in RES_LAND_SOURCES:
            raise ValueError(f"residential_land_source must be one of {RES_LAND_SOURCES}; never whole-zone area (rules 6.4)")
        if residential_land_ha <= 0:
            raise ValueError("residential_land_ha must be positive")
    if any(t in ("epc_all_time", "epc_recent10") for t in extra_tags) and "Royal Mail" not in licence:
        raise ValueError("rows built from the EPC rollup must carry its licence text (surface_manifest.epc_licence)")
    if floor_area_basis is not None and floor_area_basis not in FLOOR_AREA_BASES:
        raise ValueError(f"floor_area_basis must be one of {FLOOR_AREA_BASES}")
    if pooled.evidence_year is None:
        raise ValueError("pooled price has no evidence_year")
    if indexed.evidence_year != pooled.evidence_year or indexed.price_raw_gbp != pooled.price_gbp:
        raise ValueError("indexed price does not belong to this pooled price")
    if indexed.evidence_year != indexed.price_year and (not indexed.series or indexed.series == "none"):
        raise YearMismatchError("evidence_year differs from price_year without a recorded index")
    dcfg = config.get("dwellings") or {}
    lag = assert_base_alignment(
        price_year=indexed.price_year, rebuild_base_year=rebuild_price_base_year(config),
        dwelling_year=dwellings.year, price_vintage=vintage, dwelling_vintage=dwellings.vintage,
        policy=dcfg.get("year_policy", "strict"), max_lag_years=int(dcfg.get("max_lag_years", 0)),
    )

    tags: set[str] = set(pooled.tags) | set(indexed.tags) | set(land.tags) | set(extra_tags) | set(dwellings.tags)
    if rebuild_mix_basis == "all_stock":
        tags.add("rebuild_mix_all_stock")
    if lag:
        tags.add("dwelling_year_lag")  # per-dwelling rent at the price base; totals use the latest published count
    ratio, skew = price_skew_flag(pooled.price_gbp, typical_sale_gbp, pooled.sales_n, config["price"]["skew_flag"])
    if skew:
        tags.add("price_skew_small_sample")

    lv = land.land_value
    lv_low = lv_high = lv
    if lv is not None and band is not None and land.fill_method in ("observed_pooled", "shrunk_to_model"):
        lv_low, lv_high = min(lv, band.land_value_low), max(lv, band.land_value_high)
        tags |= set(band.tags)
    if lv is not None and model_interval is not None:
        lv_low, lv_high = min(lv_low, model_interval[0]), max(lv_high, model_interval[1])

    if land.fill_method == "not_applicable":  # rules v0.7 zero dwellings: no surface rent, no residual (null, never 0)
        band = None
        lv_low = lv_high = None
        tags.add(ZERO_DWELLINGS_FLAG)
    n = dwellings.count
    y = zone_yield.y_land if zone_yield else None
    y_pub = max(y, 0.0) if y is not None else None
    have = lv is not None and y_pub is not None and n is not None and n > 0
    lv_total = lv * n if (lv is not None and n is not None) else None  # zone total land value (mean x count)
    rent = round(lv_total * y_pub, 2) if have else None
    rent_dw = round(rent / n, 2) if have else None  # per-home = zone total / count
    y_lo = max(zone_yield.y_low, 0.0) if (zone_yield and zone_yield.y_low is not None) else y_pub
    y_hi = max(zone_yield.y_high, 0.0) if (zone_yield and zone_yield.y_high is not None) else y_pub
    unc_low = round(lv_low * n * min(y_lo, y_pub), 2) if have else None
    unc_high = round(lv_high * n * max(y_hi, y_pub), 2) if have else None
    if zone_yield is not None:
        tags |= set(zone_yield.tags)
    if residential_land_ha is None:
        rent_ha = None
        tags.add("pending_residential_land")
    else:
        rent_ha = round(rent / residential_land_ha, 2) if rent is not None else None
        for f in residential_land_low_confidence:  # per-hectare output only; totals never use the area
            if f not in RES_LAND_LOW_CONFIDENCE:
                raise ValueError(f"residential land low-confidence flag must be one of {RES_LAND_LOW_CONFIDENCE}")
            tags.add(f"res_land_low_confidence_{f}")
        if residential_land_source == "settlement_area":
            tags.add("res_land_settlement_area_rough")

    zf = zone_flags.split(";") if isinstance(zone_flags, str) else list(zone_flags or ())
    if POP_MISMATCH_FLAG in zf:
        tags.add("per_resident_hidden_pop_dwellings_mismatch")
    quality = config["quality_by_fill"][land.fill_method]
    publish = config["publish_by_fill"][land.fill_method]  # licence level; never changed by a block
    if "estate_share_gis" in tags:  # GIS parcel-derived estate input: internal until GIS clears the OS terms
        publish = "internal"
        tags.add("publish_internal_estate_input")
    status = "ok"
    if n is None:
        quality = "placeholder"  # rules 2 (v0.4): placeholders are not served
    if reconciliation is not None and not reconciliation.ok:
        status = "blocked"  # rules 4.2 / 2: hides the figure, keeps publish_level, logged via tag
        tags.add("reconciliation_breach")
    if publish not in PUBLISH_LEVELS or publish not in config["publish_levels"]:
        raise ValueError(f"publish_level {publish!r} not in {PUBLISH_LEVELS}")

    despec = float(config["policy"]["despeculation"]["urban"])
    central_rb = rebuilds["central"] if rebuilds else None
    row = {
        "code": code,
        "vintage": vintage,
        "valuation_date": str(valuation_date),
        "price_year": indexed.price_year,
        "ur6_class": ur6_class,
        "ur8_class": ur8_class,
        "dwellings": n,
        "sales_n_pooled": pooled.sales_n,
        "evidence_year": pooled.evidence_year,
        "evidence_years": pooled.years,
        "price_measure": pooled.measure,
        "price_gbp": pooled.price_gbp,
        "price_indexed_gbp": indexed.price_indexed_gbp,
        "price_index_series": indexed.series,
        "price_index_factor": indexed.factor,
        "typical_sale_gbp": typical_sale_gbp,
        "mean_median_ratio": ratio,
        "price_skew_flag": skew,
        "count_year": dwellings.year,
        "count_year_lag": lag,
        "dwellings_source": dwellings.source,
        "vacant_share": dwellings.vacant_share,
        "second_home_share": dwellings.second_home_share,
        "rebuild_status": config["rebuild"]["status"],
        "rebuild_mix_basis": rebuild_mix_basis,
        "floor_area_basis": floor_area_basis,
        "rebuild_new_gbp": central_rb.rebuild_new_gbp if central_rb else None,
        "remaining_factor": central_rb.remaining_factor if central_rb else None,
        "drc_gbp": central_rb.drc_gbp if central_rb else None,
        "drc_low_gbp": rebuilds["low"].drc_gbp if rebuilds else None,
        "drc_high_gbp": rebuilds["high"].drc_gbp if rebuilds else None,
        "drc_swing_gbp": dict(drc_swing) if drc_swing else None,  # one-at-a-time swing (rules 6.2 v0.7), internal
        "raw_residual": band.central.raw_residual if band else None,
        "negative_residual": bool(band.central.negative_residual) if band else ("negative_residual" in land.tags),
        "land_value": lv,
        "land_value_low": lv_low,
        "land_value_high": lv_high,
        "land_value_zone_total": lv_total,
        "yield_gross": gross_yield_value,
        "yield_land": y,
        "yield_source": zone_yield.source if zone_yield else None,
        "brma_mix": zone_yield.brma_mix if zone_yield else None,
        "measured_rent_per_dwelling": rent_dw,
        "measured_rent_per_resident": per_resident(rent, population, zone_flags),  # hidden on pop_dwellings_mismatch
        "measured_rent": rent,
        "residential_land_ha": residential_land_ha,
        "rent_per_res_ha": rent_ha,
        "uncertainty_low": unc_low,
        "uncertainty_high": unc_high,
        "uncertainty": uncertainty_level(lv, lv_low, lv_high, config["uncertainty"]),
        "infra_share": infra_share,
        "planning_uplift": None,  # rules 8: blank until the farm proxy exists; never guessed
        "policy_despec_factor": despec,
        "policy_rent": round(rent * despec, 2) if rent is not None else None,
        "value_tier": VALUE_TIER,
        "quality": quality,
        "fill_method": land.fill_method,
        "publish_level": publish,
        "publication_status": status,
        "commons_class": config["commons_class"],
        "net_of": list(net_of),
        "use_basis": config["use_basis"],
        "crosswalk_method": crosswalk_method,
        "source_id": source_id,
        "licence": licence,
        "proxy_tags": sorted(tags | {"planning_uplift_pending_farm_proxy", f"rebuild_{config['rebuild']['status'].lower()}"}),
        "method": METHOD,
    }
    assert tuple(row) == OUTPUT_COLUMNS
    validate_required(row)
    return row


class RowRejectedError(ValueError):
    """A row is missing a required field (rules 2, v0.4)."""


def validate_required(row: Mapping) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in row]
    if row.get("quality") != "placeholder":
        missing += [f for f in REQUIRED_FIELDS if f in row and row[f] is None]
    if missing:
        raise RowRejectedError(f"row {row.get('code')} missing required fields {sorted(set(missing))}")


def public_view(rows: Iterable[Mapping], *, level: str = "public_zone") -> list[dict]:
    """What the public API/map may serve (rules 2, v0.4).

    Drops internal-only diagnostic columns; omits blocked rows, placeholders and
    rows whose publish_level is below `level`. Rejects rows missing required fields.
    """
    order = {"internal": 0, "public_zone": 1, "public_site": 2}
    out = []
    for r in rows:
        validate_required(r)
        if r.get("publication_status") != "ok" or r.get("quality") == "placeholder":
            continue
        if order[r["publish_level"]] < order[level]:
            continue
        out.append({k: v for k, v in r.items() if k not in INTERNAL_ONLY_COLUMNS})
    return out


# --------------------------------------------------------------------------- totals


def _excluded(r: Mapping) -> bool:
    return r.get("publication_status") == "blocked" or r.get("quality") == "placeholder" or any(t in (r.get("proxy_tags") or ()) for t in EXCLUDE_FROM_TOTALS_TAGS)


def total_measured_rent(rows: Iterable[Mapping], column: str = "measured_rent") -> dict[str, float]:
    """Totals per value tier (rules 5). Only measured_rent is summable.

    Breakdown (4.3) and policy (13) columns raise. Blocked zones (reconciliation
    breach), missing dwelling years and placeholders are excluded.
    """
    if column in ATTRIBUTION_ONLY or column in POLICY_COLUMNS:
        raise AttributionOnlyError(f"{column} is a breakdown/policy column and cannot be totalled with rent")
    if column not in SUMMABLE:
        raise AttributionOnlyError(f"{column} is not a summable rent column")
    out: dict[str, float] = {}
    years: set = set()
    for r in rows:
        if _excluded(r) or r.get(column) is None:
            continue
        years.add(r.get("price_year"))
        if len(years) > 1:
            raise YearMismatchError(f"rows have differing price_year {sorted(map(str, years))}; index to one price_year first (rules 2)")
        out[r["value_tier"]] = out.get(r["value_tier"], 0.0) + float(r[column])
    return out


def total_policy_rent(rows: Iterable[Mapping]) -> float:
    """Policy view, reported separately from measured rent (rules 13)."""
    use = [r for r in rows if r.get("policy_rent") is not None and not _excluded(r)]
    if len({r.get("price_year") for r in use}) > 1:
        raise YearMismatchError("rows have differing price_year (rules 2)")
    return sum(float(r["policy_rent"]) for r in use)


def apportion_by_addresses(zone_rent_gbp: float, address_counts: Mapping[str, int]) -> dict[str, float]:
    """Split zone rent to parcels/sub-areas by address (UPRN) count. Never by area."""
    total = sum(address_counts.values())
    if total <= 0:
        raise ValueError("no addresses to apportion to")
    return {k: zone_rent_gbp * n / total for k, n in address_counts.items()}
