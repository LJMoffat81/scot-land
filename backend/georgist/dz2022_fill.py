"""DZ2022 empty-zone fill (internal / blocked / proxy).

Signed-off spec (Georgist 14 Oct 2026): Project store
``docs/scot-land-dz2022-fill-spec.md``. Fills 2022 zones that receive
address-point mass from empty 2011 zones via methods A/B/C; zero-dwelling
sources are D (``not_applicable``).

Stamps: ``publication_status=blocked``, ``publish_level=internal``,
``value_tier=proxy``, tag ``model_fill_dz2022``. No public £.

Neighbours are the committed appendix CSV. The SGUR 2022 6-fold lookup path is
a setting (tests use a fixture). Scored holdout waits until the 2011 rent
table and UR6 lookup are available — this module never invents production data.
"""

from __future__ import annotations

import csv
import hashlib
import math
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

from georgist import surface_dz2022 as dz22
from georgist import surface_rent as sr
from georgist.surface_paths import REPO_ROOT, data_dir

# --------------------------------------------------------------------------- stamps / labels

PUBLISH_LEVEL = "internal"
PUBLICATION_STATUS = "blocked"
VALUE_TIER = "proxy"
PROXY_TAG = "model_fill_dz2022"
FILL_METHOD_MODEL = "model_filled"
FILL_METHOD_NA = "not_applicable"

ESTIMATE_MEASURED = dz22.ESTIMATE_MEASURED
ESTIMATE_PARTLY = dz22.ESTIMATE_PARTLY
ESTIMATE_FULLY = dz22.ESTIMATE_FULLY
ESTIMATE_NA = "not_applicable"

CLASS_UNAFFECTED = "unaffected"
CLASS_A = "A"
CLASS_B = "B"
CLASS_C = "C"
CLASS_D = "D"

# fill_step values recorded on every B or C zone
STEP_OWN = "own_council_class"
STEP_NEXT_UR = "next_ur_class"
STEP_NEIGHBOUR = "neighbouring_council"
STEP_ISLAND = "island_group"
STEP_SCOTLAND = "scotland_ur_class"

MEASURED_FILLS = frozenset({"observed_pooled", "shrunk_to_model"})

CLASS_MIN_TRAINING = 10
EMPTY_SHARE_A_MAX = 0.50
MEASURED_SHARE_FULLY_BELOW = 0.05

# Reconciled facts (spec): 723 suppressed + 4 not in price file + 3 zero-dwellings.
SUPPRESSED_N = 723
NOT_IN_PRICE_FILE_CODES = frozenset(
    {"S01007788", "S01010462", "S01010493", "S01011598"}
)  # all filled under C
ZERO_DWELLING_CODES = frozenset(sr.ZERO_DWELLINGS_FALLBACK)  # 3; all D
# GIS also flagged S01010206 / S01010226 as absent; reconciled: they are D (zero dwellings),
# not among the 4 C-filled "not in price file" codes.
RECONCILED_EMPTY_TO_FILL_N = SUPPRESSED_N + len(NOT_IN_PRICE_FILE_CODES)  # 727

# Island group (DECIDED): no land neighbours; borrow within group before mainland.
ISLAND_COUNCILS = frozenset({"S12000013", "S12000023", "S12000027"})
# Na h-Eileanan Siar, Orkney, Shetland

DEFAULT_UR6_ADJACENCY = {
    1: (2,),
    2: (1, 3),
    3: (2, 4, 5),
    4: (3, 6),
    5: (3, 6),
    6: (4, 5),
}

NEIGHBOURS_PATH = REPO_ROOT / "data" / "reference" / "council_neighbours_2022.csv"
# Official filename; path is a setting (never commit the production extract).
UR6_LOOKUP_DEFAULT_NAME = "Urban Rural 6 Fold 2022 Lookup.csv"


class FillError(ValueError):
    """DZ2022 empty-zone fill refused (loud fail)."""


class MissingLookupError(FillError):
    """A required input path is not available yet (do not invent production data)."""


# --------------------------------------------------------------------------- helpers


def _num(v) -> float | None:
    if v is None or v == "":
        return None
    return float(v)


def _tags(row: Mapping) -> list[str]:
    raw = row.get("proxy_tags") or ()
    if isinstance(raw, str):
        return [t for t in raw.split(";") if t]
    return list(raw)


def _is_zero_dwellings(row: Mapping, zero_codes: Iterable[str]) -> bool:
    code = str(row.get("code") or "").strip()
    if code in set(zero_codes):
        return True
    flags = str(row.get("flags") or "")
    if sr.ZERO_DWELLINGS_FLAG in flags.split(";"):
        return True
    if row.get("dwellings") is not None and int(row["dwellings"]) == 0:
        return True
    return False


def _is_measured(row: Mapping) -> bool:
    fm = str(row.get("fill_method") or "").strip()
    rent = _num(row.get("measured_rent"))
    if rent is None or rent <= 0:
        return False
    return fm in MEASURED_FILLS


