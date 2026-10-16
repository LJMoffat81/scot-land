"""LAYERS-ADD-2 ingest and Data Zone aggregates.

Storage is EPSG:27700. Served coordinates are lon/lat (EPSG:4326).
Aggregates are v1.5 candidates only. Address fields never reach the database.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from typing import Any, Mapping, Sequence

from pyproj import Transformer

from layers.layers_add2_catalog import (
    BANNED_COVERAGE_LABELS,
    DZ2022_VINTAGE,
    NO_OPEN_DATA_LABEL,
    SMALL_SITE_MIN,
    TILE_PROPERTY_ALLOWLIST,
    ZONE_RE,
    assert_full_dz2022,
    assert_zone_key,
    dz2022_zone_ids,
    filter_tile_properties,
)

# Columns kept from an EPC certificate. Anything else, including free text,
# is dropped before the first write. Mutation: adding POSTCODE here fails A3.
EPC_COLUMN_ALLOWLIST: frozenset[str] = frozenset(
    {
        "TOTAL_FLOOR_AREA",
        "PROPERTY_TYPE",
        "CONSTRUCTION_AGE_BAND",
        "CURRENT_ENERGY_RATING",
        "DZ_CODE",
    }
)
EPC_BANNED_COLUMNS: frozenset[str] = frozenset(
    {
        "ADDRESS1",
        "ADDRESS2",
        "POSTTOWN",
        "POSTCODE",
        "UPRN",
        "OSG_REFERENCE_NUMBER",
        "BUILDING_REFERENCE_NUMBER",
        "REPORT_REFERENCE_NUMBER",
    }
)
EPC_SUPPRESS_BELOW = 5
EPC_BANDS = "ABCDEFG"

# Published aggregate columns. None of these are currency fields.
AGG_COLUMNS: dict[str, tuple[str, ...]] = {
    "agg_epc": (
        "zone_id",
        "dz_vintage",
        "certificate_count",
        "median_floor_area_m2",
        "share_property_type",
        "share_age_band",
        "median_epc_band",
        "suppressed",
    ),
    "agg_uprn_density": (
        "zone_id",
        "dz_vintage",
        "point_count",
        "points_per_ha",
    ),
    "agg_ofcom": (
        "zone_id",
        "dz_vintage",
        "share_full_fibre",
        "share_gigabit",
        "share_below_10",
    ),
    "agg_nrs": ("zone_id", "dz_vintage", "population", "households", "per_ha"),
    "agg_ur": ("zone_id", "dz_vintage", "fold6", "fold8"),
    "agg_roads": (
        "zone_id",
        "dz_vintage",
        "metres_motorway_junction",
        "metres_a_road",
        "metres_trunk",
    ),
    "agg_greenspace": ("zone_id", "dz_vintage", "metres_public_park", "greenspace_ha"),
    "agg_fls": ("zone_id", "dz_vintage", "share_estate"),
    "agg_vdl_council": (
        "zone_id",
        "dz_vintage",
        "coverage",
        "source_council",
        "site_count_label",
        "hectares",
    ),
    "agg_ldp_council": (
        "zone_id",
        "dz_vintage",
        "coverage",
        "source_council",
        "use_class",
        "hectares",
    ),
    "agg_contam_dz": (
        "zone_id",
        "dz_vintage",
        "coverage",
        "source_council",
        "site_count_label",
        "hectares",
    ),
}

SITE_EXPORT_BANNED: frozenset[str] = frozenset(
    {
        "site_name",
        "site_ref",
        "owner",
        "address",
        "geometry",
        "postcode",
        "uprn",
        "lat",
        "lon",
    }
)
CURRENCY_TOKENS: tuple[str, ...] = ("gbp", "rent", "price", "value")

_TO_WGS84 = Transformer.from_crs("EPSG:27700", "EPSG:4326", always_xy=True)
_UPRN_VALUE = re.compile(r"^\d{6,12}$")
_ID_NAME = re.compile(r"id", re.I)
_KEYED_URL = re.compile(r"key=|api_key|access_token", re.I)


def project_epc_row(raw: Mapping[str, Any], postcode_to_dz: Mapping[str, str]) -> dict[str, Any]:
    """Join postcode to a Data Zone in memory, then keep the allowlist only."""
    postcode = str(raw.get("POSTCODE") or "")
    dz = postcode_to_dz.get(postcode)
    if dz is None or ZONE_RE.match(str(dz)) is None:
        raise ValueError("EPC row has no Data Zone")
    projected: dict[str, Any] = {"DZ_CODE": dz}
    for column in EPC_COLUMN_ALLOWLIST:
        if column == "DZ_CODE":
            continue
        if column in raw:
            projected[column] = raw[column]
    leaked = (set(projected) & EPC_BANNED_COLUMNS) | (set(projected) - EPC_COLUMN_ALLOWLIST)
    if leaked:
        raise ValueError(f"banned EPC columns survived projection: {sorted(leaked)}")
    return projected


def _shares(values: Sequence[str]) -> str:
    counts: dict[str, int] = defaultdict(int)
    for value in values:
        counts[str(value)] += 1
    total = sum(counts.values()) or 1
    return json.dumps({key: counts[key] / total for key in sorted(counts)})


def _median_number(values: Sequence[float]) -> float:
    ordered = sorted(float(v) for v in values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2


def _median_band(bands: Sequence[str]) -> str:
    ordered = sorted(bands, key=lambda band: EPC_BANDS.index(band))
    return ordered[len(ordered) // 2]


def run_epc_job(
    records: Sequence[Mapping[str, Any]],
    postcode_to_dz: Mapping[str, str],
    *,
    zones: Sequence[str] | None = None,
    raw_blob: str = "",
) -> sqlite3.Connection:
    """Load certificates and leave only agg_epc. Staging is dropped before commit."""
    zone_list = list(zones) if zones is not None else dz2022_zone_ids()
    projected = [project_epc_row(row, postcode_to_dz) for row in records]
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("BEGIN")
    conn.execute(
        f"CREATE TABLE epc_staging ({', '.join(f'{col} TEXT' for col in sorted(EPC_COLUMN_ALLOWLIST))})"
    )
    placeholders = ", ".join("?" for _ in sorted(EPC_COLUMN_ALLOWLIST))
    order = sorted(EPC_COLUMN_ALLOWLIST)
    conn.executemany(
        f"INSERT INTO epc_staging ({', '.join(order)}) VALUES ({placeholders})",
        [tuple("" if row.get(col) is None else str(row.get(col)) for col in order) for row in projected],
    )
    staging_cols = {
        row[1]
        for row in conn.execute("PRAGMA table_info(epc_staging)")
    }
    if staging_cols & EPC_BANNED_COLUMNS:
        conn.execute("ROLLBACK")
        raise ValueError("banned column reached staging")
    if raw_blob:
        hits = conn.execute(
            "SELECT 1 FROM epc_staging WHERE "
            + " OR ".join(f"{col} = ?" for col in order),
            tuple(raw_blob for _ in order),
        ).fetchone()
        if hits is not None:
            conn.execute("ROLLBACK")
            raise ValueError("raw file was copied into the database")

    by_zone: dict[str, list[sqlite3.Row]] = defaultdict(list)
    for row in conn.execute("SELECT * FROM epc_staging"):
        by_zone[row["DZ_CODE"]].append(row)

    conn.execute(
        """
        CREATE TABLE agg_epc (
            zone_id TEXT NOT NULL,
            dz_vintage INTEGER NOT NULL,
            certificate_count INTEGER,
            median_floor_area_m2 REAL,
            share_property_type TEXT,
            share_age_band TEXT,
            median_epc_band TEXT,
            suppressed INTEGER NOT NULL,
            PRIMARY KEY (zone_id, dz_vintage)
        )
        """
    )
    for zone_id in zone_list:
        assert_zone_key(zone_id, DZ2022_VINTAGE)
        group = by_zone.get(zone_id, [])
        count = len(group)
        if count < EPC_SUPPRESS_BELOW:
            conn.execute(
                """
                INSERT INTO agg_epc (
                    zone_id, dz_vintage, certificate_count, median_floor_area_m2,
                    share_property_type, share_age_band, median_epc_band, suppressed
                ) VALUES (?, ?, NULL, NULL, NULL, NULL, NULL, 1)
                """,
                (zone_id, DZ2022_VINTAGE),
            )
            continue
        areas = [float(row["TOTAL_FLOOR_AREA"]) for row in group]
        types = [str(row["PROPERTY_TYPE"]) for row in group]
        ages = [str(row["CONSTRUCTION_AGE_BAND"]) for row in group]
        bands = [str(row["CURRENT_ENERGY_RATING"]) for row in group]
        conn.execute(
            """
            INSERT INTO agg_epc (
                zone_id, dz_vintage, certificate_count, median_floor_area_m2,
                share_property_type, share_age_band, median_epc_band, suppressed
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                zone_id,
                DZ2022_VINTAGE,
                count,
                _median_number(areas),
                _shares(types),
                _shares(ages),
                _median_band(bands),
            ),
        )
    conn.execute("DROP TABLE epc_staging")
    conn.execute("COMMIT")
    return conn


