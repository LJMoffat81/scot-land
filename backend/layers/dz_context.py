"""Data Zone context metrics: house prices, SIMD, population density.

Attributes load from ``data/processed/gis/dz_context_metrics.csv`` (PostGIS
``processed.gis_dz_context_metrics`` when loaded). Zone polygons come from
``dz_boundaries`` when the boundaries agent has loaded them — this module never
ships or invents boundary geometry.

No modelled AGR £ is attached.
"""

from __future__ import annotations

import csv
import hashlib
from functools import lru_cache
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
METRICS_CSV = REPO_ROOT / "data" / "processed" / "gis" / "dz_context_metrics.csv"

# Catalog / source stamps (OGL NRS/SG + UK HPI + RoS)
SIMD_SOURCE_URL = (
    "https://www.gov.scot/publications/scottish-index-of-multiple-deprivation-2020v2-data-zone-look-up/"
)
POP_SOURCE_URL = (
    "https://www.nrscotland.gov.uk/publications/small-area-population-estimates-mid-2024-2022-data-zones/"
)
HPI_SOURCE_URL = (
    "https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/"
)
ROS_PRICES_URL = (
    "https://data.gov.scot/dataset/house_prices___residential_properties_sales_and_price"
)
LICENCE = "OGL v3.0"

ATTRIBUTION = (
    "Contains National Records of Scotland data (small area population estimates) "
    "© Crown copyright and database right 2026; contains Scottish Government data "
    "(SIMD 2020v2) © Crown copyright 2025; contains Registers of Scotland data "
    "(residential sales and price) © Crown copyright 2026; UK House Price Index "
    "© Crown copyright (HM Land Registry, Registers of Scotland, ONS). "
    "Licensed under the Open Government Licence v3.0."
)

METRIC_DEFS: dict[str, dict[str, Any]] = {
    "house_price": {
        "property": "house_price_median_gbp",
        "fallback_property": "council_hpi_average_price_gbp",
        "label": "House prices (Data Zone)",
        "unit": "£",
        "group": "context",
        "description": (
            "RoS residential sale median at DZ2011 where published; otherwise "
            "UK HPI council average attributed via local authority. Not a tax bill."
        ),
    },
    "simd": {
        "property": "simd_decile",
        "label": "SIMD decile (Data Zone)",
        "unit": "decile 1–10 (1 = most deprived)",
        "group": "context",
        "description": (
            "SIMD 2020v2 decile on DZ2011; modal decile on DZ2022 via people "
            "crosswalk. Equity context only."
        ),
    },
    "pop_density": {
        "property": "population_density_per_km2",
        "label": "Population density (Data Zone)",
        "unit": "people/km²",
        "group": "context",
        "description": (
            "NRS mid-year population ÷ zone area (ha from GIS dz_residential_land). "
            "Pressure on land — not a charge."
        ),
    },
}


def _num(v: Any) -> float | int | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    try:
        if isinstance(v, str) and "." not in v:
            return int(v)
        f = float(v)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return None