def _is_empty_to_fill(row: Mapping, zero_codes: Iterable[str]) -> bool:
    if _is_zero_dwellings(row, zero_codes):
        return False
    if _is_measured(row):
        return False
    rent = _num(row.get("measured_rent"))
    if rent is not None and rent > 0 and str(row.get("fill_method") or "") == FILL_METHOD_MODEL:
        return False
    return True


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_island_council(la_code: str) -> bool:
    return str(la_code).strip() in ISLAND_COUNCILS


# --------------------------------------------------------------------------- lookups


def load_neighbouring_councils(path: Path | str | None = None) -> dict[str, tuple[str, ...]]:
    """Load committed ``council_neighbours_2022.csv`` (never compute at run time)."""
    p = Path(path) if path is not None else NEIGHBOURS_PATH
    if not p.is_file():
        raise MissingLookupError(f"neighbouring-council lookup missing: {p}")
    by: dict[str, set[str]] = defaultdict(set)
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            try:
                a = str(row["council_a"]).strip()
                b = str(row["council_b"]).strip()
            except KeyError as exc:
                raise FillError(f"{p.name} row {i}: {exc}") from exc
            if not a or not b or a == b:
                raise FillError(f"{p.name} row {i}: bad edge {a!r}->{b!r}")
            by[a].add(b)
            by[b].add(a)
    if not by:
        raise FillError(f"neighbouring-council lookup empty: {p}")
    # Islands must not appear as land neighbours.
    for isl in ISLAND_COUNCILS:
        if isl in by:
            raise FillError(
                f"island council {isl} must not appear in land-neighbour file {p}"
            )
    return {k: tuple(sorted(v)) for k, v in by.items()}


def default_ur6_lookup_path() -> Path:
    """Configured path for the NRS SPD 'Urban Rural 6 Fold 2022 Lookup.csv'."""
    return data_dir("raw") / "nrs_spd" / UR6_LOOKUP_DEFAULT_NAME


def load_ur6_dz2022(path: Path | str | None = None) -> dict[str, int]:
    """SGUR / NRS 6-fold 2022 on DZ2022. Do not use the 8-fold map layer.

    Accepts official-style columns (``DZ22_Code`` / ``UR6_Code`` / ``DataZone`` /
    ``UR6FOLD``) or fixture ``code,ur6_class``. Path is a setting; production
    file is never committed.
    """
    p = Path(path) if path is not None else default_ur6_lookup_path()
    if not p.is_file():
        raise MissingLookupError(
            f"Urban Rural 6 Fold 2022 Lookup missing: {p} "
            "(path is a setting; tests pass a fixture; do not use 8-fold)"
        )
    out: dict[str, int] = {}
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for i, row in enumerate(csv.DictReader(fh)):
            code = str(
                row.get("code")
                or row.get("DZ22_Code")
                or row.get("DataZone")
                or row.get("DZ_CODE")
                or ""
            ).strip()
            raw = (
                row.get("ur6_class")
                if row.get("ur6_class") not in (None, "")
                else row.get("UR6_Code")
                if row.get("UR6_Code") not in (None, "")
                else row.get("UR6FOLD")
            )
            try:
                ur6 = int(raw)
            except (TypeError, ValueError) as exc:
                raise FillError(f"{p.name} row {i}: bad ur6 {raw!r}") from exc
            if ur6 < 1 or ur6 > 6:
                raise FillError(f"{p.name} row {i}: ur6 {ur6} outside 1–6")
            if not code:
                raise FillError(f"{p.name} row {i}: missing code")
            out[code] = ur6
    if not out:
        raise FillError(f"UR6 lookup empty: {p}")
    return out


def load_zone_spine_councils(
    path: Path | str | None = None, *, vintage: int = 2011
) -> dict[str, str]:
    p = Path(path) if path is not None else (
        REPO_ROOT / "data" / "processed" / "datazones" / "zone_spine.csv"
    )
    if not p.is_file():
        raise FillError(f"zone_spine missing: {p}")
    out: dict[str, str] = {}
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            if int(row["vintage"]) != vintage:
                continue
            out[str(row["code"]).strip()] = str(row["la_code"]).strip()
    return out