def aggregate_point_density(
    counts_by_zone: Mapping[str, int],
    hectares_by_zone: Mapping[str, float],
) -> list[dict[str, Any]]:
    """Internal density table. Column names do not carry an address key."""
    rows: list[dict[str, Any]] = []
    for zone_id in dz2022_zone_ids():
        count = int(counts_by_zone.get(zone_id, 0))
        hectares = hectares_by_zone.get(zone_id)
        per_ha = None if not hectares else count / float(hectares)
        rows.append(
            {
                "zone_id": zone_id,
                "dz_vintage": DZ2022_VINTAGE,
                "point_count": count,
                "points_per_ha": per_ha,
            }
        )
    assert_full_dz2022(rows)
    return rows


def assert_no_uprn_export(columns: Sequence[str], rows: Sequence[Mapping[str, Any]]) -> None:
    for column in columns:
        if "uprn" in column.lower():
            raise ValueError(f"export column names an address key: {column}")
    for row in rows:
        for key, value in row.items():
            if "uprn" in str(key).lower():
                raise ValueError(f"export field names an address key: {key}")
            if _ID_NAME.search(str(key)) and isinstance(value, str) and _UPRN_VALUE.match(value):
                raise ValueError(f"id field holds an address-like value: {key}")


def rollup_ofcom(
    oa_rows: Sequence[Mapping[str, Any]],
    weights: Sequence[tuple[str, str, float]],
) -> list[dict[str, Any]]:
    """Household-weighted OA to DZ2022. Weights must sum to 1 per OA."""
    sums: dict[str, float] = defaultdict(float)
    for oa, zone_id, weight in weights:
        assert_zone_key(zone_id, DZ2022_VINTAGE)
        sums[oa] += float(weight)
    for oa, total in sums.items():
        if abs(total - 1.0) > 1e-9:
            raise ValueError(f"weights for {oa} sum to {total}")
    source = {str(row["oa"]): row for row in oa_rows}
    if set(source) != set(sums):
        raise ValueError("an output area was dropped or double-counted")
    numer: dict[str, dict[str, float]] = defaultdict(
        lambda: {"fibre": 0.0, "gigabit": 0.0, "slow": 0.0, "premises": 0.0}
    )
    allocated = 0.0
    for oa, zone_id, weight in weights:
        row = source[oa]
        premises = float(row["premises"]) * float(weight)
        allocated += premises
        bucket = numer[zone_id]
        bucket["premises"] += premises
        bucket["fibre"] += premises * float(row["full_fibre"])
        bucket["gigabit"] += premises * float(row["gigabit"])
        bucket["slow"] += premises * float(row["below_10"])
    expected = sum(float(row["premises"]) for row in oa_rows)
    if abs(allocated - expected) > 1e-6:
        raise ValueError("premises were dropped or double-counted")
    rows: list[dict[str, Any]] = []
    for zone_id, bucket in numer.items():
        denom = bucket["premises"] or 1.0
        rows.append(
            {
                "zone_id": zone_id,
                "dz_vintage": DZ2022_VINTAGE,
                "share_full_fibre": bucket["fibre"] / denom,
                "share_gigabit": bucket["gigabit"] / denom,
                "share_below_10": bucket["slow"] / denom,
                "premises": bucket["premises"],
            }
        )
    return rows


