"""Scottish Government surface-rent roll-up (internal / unpublished).

Hierarchy (designer brief v3.1 / Laurie charter): Data Zone 2022 (S01) →
Intermediate Zone (S02) → Council Area (S12) → Scotland (S92). Parent links
come from ``datazones.zone_spine`` (``iz_code``, ``la_code``), which carries the
official SG 2022 Data Zone lookup (OGL v3.0;
https://statistics.gov.scot/data/data-zone-lookup-2022). Each DZ contributes
once — no double counting.

Only ``measured_rent`` is summed (rules §2). Mixed ``price_year`` or
``valuation_date`` refuses the roll-up. Every aggregate row is
``publish_level=internal`` so public routes never serve these £ figures
(roll-up figures stay unpublished until ECONOMIC_RULES sign-off).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, Sequence

from georgist.surface_dz2022 import combine_estimate_labels
from georgist.surface_zones import validate_code, vintage_int

GEO_LEVELS = ("data_zone", "intermediate_zone", "council", "scotland")
SCOTLAND_CODE = "S92000003"
PUBLISH_LEVEL = "internal"
WEIGHT_TOL = 1e-6


class RollupError(ValueError):
    """SG surface-rent roll-up refused (loud fail)."""


def _num(v) -> float | None:
    if v is None:
        return None
    return float(v)


def _code_prefix_ok(level: str, code: str) -> bool:
    if level == "data_zone":
        return code.startswith("S01") and len(code) == 9
    if level == "intermediate_zone":
        return code.startswith("S02") and len(code) == 9
    if level == "council":
        return code.startswith("S12") and len(code) == 9
    if level == "scotland":
        return code == SCOTLAND_CODE
    raise RollupError(f"unknown geo_level {level!r}")


def spine_index_dz2022(spine_rows: Iterable[Mapping]) -> dict[str, Mapping]:
    """Index DZ2022 spine rows by code; refuse missing IZ/LA or IZ spanning LAs."""
    by_code: dict[str, Mapping] = {}
    iz_to_la: dict[str, str] = {}
    for r in spine_rows:
        vin = vintage_int(r["vintage"])
        if vin != 2022:
            continue
        code = str(r["code"]).strip()
        validate_code(code, 2022)
        iz = str(r.get("iz_code") or "").strip()
        la = str(r.get("la_code") or "").strip()
        if not iz.startswith("S02") or len(iz) != 9:
            raise RollupError(f"DZ2022 {code} has invalid iz_code {iz!r}")
        if not la.startswith("S12") or len(la) != 9:
            raise RollupError(f"DZ2022 {code} has invalid la_code {la!r}")
        if iz in iz_to_la and iz_to_la[iz] != la:
            raise RollupError(f"IZ {iz} spans multiple councils ({iz_to_la[iz]} and {la})")
        iz_to_la[iz] = la
        if code in by_code:
            raise RollupError(f"duplicate zone_spine row for {code} vintage 2022")
        by_code[code] = r
    if not by_code:
        raise RollupError("no DZ2022 rows in zone_spine")
    return by_code


def _agg_row(
    *,
    geo_level: str,
    code: str,
    parent_code: str | None,
    valuation_date: str,
    price_year: int,
    rents: Sequence[float | None],
    value_tier: str,
    crosswalk_method: str,
    source_id: str,
    licence: str,
    method: str,
    zone_codes: Sequence[str],
    estimate_label: str,
) -> dict:
    if not _code_prefix_ok(geo_level, code):
        raise RollupError(f"{geo_level} code {code!r} fails SG prefix check")
    present = [r for r in rents if r is not None]
    withheld = len(rents) - len(present)
    if not rents:
        raise RollupError(f"no child zones for {geo_level} {code}")
    measured = sum(present) if present else None
    return {
        "geo_level": geo_level,
        "code": code,
        "vintage": 2022,
        "valuation_date": valuation_date,
        "price_year": int(price_year),
        "measured_rent": measured,
        "zone_count": len(zone_codes),
        "withheld_zone_count": withheld,
        "value_tier": value_tier,
        "quality": "derived",
        "publish_level": PUBLISH_LEVEL,
        "publication_status": "ok",
        "commons_class": "surface",
        "crosswalk_method": crosswalk_method,
        "source_id": source_id,
        "licence": licence,
        "method": method,
        "parent_code": parent_code,
        "estimate_label": estimate_label,
        "child_zone_codes": list(zone_codes),
        "note": (
            "INTERNAL / UNPUBLISHED SG roll-up. Not an official valuation or tax bill. "
            "Not served on public routes."
        ),
    }


def rollup_surface_rent_dz2022(
    dz2022_rows: Sequence[Mapping],
    spine_rows: Iterable[Mapping],
) -> list[dict]:
    """Roll DZ2022 surface rents up IZ → council → Scotland.

    Input rows must be vintage 2022. ``publish_level`` on inputs may be internal;
    aggregates are always internal. Returns leaf data_zone rows plus the three
    parent levels (for a single internal view of the hierarchy).
    """
    if not dz2022_rows:
        raise RollupError("no DZ2022 surface rows to roll up")
    spine = spine_index_dz2022(spine_rows)

    by_code: dict[str, Mapping] = {}
    for row in dz2022_rows:
        code = str(row["code"]).strip()
        vin = vintage_int(row["vintage"])
        if vin != 2022:
            raise RollupError(f"rollup requires vintage 2022, got {vin} for {code}")
        validate_code(code, 2022)
        if code not in spine:
            raise RollupError(f"zone_spine missing DZ2022 row for {code}")
        if code in by_code:
            raise RollupError(f"duplicate surface row for {code}")
        by_code[code] = row

    price_years = {r["price_year"] for r in by_code.values()}
    val_dates = {str(r["valuation_date"]) for r in by_code.values()}
    tiers = {r.get("value_tier") for r in by_code.values()}
    methods_xw = {r.get("crosswalk_method") for r in by_code.values()}
    if len(price_years) != 1:
        raise RollupError(f"mixed price_year in DZ2022 rows: {sorted(price_years)}")
    if len(val_dates) != 1:
        raise RollupError(f"mixed valuation_date in DZ2022 rows: {sorted(val_dates)}")
    if None in tiers or len(tiers) != 1:
        raise RollupError(f"mixed or missing value_tier in DZ2022 rows: {tiers}")
    if None in methods_xw or len(methods_xw) != 1:
        raise RollupError(f"mixed or missing crosswalk_method: {methods_xw}")

    price_year = next(iter(price_years))
    valuation_date = next(iter(val_dates))
    value_tier = next(iter(tiers))
    crosswalk_method = next(iter(methods_xw))
    # Provenance from first row; roll-up does not invent a new licence.
    head = next(iter(by_code.values()))
    source_id = str(head.get("source_id") or "surface_rent_dz2022_rollup")
    licence = str(head.get("licence") or "")
    if not licence:
        raise RollupError("licence required on surface rows for roll-up provenance")
    method = str(head.get("method") or "residual_drc_surface_v1") + "+sg_rollup_dz2022"

    def _labels_for(zones: Sequence[str]) -> str:
        labels = [str(by_code[z].get("estimate_label") or "") for z in zones]
        if any(not lbl for lbl in labels):
            raise RollupError(
                f"estimate_label required on every DZ2022 row for roll-up "
                f"(missing on {[z for z, lbl in zip(zones, labels) if not lbl][:3]})"
            )
        return combine_estimate_labels(labels)

    out: list[dict] = []
    # Leaves (data zone) — same £ figures, marked as hierarchy leaves.
    for code in sorted(by_code):
        row = by_code[code]
        sp = spine[code]
        out.append(
            _agg_row(
                geo_level="data_zone",
                code=code,
                parent_code=str(sp["iz_code"]).strip(),
                valuation_date=valuation_date,
                price_year=price_year,
                rents=[_num(row.get("measured_rent"))],
                value_tier=value_tier,
                crosswalk_method=crosswalk_method,
                source_id=source_id,
                licence=licence,
                method=method,
                zone_codes=[code],
                estimate_label=_labels_for([code]),
            )
        )

    iz_children: dict[str, list[str]] = defaultdict(list)
    la_children: dict[str, list[str]] = defaultdict(list)
    for code in by_code:
        sp = spine[code]
        iz_children[str(sp["iz_code"]).strip()].append(code)
        la_children[str(sp["la_code"]).strip()].append(code)

    for iz in sorted(iz_children):
        zones = sorted(iz_children[iz])
        la = str(spine[zones[0]]["la_code"]).strip()
        out.append(
            _agg_row(
                geo_level="intermediate_zone",
                code=iz,
                parent_code=la,
                valuation_date=valuation_date,
                price_year=price_year,
                rents=[_num(by_code[z].get("measured_rent")) for z in zones],
                value_tier=value_tier,
                crosswalk_method=crosswalk_method,
                source_id=source_id,
                licence=licence,
                method=method,
                zone_codes=zones,
                estimate_label=_labels_for(zones),
            )
        )

    for la in sorted(la_children):
        zones = sorted(la_children[la])
        out.append(
            _agg_row(
                geo_level="council",
                code=la,
                parent_code=SCOTLAND_CODE,
                valuation_date=valuation_date,
                price_year=price_year,
                rents=[_num(by_code[z].get("measured_rent")) for z in zones],
                value_tier=value_tier,
                crosswalk_method=crosswalk_method,
                source_id=source_id,
                licence=licence,
                method=method,
                zone_codes=zones,
                estimate_label=_labels_for(zones),
            )
        )

    all_zones = sorted(by_code)
    out.append(
        _agg_row(
            geo_level="scotland",
            code=SCOTLAND_CODE,
            parent_code=None,
            valuation_date=valuation_date,
            price_year=price_year,
            rents=[_num(by_code[z].get("measured_rent")) for z in all_zones],
            value_tier=value_tier,
            crosswalk_method=crosswalk_method,
            source_id=source_id,
            licence=licence,
            method=method,
            zone_codes=all_zones,
            estimate_label=_labels_for(all_zones),
        )
    )

    # Integrity: Scotland total == sum of councils == sum of IZs == sum of DZ rents present.
    by_level = {lvl: [r for r in out if r["geo_level"] == lvl] for lvl in GEO_LEVELS}

    def _sum_rent(rows: Sequence[Mapping]) -> float:
        return sum(float(r["measured_rent"]) for r in rows if r["measured_rent"] is not None)

    s_dz = _sum_rent(by_level["data_zone"])
    s_iz = _sum_rent(by_level["intermediate_zone"])
    s_la = _sum_rent(by_level["council"])
    s_sc = _sum_rent(by_level["scotland"])
    if max(abs(s_dz - s_iz), abs(s_dz - s_la), abs(s_dz - s_sc)) > WEIGHT_TOL:
        raise RollupError(
            f"roll-up totals disagree DZ={s_dz} IZ={s_iz} LA={s_la} Scotland={s_sc}"
        )
    return out


# Columns persisted on surface_rent_rollup (child_zone_codes / note stay in-memory only).
ROLLUP_DB_COLUMNS = (
    "geo_level",
    "code",
    "vintage",
    "valuation_date",
    "price_year",
    "measured_rent",
    "zone_count",
    "withheld_zone_count",
    "value_tier",
    "quality",
    "publish_level",
    "publication_status",
    "commons_class",
    "crosswalk_method",
    "source_id",
    "licence",
    "method",
    "parent_code",
)


def rollup_db_rows(rows: Sequence[Mapping]) -> list[dict]:
    """Strip in-memory-only fields; refuse any non-internal publish_level."""
    out = []
    for r in rows:
        if r.get("geo_level") == "data_zone":
            continue  # leaves live on surface_rent_dz
        if r.get("publish_level") != PUBLISH_LEVEL:
            raise RollupError(
                f"rollup row {r.get('geo_level')}/{r.get('code')} must be publish_level=internal"
            )
        out.append({c: r.get(c) for c in ROLLUP_DB_COLUMNS})
    return out
