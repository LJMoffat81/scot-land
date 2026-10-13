"""DZ2022 surface rent path: value-weighted crosswalk from DZ2011 (internal only).

Designer brief v3.1 / CHARTER: surface rent is still computed on DZ2011 (RoS
native) and needs a 2011→2022 crosswalk before the SG roll-up. DZ2022 is the
unit of account. Crosswalk is value-weighted (economic rules §11 — never
population or area). Results stay ``publish_level=internal`` and ``publication_status=blocked``
until ECONOMIC_RULES / publishability clearance; source ``ok`` does not
unblock. Public layers already filter that level out.

Fail loudly: missing sources, weights that do not sum to 1, forbidden methods,
mixed price years / valuation dates, or codes outside the official ranges.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable, Mapping, MutableMapping, Sequence

from georgist.surface_zones import CODE_RANGES, validate_code, vintage_int

WEIGHT_TOL = 1e-6
CROSSWALK_METHOD = "value_weighted"
PUBLISH_LEVEL = "internal"
# Blocked always wins: new DZ2022 rows stay blocked unless explicitly cleared
# later via the publishability path (never by inheriting source ``ok``).
PUBLICATION_STATUS = "blocked"
PROXY_TAGS = (
    "crosswalked_from_dz2011",
    "research_estimate",
    "unpublished_pending_economic_rules",
)

# Zone totals that add under value weights. Per-dwelling / diagnostic fields are
# recomputed or cleared — never silently area-weighted.
SUMMABLE_FIELDS = (
    "measured_rent",
    "uncertainty_low",
    "uncertainty_high",
    "land_value_zone_total",
    "infra_share",
    "planning_uplift",
    "policy_rent",
)


class CrosswalkError(ValueError):
    """DZ2011→DZ2022 surface crosswalk refused (loud fail)."""


def _num(v) -> float | None:
    if v is None:
        return None
    return float(v)


def _tags(row: Mapping) -> list[str]:
    raw = row.get("proxy_tags") or ()
    if isinstance(raw, str):
        return [t for t in raw.split(";") if t]
    return list(raw)


def validate_value_crosswalk(pairs: Sequence[Mapping]) -> dict[str, list[tuple[str, float]]]:
    """Validate a value-weighted DZ2011→DZ2022 crosswalk; return {dz2011: [(dz2022, w), ...]}.

    Each pair needs ``dz2011``, ``dz2022``, ``weight``. Optional ``method`` must be
    ``value_weighted`` or ``address_uprn`` (population / area methods are refused).
    Weights per dz2011 must sum to 1 within WEIGHT_TOL.
    """
    if not pairs:
        raise CrosswalkError("value crosswalk is empty")
    by_src: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for i, p in enumerate(pairs):
        try:
            src = str(p["dz2011"]).strip()
            dst = str(p["dz2022"]).strip()
            w = float(p["weight"])
        except (KeyError, TypeError, ValueError) as exc:
            raise CrosswalkError(f"crosswalk row {i} missing dz2011/dz2022/weight: {exc}") from exc
        validate_code(src, 2011)
        validate_code(dst, 2022)
        method = str(p.get("method") or CROSSWALK_METHOD).strip()
        if method in ("pop_hhres_2022", "footprint_area", "area_weighted", "population"):
            raise CrosswalkError(
                f"surface crosswalk may not use {method!r} (rules 11); "
                f"use value_weighted or address_uprn (row {i}: {src}->{dst})"
            )
        if method not in (CROSSWALK_METHOD, "address_uprn"):
            raise CrosswalkError(f"unknown surface crosswalk method {method!r} at row {i}")
        if w < 0 or w > 1 + WEIGHT_TOL:
            raise CrosswalkError(f"weight {w} out of [0,1] for {src}->{dst}")
        by_src[src].append((dst, w))
    for src, edges in by_src.items():
        total = sum(w for _, w in edges)
        if abs(total - 1.0) > WEIGHT_TOL:
            raise CrosswalkError(
                f"weights for {src} sum to {total}, not 1.0 (tol {WEIGHT_TOL})"
            )
    return dict(by_src)


def one_to_one_value_crosswalk(people_crosswalk_rows: Iterable[Mapping]) -> list[dict]:
    """Build a value-weighted crosswalk from 1:1 people-crosswalk topology only.

    Split or merged zones need an explicit value/address weight file — they are
    refused here rather than silently using population shares (rules 11).
    """
    targets: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, set[str]] = defaultdict(set)
    rows = list(people_crosswalk_rows)
    if not rows:
        raise CrosswalkError("people crosswalk is empty")
    for r in rows:
        src, dst = str(r["dz2011"]).strip(), str(r["dz2022"]).strip()
        targets[src].add(dst)
        sources[dst].add(src)
    out: list[dict] = []
    for r in rows:
        src, dst = str(r["dz2011"]).strip(), str(r["dz2022"]).strip()
        if len(targets[src]) != 1 or len(sources[dst]) != 1:
            continue
        w = float(r.get("weight", 1.0))
        if abs(w - 1.0) > WEIGHT_TOL:
            raise CrosswalkError(
                f"1:1 pair {src}->{dst} has weight {w}, expected 1.0"
            )
        out.append(
            {
                "dz2011": src,
                "dz2022": dst,
                "weight": 1.0,
                "method": CROSSWALK_METHOD,
            }
        )
    if not out:
        raise CrosswalkError("no 1:1 DZ2011↔DZ2022 pairs available for value_weighted topology")
    validate_value_crosswalk(out)
    return out


def require_complete_value_crosswalk(
    people_crosswalk_rows: Iterable[Mapping],
    *,
    value_pairs: Sequence[Mapping] | None = None,
) -> list[dict]:
    """1:1 topology plus explicit value weights for every split/merge; else loud fail."""
    rows = list(people_crosswalk_rows)
    targets: dict[str, set[str]] = defaultdict(set)
    sources: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        targets[str(r["dz2011"]).strip()].add(str(r["dz2022"]).strip())
        sources[str(r["dz2022"]).strip()].add(str(r["dz2011"]).strip())
    need_explicit = sorted(
        s for s, ds in targets.items() if len(ds) != 1 or any(len(sources[d]) != 1 for d in ds)
    )
    out = one_to_one_value_crosswalk(rows)
    if need_explicit:
        if not value_pairs:
            raise CrosswalkError(
                f"{len(need_explicit)} DZ2011 zones split or merge and need explicit "
                f"value_weighted/address_uprn weights (e.g. {need_explicit[:3]}); "
                "population shares are forbidden for surface rent (rules 11)"
            )
        explicit = validate_value_crosswalk(value_pairs)
        missing = [s for s in need_explicit if s not in explicit]
        if missing:
            raise CrosswalkError(
                f"explicit value crosswalk missing {len(missing)} DZ2011 codes "
                f"(e.g. {missing[:3]})"
            )
        # Drop any 1:1 rows superseded by explicit coverage of the same source.
        covered = set(explicit)
        out = [p for p in out if p["dz2011"] not in covered]
        for src, edges in explicit.items():
            for dst, w in edges:
                out.append(
                    {
                        "dz2011": src,
                        "dz2022": dst,
                        "weight": w,
                        "method": CROSSWALK_METHOD,
                    }
                )
    return out


def _scale_summable(row: Mapping, weight: float) -> dict[str, float | None]:
    out: dict[str, float | None] = {}
    for key in SUMMABLE_FIELDS:
        v = _num(row.get(key))
        out[key] = None if v is None else v * weight
    return out


def _merge_numeric(parts: Sequence[Mapping], key: str) -> float | None:
    vals = [_num(p.get(key)) for p in parts]
    present = [v for v in vals if v is not None]
    if not present:
        return None
    if len(present) != len(vals):
        raise CrosswalkError(f"mixed null/non-null {key} when merging DZ2022 contributions")
    return sum(present)


def crosswalk_surface_to_dz2022(
    dz2011_rows: Sequence[Mapping],
    crosswalk: Sequence[Mapping],
    *,
    dwellings_by_code: Mapping[str, int] | None = None,
) -> list[dict]:
    """Push DZ2011 surface rows onto DZ2022 via a validated value-weighted crosswalk.

    Every output row is vintage 2022, ``crosswalk_method=value_weighted``,
    ``publish_level=internal``, ``publication_status=blocked``. When
    ``dwellings_by_code`` supplies the DZ2022 dwelling count, per-dwelling rent
    is recomputed; otherwise dwellings and per-dwelling figures are left null
    (never invented).
    """
    by_src = validate_value_crosswalk(crosswalk)
    sources: dict[str, Mapping] = {}
    for row in dz2011_rows:
        code = str(row["code"]).strip()
        vin = vintage_int(row["vintage"])
        if vin != 2011:
            raise CrosswalkError(f"source row {code} has vintage {vin}, expected 2011")
        validate_code(code, 2011)
        if code in sources:
            raise CrosswalkError(f"duplicate DZ2011 source row for {code}")
        sources[code] = row

    # All sources that appear in the crosswalk must be present; extras are ignored
    # only when the caller passes a partial crosswalk for a subset run — but then
    # every listed source must exist.
    missing = sorted(s for s in by_src if s not in sources)
    if missing:
        raise CrosswalkError(
            f"DZ2011 surface rows missing for {len(missing)} crosswalk sources "
            f"(e.g. {missing[:3]})"
        )

    price_years = {sources[s]["price_year"] for s in by_src}
    val_dates = {str(sources[s]["valuation_date"]) for s in by_src}
    if len(price_years) != 1:
        raise CrosswalkError(f"mixed price_year in DZ2011 sources: {sorted(price_years)}")
    if len(val_dates) != 1:
        raise CrosswalkError(f"mixed valuation_date in DZ2011 sources: {sorted(val_dates)}")

    contribs: dict[str, list[dict]] = defaultdict(list)
    for src, edges in by_src.items():
        base = sources[src]
        for dst, w in edges:
            piece = dict(base)
            piece.update(_scale_summable(base, w))
            piece["_src"] = src
            piece["_weight"] = w
            contribs[dst].append(piece)

    out: list[dict] = []
    for dst in sorted(contribs):
        parts = contribs[dst]
        validate_code(dst, 2022)
        head = parts[0]
        row: MutableMapping = {k: head.get(k) for k in head if not str(k).startswith("_")}
        row["code"] = dst
        row["vintage"] = 2022
        row["crosswalk_method"] = CROSSWALK_METHOD
        row["publish_level"] = PUBLISH_LEVEL
        # Ignore source publication_status: blocked always wins on conversion.
        row["publication_status"] = PUBLICATION_STATUS
        for key in SUMMABLE_FIELDS:
            row[key] = _merge_numeric(parts, key)
        # Per-dwelling / price diagnostics do not add across splits/merges.
        multi = len(parts) > 1 or any(abs(p["_weight"] - 1.0) > WEIGHT_TOL for p in parts)
        if multi:
            for clear in (
                "price_gbp",
                "price_indexed_gbp",
                "typical_sale_gbp",
                "mean_median_ratio",
                "raw_residual",
                "land_value",
                "land_value_low",
                "land_value_high",
                "drc_gbp",
                "drc_low_gbp",
                "drc_high_gbp",
                "rebuild_new_gbp",
                "remaining_factor",
                "measured_rent_per_dwelling",
                "measured_rent_per_resident",
                "rent_per_res_ha",
                "residential_land_ha",
                "sales_n_pooled",
                "brma_mix",
                "drc_swing_gbp",
            ):
                row[clear] = None
            row["price_skew_flag"] = None
            row["negative_residual"] = False
            row["fill_method"] = "model_filled"
            row["quality"] = "modelled"
        dwellings = None
        if dwellings_by_code is not None:
            if dst not in dwellings_by_code:
                raise CrosswalkError(f"DZ2022 dwellings missing for {dst}")
            dwellings = int(dwellings_by_code[dst])
            if dwellings < 0:
                raise CrosswalkError(f"negative dwellings for {dst}")
        row["dwellings"] = dwellings
        if dwellings is not None and dwellings > 0 and row.get("measured_rent") is not None:
            row["measured_rent_per_dwelling"] = round(float(row["measured_rent"]) / dwellings, 2)
        elif dwellings == 0:
            row["measured_rent"] = None
            row["measured_rent_per_dwelling"] = None
            row["uncertainty_low"] = None
            row["uncertainty_high"] = None
            row["fill_method"] = "not_applicable"
            row["quality"] = "placeholder"
        tags = set(_tags(head))
        for p in parts[1:]:
            tags.update(_tags(p))
        tags.update(PROXY_TAGS)
        if multi:
            tags.add("value_weighted_merge_or_split")
        row["proxy_tags"] = sorted(tags)
        row["method"] = head.get("method") or "residual_drc_surface_v1"
        # Range check — DZ2022 codes only.
        lo, hi = CODE_RANGES[2022]
        n = int(dst[3:])
        if not (lo <= n <= hi):
            raise CrosswalkError(f"code {dst!r} outside DZ2022 range")
        out.append(dict(row))
    return out