def serve_lonlat(x: float, y: float, srid: int) -> tuple[float, float]:
    """Return lon/lat. A stored 27700 easting must not be served as-is."""
    if srid == 4326:
        lon, lat = float(x), float(y)
    elif srid == 27700:
        lon, lat = _TO_WGS84.transform(float(x), float(y))
    else:
        raise ValueError(f"unsupported SRID {srid}")
    if abs(lon) > 180 or abs(lat) > 90:
        raise ValueError("served coordinate is outside lon/lat bounds")
    return float(lon), float(lat)


def suppress_site_totals(count: int, hectares: float) -> tuple[str, float | None]:
    """Zero stays zero. One or two sites hide the area. Three or more show it."""
    if count <= 0:
        return "0", 0.0
    if count < SMALL_SITE_MIN:
        return "<3", None
    return str(count), float(hectares)


def rollup_council_measure(
    *,
    zones_by_council: Mapping[str, Sequence[str]],
    covered_councils: set[str],
    sites: Sequence[Mapping[str, Any]],
    use_class: bool = False,
) -> list[dict[str, Any]]:
    """DZ totals for council-direct V&DL, contaminated land, or LDP.

    Uncovered councils stay null. Covered councils with no sites are zero.
    Site names and geometry are not copied.
    """
    council_of: dict[str, str] = {}
    for council, zones in zones_by_council.items():
        for zone_id in zones:
            assert_zone_key(zone_id, DZ2022_VINTAGE)
            council_of[zone_id] = council
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = defaultdict(list)
    for site in sites:
        zone_id = str(site["zone_id"])
        klass = str(site.get("use_class") or "")
        grouped[(zone_id, klass if use_class else "")].append(site)

    rows: list[dict[str, Any]] = []
    classes = sorted({key[1] for key in grouped}) or [""]
    for zone_id, council in council_of.items():
        covered = council in covered_councils
        class_list = classes if use_class else [""]
        for klass in class_list:
            bucket = grouped.get((zone_id, klass), [])
            if not covered:
                row = {
                    "zone_id": zone_id,
                    "dz_vintage": DZ2022_VINTAGE,
                    "coverage": "uncovered",
                    "source_council": council,
                    "hectares": None,
                }
                if use_class:
                    row["use_class"] = klass or None
                    row["site_count_label"] = None
                else:
                    row["site_count_label"] = None
                rows.append(row)
                continue
            hectares = sum(float(site.get("hectares") or 0) for site in bucket)
            if use_class:
                rows.append(
                    {
                        "zone_id": zone_id,
                        "dz_vintage": DZ2022_VINTAGE,
                        "coverage": "covered",
                        "source_council": council,
                        "use_class": klass or "unspecified",
                        "hectares": hectares,
                    }
                )
                continue
            label, shown = suppress_site_totals(len(bucket), hectares)
            rows.append(
                {
                    "zone_id": zone_id,
                    "dz_vintage": DZ2022_VINTAGE,
                    "coverage": "covered",
                    "source_council": council,
                    "site_count_label": label,
                    "hectares": shown,
                }
            )
    return rows


