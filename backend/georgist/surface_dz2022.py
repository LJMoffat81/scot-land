"""DZ2022 surface rent path: address-UPRN (or value-weighted) crosswalk from DZ2011.

Designer brief v3.1 / CHARTER: surface rent is still computed on DZ2011 (RoS
native) and needs a 2011→2022 crosswalk before the SG roll-up. DZ2022 is the
unit of account. Preferred path is address-point (UPRN) shares from a configured
local GIS handoff folder (economic rules §11 — never population or area).
Value-weighted shares remain allowed where addresses are unavailable. Results
stay ``publish_level=internal`` and ``publication_status=blocked`` until
ECONOMIC_RULES / publishability clearance; source ``ok`` does not unblock.

Fail loudly: missing sources, rent zones absent from the crosswalk, weights that
do not sum to 1, forbidden methods, mixed price years / valuation dates, zero
dwellings on a 2022 destination, codes outside the official ranges, or rent
landing on a DZ2022 zone with no address points at all.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

from georgist.surface_paths import data_dir
from georgist.surface_zones import CODE_RANGES, validate_code, vintage_int

WEIGHT_TOL = 1e-6
PENNY = 0.005  # Scotland total conservation to the penny
CROSSWALK_METHOD = "value_weighted"  # legacy explicit value shares
ADDRESS_CROSSWALK_METHOD = "address_uprn"
GIS_UPRN_METHOD = "uprn_point_in_polygon"
# Surface stamp for address path (schema enum); GIS file keeps uprn_point_in_polygon.
METHOD_STAMP = {
    CROSSWALK_METHOD: CROSSWALK_METHOD,
    ADDRESS_CROSSWALK_METHOD: ADDRESS_CROSSWALK_METHOD,
    GIS_UPRN_METHOD: ADDRESS_CROSSWALK_METHOD,
}
ALLOWED_PAIR_METHODS = frozenset(METHOD_STAMP)
FORBIDDEN_METHODS = frozenset(
    ("pop_hhres_2022", "footprint_area", "area_weighted", "population", "area")
)
PUBLISH_LEVEL = "internal"
# Blocked always wins: new DZ2022 rows stay blocked unless explicitly cleared
# later via the publishability path (never by inheriting source ``ok``).
PUBLICATION_STATUS = "blocked"
PROXY_TAGS = (
    "crosswalked_from_dz2011",
    "research_estimate",
    "unpublished_pending_economic_rules",
)

# Min-share filter (default ON): drop only if share < 1% AND uprn_count < 5.
MIN_SHARE_DEFAULT = 0.01
MIN_UPRN_COUNT_DEFAULT = 5
# Valuation pin: 2,848 of 14,458 pairs (5,197 UPRNs) after default filter.
EXPECTED_MIN_SHARE_DROPPED_PAIRS = 2848
EXPECTED_MIN_SHARE_DROPPED_UPRNS = 5197
EXPECTED_RAW_PAIRS = 14458
EXPECTED_DZ2011 = 6976
EXPECTED_DZ2022 = 7392

# Estimate labels: measured / partly estimated / fully estimated.
ESTIMATE_MEASURED = "measured"
ESTIMATE_PARTLY = "partly_estimated"
ESTIMATE_FULLY = "fully_estimated"
MEASURED_FILLS = frozenset({"observed_pooled"})
PARTLY_FILLS = frozenset({"shrunk_to_model"})
FULLY_ESTIMATED_FILLS = frozenset({"model_filled"})

# Zone totals that add under value/address weights. Per-dwelling / diagnostic fields
# are recomputed or cleared — never silently area-weighted.
SUMMABLE_FIELDS = (
    "measured_rent",
    "uncertainty_low",
    "uncertainty_high",
    "land_value_zone_total",
    "infra_share",
    "planning_uplift",
    "policy_rent",
)

WEIGHTS_FILENAME = "dz2011_dz2022_uprn_weights.csv"
ZERO_FILENAME = "dz_crosswalk_zero_uprn.csv"

OS_OGL_ATTRIBUTION = (
    "Contains OS data © Crown copyright and database right 2026. "
    "Contains National Records of Scotland data © Crown copyright 2026, "
    "licensed under the Open Government Licence v3.0. "
    "Contains Scottish Government data © Crown copyright 2026 (OGL)."
)


def uprn_crosswalk_dir() -> Path:
    """Configured local folder for the full GIS UPRN crosswalk (not in git)."""
    return data_dir("dz_uprn_crosswalk")


def default_uprn_weights_path() -> Path:
    return uprn_crosswalk_dir() / WEIGHTS_FILENAME


def default_zero_uprn_path() -> Path:
    return uprn_crosswalk_dir() / ZERO_FILENAME


class CrosswalkError(ValueError):
    """DZ2011→DZ2022 surface crosswalk refused (loud fail)."""


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def _tags(row: Mapping) -> list[str]:
    raw = row.get("proxy_tags") or ()
    if isinstance(raw, str):
        return [t for t in raw.split(";") if t]
    return list(raw)


def _parse_bool(v) -> bool:
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no", ""):
        return False
    raise CrosswalkError(f"cannot parse boolean {v!r}")


def estimate_label_for_fill(fill_method: str | None) -> str:
    """Map a DZ2011 fill_method to measured / partly_estimated / fully_estimated."""
    fm = (fill_method or "").strip()
    if fm in MEASURED_FILLS:
        return ESTIMATE_MEASURED
    if fm in PARTLY_FILLS:
        return ESTIMATE_PARTLY
    if fm in FULLY_ESTIMATED_FILLS:
        return ESTIMATE_FULLY
    # Unknown / not_applicable: treat as fully estimated so we never claim measured.
    return ESTIMATE_FULLY


# Weakest → strongest (Methods v1.2): a 2022 zone never looks stronger than its
# weakest 2011 piece (partly-estimated never shows as measured; measured + fully
# → fully_estimated).
_ESTIMATE_WEAKNESS = {
    ESTIMATE_FULLY: 0,
    ESTIMATE_PARTLY: 1,
    ESTIMATE_MEASURED: 2,
}


def combine_estimate_labels(labels: Sequence[str]) -> str:
    """2022 zone label = weakest estimate label among its 2011 pieces."""
    if not labels:
        return ESTIMATE_FULLY
    ranked = [lbl for lbl in labels if lbl in _ESTIMATE_WEAKNESS]
    if not ranked:
        return ESTIMATE_FULLY
    return min(ranked, key=lambda lbl: _ESTIMATE_WEAKNESS[lbl])


def _normalize_pair_method(raw: str | None, *, default: str = CROSSWALK_METHOD) -> str:
    method = str(raw or default).strip()
    if method in FORBIDDEN_METHODS:
        raise CrosswalkError(
            f"surface crosswalk may not use {method!r} (rules 11); "
            f"use {ADDRESS_CROSSWALK_METHOD} or {CROSSWALK_METHOD}"
        )
    if method not in ALLOWED_PAIR_METHODS:
        raise CrosswalkError(f"unknown surface crosswalk method {method!r}")
    return method


def validate_value_crosswalk(pairs: Sequence[Mapping]) -> dict[str, list[tuple[str, float]]]:
    """Validate a DZ2011→DZ2022 crosswalk; return {dz2011: [(dz2022, w), ...]}.

    Each pair needs ``dz2011``, ``dz2022``, ``weight``. Optional ``method`` must be
    ``value_weighted``, ``address_uprn``, or GIS ``uprn_point_in_polygon``
    (population / area methods are refused). Weights per dz2011 must sum to 1
    within WEIGHT_TOL.
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
        _normalize_pair_method(p.get("method"), default=CROSSWALK_METHOD)
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


