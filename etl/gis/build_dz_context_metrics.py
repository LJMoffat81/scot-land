#!/usr/bin/env python3
"""Build Data Zone context metrics: house prices (RoS + council HPI), SIMD, density.

Joins open OGL tables already in the repo. Does NOT invent zone polygons —
geometry stays with the Data Zone boundaries loader.

Outputs: data/processed/gis/dz_context_metrics.csv
Run from repo root: python etl/gis/build_dz_context_metrics.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "data" / "processed" / "gis" / "dz_context_metrics.csv"
MANIFEST = REPO / "data" / "processed" / "gis" / "manifest.csv"

SPINE = REPO / "data" / "processed" / "datazones" / "zone_spine.csv"
SIMD2011 = REPO / "data" / "processed" / "datazones" / "simd2020v2_dz2011.csv"
SIMD2022 = REPO / "data" / "processed" / "datazones" / "simd2020v2_on_dz2022.csv"
ZONE_HA = REPO / "data" / "processed" / "gis" / "dz_residential_land.csv"
ROS_PRICES = REPO / "data" / "processed" / "dz2011_prices.csv"
COUNCILS = REPO / "data" / "processed" / "councils.json"

COLUMNS = [
    "code",
    "vintage",
    "name",
    "la_code",
    "la_name",
    "population",
    "pop_year",
    "zone_ha",
    "population_density_per_km2",
    "simd_rank",
    "simd_decile",
    "simd_quintile",
    "in_simd_20pct_most_deprived",
    "house_price_median_gbp",
    "house_price_sales_n",
    "council_hpi_average_price_gbp",
    "hpi_period",
    "price_basis",
]


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def _i(v: str | None) -> int | None:
    if v is None or v == "":
        return None
    return int(float(v))


def build_rows() -> list[dict[str, object]]:
    spine = _read_csv(SPINE)
    ha_by = {(r["code"], int(r["vintage"])): _f(r.get("zone_ha")) for r in _read_csv(ZONE_HA)}
    simd11 = {r["code"]: r for r in _read_csv(SIMD2011)}
    simd22 = {r["code"]: r for r in _read_csv(SIMD2022)}
    ros = {r["dz2011"]: r for r in _read_csv(ROS_PRICES)}

    with COUNCILS.open(encoding="utf-8") as fh:
        councils_doc = json.load(fh)
    hpi_period = councils_doc.get("hpi_period") or ""
    hpi_by_la = {
        c["code"]: c.get("average_price_gbp")
        for c in councils_doc.get("councils") or []
        if c.get("code")
    }

    rows: list[dict[str, object]] = []
    for s in spine:
        code = s["code"]
        vintage = int(s["vintage"])
        population = _i(s.get("population"))
        zone_ha = ha_by.get((code, vintage))
        density = None
        if population is not None and zone_ha and zone_ha > 0:
            # zone_ha is hectares; km² = ha / 100
            density = round(population / (zone_ha / 100.0), 1)

        simd_rank = None
        simd_decile = None
        simd_quintile = None
        if vintage == 2011 and code in simd11:
            sm = simd11[code]
            simd_rank = _i(sm.get("simd_rank"))
            simd_decile = _i(sm.get("simd_decile"))
            simd_quintile = _i(sm.get("simd_quintile"))
        elif vintage == 2022 and code in simd22:
            sm = simd22[code]
            simd_decile = _i(sm.get("modal_decile"))
            if simd_decile is not None:
                simd_quintile = (simd_decile + 1) // 2

        in_20 = None
        if simd_decile is not None:
            in_20 = simd_decile <= 2

        house_med = None
        house_n = None
        if vintage == 2011 and code in ros:
            rp = ros[code]
            house_med = _f(rp.get("dz_med_pool_approx"))
            house_n = _i(rp.get("dz_n_pool"))
            if house_med is not None:
                house_med = round(house_med)

        la_code = s.get("la_code") or ""
        council_hpi = hpi_by_la.get(la_code)
        if council_hpi is not None:
            council_hpi = round(float(council_hpi))

        if house_med is not None:
            price_basis = "ros_dz_median_pool_2021_2023"
        elif council_hpi is not None:
            price_basis = "council_uk_hpi"
        else:
            price_basis = ""

        rows.append(
            {
                "code": code,
                "vintage": vintage,
                "name": s.get("name") or "",
                "la_code": la_code,
                "la_name": s.get("la_name") or "",
                "population": population if population is not None else "",
                "pop_year": _i(s.get("pop_year")) if s.get("pop_year") else "",
                "zone_ha": round(zone_ha, 4) if zone_ha is not None else "",
                "population_density_per_km2": density if density is not None else "",
                "simd_rank": simd_rank if simd_rank is not None else "",
                "simd_decile": simd_decile if simd_decile is not None else "",
                "simd_quintile": simd_quintile if simd_quintile is not None else "",
                "in_simd_20pct_most_deprived": (
                    "true" if in_20 is True else "false" if in_20 is False else ""
                ),
                "house_price_median_gbp": house_med if house_med is not None else "",
                "house_price_sales_n": house_n if house_n is not None else "",
                "council_hpi_average_price_gbp": (
                    council_hpi if council_hpi is not None else ""
                ),
                "hpi_period": hpi_period,
                "price_basis": price_basis,
            }
        )
    rows.sort(key=lambda r: (int(r["vintage"]), str(r["code"])))
    return rows


def write_csv(rows: list[dict[str, object]]) -> tuple[int, str]:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row[k] for k in COLUMNS})
    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    return len(rows), digest


def upsert_manifest(rows: int, sha256: str) -> None:
    text = MANIFEST.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(text.splitlines())
    fieldnames = list(reader.fieldnames or [])
    existing = [r for r in reader if r.get("file") != "dz_context_metrics.csv"]
    entry = {
        "file": "dz_context_metrics.csv",
        "owner": "gis",
        "source": (
            "NRS SAPE population (zone_spine) + GIS dz_residential_land zone_ha; "
            "SG SIMD 2020v2 (DZ2011 ranks/deciles; DZ2022 modal decile via people crosswalk); "
            "RoS residential sales medians DZ2011 (data.gov.scot); "
            "UK HPI council averages attributed via LA code (HM Land Registry / RoS / ONS)"
        ),
        "licence": "OGL v3.0",
        "attribution": (
            "Contains National Records of Scotland data (small area population estimates) "
            "© Crown copyright and database right 2026; contains Scottish Government data "
            "(SIMD 2020v2) © Crown copyright 2025; contains Registers of Scotland data "
            "(residential sales and price, via data.gov.scot) © Crown copyright 2026; "
            "UK House Price Index © Crown copyright (HM Land Registry, Registers of Scotland, ONS); "
            "data zone areas from Scot-LAND GIS dz_residential_land (SG boundaries / OGL). "
            "Licensed under the Open Government Licence v3.0."
        ),
        "publish_level": "public_zone",
        "zone_vintage": "2011;2022",
        "key": "(code, vintage)",
        "rows": str(rows),
        "sha256": sha256,
        "source_year": "",
    }
    for col in fieldnames:
        entry.setdefault(col, "")
    existing.append(entry)
    with MANIFEST.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        for row in existing:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def main() -> int:
    for path in (SPINE, SIMD2011, SIMD2022, ZONE_HA, ROS_PRICES, COUNCILS, MANIFEST):
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 1
    rows = build_rows()
    n, digest = write_csv(rows)
    upsert_manifest(n, digest)
    print(f"wrote {OUT} rows={n} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