def load_2011_rent_table(path: Path | str) -> list[dict]:
    """Load 2011-zone rent table (zone_id, central, low, high, status). Never commit."""
    p = Path(path)
    if not p.is_file():
        raise MissingLookupError(
            f"2011 rent table missing: {p} (path is a setting; never commit)"
        )
    rows: list[dict] = []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        for i, raw in enumerate(csv.DictReader(fh)):
            code = str(raw.get("zone_id") or raw.get("code") or "").strip()
            if not code:
                raise FillError(f"{p.name} row {i}: missing zone_id/code")
            central = _num(raw.get("central") if "central" in raw else raw.get("measured_rent"))
            low = _num(raw.get("low") if "low" in raw else raw.get("uncertainty_low"))
            high = _num(raw.get("high") if "high" in raw else raw.get("uncertainty_high"))
            status = str(raw.get("status") or raw.get("fill_method") or "").strip()
            if not status:
                status = "observed_pooled" if central and central > 0 else "model_fill_pending"
            rows.append(
                {
                    "code": code,
                    "vintage": 2011,
                    "measured_rent": central,
                    "uncertainty_low": low if low is not None else central,
                    "uncertainty_high": high if high is not None else central,
                    "fill_method": status,
                    "dwellings": int(raw["dwellings"]) if raw.get("dwellings") not in (None, "") else None,
                    "la_code": str(raw["la_code"]).strip() if raw.get("la_code") else None,
                    "ur6_class": int(raw["ur6_class"]) if raw.get("ur6_class") not in (None, "") else None,
                    "sales_n": int(raw["sales_n"]) if raw.get("sales_n") not in (None, "") else None,
                    "flags": str(raw.get("flags") or ""),
                    "value_tier": VALUE_TIER,
                    "publication_status": PUBLICATION_STATUS,
                    "publish_level": PUBLISH_LEVEL,
                }
            )
    if not rows:
        raise FillError(f"2011 rent table empty: {p}")
    return rows


def reconciled_facts() -> dict:
    """Documented reconciled zone counts from the signed-off spec."""
    return {
        "suppressed_n": SUPPRESSED_N,
        "not_in_price_file": sorted(NOT_IN_PRICE_FILE_CODES),
        "not_in_price_file_n": len(NOT_IN_PRICE_FILE_CODES),
        "not_in_price_file_fill": CLASS_C,
        "zero_dwellings": sorted(ZERO_DWELLING_CODES),
        "zero_dwellings_n": len(ZERO_DWELLING_CODES),
        "zero_dwellings_fill": CLASS_D,
        "empty_to_fill_n": RECONCILED_EMPTY_TO_FILL_N,
        "note": (
            "723 suppressed + 4 not in price file (C) + 3 zero-dwellings (D). "
            "S01010206/S01010226 are zero-dwellings (D), not among the 4 C codes."
        ),
    }


# --------------------------------------------------------------------------- classification


@dataclass(frozen=True)
class ZoneClass:
    code: str
    fill_class: str
    empty_share: float
    measured_share: float
    zero_share: float
    uprn_total: int
    measured_uprns: int
    empty_uprns: int
    zero_uprns: int


def classify_dz2022_zones(
    dz2011_rows: Sequence[Mapping],
    weight_pairs: Sequence[Mapping],
    *,
    zero_codes: Iterable[str] = sr.ZERO_DWELLINGS_FALLBACK,
) -> dict[str, ZoneClass]:
    by_2011 = {str(r["code"]).strip(): r for r in dz2011_rows}
    zero = set(zero_codes)
    totals: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "measured": 0, "empty": 0, "zero": 0}
    )
    for p in weight_pairs:
        src = str(p["dz2011"]).strip()
        dst = str(p["dz2022"]).strip()
        n = int(p.get("uprn_count") or 0)
        if n <= 0:
            continue
        row = by_2011.get(src)
        if row is None:
            raise FillError(f"weight source {src} missing from 2011 rent table")
        bucket = totals[dst]
        bucket["total"] += n
        if _is_zero_dwellings(row, zero):
            bucket["zero"] += n
        elif _is_empty_to_fill(row, zero):
            bucket["empty"] += n
        elif _is_measured(row):
            bucket["measured"] += n
        else:
            bucket["empty"] += n

    out: dict[str, ZoneClass] = {}
    for dst, b in totals.items():
        total = b["total"]
        if total <= 0:
            raise FillError(f"DZ2022 {dst} has zero address points in weights")
        empty_share = b["empty"] / total
        measured_share = b["measured"] / total
        zero_share = b["zero"] / total
        if b["zero"] == total:
            klass = CLASS_D
        elif empty_share == 0:
            klass = CLASS_UNAFFECTED
        elif empty_share <= EMPTY_SHARE_A_MAX:
            klass = CLASS_A
        elif empty_share < 1.0:
            klass = CLASS_B
        else:
            klass = CLASS_C
        out[dst] = ZoneClass(
            code=dst,
            fill_class=klass,
            empty_share=empty_share,
            measured_share=measured_share,
            zero_share=zero_share,
            uprn_total=total,
            measured_uprns=b["measured"],
            empty_uprns=b["empty"],
            zero_uprns=b["zero"],
        )
    return out


# --------------------------------------------------------------------------- method C group models


@dataclass
class GroupModel:
    la_code: str
    ur6_class: int
    train_n: int
    log_p10: float
    log_p50: float
    log_p90: float
    fill_step: str
    borrowed_class: tuple[str, ...] = ()
    scotland_fallback: bool = False


