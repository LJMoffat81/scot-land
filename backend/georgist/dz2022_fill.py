"""DZ2022 empty-zone fill (internal / blocked / proxy).

Signed-off spec (Georgist 14 Oct 2026): Project store
``docs/scot-land-dz2022-fill-spec.md``. FILL-POOLED: run fill on pooled 2011
rent tables (``docs/fill-pooled.md``). Fills 2022 zones that receive
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
import json
import logging
import math
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

from georgist import surface_dz2022 as dz22
from georgist import surface_rent as sr
from georgist.surface_paths import REPO_ROOT, data_dir

LOG = logging.getLogger(__name__)

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

# Per-zone fill_step (FILL-POOLED C4). C sub-steps stay on c_sub_step.
STEP_MEASURED_2023 = "measured_2023"
STEP_POOLED_3Y = "pooled_3y"
STEP_POOLED_5Y = "pooled_5y"
STEP_A_RESCALE = "A_rescale"
STEP_B_BLEND = "B_blend"
STEP_C_MODEL = "C_model"
STEP_NA = "not_applicable"

# C (and B empty-part) borrowing sub-steps — Methods v1.2 (no next-UR class).
STEP_OWN = "own_council_class"
STEP_NEIGHBOUR = "neighbouring_council"
STEP_ISLAND = "island_group"
STEP_SCOTLAND = "scotland_ur_class"

C_SUB_STEPS = frozenset(
    {STEP_OWN, STEP_NEIGHBOUR, STEP_ISLAND, STEP_SCOTLAND}
)
TOP_LEVEL_STEPS = frozenset(
    {
        STEP_MEASURED_2023,
        STEP_POOLED_3Y,
        STEP_POOLED_5Y,
        STEP_A_RESCALE,
        STEP_B_BLEND,
        STEP_C_MODEL,
        STEP_NA,
    }
)

MEASURED_FILLS = frozenset({"observed_pooled", "shrunk_to_model"})

CLASS_MIN_TRAINING = 10
EMPTY_SHARE_A_MAX = 0.50
MEASURED_SHARE_FULLY_BELOW = 0.05

# Post-pooling model-fill target (FILL-POOLED / M3). Pre-pooling baseline was 727.
# Prefer surface.yaml model_fill.null_dz_fill_target_n; this default matches config.
DEFAULT_NULL_DZ_FILL_TARGET_N = 129
PRE_POOLING_EMPTY_TO_FILL_N = 727  # historical only — gates must not expect this
PRE_POOLING_SUPPRESSED_N = 723
# FILL-MEASURED-ZERO: pooled price present but residual floors to £0 (cost >= price).
DEFAULT_MEASURED_ZERO_N = 27

NOT_IN_PRICE_FILE_CODES = frozenset(
    {"S01007788", "S01010462", "S01010493", "S01011598"}
)  # all filled under C; inside the 129 model-fill set
ZERO_DWELLING_CODES = frozenset(sr.ZERO_DWELLINGS_FALLBACK)  # 3; all D
COST_AT_OR_ABOVE_PRICE_TAG = "cost_at_or_above_price"
# GIS also flagged S01010206 / S01010226 as absent; reconciled: they are D (zero dwellings),
# not among the 4 C-filled "not in price file" codes.

# Evidence windows written by the pooled rent-table entrypoint.
EVIDENCE_WINDOWS = frozenset({"2023", "pooled_3y", "pooled_5y"})
POOLING_CONFIG_HASH_KEYS = (
    "measure",
    "pool_years",
    "pool_years_max",
    "n_min",
    "n_full",
    "shrinkage_k",
)

# Island group (DECIDED): no land neighbours; borrow within group before mainland.
ISLAND_COUNCILS = frozenset({"S12000013", "S12000023", "S12000027"})
# Na h-Eileanan Siar, Orkney, Shetland

NEIGHBOURS_PATH = REPO_ROOT / "data" / "reference" / "council_neighbours_2022.csv"
# Official filename; path is a setting (never commit the production extract).
UR6_LOOKUP_DEFAULT_NAME = "Urban Rural 6 Fold 2022 Lookup.csv"


class FillError(ValueError):
    """DZ2022 empty-zone fill refused (loud fail)."""


class MissingLookupError(FillError):
    """A required input path is not available yet (do not invent production data)."""


class UnpooledTableError(FillError):
    """2011 rent table lacks a pooling stamp (evidence_window + config hash)."""


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


def has_price_evidence(row: Mapping) -> bool:
    """True when the zone has measured or pooled price evidence.

    FILL-MEASURED-ZERO: evidence is never inferred from ``rent == 0``. A floored
    residual with ``observed_pooled`` / ``shrunk_to_model`` still counts. Explicit
    ``price_gbp`` / ``price_indexed_gbp`` on a surface row also count. Sales-only
    or ``model_fill_pending`` without a measured fill_method do **not**.
    """
    fm = str(row.get("fill_method") or "").strip()
    if fm in MEASURED_FILLS:
        return True
    if row.get("price_gbp") is not None and row.get("price_gbp") != "":
        return True
    if row.get("price_indexed_gbp") is not None and row.get("price_indexed_gbp") != "":
        return True
    return False


def _is_measured(row: Mapping) -> bool:
    """Measured/pooled evidence, including floored zeros (cost >= price).

    Never uses ``rent == 0`` as a missing-price signal. A measured zero cannot be
    treated as empty and must not be overwritten by the fill.
    """
    fm = str(row.get("fill_method") or "").strip()
    if fm not in MEASURED_FILLS:
        return False
    rent = _num(row.get("measured_rent"))
    if rent is None or rent < 0:
        return False
    return True


def _is_empty_to_fill(row: Mapping, zero_codes: Iterable[str]) -> bool:
    """Needs filling = no price evidence (never ``rent == 0``)."""
    if _is_zero_dwellings(row, zero_codes):
        return False
    if _is_measured(row):
        return False
    rent = _num(row.get("measured_rent"))
    if rent is not None and rent > 0 and str(row.get("fill_method") or "") == FILL_METHOD_MODEL:
        return False
    return True


def is_measured_zero(row: Mapping) -> bool:
    """Floored residual with price evidence (cost >= price); not zero-dwellings N/A."""
    rent = _num(row.get("measured_rent"))
    if rent is None or rent != 0:
        return False
    fm = str(row.get("fill_method") or "").strip()
    if fm == FILL_METHOD_NA:
        return False
    return _is_measured(row) and has_price_evidence(row)


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


def pooling_config_payload(config: Mapping | None = None) -> dict:
    """Canonical price/pooling knobs hashed into the rent-table stamp."""
    cfg = config if config is not None else sr.load_config()
    price = cfg.get("price") or {}
    out = {}
    for key in POOLING_CONFIG_HASH_KEYS:
        if key not in price:
            raise FillError(f"surface.yaml price.{key} required for pooling stamp")
        val = price[key]
        out[key] = float(val) if key == "shrinkage_k" else (
            int(val) if key != "measure" else str(val)
        )
    return out


def pooling_config_sha256(config: Mapping | None = None) -> str:
    payload = pooling_config_payload(config)
    canon = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canon.encode("utf-8")).hexdigest()


def null_dz_fill_target_from_config(config: Mapping | None = None) -> int:
    """Post-pooling model-fill target (includes the 4 not-in-price-file codes)."""
    cfg = config if config is not None else sr.load_config()
    section = cfg.get("model_fill") or {}
    return int(section.get("null_dz_fill_target_n", DEFAULT_NULL_DZ_FILL_TARGET_N))


def evidence_window_to_step(window: str | None) -> str:
    """Map rent-table evidence_window → top-level fill_step for measured zones."""
    w = str(window or "").strip()
    if w in ("2023", STEP_MEASURED_2023):
        return STEP_MEASURED_2023
    if w == "pooled_3y":
        return STEP_POOLED_3Y
    if w == "pooled_5y":
        return STEP_POOLED_5Y
    if not w:
        return STEP_MEASURED_2023
    raise FillError(f"unknown evidence_window {window!r}")


def load_2011_rent_table(path: Path | str) -> list[dict]:
    """Load 2011-zone rent table (zone_id, central, low, high, status). Never commit.

    Pooled tables also carry ``evidence_window``, ``evidence_oldest_year``,
    ``sales_n``, and ``pooling_config_sha256`` (FILL-POOLED stamp).
    """
    p = Path(path)
    if not p.is_file():
        raise MissingLookupError(
            f"2011 rent table missing: {p} (path is a setting; never commit)"
        )
    rows: list[dict] = []
    with p.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = set(reader.fieldnames or ())
        for i, raw in enumerate(reader):
            code = str(raw.get("zone_id") or raw.get("code") or "").strip()
            if not code:
                raise FillError(f"{p.name} row {i}: missing zone_id/code")
            central = _num(raw.get("central") if "central" in raw else raw.get("measured_rent"))
            low = _num(raw.get("low") if "low" in raw else raw.get("uncertainty_low"))
            high = _num(raw.get("high") if "high" in raw else raw.get("uncertainty_high"))
            status = str(raw.get("status") or raw.get("fill_method") or "").strip()
            sales_raw = raw.get("sales_n")
            sales_n_hint = (
                int(sales_raw) if sales_raw not in (None, "") else None
            )
            if not status:
                # FILL-MEASURED-ZERO: central==0 with sales is still observed, not pending.
                if sales_n_hint is not None and sales_n_hint > 0 and central is not None:
                    status = "observed_pooled"
                elif central is not None and central > 0:
                    status = "observed_pooled"
                else:
                    status = "model_fill_pending"
            # Measured zero keeps band £0 → upper; never collapse high to flat £0 when given.
            if low is None:
                low = 0.0 if central == 0.0 else central
            if high is None:
                high = central
            row = {
                "code": code,
                "vintage": 2011,
                "measured_rent": central,
                "uncertainty_low": low,
                "uncertainty_high": high,
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
            if "evidence_window" in fieldnames:
                row["evidence_window"] = str(raw.get("evidence_window") or "").strip()
            if "evidence_oldest_year" in fieldnames:
                ey = str(raw.get("evidence_oldest_year") or "").strip()
                if not ey:
                    row["evidence_oldest_year"] = None
                else:
                    try:
                        row["evidence_oldest_year"] = int(ey)
                    except ValueError as exc:
                        raise FillError(
                            f"{p.name} row {i}: bad evidence_oldest_year {ey!r}"
                        ) from exc
            if "pooling_config_sha256" in fieldnames:
                row["pooling_config_sha256"] = str(
                    raw.get("pooling_config_sha256") or ""
                ).strip()
            rows.append(row)
    if not rows:
        raise FillError(f"2011 rent table empty: {p}")
    return rows


def table_has_pooling_stamp(
    rows: Sequence[Mapping], *, config: Mapping | None = None
) -> bool:
    """True when every row carries evidence_window + matching pooling_config_sha256."""
    if not rows:
        return False
    expected = pooling_config_sha256(config)
    for r in rows:
        if "evidence_window" not in r:
            return False
        digest = str(r.get("pooling_config_sha256") or "").strip()
        if digest != expected:
            return False
    return True


def ensure_pooling_stamp(
    rows: Sequence[Mapping],
    *,
    config: Mapping | None = None,
    override: bool = False,
    reason: str | None = None,
    logger: logging.Logger | None = None,
) -> None:
    """Refuse an unpooled 2011 table unless ``override`` + non-empty ``reason``."""
    if table_has_pooling_stamp(rows, config=config):
        return
    if override:
        if not reason or not str(reason).strip():
            raise FillError("pooling-stamp override requires a non-empty reason")
        (logger or LOG).warning(
            "FILL-POOLED override: accepting unpooled 2011 rent table (%s)",
            reason,
        )
        return
    raise UnpooledTableError(
        "2011 rent table missing pooling stamp "
        "(evidence_window column + pooling_config_sha256); "
        "refuse unpooled input (pass --override --reason to force)"
    )


def measured_zero_n_from_config(config: Mapping | None = None) -> int:
    """Expected measured-zero count (pooled price, floored residual)."""
    if config is None:
        config = sr.load_config()
    section = (config.get("dz2022_empty_fill") or {}).get("reconciled") or {}
    if "measured_zeros_n" in section:
        return int(section["measured_zeros_n"])
    return DEFAULT_MEASURED_ZERO_N


def reconciled_facts(config: Mapping | None = None) -> dict:
    """Post-pooling reconciled zone counts (config target + fixed code lists)."""
    target = null_dz_fill_target_from_config(config)
    measured_zeros = measured_zero_n_from_config(config)
    return {
        "model_fill_n": target,
        "suppressed_after_pooling_n": target - len(NOT_IN_PRICE_FILE_CODES),
        "not_in_price_file": sorted(NOT_IN_PRICE_FILE_CODES),
        "not_in_price_file_n": len(NOT_IN_PRICE_FILE_CODES),
        "not_in_price_file_fill": CLASS_C,
        "zero_dwellings": sorted(ZERO_DWELLING_CODES),
        "zero_dwellings_n": len(ZERO_DWELLING_CODES),
        "zero_dwellings_fill": CLASS_D,
        "measured_zeros_n": measured_zeros,
        "empty_to_fill_n": target,
        "pre_pooling_empty_to_fill_n": PRE_POOLING_EMPTY_TO_FILL_N,
        "note": (
            f"{target} model-fill after pooling (includes "
            f"{len(NOT_IN_PRICE_FILE_CODES)} not-in-price-file) + "
            f"{measured_zeros} measured zeros (cost >= price, not filled) + "
            f"{len(ZERO_DWELLING_CODES)} zero-dwellings (D). "
            "S01010206/S01010226 are zero-dwellings (D), not among the 4 C codes. "
            f"Pre-pooling baseline was {PRE_POOLING_EMPTY_TO_FILL_N}."
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
    class_min: int = CLASS_MIN_TRAINING,
) -> GroupModel:
    """Borrowing order per Methods v1.2 island / mainland rules; always fills."""
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

    # Mainland (Methods v1.2): own → neighbouring council same UR class →
    # Scotland-wide same class. No next-UR-class borrow.
    if len(logs) < class_min:
        for nla in neighbours.get(la, ()):
            extra = by_group.get((nla, int(ur6))) or ()
            if not extra:
                continue
            logs.extend(extra)
            borrowed.append(f"council:{nla}")
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
    class_min: int = CLASS_MIN_TRAINING,
    target_keys: Iterable[tuple[str, int]] | None = None,
) -> dict[tuple[str, int], GroupModel]:
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
    c_sub_step: str | None = None,
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
    if c_sub_step is not None:
        row["c_sub_step"] = c_sub_step
        tags.append(f"c_sub_step={c_sub_step}")
    _stamp_blocked(row, estimate_label=estimate_label, extra_tags=tags)
    return row


def _measured_step_for_edges(
    edges: Sequence[Mapping], by_2011: Mapping[str, Mapping]
) -> str:
    """UPRN-weighted evidence_window among measured 2011 sources → top-level step."""
    votes: Counter[str] = Counter()
    for e in edges:
        src = by_2011.get(str(e["dz2011"]).strip())
        if src is None or not _is_measured(src):
            continue
        n = int(e.get("uprn_count") or 0)
        if n <= 0:
            continue
        step = evidence_window_to_step(src.get("evidence_window"))
        votes[step] += n
    if not votes:
        return STEP_MEASURED_2023
    # Prefer weaker evidence on ties: pooled_5y > pooled_3y > measured_2023.
    order = (STEP_POOLED_5Y, STEP_POOLED_3Y, STEP_MEASURED_2023)
    best_n = max(votes.values())
    for step in order:
        if votes.get(step, 0) == best_n:
            return step
    return votes.most_common(1)[0][0]


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
    class_min: int = CLASS_MIN_TRAINING,
    band_widen: Mapping[str, Sequence[float]] | None = None,
    scotland_holdout_errors_by_ur6: Mapping[int, Sequence[float]] | None = None,
    require_pooling_stamp: bool = True,
    override_unpooled: bool = False,
    override_reason: str | None = None,
    config: Mapping | None = None,
) -> FillResult:
    """Classify and fill DZ2022 empty-zone mass (A/B/C/D). Every zone is filled."""
    if require_pooling_stamp:
        ensure_pooling_stamp(
            dz2011_rows,
            config=config,
            override=override_unpooled,
            reason=override_reason,
        )
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
                    fill_step=STEP_NA,
                )
            )
            continue

        if klass.fill_class == CLASS_UNAFFECTED:
            measured_step = _measured_step_for_edges(edges, by_2011)
            extra = ["unaffected_empty_share_0"]
            if measured_rent == 0.0:
                # FILL-MEASURED-ZERO: keep internal tag; band is £0 → high.
                extra.append(COST_AT_OR_ABOVE_PRICE_TAG)
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
                extra_tags=extra,
                fill_step=measured_step,
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
                    fill_step=STEP_A_RESCALE,
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
                    fill_step=STEP_C_MODEL,
                    c_sub_step=model.fill_step,
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
                fill_step=STEP_B_BLEND,
                c_sub_step=model.fill_step,
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

    step_counts = count_fill_steps(out_rows)
    stats = {
        "n_2022": len(out_rows),
        "by_class": {
            c: sum(1 for z in classifications.values() if z.fill_class == c)
            for c in (CLASS_UNAFFECTED, CLASS_A, CLASS_B, CLASS_C, CLASS_D)
        },
        "by_fill_step": dict(step_counts["by_fill_step"]),
        "by_c_sub_step": dict(step_counts["by_c_sub_step"]),
        "publication_status": PUBLICATION_STATUS,
        "value_tier": VALUE_TIER,
        "proxy_tag": PROXY_TAG,
        "reconciled": reconciled_facts(config),
    }
    return FillResult(
        rows_2022=out_rows,
        classifications=classifications,
        models=models,
        rows_2011_for_conservation=rows_2011_cons,
        stats=stats,
    )


def count_fill_steps(rows_2022: Sequence[Mapping]) -> dict:
    """Per-zone step inventory: exactly one top-level step; C sub-steps sum to C."""
    by_step: Counter[str] = Counter()
    by_c_sub: Counter[str] = Counter()
    missing = []
    for r in rows_2022:
        step = str(r.get("fill_step") or "").strip()
        if not step:
            missing.append(str(r.get("code") or ""))
            continue
        by_step[step] += 1
        if step == STEP_C_MODEL:
            sub = str(r.get("c_sub_step") or "").strip()
            if not sub:
                missing.append(str(r.get("code") or ""))
                continue
            by_c_sub[sub] += 1
    return {
        "by_fill_step": by_step,
        "by_c_sub_step": by_c_sub,
        "missing_step_codes": missing,
        "n_rows": len(rows_2022),
        "n_with_step": sum(by_step.values()),
        "c_model_n": by_step.get(STEP_C_MODEL, 0),
        "c_sub_step_sum": sum(by_c_sub.values()),
    }


def format_step_count_table(rows_2022: Sequence[Mapping]) -> str:
    """Counts-only table printed at end of a fill run (no £)."""
    counts = count_fill_steps(rows_2022)
    lines = ["fill_step,count"]
    for step in sorted(counts["by_fill_step"]):
        lines.append(f"{step},{counts['by_fill_step'][step]}")
    lines.append("c_sub_step,count")
    for sub in sorted(counts["by_c_sub_step"]):
        lines.append(f"{sub},{counts['by_c_sub_step'][sub]}")
    return "\n".join(lines)


def print_step_count_table(
    rows_2022: Sequence[Mapping], *, file=None
) -> dict:
    text = format_step_count_table(rows_2022)
    print(text, file=file)
    return count_fill_steps(rows_2022)


def assert_fill_step_inventory(rows_2022: Sequence[Mapping]) -> None:
    """T4: every zone one step; C sub-step counts sum to C total."""
    counts = count_fill_steps(rows_2022)
    if counts["missing_step_codes"]:
        raise FillError(
            f"fill_step missing for zones: {counts['missing_step_codes'][:10]}"
        )
    if counts["n_with_step"] != counts["n_rows"]:
        raise FillError(
            f"fill_step inventory {counts['n_with_step']} != n_rows {counts['n_rows']}"
        )
    if counts["c_sub_step_sum"] != counts["c_model_n"]:
        raise FillError(
            f"c_sub_step sum {counts['c_sub_step_sum']} != "
            f"C_model total {counts['c_model_n']}"
        )
    for step in counts["by_fill_step"]:
        if step not in TOP_LEVEL_STEPS:
            raise FillError(f"unknown fill_step {step!r}")
    for sub in counts["by_c_sub_step"]:
        if sub not in C_SUB_STEPS:
            raise FillError(f"unknown c_sub_step {sub!r}")


def count_measured_zeros(dz2011_rows: Sequence[Mapping]) -> int:
    """Count floored measured/pooled zeros (cost >= price); excludes N/A zero-dwellings."""
    zero = set(ZERO_DWELLING_CODES)
    n = 0
    for r in dz2011_rows:
        if _is_zero_dwellings(r, zero):
            continue
        if is_measured_zero(r):
            n += 1
    return n


def count_reconciled_sources(dz2011_rows: Sequence[Mapping]) -> dict[str, int]:
    """Count model-fill / not-in-price-file / zero-dwellings on a 2011 inventory.

    ``model_fill_n`` includes the 4 not-in-price-file codes (post-pooling target).
    Measured zeros are never counted as model-fill (FILL-MEASURED-ZERO).
    """
    zero = set(ZERO_DWELLING_CODES)
    n_zero = 0
    n_not_in_price = 0
    n_model_fill = 0
    for r in dz2011_rows:
        code = str(r.get("code") or "").strip()
        if _is_zero_dwellings(r, zero) or code in zero:
            n_zero += 1
            continue
        if is_measured_zero(r):
            # Price evidence + floored residual — keep measured; do not fill.
            continue
        if code in NOT_IN_PRICE_FILE_CODES or "absent_from_ros_price_file" in str(
            r.get("flags") or ""
        ).split(";"):
            # Reconciled: the 4 C-filled codes (not the zero-dwelling absents).
            if code in NOT_IN_PRICE_FILE_CODES:
                n_not_in_price += 1
                n_model_fill += 1
            elif _is_empty_to_fill(r, zero):
                n_model_fill += 1
            continue
        if _is_empty_to_fill(r, zero):
            n_model_fill += 1
    return {
        "model_fill_n": n_model_fill,
        "not_in_price_file_n": n_not_in_price,
        "zero_dwellings_n": n_zero,
    }


def expected_reconciled_counts(config: Mapping | None = None) -> dict[str, int]:
    """Expected post-pooling gate counts from config + fixed code lists."""
    return {
        "model_fill_n": null_dz_fill_target_from_config(config),
        "not_in_price_file_n": len(NOT_IN_PRICE_FILE_CODES),
        "zero_dwellings_n": len(ZERO_DWELLING_CODES),
    }


def assert_reconciled_source_counts(
    dz2011_rows: Sequence[Mapping], *, config: Mapping | None = None
) -> None:
    """Real-run gate: inventory must match post-pooling config target / 4 / 3.

    Feeding the pre-pooling 723/727 inventory must fail once config is 129.
    """
    counts = count_reconciled_sources(dz2011_rows)
    expected = expected_reconciled_counts(config)
    if counts != expected:
        raise FillError(
            f"reconciled source counts {counts} != expected {expected} "
            f"(post-pooling model-fill {expected['model_fill_n']} includes "
            f"{expected['not_in_price_file_n']} not-in-price-file; "
            f"{expected['zero_dwellings_n']} zero-dwellings; "
            f"pre-pooling {PRE_POOLING_EMPTY_TO_FILL_N} must not pass)"
        )
    # Hard refuse the retired pre-pooling constants if someone reintroduces them.
    if expected["model_fill_n"] in (
        PRE_POOLING_EMPTY_TO_FILL_N,
        PRE_POOLING_SUPPRESSED_N,
    ):
        raise FillError(
            f"null_dz_fill_target_n must be post-pooling "
            f"(not {PRE_POOLING_EMPTY_TO_FILL_N}/{PRE_POOLING_SUPPRESSED_N})"
        )


def assert_post_fill_gate(
    rows_2011: Sequence[Mapping],
    rows_2022: Sequence[Mapping],
    *,
    require_reconciled_counts: bool = False,
    source_2011: Sequence[Mapping] | None = None,
    config: Mapping | None = None,
) -> None:
    """Gate: Scotland total conserved; non-N/A rents > 0 or measured zeros.

    FILL-MEASURED-ZERO: a zero passes ONLY when the row is a measured zero with
    price evidence. A zero with no price evidence still FAILs. Expected model-fill
    count stays 129 (measured zeros are not filled).

    On a real run pass ``require_reconciled_counts=True`` and the original 2011
    rent-table inventory as ``source_2011`` to assert the post-pooling
    model-fill target / 4 not-in-price-file / 3 zero-dwellings counts.
    """
    dz22.assert_scotland_total_conserved(rows_2011, rows_2022, field="measured_rent")
    if require_reconciled_counts:
        inventory = source_2011 if source_2011 is not None else rows_2011
        assert_reconciled_source_counts(inventory, config=config)
    for r in rows_2022:
        label = str(r.get("estimate_label") or "")
        fm = str(r.get("fill_method") or "")
        rent = _num(r.get("measured_rent"))
        if label == ESTIMATE_NA or fm == FILL_METHOD_NA:
            continue
        if rent is None or rent < 0:
            raise FillError(
                f"post-fill gate: DZ2022 {r.get('code')} has rent {rent}; "
                "expected > 0 or measured zero with price evidence"
            )
        if rent == 0:
            if not is_measured_zero(r):
                raise FillError(
                    f"post-fill gate: DZ2022 {r.get('code')} has rent 0 without "
                    "measured price evidence (zero with no evidence must FAIL)"
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