def apply_min_share_filter(
    rows: Sequence[Mapping],
    *,
    min_share: float = MIN_SHARE_DEFAULT,
    min_uprn_count: int = MIN_UPRN_COUNT_DEFAULT,
) -> tuple[list[dict], dict]:
    """Drop pairs with share < min_share AND uprn_count < min_uprn_count; redistribute.

    Share is given back within the same 2011 zone. Every 2011 and 2022 zone that
    appeared in ``rows`` must still be covered after the filter.
    """
    by_src: dict[str, list[Mapping]] = defaultdict(list)
    for r in rows:
        by_src[str(r["dz2011"]).strip()].append(r)

    kept: list[dict] = []
    dropped_pairs = 0
    dropped_uprns = 0
    for src, edges in by_src.items():
        keep: list[Mapping] = []
        drop: list[Mapping] = []
        for e in edges:
            share = float(e["weight"])
            cnt = int(e.get("uprn_count") or 0)
            if share < min_share and cnt < min_uprn_count:
                drop.append(e)
            else:
                keep.append(e)
        if not keep:
            raise CrosswalkError(
                f"min-share filter would drop all pairs for {src}; refusing"
            )
        dropped_pairs += len(drop)
        dropped_uprns += sum(int(e.get("uprn_count") or 0) for e in drop)
        keep_share = sum(float(e["weight"]) for e in keep)
        if keep_share <= 0:
            raise CrosswalkError(f"min-share filter left zero keep-share for {src}")
        for e in keep:
            row = dict(e)
            row["weight"] = float(e["weight"]) / keep_share
            row["dz2011"] = src
            row["dz2022"] = str(e["dz2022"]).strip()
            kept.append(row)

    dz2011 = {r["dz2011"] for r in kept}
    dz2022 = {r["dz2022"] for r in kept}
    orig11 = {str(r["dz2011"]).strip() for r in rows}
    orig22 = {str(r["dz2022"]).strip() for r in rows}
    if dz2011 != orig11:
        raise CrosswalkError(
            f"min-share filter lost {len(orig11 - dz2011)} DZ2011 zones"
        )
    if dz2022 != orig22:
        raise CrosswalkError(
            f"min-share filter lost {len(orig22 - dz2022)} DZ2022 zones"
        )

    # Re-validate sums.
    validate_value_crosswalk(kept)
    stats = {
        "raw_pairs": len(rows),
        "kept_pairs": len(kept),
        "dropped_pairs": dropped_pairs,
        "dropped_uprns": dropped_uprns,
        "dz2011": len(dz2011),
        "dz2022": len(dz2022),
        "min_share": min_share,
        "min_uprn_count": min_uprn_count,
    }
    return kept, stats