def _percentile(sorted_vals: Sequence[float], q: float) -> float:
    if not sorted_vals:
        raise FillError("percentile on empty sample")
    if len(sorted_vals) == 1:
        return float(sorted_vals[0])
    pos = (len(sorted_vals) - 1) * (q / 100.0)
    lo = int(math.floor(pos))
    hi = int(math.ceil(pos))
    if lo == hi:
        return float(sorted_vals[lo])
    w = pos - lo
    return float(sorted_vals[lo]) * (1.0 - w) + float(sorted_vals[hi]) * w


def _log_rent_per_dwelling(row: Mapping) -> float | None:
    rent = _num(row.get("measured_rent"))
    dwellings = row.get("dwellings")
    if rent is None or rent <= 0 or not dwellings or int(dwellings) <= 0:
        return None
    return math.log(rent / int(dwellings))


def _collect_logs(
    by_group: Mapping[tuple[str, int], Sequence[float]],
    keys: Iterable[tuple[str, int]],
) -> list[float]:
    out: list[float] = []
    for k in keys:
        out.extend(by_group.get(k) or ())
    return out


def _fit_one(
    la: str,
    ur6: int,
    logs: Sequence[float],
    *,
    fill_step: str,
    borrowed: Sequence[str],
    scotland_fallback: bool = False,
) -> GroupModel:
    logs_sorted = sorted(logs)
    return GroupModel(
        la_code=la,
        ur6_class=ur6,
        train_n=len(logs),
        log_p10=_percentile(logs_sorted, 10),
        log_p50=_percentile(logs_sorted, 50),
        log_p90=_percentile(logs_sorted, 90),
        fill_step=fill_step,
        borrowed_class=tuple(borrowed),
        scotland_fallback=scotland_fallback,
    )


def resolve_group_model(
    la: str,
    ur6: int,
    by_group: Mapping[tuple[str, int], Sequence[float]],
    *,
    neighbours: Mapping[str, Sequence[str]],
    ur6_adjacency: Mapping[int, Sequence[int]],
    class_min: int = CLASS_MIN_TRAINING,
) -> GroupModel:
    """Borrowing order per signed-off island / mainland rules; always fills."""
    adj = {int(k): tuple(int(x) for x in v) for k, v in ur6_adjacency.items()}
    own = list(by_group.get((la, ur6)) or ())
    if len(own) >= class_min:
        return _fit_one(la, ur6, own, fill_step=STEP_OWN, borrowed=())

    borrowed: list[str] = []
    logs = list(own)

    if is_island_council(la):
        # Islands: own → island group same class → Scotland-wide same class.
        # STEP_ISLAND only when the island pool reaches class_min; otherwise continue
        # to Scotland-wide (never label a still-thin pool as island).
        if len(logs) < class_min:
            for other in sorted(ISLAND_COUNCILS - {la}):
                extra = by_group.get((other, ur6)) or ()
                if extra:
                    logs.extend(extra)
                    borrowed.append(f"island:{other}")
            if len(logs) >= class_min:
                return _fit_one(
                    la, ur6, logs, fill_step=STEP_ISLAND, borrowed=borrowed
                )

        # Still under class_min after island pooling → Scotland-wide same UR class.
        scot: list[float] = []
        for (_ola, our), vals in by_group.items():
            if int(our) == int(ur6):
                scot.extend(vals)
        if len(scot) < 1:
            raise FillError(
                f"no training logs for island council {la} UR6 {ur6} "
                "(island pool still under class_min and Scotland-wide same class empty)"
            )
        tags = list(borrowed) + [f"scotland_ur6:{ur6}"]
        return _fit_one(
            la,
            ur6,
            scot,
            fill_step=STEP_SCOTLAND,
            borrowed=tags,
            scotland_fallback=True,
        )

    # Mainland: own → next UR class → neighbouring council → Scotland-wide same class.
    if len(logs) < class_min:
        for other in adj.get(ur6, ()):
            extra = by_group.get((la, int(other))) or ()
            if extra:
                logs.extend(extra)
                borrowed.append(f"ur6:{other}")
            if len(logs) >= class_min:
                return _fit_one(
                    la, ur6, logs, fill_step=STEP_NEXT_UR, borrowed=borrowed
                )

    if len(logs) < class_min:
        for nla in neighbours.get(la, ()):
            for try_ur in (ur6, *adj.get(ur6, ())):
                extra = by_group.get((nla, int(try_ur))) or ()
                if not extra:
                    continue
                logs.extend(extra)
                tag = f"council:{nla}" if int(try_ur) == int(ur6) else f"council:{nla}|ur6:{try_ur}"
                borrowed.append(tag)
                if len(logs) >= class_min:
                    return _fit_one(
                        la, ur6, logs, fill_step=STEP_NEIGHBOUR, borrowed=borrowed
                    )

    # Scotland-wide same UR class (final fallback — every zone is filled).
    scot: list[float] = []
    for (_ola, our), vals in by_group.items():
        if int(our) == int(ur6):
            scot.extend(vals)
    if len(scot) >= class_min or (scot and len(logs) < class_min):
        tags = list(borrowed) + [f"scotland_ur6:{ur6}"]
        return _fit_one(
            la,
            ur6,
            scot,
            fill_step=STEP_SCOTLAND,
            borrowed=tags,
            scotland_fallback=True,
        )
    if len(logs) >= 1:
        if any(t.startswith("council:") for t in borrowed):
            step = STEP_NEIGHBOUR
        elif any(t.startswith("ur6:") for t in borrowed):
            step = STEP_NEXT_UR
        else:
            step = STEP_OWN
        return _fit_one(la, ur6, logs, fill_step=step, borrowed=borrowed)
    raise FillError(
        f"no training logs for council {la} UR6 {ur6} after all borrow steps"
    )