def coverage_legend(row: Mapping[str, Any]) -> dict[str, str]:
    """Uncovered land is grey and labelled 'no open data', never as zero."""
    if row.get("coverage") == "uncovered":
        return {"label": NO_OPEN_DATA_LABEL, "fill": "#bdbdbd"}
    label = str(row.get("site_count_label"))
    if label.lower() in BANNED_COVERAGE_LABELS:
        raise ValueError(label)
    return {"label": label, "fill": "#2e7d32"}


def public_site_export(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    exported: list[dict[str, Any]] = []
    for row in rows:
        clean = {key: value for key, value in row.items() if key not in SITE_EXPORT_BANNED}
        if set(clean) & SITE_EXPORT_BANNED:
            raise ValueError("site field survived export")
        exported.append(clean)
    return exported


def assert_style_urls_free(urls: Sequence[str]) -> None:
    for url in urls:
        if _KEYED_URL.search(url):
            raise ValueError(f"keyed tile endpoint: {url}")


def assert_no_currency_columns() -> None:
    for name, columns in AGG_COLUMNS.items():
        for column in columns:
            lower = column.lower()
            if any(token in lower for token in CURRENCY_TOKENS):
                raise ValueError(f"{name}.{column} looks like a currency column")
            if "£" in column:
                raise ValueError(column)


def allowed_tile_keys() -> dict[str, frozenset[str]]:
    return TILE_PROPERTY_ALLOWLIST


__all__ = [
    "AGG_COLUMNS",
    "EPC_COLUMN_ALLOWLIST",
    "aggregate_point_density",
    "assert_full_dz2022",
    "assert_no_currency_columns",
    "assert_no_uprn_export",
    "assert_style_urls_free",
    "coverage_legend",
    "filter_tile_properties",
    "public_site_export",
    "rollup_council_measure",
    "rollup_ofcom",
    "run_epc_job",
    "serve_lonlat",
    "suppress_site_totals",
]