def _row_codes(row: Mapping) -> tuple[str, str]:
    """Accept GIS ``dz2011_code``/``dz2022_code`` or staged ``dz2011``/``dz2022``."""
    try:
        src = str(row.get("dz2011") or row["dz2011_code"]).strip()
        dst = str(row.get("dz2022") or row["dz2022_code"]).strip()
    except KeyError as exc:
        raise CrosswalkError(f"row missing dz2011/dz2022: {exc}") from exc
    return src, dst


def load_uprn_weight_rows(
    path: Path | str | None = None,
    *,
    apply_min_share: bool = True,
    min_share: float = MIN_SHARE_DEFAULT,
    min_uprn_count: int = MIN_UPRN_COUNT_DEFAULT,
    require_full_scotland: bool | None = None,
) -> tuple[list[dict], dict]:
    """Load a UPRN weight table; optionally apply the min-share filter.

    Default path is ``{dz_uprn_crosswalk_dir}/dz2011_dz2022_uprn_weights.csv``
    (configured local GIS handoff — not committed). Synthetic fixtures may be
    passed explicitly. When ``require_full_scotland`` is True (default if the
    file has the full Scotland row count), pin expected zone/pair counts.
    """
    p = Path(path) if path is not None else default_uprn_weights_path()
    if not p.is_file():
        raise CrosswalkError(
            f"UPRN weight file missing: {p} "
            "(set SCOT_LAND_DZ_UPRN_CROSSWALK_DIR or paths.dz_uprn_crosswalk)"
        )
    raw: list[dict] = []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            try:
                src, dst = _row_codes(row)
                weight = float(row["weight"] if "weight" in row else row["share_of_dz2011"])
                uprn_count = int(row["uprn_count"])
            except (KeyError, TypeError, ValueError, CrosswalkError) as exc:
                raise CrosswalkError(f"{p.name} row {i}: {exc}") from exc
            method = _normalize_pair_method(row.get("method"), default=GIS_UPRN_METHOD)
            if METHOD_STAMP[method] != ADDRESS_CROSSWALK_METHOD:
                raise CrosswalkError(
                    f"{p.name} row {i}: expected address-UPRN method, got {method!r}"
                )
            hh = row.get("hh2022_share", "")
            raw.append(
                {
                    "dz2011": src,
                    "dz2022": dst,
                    "weight": weight,
                    "uprn_count": uprn_count,
                    "hh2022_share": _num(hh),
                    "share_diff_flag": _parse_bool(row.get("share_diff_flag", False)),
                    "method": method,
                }
            )
    if not raw:
        raise CrosswalkError(f"UPRN weight file empty: {p}")
    full = len(raw) == EXPECTED_RAW_PAIRS
    if require_full_scotland is None:
        require_full_scotland = full
    if require_full_scotland and len(raw) != EXPECTED_RAW_PAIRS:
        raise CrosswalkError(
            f"UPRN weights have {len(raw)} rows, expected {EXPECTED_RAW_PAIRS}"
        )
    # Recompute weights from integer uprn_count — CSV shares are rounded to 6 dp.
    by_src_counts: dict[str, list[dict]] = defaultdict(list)
    for r in raw:
        by_src_counts[r["dz2011"]].append(r)
    for src, edges in by_src_counts.items():
        total_u = sum(e["uprn_count"] for e in edges)
        if total_u <= 0:
            raise CrosswalkError(f"DZ2011 {src} has zero UPRNs in weight file")
        for e in edges:
            e["weight"] = e["uprn_count"] / total_u
    validate_value_crosswalk(raw)
    dz2011 = {r["dz2011"] for r in raw}
    dz2022 = {r["dz2022"] for r in raw}
    if require_full_scotland and (
        len(dz2011) != EXPECTED_DZ2011 or len(dz2022) != EXPECTED_DZ2022
    ):
        raise CrosswalkError(
            f"UPRN weights cover {len(dz2011)} DZ2011 / {len(dz2022)} DZ2022; "
            f"expected {EXPECTED_DZ2011}/{EXPECTED_DZ2022}"
        )
    stats: dict = {
        "path": str(p),
        "attribution": OS_OGL_ATTRIBUTION,
        "raw_pairs": len(raw),
        "flagged_pairs": sum(1 for r in raw if r["share_diff_flag"]),
        "hh_share_missing_rows": sum(1 for r in raw if r["hh2022_share"] is None),
        "dz2011": len(dz2011),
        "dz2022": len(dz2022),
        "apply_min_share": apply_min_share,
        "full_scotland": require_full_scotland,
    }
    if not apply_min_share:
        stats.update(kept_pairs=len(raw), dropped_pairs=0, dropped_uprns=0)
        return raw, stats
    kept, filt = apply_min_share_filter(
        raw, min_share=min_share, min_uprn_count=min_uprn_count
    )
    stats.update(filt)
    if require_full_scotland:
        if filt["dropped_pairs"] != EXPECTED_MIN_SHARE_DROPPED_PAIRS:
            raise CrosswalkError(
                f"min-share dropped {filt['dropped_pairs']} pairs, "
                f"expected {EXPECTED_MIN_SHARE_DROPPED_PAIRS}"
            )
        if filt["dropped_uprns"] != EXPECTED_MIN_SHARE_DROPPED_UPRNS:
            raise CrosswalkError(
                f"min-share dropped {filt['dropped_uprns']} UPRNs, "
                f"expected {EXPECTED_MIN_SHARE_DROPPED_UPRNS}"
            )
    return kept, stats