def fit_council_ur6_models(
    measured_2011: Sequence[Mapping],
    *,
    neighbours: Mapping[str, Sequence[str]],
    ur6_adjacency: Mapping[int, Sequence[int]] | None = None,
    class_min: int = CLASS_MIN_TRAINING,
    target_keys: Iterable[tuple[str, int]] | None = None,
) -> dict[tuple[str, int], GroupModel]:
    adj = {
        int(k): tuple(int(x) for x in v)
        for k, v in (ur6_adjacency or DEFAULT_UR6_ADJACENCY).items()
    }
    by_group: dict[tuple[str, int], list[float]] = defaultdict(list)
    for r in measured_2011:
        la = str(r.get("la_code") or "").strip()
        ur6 = r.get("ur6_class")
        if not la or ur6 is None:
            continue
        log_v = _log_rent_per_dwelling(r)
        if log_v is None:
            continue
        by_group[(la, int(ur6))].append(log_v)
    if not by_group:
        raise FillError("no measured 2011 zones with log rent/dwelling for method C")

    keys = set(by_group)
    if target_keys is not None:
        keys |= {(str(a), int(u)) for a, u in target_keys}

    fitted: dict[tuple[str, int], GroupModel] = {}
    for la, ur6 in sorted(keys):
        fitted[(la, ur6)] = resolve_group_model(
            la,
            ur6,
            by_group,
            neighbours=neighbours,
            ur6_adjacency=adj,
            class_min=class_min,
        )
    return fitted


def predict_group_rent(
    model: GroupModel, *, dwellings: int
) -> tuple[float, float, float]:
    if dwellings <= 0:
        raise FillError("predict_group_rent needs positive dwellings")
    low = dwellings * math.exp(model.log_p10)
    central = dwellings * math.exp(model.log_p50)
    high = dwellings * math.exp(model.log_p90)
    return tuple(sorted((low, central, high)))  # type: ignore[return-value]


# --------------------------------------------------------------------------- widen helpers


def widen_range_by_empty_share(
    low: float, central: float, high: float, empty_share: float
) -> tuple[float, float, float]:
    if empty_share < 0 or empty_share > 1:
        raise FillError(f"empty_share {empty_share} out of [0,1]")
    factor = 1.0 + float(empty_share)
    half_lo = max(0.0, central - low) * factor
    half_hi = max(0.0, high - central) * factor
    return central - half_lo, central, central + half_hi


def widen_bands_from_holdout_errors(
    low: float,
    central: float,
    high: float,
    *,
    abs_log_errors: Sequence[float],
) -> tuple[float, float, float]:
    """Widen using holdout abs log errors (no re-fit). Scotland-fallback / fail path."""
    if not abs_log_errors:
        return low, central, high
    errs = sorted(float(x) for x in abs_log_errors)
    pad = _percentile(errs, 90)
    return min(low, central * math.exp(-pad)), central, max(high, central * math.exp(pad))


# --------------------------------------------------------------------------- fill pipeline


@dataclass
class FillResult:
    rows_2022: list[dict]
    classifications: dict[str, ZoneClass]
    models: dict[tuple[str, int], GroupModel]
    rows_2011_for_conservation: list[dict]
    stats: dict = field(default_factory=dict)


def _stamp_blocked(
    row: MutableMapping, *, estimate_label: str, extra_tags: Iterable[str] = ()
) -> None:
    row["publish_level"] = PUBLISH_LEVEL
    row["publication_status"] = PUBLICATION_STATUS
    row["value_tier"] = VALUE_TIER
    row["estimate_label"] = estimate_label
    tags = set(_tags(row))
    tags.add(PROXY_TAG)
    tags.add(f"estimate_label={estimate_label}")
    tags.update(extra_tags)
    row["proxy_tags"] = sorted(tags)