def _boolish(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in {"true", "1", "t", "yes"}:
        return True
    if s in {"false", "0", "f", "no"}:
        return False
    return None


@lru_cache(maxsize=1)
def load_metrics_rows() -> tuple[dict[str, Any], ...]:
    """Rows from the staged CSV (CI / offline). Empty if the file is missing."""
    if not METRICS_CSV.exists():
        return ()
    with METRICS_CSV.open(encoding="utf-8-sig", newline="") as fh:
        rows = []
        for raw in csv.DictReader(fh):
            rows.append(
                {
                    "code": raw["code"],
                    "vintage": int(raw["vintage"]),
                    "name": raw.get("name") or "",
                    "la_code": raw.get("la_code") or "",
                    "la_name": raw.get("la_name") or "",
                    "population": _num(raw.get("population")),
                    "pop_year": _num(raw.get("pop_year")),
                    "zone_ha": _num(raw.get("zone_ha")),
                    "population_density_per_km2": _num(
                        raw.get("population_density_per_km2")
                    ),
                    "simd_rank": _num(raw.get("simd_rank")),
                    "simd_decile": _num(raw.get("simd_decile")),
                    "simd_quintile": _num(raw.get("simd_quintile")),
                    "in_simd_20pct_most_deprived": _boolish(
                        raw.get("in_simd_20pct_most_deprived")
                    ),
                    "house_price_median_gbp": _num(raw.get("house_price_median_gbp")),
                    "house_price_sales_n": _num(raw.get("house_price_sales_n")),
                    "council_hpi_average_price_gbp": _num(
                        raw.get("council_hpi_average_price_gbp")
                    ),
                    "hpi_period": raw.get("hpi_period") or "",
                    "price_basis": raw.get("price_basis") or "",
                    # Choropleth paint property used by the map (prefer RoS median).
                    "average_price_gbp": (
                        _num(raw.get("house_price_median_gbp"))
                        or _num(raw.get("council_hpi_average_price_gbp"))
                    ),
                }
            )
        return tuple(rows)


def metrics_by_code(vintage: int | None = 2011) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for row in load_metrics_rows():
        if vintage is not None and row["vintage"] != vintage:
            continue
        out[str(row["code"])] = row
    return out


def _rows_from_postgis() -> list[dict[str, Any]] | None:
    """Return rows from PostGIS when the table is loaded; None if unavailable."""
    try:
        from georgist import db
    except Exception:
        return None
    try:
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = 'processed'
                        AND table_name = 'gis_dz_context_metrics'
                    )
                    """
                )
                if not cur.fetchone()[0]:
                    return None
                cur.execute(
                    """
                    SELECT code, vintage, name, la_code, la_name, population, pop_year,
                           zone_ha, population_density_per_km2, simd_rank, simd_decile,
                           simd_quintile, in_simd_20pct_most_deprived,
                           house_price_median_gbp, house_price_sales_n,
                           council_hpi_average_price_gbp, hpi_period, price_basis
                    FROM processed.gis_dz_context_metrics
                    ORDER BY vintage, code
                    """
                )
                cols = [d[0] for d in cur.description]
                rows = []
                for tup in cur.fetchall():
                    raw = dict(zip(cols, tup))
                    row = {
                        "code": str(raw["code"]).strip(),
                        "vintage": int(raw["vintage"]),
                        "name": raw.get("name") or "",
                        "la_code": raw.get("la_code") or "",
                        "la_name": raw.get("la_name") or "",
                        "population": _num(raw.get("population")),
                        "pop_year": _num(raw.get("pop_year")),
                        "zone_ha": _num(raw.get("zone_ha")),
                        "population_density_per_km2": _num(
                            raw.get("population_density_per_km2")
                        ),
                        "simd_rank": _num(raw.get("simd_rank")),
                        "simd_decile": _num(raw.get("simd_decile")),
                        "simd_quintile": _num(raw.get("simd_quintile")),
                        "in_simd_20pct_most_deprived": _boolish(
                            raw.get("in_simd_20pct_most_deprived")
                        ),
                        "house_price_median_gbp": _num(
                            raw.get("house_price_median_gbp")
                        ),
                        "house_price_sales_n": _num(raw.get("house_price_sales_n")),
                        "council_hpi_average_price_gbp": _num(
                            raw.get("council_hpi_average_price_gbp")
                        ),
                        "hpi_period": raw.get("hpi_period") or "",
                        "price_basis": raw.get("price_basis") or "",
                    }
                    row["average_price_gbp"] = (
                        row["house_price_median_gbp"]
                        or row["council_hpi_average_price_gbp"]
                    )
                    rows.append(row)
                return rows
    except Exception:
        return None


def _boundaries_geojson(vintage: int) -> dict[str, Any] | None:
    """Load zone polygons from PostGIS when present. Never invents geometry."""
    try:
        from georgist import db
    except Exception:
        return None
    try:
        with db.connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT EXISTS (
                      SELECT 1 FROM information_schema.tables
                      WHERE table_schema = 'public' AND table_name = 'dz_boundaries'
                    )
                    """
                )
                if not cur.fetchone()[0]:
                    return None
                cur.execute(
                    "SELECT COUNT(*) FROM dz_boundaries WHERE vintage = %s",
                    (vintage,),
                )
                if int(cur.fetchone()[0]) == 0:
                    return None
                cur.execute(
                    """
                    SELECT code, name,
                           ST_AsGeoJSON(ST_Transform(geom, 4326))::json AS geometry
                    FROM dz_boundaries
                    WHERE vintage = %s
                    """,
                    (vintage,),
                )
                features = []
                for code, name, geom in cur.fetchall():
                    features.append(
                        {
                            "type": "Feature",
                            "geometry": geom,
                            "properties": {
                                "code": str(code).strip(),
                                "name": name or "",
                                "vintage": vintage,
                            },
                        }
                    )
                return {"type": "FeatureCollection", "features": features}
    except Exception:
        return None