def load_zero_uprn_overlap_pairs(path: Path | str | None = None) -> list[dict]:
    """Load ``kind == overlap_pair`` rows from the zero-UPRN companion CSV."""
    p = Path(path) if path is not None else default_zero_uprn_path()
    if not p.is_file():
        raise CrosswalkError(
            f"zero-UPRN file missing: {p} "
            "(set SCOT_LAND_DZ_UPRN_CROSSWALK_DIR or paths.dz_uprn_crosswalk)"
        )
    out: list[dict] = []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if str(row.get("kind", "")).strip() != "overlap_pair":
                continue
            src, dst = _row_codes(row)
            out.append(
                {
                    "kind": "overlap_pair",
                    "dz2011": src,
                    "dz2022": dst,
                    "area_ha": _num(row.get("area_ha")),
                    "pct_of_dz2011": _num(row.get("pct_of_dz2011")),
                    "pct_of_dz2022": _num(row.get("pct_of_dz2022")),
                }
            )
    return out


def uprn_totals_by_dz2022(pairs: Sequence[Mapping]) -> dict[str, int]:
    """Sum uprn_count per DZ2022 across the (possibly filtered) weight pairs."""
    totals: dict[str, int] = defaultdict(int)
    for p in pairs:
        totals[str(p["dz2022"]).strip()] += int(p.get("uprn_count") or 0)
    return dict(totals)


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
    """1:1 topology plus explicit value/address weights for every split/merge; else loud fail."""
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
                # Preserve address method when the explicit file carries it.
                method = CROSSWALK_METHOD
                for p in value_pairs:
                    if str(p["dz2011"]).strip() == src and str(p["dz2022"]).strip() == dst:
                        method = _normalize_pair_method(p.get("method"), default=CROSSWALK_METHOD)
                        break
                out.append(
                    {
                        "dz2011": src,
                        "dz2022": dst,
                        "weight": w,
                        "method": METHOD_STAMP[method],
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


def _pair_methods(crosswalk: Sequence[Mapping]) -> set[str]:
    return {
        METHOD_STAMP[_normalize_pair_method(p.get("method"), default=CROSSWALK_METHOD)]
        for p in crosswalk
    }


def crosswalk_surface_to_dz2022(
    dz2011_rows: Sequence[Mapping],
    crosswalk: Sequence[Mapping],
    *,
    dwellings_by_code: Mapping[str, int] | None = None,
    uprn_totals_2022: Mapping[str, int] | None = None,
) -> list[dict]:
    """Push DZ2011 surface rows onto DZ2022 via a validated crosswalk.

    Every output row is vintage 2022, ``publish_level=internal``,
    ``publication_status=blocked``. ``crosswalk_method`` is stamped from the
    pairs (``address_uprn`` or ``value_weighted`` — never population/area).
    When ``dwellings_by_code`` supplies the DZ2022 dwelling count, per-dwelling
    rent is recomputed; otherwise dwellings and per-dwelling figures are left
    null (never invented).

    If ``uprn_totals_2022`` is provided, rent landing on a DZ2022 with zero
    address points raises (derelict / best-permitted-use is out of this path).
    """
    by_src = validate_value_crosswalk(crosswalk)
    methods = _pair_methods(crosswalk)
    if len(methods) != 1:
        raise CrosswalkError(f"mixed crosswalk methods in one run: {sorted(methods)}")
    stamp_method = next(iter(methods))

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

    # Every crosswalk source needs a rent row; every rent row must appear in the
    # crosswalk (no silent skip of orphan 2011 zones).
    missing_rent = sorted(s for s in by_src if s not in sources)
    if missing_rent:
        raise CrosswalkError(
            f"DZ2011 surface rows missing for {len(missing_rent)} crosswalk sources "
            f"(e.g. {missing_rent[:3]})"
        )
    missing_xw = sorted(s for s in sources if s not in by_src)
    if missing_xw:
        raise CrosswalkError(
            f"DZ2011 surface rows missing from crosswalk for {len(missing_xw)} zones "
            f"(e.g. {missing_xw[:3]})"
        )

    price_years = {sources[s]["price_year"] for s in by_src}
    val_dates = {str(sources[s]["valuation_date"]) for s in by_src}
    if len(price_years) != 1:
        raise CrosswalkError(f"mixed price_year in DZ2011 sources: {sorted(price_years)}")
    if len(val_dates) != 1:
        raise CrosswalkError(f"mixed valuation_date in DZ2011 sources: {sorted(val_dates)}")

    # Pass through census-disagree flags from weight pairs (do not break conversion).
    flags_by_dst: dict[str, bool] = defaultdict(bool)
    for p in crosswalk:
        if _parse_bool(p.get("share_diff_flag", False)):
            flags_by_dst[str(p["dz2022"]).strip()] = True

    contribs: dict[str, list[dict]] = defaultdict(list)
    for src, edges in by_src.items():
        base = sources[src]
        src_label = estimate_label_for_fill(str(base.get("fill_method") or ""))
        for dst, w in edges:
            piece = dict(base)
            piece.update(_scale_summable(base, w))
            piece["_src"] = src
            piece["_weight"] = w
            piece["_estimate_label"] = src_label
            contribs[dst].append(piece)

    out: list[dict] = []
    for dst in sorted(contribs):
        parts = contribs[dst]
        validate_code(dst, 2022)
        if uprn_totals_2022 is not None and int(uprn_totals_2022.get(dst, 0)) <= 0:
            raise CrosswalkError(
                f"rent would land on DZ2022 {dst} with no address points; "
                "refuse (derelict / best-permitted-use under v0.7 is a separate path)"
            )
        head = parts[0]
        row: MutableMapping = {k: head.get(k) for k in head if not str(k).startswith("_")}
        row["code"] = dst
        row["vintage"] = 2022
        row["crosswalk_method"] = stamp_method
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
        if dwellings == 0:
            raise CrosswalkError(
                f"DZ2022 {dst} has zero dwellings; refuse blanking rent "
                "(derelict / best-permitted-use under v0.7 is a separate path)"
            )
        if dwellings is not None and dwellings > 0 and row.get("measured_rent") is not None:
            row["measured_rent_per_dwelling"] = round(float(row["measured_rent"]) / dwellings, 2)
        labels = [str(p["_estimate_label"]) for p in parts]
        # Methods v1.2: 2022 zone takes the weakest 2011 piece label.
        if multi and all(lbl == ESTIMATE_MEASURED for lbl in labels):
            # Split of measured rent is still measured (weights are address shares).
            est = ESTIMATE_MEASURED
        else:
            est = combine_estimate_labels(labels)
        row["estimate_label"] = est
        tags = set(_tags(head))
        for p in parts[1:]:
            tags.update(_tags(p))
        tags.update(PROXY_TAGS)
        tags.add(f"estimate_label={est}")
        if flags_by_dst.get(dst):
            tags.add("share_diff_flag")
        if multi:
            tags.add(f"{stamp_method}_merge_or_split")
        row["proxy_tags"] = sorted(tags)
        row["method"] = head.get("method") or "residual_drc_surface_v1"
        # Range check — DZ2022 codes only.
        lo, hi = CODE_RANGES[2022]
        n = int(dst[3:])
        if not (lo <= n <= hi):
            raise CrosswalkError(f"code {dst!r} outside DZ2022 range")
        out.append(dict(row))
    return out


def assert_scotland_total_conserved(
    dz2011_rows: Sequence[Mapping],
    dz2022_rows: Sequence[Mapping],
    *,
    field: str = "measured_rent",
) -> None:
    """Scotland 2011 total must equal 2022 total to the penny."""
    t11 = sum(float(r[field]) for r in dz2011_rows if r.get(field) is not None)
    t22 = sum(float(r[field]) for r in dz2022_rows if r.get(field) is not None)
    if abs(t11 - t22) > PENNY:
        raise CrosswalkError(
            f"Scotland {field} not conserved to the penny: 2011={t11:.4f} 2022={t22:.4f}"
        )