def _base_2022_row(
    code: str,
    *,
    rent: float | None,
    low: float | None,
    high: float | None,
    fill_method: str,
    estimate_label: str,
    dwellings: int | None,
    la_code: str | None,
    ur6_class: int | None,
    extra_tags: Iterable[str] = (),
    borrowed_class: Sequence[str] = (),
    fill_step: str | None = None,
) -> dict:
    row: dict = {
        "code": code,
        "vintage": 2022,
        "measured_rent": rent,
        "uncertainty_low": low,
        "uncertainty_high": high,
        "fill_method": fill_method,
        "dwellings": dwellings,
        "la_code": la_code,
        "ur6_class": ur6_class,
        "quality": (
            "modelled"
            if fill_method == FILL_METHOD_MODEL
            else "placeholder"
            if fill_method == FILL_METHOD_NA
            else "derived"
        ),
        "commons_class": "surface",
        "crosswalk_method": dz22.ADDRESS_CROSSWALK_METHOD,
        "method": "dz2022_empty_fill_v1",
        "source_id": "dz2022_empty_fill",
        "licence": "research_estimate_internal",
    }
    tags = list(extra_tags)
    if borrowed_class:
        tags.append("borrowed_class:" + ",".join(borrowed_class))
        row["borrowed_class"] = list(borrowed_class)
    if fill_step is not None:
        row["fill_step"] = fill_step
        tags.append(f"fill_step={fill_step}")
    _stamp_blocked(row, estimate_label=estimate_label, extra_tags=tags)
    return row