def _metrics_csv_sha8() -> str:
    """First 8 hex chars of SHA-256 over ``dz_context_metrics.csv`` bytes."""
    if not METRICS_CSV.is_file():
        return hashlib.sha256(b"").hexdigest()[:8]
    return hashlib.sha256(METRICS_CSV.read_bytes()).hexdigest()[:8]


def dz_values_lineage(
    vintage: int,
    *,
    codes: list[str],
    measure: str = "pop_density",
) -> dict[str, Any]:
    """Lineage block for Data Zone value payloads (TARGET-ARCH-1 §Lineage)."""
    if type(vintage) is not int or vintage not in (2011, 2022):
        raise ValueError(
            f"DZ: vintage must be 2011 or 2022, got {vintage!r}"
        )
    if type(measure) is not str or not measure.strip() or measure not in METRIC_DEFS:
        raise ValueError(
            f"DZ: measure must be one of {sorted(METRIC_DEFS)}, got {measure!r}"
        )
    if type(codes) is not list:
        raise ValueError(
            f"DZ: codes must be a non-empty list of non-empty strings, got {type(codes).__name__}"
        )
    if not codes:
        raise ValueError(
            "DZ: codes must be a non-empty list of non-empty strings"
        )
    cleaned: list[str] = []
    for code in codes:
        if type(code) is not str or not code.strip():
            raise ValueError(
                f"DZ: codes must be a non-empty list of non-empty strings, got element {code!r}"
            )
        cleaned.append(code.strip())
    ordered = sorted(set(cleaned))
    unit = f"dz{vintage}"
    as_of = f"{vintage}-01-01"
    sha8 = _metrics_csv_sha8()
    child_set_hash = hashlib.sha256(
        "\n".join(ordered).encode("utf-8")
    ).hexdigest()
    return {
        "source_layer_ids": [unit],
        "dataset_version": f"{unit}@{as_of}-{sha8}",
        "as_of": as_of,
        "method": "source",
        "unit": unit,
        "roll_up_to": ["council", "scotland"],
        "child_count": len(ordered),
        "child_set_hash": child_set_hash,
    }


def build_metrics_payload(*, vintage: int = 2011, include_geometry: bool = True) -> dict[str, Any]:
    """Attribute FeatureCollection; geometry only when dz_boundaries is loaded."""
    pg_rows = _rows_from_postgis()
    rows = pg_rows if pg_rows is not None else list(load_metrics_rows())
    rows = [r for r in rows if r["vintage"] == vintage]
    by_code = {r["code"]: r for r in rows}

    geom_fc = _boundaries_geojson(vintage) if include_geometry else None
    features: list[dict[str, Any]] = []
    geometry_status = "pending_boundaries"

    if geom_fc and geom_fc.get("features"):
        geometry_status = "postgis"
        for feat in geom_fc["features"]:
            props = dict(feat.get("properties") or {})
            code = str(props.get("code") or "")
            metrics = by_code.get(code) or {}
            merged = {**metrics, **props, "code": code, "vintage": vintage}
            # Prefer metric name over boundary name when both set
            if metrics.get("name"):
                merged["name"] = metrics["name"]
            features.append(
                {
                    "type": "Feature",
                    "geometry": feat.get("geometry"),
                    "properties": merged,
                }
            )
    else:
        # Honest attribute-only delivery until the boundaries PR loads GeoJSON.
        for row in rows:
            features.append(
                {
                    "type": "Feature",
                    "geometry": None,
                    "properties": row,
                }
            )

    metrics_meta = {}
    for mid, defn in METRIC_DEFS.items():
        prop = defn["property"]
        vals = [
            f["properties"].get(prop)
            for f in features
            if f["properties"].get(prop) is not None
        ]
        metrics_meta[mid] = {
            **{k: v for k, v in defn.items()},
            "min": min(vals) if vals else None,
            "max": max(vals) if vals else None,
        }

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "layer": "dz_context",
            "vintage": vintage,
            "feature_count": len(features),
            "geometry_status": geometry_status,
            "source": "processed.gis_dz_context_metrics"
            if pg_rows is not None
            else str(METRICS_CSV.relative_to(REPO_ROOT)),
            "licence": LICENCE,
            "attribution": ATTRIBUTION,
            "metrics": metrics_meta,
            "note": (
                "Data Zone house prices (RoS median / council UK HPI), SIMD 2020v2, "
                "and NRS population density. Context only — no modelled money figures. "
                + (
                    "Zone polygons pending Data Zone boundaries load."
                    if geometry_status == "pending_boundaries"
                    else "Zone polygons from PostGIS dz_boundaries."
                )
            ),
            "sources": {
                "simd": {"url": SIMD_SOURCE_URL, "licence": LICENCE},
                "population": {"url": POP_SOURCE_URL, "licence": LICENCE},
                "hpi_council": {"url": HPI_SOURCE_URL, "licence": LICENCE},
                "ros_house_prices": {"url": ROS_PRICES_URL, "licence": LICENCE},
            },
            "lineage": (
                dz_values_lineage(
                    vintage,
                    codes=[
                        str(f["properties"]["code"])
                        for f in features
                        if f.get("properties", {}).get("code")
                    ],
                )
                if features
                else None
            ),
        },
    }