def fill_dz2022_empty_zones(
    dz2011_rows: Sequence[Mapping],
    weight_pairs: Sequence[Mapping],
    *,
    council_by_2011: Mapping[str, str],
    council_by_2022: Mapping[str, str],
    ur6_by_2011: Mapping[str, int],
    ur6_by_2022: Mapping[str, int],
    neighbours: Mapping[str, Sequence[str]],
    dwellings_by_2022: Mapping[str, int] | None = None,
    zero_codes: Iterable[str] = sr.ZERO_DWELLINGS_FALLBACK,
    ur6_adjacency: Mapping[int, Sequence[int]] | None = None,
    class_min: int = CLASS_MIN_TRAINING,
    band_widen: Mapping[str, Sequence[float]] | None = None,
    scotland_holdout_errors_by_ur6: Mapping[int, Sequence[float]] | None = None,
) -> FillResult:
    """Classify and fill DZ2022 empty-zone mass (A/B/C/D). Every zone is filled."""
    zero = set(zero_codes)
    enriched_2011: list[dict] = []
    for raw in dz2011_rows:
        r = dict(raw)
        code = str(r["code"]).strip()
        r["code"] = code
        if not r.get("la_code"):
            r["la_code"] = council_by_2011.get(code)
        if r.get("ur6_class") is None:
            r["ur6_class"] = ur6_by_2011.get(code)
        enriched_2011.append(r)

    classifications = classify_dz2022_zones(enriched_2011, weight_pairs, zero_codes=zero)
    by_dst: dict[str, list[Mapping]] = defaultdict(list)
    for p in weight_pairs:
        by_dst[str(p["dz2022"]).strip()].append(p)
    by_2011 = {r["code"]: r for r in enriched_2011}

    target_keys = []
    for dst, klass in classifications.items():
        if klass.fill_class in (CLASS_B, CLASS_C):
            la = council_by_2022.get(dst)
            ur6 = ur6_by_2022.get(dst)
            if la is not None and ur6 is not None:
                target_keys.append((la, int(ur6)))

    measured = [r for r in enriched_2011 if _is_measured(r)]
    models = fit_council_ur6_models(
        measured,
        neighbours=neighbours,
        ur6_adjacency=ur6_adjacency,
        class_min=class_min,
        target_keys=target_keys,
    )

    widen = {k: list(v) for k, v in (band_widen or {}).items()}
    scot_errs = {int(k): list(v) for k, v in (scotland_holdout_errors_by_ur6 or {}).items()}

    def _maybe_widen(klass: str, low: float, central: float, high: float) -> tuple[float, float, float]:
        errs = widen.get(klass) or widen.get(klass.lower())
        if errs:
            return widen_bands_from_holdout_errors(low, central, high, abs_log_errors=errs)
        return low, central, high

    out_rows: list[dict] = []
    for dst, klass in sorted(classifications.items()):
        la = council_by_2022.get(dst)
        ur6 = ur6_by_2022.get(dst)
        dwellings = None
        if dwellings_by_2022 is not None:
            if dst not in dwellings_by_2022:
                raise FillError(f"DZ2022 dwellings missing for {dst}")
            dwellings = int(dwellings_by_2022[dst])

        edges = by_dst[dst]
        measured_rent = measured_low = measured_high = 0.0
        measured_uprns = 0
        for e in edges:
            src = str(e["dz2011"]).strip()
            src_row = by_2011[src]
            n = int(e.get("uprn_count") or 0)
            w = float(e["weight"])
            if _is_measured(src_row):
                rent = float(src_row["measured_rent"]) * w
                lo = float(src_row.get("uncertainty_low") or src_row["measured_rent"]) * w
                hi = float(src_row.get("uncertainty_high") or src_row["measured_rent"]) * w
                measured_rent += rent
                measured_low += lo
                measured_high += hi
                measured_uprns += n

        if klass.fill_class == CLASS_D:
            out_rows.append(
                _base_2022_row(
                    dst,
                    rent=0.0,
                    low=0.0,
                    high=0.0,
                    fill_method=FILL_METHOD_NA,
                    estimate_label=ESTIMATE_NA,
                    dwellings=dwellings if dwellings is not None else 0,
                    la_code=la,
                    ur6_class=ur6,
                    extra_tags=("zero_dwellings",),
                )
            )
            continue

        if klass.fill_class == CLASS_UNAFFECTED:
            row = _base_2022_row(
                dst,
                rent=measured_rent,
                low=measured_low,
                high=measured_high,
                fill_method="observed_pooled",
                estimate_label=ESTIMATE_MEASURED,
                dwellings=dwellings,
                la_code=la,
                ur6_class=ur6,
                extra_tags=("unaffected_empty_share_0",),
            )
            row["quality"] = "derived"
            out_rows.append(row)
            continue

        if klass.fill_class == CLASS_A:
            if measured_uprns <= 0:
                raise FillError(f"class A zone {dst} has no measured UPRNs")
            scale = klass.uprn_total / measured_uprns
            central = measured_rent * scale
            low = measured_low * scale
            high = measured_high * scale
            low, central, high = widen_range_by_empty_share(
                low, central, high, klass.empty_share
            )
            low, central, high = _maybe_widen(CLASS_A, low, central, high)
            out_rows.append(
                _base_2022_row(
                    dst,
                    rent=central,
                    low=low,
                    high=high,
                    fill_method=FILL_METHOD_MODEL,
                    estimate_label=ESTIMATE_PARTLY,
                    dwellings=dwellings,
                    la_code=la,
                    ur6_class=ur6,
                    extra_tags=(f"fill_class=A", f"empty_share={klass.empty_share:.6f}"),
                )
            )
            continue

        if la is None or ur6 is None:
            raise FillError(f"DZ2022 {dst} missing la_code/ur6_class for method C")
        key = (la, int(ur6))
        if key not in models:
            raise FillError(f"no council×UR6 model for {key}")
        model = models[key]

        if klass.fill_class == CLASS_C:
            if dwellings is None or dwellings <= 0:
                raise FillError(f"class C zone {dst} needs positive dwellings")
            low, central, high = predict_group_rent(model, dwellings=dwellings)
            if model.scotland_fallback:
                errs = scot_errs.get(int(ur6)) or widen.get(CLASS_C) or ()
                low, central, high = widen_bands_from_holdout_errors(
                    low, central, high, abs_log_errors=errs
                )
            else:
                low, central, high = _maybe_widen(CLASS_C, low, central, high)
            out_rows.append(
                _base_2022_row(
                    dst,
                    rent=central,
                    low=low,
                    high=high,
                    fill_method=FILL_METHOD_MODEL,
                    estimate_label=ESTIMATE_FULLY,
                    dwellings=dwellings,
                    la_code=la,
                    ur6_class=ur6,
                    extra_tags=(f"fill_class=C",),
                    borrowed_class=model.borrowed_class,
                    fill_step=model.fill_step,
                )
            )
            continue

        # CLASS_B
        if dwellings is None or dwellings <= 0:
            raise FillError(f"class B zone {dst} needs positive dwellings")
        empty_dwellings = max(1, int(round(dwellings * klass.empty_share)))
        e_low, e_central, e_high = predict_group_rent(model, dwellings=empty_dwellings)
        central = measured_rent + e_central
        low = measured_low + e_low
        high = measured_high + e_high
        if model.scotland_fallback:
            errs = scot_errs.get(int(ur6)) or widen.get(CLASS_B) or ()
            low, central, high = widen_bands_from_holdout_errors(
                low, central, high, abs_log_errors=errs
            )
            est = ESTIMATE_FULLY
        else:
            low, central, high = _maybe_widen(CLASS_B, low, central, high)
            est = (
                ESTIMATE_FULLY
                if klass.measured_share < MEASURED_SHARE_FULLY_BELOW
                else ESTIMATE_PARTLY
            )
        out_rows.append(
            _base_2022_row(
                dst,
                rent=central,
                low=low,
                high=high,
                fill_method=FILL_METHOD_MODEL,
                estimate_label=est,
                dwellings=dwellings,
                la_code=la,
                ur6_class=ur6,
                extra_tags=(
                    f"fill_class=B",
                    f"empty_share={klass.empty_share:.6f}",
                    f"measured_share={klass.measured_share:.6f}",
                ),
                borrowed_class=model.borrowed_class,
                fill_step=model.fill_step,
            )
        )

    # Conservation companion: attribute each 2022 rent back by destination UPRN share.
    attributed: dict[str, float] = defaultdict(float)
    out_by = {r["code"]: r for r in out_rows}
    for dst, edges in by_dst.items():
        rent = _num(out_by[dst].get("measured_rent")) or 0.0
        total_u = sum(int(e.get("uprn_count") or 0) for e in edges)
        if total_u <= 0:
            continue
        for e in edges:
            src = str(e["dz2011"]).strip()
            attributed[src] += rent * int(e.get("uprn_count") or 0) / total_u
    rows_2011_cons = []
    for r in enriched_2011:
        rr = dict(r)
        rr["measured_rent"] = float(attributed.get(r["code"], 0.0))
        rows_2011_cons.append(rr)

    stats = {
        "n_2022": len(out_rows),
        "by_class": {
            c: sum(1 for z in classifications.values() if z.fill_class == c)
            for c in (CLASS_UNAFFECTED, CLASS_A, CLASS_B, CLASS_C, CLASS_D)
        },
        "publication_status": PUBLICATION_STATUS,
        "value_tier": VALUE_TIER,
        "proxy_tag": PROXY_TAG,
        "reconciled": reconciled_facts(),
    }
    return FillResult(
        rows_2022=out_rows,
        classifications=classifications,
        models=models,
        rows_2011_for_conservation=rows_2011_cons,
        stats=stats,
    )


def count_reconciled_sources(dz2011_rows: Sequence[Mapping]) -> dict[str, int]:
    """Count suppressed / not-in-price-file / zero-dwellings on a 2011 inventory."""
    zero = set(ZERO_DWELLING_CODES)
    n_zero = 0
    n_not_in_price = 0
    n_suppressed = 0
    for r in dz2011_rows:
        code = str(r.get("code") or "").strip()
        if _is_zero_dwellings(r, zero) or code in zero:
            n_zero += 1
            continue
        if code in NOT_IN_PRICE_FILE_CODES or "absent_from_ros_price_file" in str(
            r.get("flags") or ""
        ).split(";"):
            # Reconciled: the 4 C-filled codes (not the zero-dwelling absents).
            if code in NOT_IN_PRICE_FILE_CODES:
                n_not_in_price += 1
            continue
        if _is_empty_to_fill(r, zero):
            n_suppressed += 1
    return {
        "suppressed_n": n_suppressed,
        "not_in_price_file_n": n_not_in_price,
        "zero_dwellings_n": n_zero,
    }


def assert_reconciled_source_counts(dz2011_rows: Sequence[Mapping]) -> None:
    """Real-run gate: inventory must match reconciled 723 / 4 / 3."""
    counts = count_reconciled_sources(dz2011_rows)
    expected = {
        "suppressed_n": SUPPRESSED_N,
        "not_in_price_file_n": len(NOT_IN_PRICE_FILE_CODES),
        "zero_dwellings_n": len(ZERO_DWELLING_CODES),
    }
    if counts != expected:
        raise FillError(
            f"reconciled source counts {counts} != expected {expected} "
            "(723 suppressed + 4 not in price file + 3 zero-dwellings)"
        )


def assert_post_fill_gate(
    rows_2011: Sequence[Mapping],
    rows_2022: Sequence[Mapping],
    *,
    require_reconciled_counts: bool = False,
    source_2011: Sequence[Mapping] | None = None,
) -> None:
    """Gate: Scotland total conserved; every 2022 zone rent > 0 except N/A.

    On a real run pass ``require_reconciled_counts=True`` and the original 2011
    rent-table inventory as ``source_2011`` to assert the signed-off
    723 suppressed / 4 not-in-price-file / 3 zero-dwellings counts.
    """
    dz22.assert_scotland_total_conserved(rows_2011, rows_2022, field="measured_rent")
    if require_reconciled_counts:
        inventory = source_2011 if source_2011 is not None else rows_2011
        assert_reconciled_source_counts(inventory)
    for r in rows_2022:
        label = str(r.get("estimate_label") or "")
        fm = str(r.get("fill_method") or "")
        rent = _num(r.get("measured_rent"))
        if label == ESTIMATE_NA or fm == FILL_METHOD_NA:
            continue
        if rent is None or rent <= 0:
            raise FillError(
                f"post-fill gate: DZ2022 {r.get('code')} has rent {rent}; "
                "expected > 0 (except not_applicable)"
            )
        if r.get("publication_status") != PUBLICATION_STATUS:
            raise FillError(
                f"post-fill gate: {r.get('code')} publication_status must stay blocked"
            )
        if r.get("value_tier") != VALUE_TIER:
            raise FillError(f"post-fill gate: {r.get('code')} value_tier must stay proxy")
        if PROXY_TAG not in _tags(r):
            raise FillError(f"post-fill gate: {r.get('code')} missing {PROXY_TAG}")


def class_min_from_settings(config: Mapping | None = None) -> int:
    """``dz2022_empty_fill.class_min_training`` from surface.yaml (default 10)."""
    if config is None:
        config = sr.load_config()
    section = config.get("dz2022_empty_fill") or {}
    return int(section.get("class_min_training", CLASS_MIN_TRAINING))