def metrics_for_zone(code: str, vintage: int) -> dict[str, Any] | None:
    for row in load_metrics_rows():
        if row["code"] == code and row["vintage"] == vintage:
            return row
    pg = _rows_from_postgis()
    if pg:
        for row in pg:
            if row["code"] == code and row["vintage"] == vintage:
                return row
    return None


def catalog_layers() -> list[dict[str, Any]]:
    """Three live catalog entries (HPI, SIMD, density) at Data Zone grain.

    Ledger-frame surface inputs for row 1 (zone grain) — not LayersPanel toggles.
    """
    common = {
        "group": "spatial",
        "status": "live",
        "endpoint": "/layers/open/dz-context",
        "licence": LICENCE,
        "licence_url": (
            "https://www.nationalarchives.gov.uk/doc/"
            "open-government-licence/version/3/"
        ),
        "attribution": ATTRIBUTION,
        "minzoom": 8,
        "ledger_role": "ledger-frame",
        "ledger_row": "1",
        "ui_surface": "ledger",
    }
    return [
        {
            **common,
            "id": "dz_house_price",
            "label": "House prices (Data Zone)",
            "description": METRIC_DEFS["house_price"]["description"],
            "source_url": ROS_PRICES_URL,
            "also": HPI_SOURCE_URL,
        },
        {
            **common,
            "id": "dz_simd",
            "label": "SIMD (Data Zone)",
            "description": METRIC_DEFS["simd"]["description"],
            "source_url": SIMD_SOURCE_URL,
        },
        {
            **common,
            "id": "dz_pop_density",
            "label": "Population density (Data Zone)",
            "description": METRIC_DEFS["pop_density"]["description"],
            "source_url": POP_SOURCE_URL,
        },
    ]


def source_registry() -> dict[str, Any]:
    """Block for data/config/sources.yaml consumers / docs."""
    return {
        "dz_context_metrics": {
            "role": "data_zone_hpi_simd_population_density",
            "path": "data/processed/gis/dz_context_metrics.csv",
            "postgis_table": "processed.gis_dz_context_metrics",
            "endpoint": "/layers/open/dz-context",
            "licence": LICENCE,
            "attribution": ATTRIBUTION,
            "build": "python etl/gis/build_dz_context_metrics.py",
            "sources": {
                "simd": {
                    "name": "SIMD 2020v2 data zone look-up",
                    "publisher": "Scottish Government",
                    "licence": LICENCE,
                    "url": SIMD_SOURCE_URL,
                },
                "population": {
                    "name": "NRS small area population estimates",
                    "publisher": "National Records of Scotland",
                    "licence": LICENCE,
                    "url": POP_SOURCE_URL,
                },
                "zone_area": {
                    "name": "Data Zone area (ha) from GIS dz_residential_land",
                    "publisher": "Scottish Government boundaries via Scot-LAND GIS",
                    "licence": LICENCE,
                    "url": "https://www.spatialdata.gov.scot/",
                },
                "ros_house_prices": {
                    "name": "House prices — residential properties sales and price",
                    "publisher": "Registers of Scotland / Scottish Government",
                    "licence": LICENCE,
                    "url": ROS_PRICES_URL,
                },
                "uk_hpi": {
                    "name": "UK House Price Index (council averages)",
                    "publisher": "HM Land Registry / RoS / ONS",
                    "licence": LICENCE,
                    "url": HPI_SOURCE_URL,
                },
            },
            "gaps": [
                "UK HPI has no Data Zone series — council HPI is attributed via LA code",
                "RoS sale medians are DZ2011 only (2004–2023 open file)",
                "Map polygons require dz_boundaries (separate GIS boundaries work)",
            ],
        }
    }

