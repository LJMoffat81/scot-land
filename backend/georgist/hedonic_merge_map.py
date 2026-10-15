"""v1.4 O-MM: hedonic market-cell merge map (spec §2.1–2.2).

Cells = CA2019 × UR3 (urban 1–2, towns 3–4, rural 5–6 from DZ2011 URC 2020).
A cell is estimable iff n ≥ 40 fit-window zones AND IQR(ln A_z) ≥ 0.30;
else merge same-UR3 within ITL3, then same-UR3 nationally.

Inputs are sale COUNTS and plot areas A_z only — never price/value/rent columns.
Output is written outside git (gitignored); sha256 is printed by the CLI.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import random
import zipfile
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

# Seed is read from v14_prereg_freeze.json (not hard-coded). Draft location per
# v14_prereg_DRAFT.md § freeze note; file may be absent on CI / cloud VMs.
DEFAULT_PREREG_FREEZE_PATH = Path("/workspace/scotland-rules/v14_prereg_freeze.json")

MIN_ZONES = 40
MIN_IQR_LN_A = 0.30
FIT_YEARS = (2021, 2022)
MIN_SALES_PER_YEAR = 5
MIN_SALES_POOLED = 10
UPRN_KEEP_SHARE_MIN = 0.90
# E8 drop (consumer-side; same thresholds as DZ2022 UPRN crosswalk).
E8_MIN_SHARE = 0.01
E8_MIN_UPRN_COUNT = 5

# Exact column names that must never be loaded (sale/price/value/rent tables).
PRICE_VALUE_RENT_DENYLIST = frozenset(
    {
        "price",
        "mean",
        "median",
        "lq",
        "uq",
        "lower quartile",
        "upper quartile",
        "value",
        "rent",
        "gbp",
        "£",
        "dz_med",
        "dz_med2021",
        "dz_med2022",
        "dz_med2023",
        "dz_med_pool_approx",
        "iz_med2021",
        "iz_med2022",
        "iz_med2023",
        "iz_med_pool_approx",
        "ca_med2021",
        "ca_med2022",
        "ca_med2023",
        "ca_med_pool_approx",
        "price - mean",
        "price - median",
        "price - lower quartile",
        "price - upper quartile",
    }
)

# Any column whose lowercased name *contains* one of these is refused.
_PRICE_RENT_VALUE_POUND_TOKENS = ("price", "rent", "value", "£")

UR8_TO_UR6 = {1: 1, 2: 2, 3: 3, 4: 4, 5: 4, 6: 5, 7: 6, 8: 6}
UR3_LABEL = {"urban": "urban", "towns": "towns", "rural": "rural"}

MERGE_MAP_COLUMNS = (
    "dz2011",
    "ca2019",
    "itl3",
    "ur6",
    "ur3",
    "a_z_m2",
    "n_sales_fit",
    "cell_ca",
    "cell_itl3",
    "cell_final",
    "merge_level",
)


@dataclass(frozen=True)
class ZoneRow:
    dz2011: str
    ca2019: str
    itl3: str
    ur6: int
    ur3: str
    a_z_m2: float
    n_sales_fit: int


def ur6_to_ur3(ur6: int) -> str:
    if ur6 in (1, 2):
        return "urban"
    if ur6 in (3, 4):
        return "towns"
    if ur6 in (5, 6):
        return "rural"
    raise ValueError(f"UR6 class out of range: {ur6}")


def cell_id(ca_or_itl_or_national: str, ur3: str) -> str:
    return f"{ca_or_itl_or_national}|{ur3}"


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_seed_from_prereg_freeze(path: Path | str) -> int:
    """Read tie-break seed from freeze JSON: ``seeds.hedonic_cluster_bootstrap``.

    The path must exist (default production path
    ``/workspace/scotland-rules/v14_prereg_freeze.json``). Does not invent or
    pin a freeze-file sha256 — seed field is authoritative.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(
            "v14_prereg_freeze.json missing; seed cannot be loaded. "
            f"Exact path needed: {p}"
        )
    with p.open(encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{p} root must be a JSON object")
    seeds = data.get("seeds")
    if not isinstance(seeds, dict) or "hedonic_cluster_bootstrap" not in seeds:
        raise ValueError(
            f"{p} missing seeds.hedonic_cluster_bootstrap "
            "(required for O-MM merge-map tie-break)"
        )
    return int(seeds["hedonic_cluster_bootstrap"])


def assert_no_price_columns(columns: Iterable[str]) -> list[str]:
    """Raise if any loaded column name matches the price/value/rent denylist."""
    kept: list[str] = []
    denied: list[str] = []
    for raw in columns:
        name = str(raw).strip()
        key = name.lower()
        kept.append(name)
        if key in PRICE_VALUE_RENT_DENYLIST:
            denied.append(name)
            continue
        if any(tok in key for tok in _PRICE_RENT_VALUE_POUND_TOKENS):
            denied.append(name)
            continue
        # Bare measure names (exact), not household/population *Count* fields.
        if key in {"mean", "median", "gbp"}:
            denied.append(name)
    if denied:
        raise ValueError(
            "refusing to load price/value/rent columns for O-MM merge map: "
            + ", ".join(sorted(set(denied)))
        )
    return kept


def _pick_modal(weighted: Mapping[str, float], *, dz: str, seed: int) -> str:
    """Household-weighted modal code; seeded tie-break among equal weights."""
    if not weighted:
        raise ValueError(f"no modal candidates for {dz}")
    max_w = max(weighted.values())
    tied = sorted(c for c, w in weighted.items() if w == max_w)
    if len(tied) == 1:
        return tied[0]
    rng = random.Random(f"{seed}:{dz}:{','.join(tied)}")
    return rng.choice(tied)


def load_ca_itl3_from_spd(
    spd_zip: Path,
    *,
    member: str = "SmallUser.csv",
    seed: int,
) -> dict[str, tuple[str, str]]:
    """Modal CA2019 and ITL3 per DZ2011, weighted by CensusHouseholdCount2022."""
    need = {
        "DataZone2011Code",
        "CouncilArea2019Code",
        "ITL2025Level3Code",
        "CensusHouseholdCount2022",
    }
    ca_w: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    itl_w: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    with zipfile.ZipFile(spd_zip) as zf:
        with zf.open(member) as raw:
            text = io.TextIOWrapper(raw, encoding="utf-8", newline="")
            reader = csv.DictReader(text)
            assert_no_price_columns(reader.fieldnames or [])
            missing = need - set(reader.fieldnames or [])
            if missing:
                raise ValueError(f"SPD {member} missing columns: {sorted(missing)}")
            for row in reader:
                dz = (row.get("DataZone2011Code") or "").strip()
                ca = (row.get("CouncilArea2019Code") or "").strip()
                itl = (row.get("ITL2025Level3Code") or "").strip()
                if not dz or not ca or not itl:
                    continue
                try:
                    hh = float(row.get("CensusHouseholdCount2022") or 0)
                except ValueError:
                    hh = 0.0
                if hh <= 0:
                    continue
                ca_w[dz][ca] += hh
                itl_w[dz][itl] += hh
    out: dict[str, tuple[str, str]] = {}
    for dz in sorted(set(ca_w) | set(itl_w)):
        out[dz] = (
            _pick_modal(ca_w[dz], dz=dz, seed=seed),
            _pick_modal(itl_w[dz], dz=dz, seed=seed),
        )
    return out


def load_ur6_lookup(path: Path) -> dict[str, int]:
    """DZ2011 → UR6. Accepts D13 (DataZone/UR6FOLD) or processed dz2011/ur8."""
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = assert_no_price_columns(reader.fieldnames or [])
        colset = set(cols)
        out: dict[str, int] = {}
        if {"DataZone", "UR6FOLD"} <= colset:
            for row in reader:
                code = (row.get("DataZone") or "").strip()
                if not code:
                    continue
                out[code] = int(row["UR6FOLD"])
            return out
        if {"dz2011", "ur8"} <= colset:
            for row in reader:
                code = (row.get("dz2011") or "").strip()
                if not code:
                    continue
                ur8 = int(row["ur8"])
                if ur8 not in UR8_TO_UR6:
                    raise ValueError(f"UR8 class {ur8} out of range for {code}")
                out[code] = UR8_TO_UR6[ur8]
            return out
        if {"dz2011", "ur6"} <= colset:
            for row in reader:
                code = (row.get("dz2011") or "").strip()
                if not code:
                    continue
                out[code] = int(row["ur6"])
            return out
    raise ValueError(
        f"urban-rural lookup {path} needs DataZone/UR6FOLD, dz2011/ur6, or dz2011/ur8"
    )


def load_fit_window_counts(
    path: Path,
    *,
    years: Sequence[int] = FIT_YEARS,
    min_per_year: int = MIN_SALES_PER_YEAR,
    min_pooled: int = MIN_SALES_POOLED,
) -> dict[str, int]:
    """Return {dz2011: pooled_n} for zones that meet the fit-window count rule.

    Accepts either:
    - long extract: code, year, sales_n [, suppressed]
    - wide RoS-style count file with explicit count columns only (no prices).
    """
    with path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = assert_no_price_columns(reader.fieldnames or [])
        colset = {c.lower() for c in cols}
        rows = list(reader)

    year_set = {int(y) for y in years}
    per_zone: dict[str, dict[int, int]] = defaultdict(dict)

    if {"code", "year", "sales_n"} <= colset:
        for row in rows:
            code = (row.get("code") or "").strip()
            if not code:
                continue
            try:
                year = int(row["year"])
            except (TypeError, ValueError):
                continue
            if year not in year_set:
                continue
            if str(row.get("suppressed", "")).strip().lower() in {"true", "1", "yes"}:
                # Suppressed rows may still carry a count; fit window needs ≥5.
                pass
            try:
                n = int(float(row["sales_n"]))
            except (TypeError, ValueError):
                continue
            per_zone[code][year] = n
    else:
        # Wide count-only: require columns like n_2021 / count_2021 / sales_n_2021.
        year_cols: dict[int, str] = {}
        for c in cols:
            cl = c.lower()
            for y in year_set:
                if cl in {f"n_{y}", f"count_{y}", f"sales_n_{y}", f"dz_n{y}"}:
                    year_cols[y] = c
        if set(year_cols) != year_set:
            raise ValueError(
                f"count file {path} missing year count columns for {sorted(year_set)}; "
                f"have {sorted(colset)}"
            )
        code_col = next(
            (c for c in cols if c.lower() in {"code", "dz2011", "datazone", "geographycode"}),
            None,
        )
        if code_col is None:
            raise ValueError(f"count file {path} has no zone code column")
        for row in rows:
            code = (row.get(code_col) or "").strip()
            if not code:
                continue
            for y, cname in year_cols.items():
                raw = (row.get(cname) or "").strip()
                if not raw:
                    continue
                try:
                    per_zone[code][y] = int(float(raw))
                except ValueError:
                    continue

    out: dict[str, int] = {}
    for code, by_year in per_zone.items():
        if any(by_year.get(y, 0) < min_per_year for y in year_set):
            continue
        pooled = sum(by_year[y] for y in year_set)
        if pooled < min_pooled:
            continue
        out[code] = pooled
    return out


def _e8_filter_pairs(
    pairs: list[dict],
) -> tuple[list[dict], dict[str, int], dict[str, int]]:
    """Drop E8 sliver pairs and return kept pairs plus raw/kept UPRN totals per DZ2011."""
    by_j: dict[str, list[dict]] = defaultdict(list)
    for p in pairs:
        by_j[p["dz2022"]].append(p)

    kept: list[dict] = []
    raw_u_i: dict[str, int] = defaultdict(int)
    kept_u_i: dict[str, int] = defaultdict(int)

    for edges in by_j.values():
        total_j = sum(int(e["uprn_count"]) for e in edges)
        if total_j <= 0:
            continue
        kept_edges: list[dict] = []
        for e in edges:
            raw_u_i[e["dz2011"]] += int(e["uprn_count"])
            share = int(e["uprn_count"]) / total_j
            if share < E8_MIN_SHARE and int(e["uprn_count"]) < E8_MIN_UPRN_COUNT:
                continue
            kept_edges.append(e)
        # Redistribute weights over kept edges for target j.
        kept_total = sum(int(e["uprn_count"]) for e in kept_edges)
        if kept_total <= 0:
            continue
        for e in kept_edges:
            e = dict(e)
            e["w"] = int(e["uprn_count"]) / kept_total
            kept.append(e)
            kept_u_i[e["dz2011"]] += int(e["uprn_count"])
    return kept, dict(raw_u_i), dict(kept_u_i)


def load_a_z_m2(
    plot_split_path: Path,
    uprn_weights_path: Path,
    *,
    plot_ha_col: str = "house_plot_ha",
    homes_col: str = "homes",
    code_col: str | None = None,
) -> dict[str, float]:
    """Build DZ2011 A_z (m²/home) via §3.2 ratio of apportioned sums."""
    with plot_split_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        cols = assert_no_price_columns(reader.fieldnames or [])
        if code_col is None:
            for cand in ("code", "dz2022", "DataZone", "dz2022_code"):
                if cand in cols:
                    code_col = cand
                    break
        if code_col is None or plot_ha_col not in cols or homes_col not in cols:
            raise ValueError(
                f"plot_split {plot_split_path} needs code + {plot_ha_col} + {homes_col}; have {cols}"
            )
        plot_by_j: dict[str, tuple[float, float]] = {}
        for row in reader:
            j = (row.get(code_col) or "").strip()
            if not j:
                continue
            flags = (row.get("method_flags") or row.get("flags") or "").lower()
            if "no_residential_parcel" in flags:
                continue
            try:
                ha = float(row[plot_ha_col])
                homes = float(row[homes_col])
            except (TypeError, ValueError):
                continue
            if homes <= 0 or ha < 0:
                continue
            plot_by_j[j] = (ha, homes)

    with uprn_weights_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        assert_no_price_columns(reader.fieldnames or [])
        # Accept dz2011/dz2022 or *_code.
        field = {c.lower(): c for c in (reader.fieldnames or [])}
        c11 = field.get("dz2011") or field.get("dz2011_code")
        c22 = field.get("dz2022") or field.get("dz2022_code")
        cu = field.get("uprn_count")
        if not c11 or not c22 or not cu:
            raise ValueError(
                f"uprn weights {uprn_weights_path} need dz2011, dz2022, uprn_count"
            )
        pairs: list[dict] = []
        for row in reader:
            i = (row.get(c11) or "").strip()
            j = (row.get(c22) or "").strip()
            if not i or not j:
                continue
            try:
                n = int(float(row[cu]))
            except (TypeError, ValueError):
                continue
            if n <= 0:
                continue
            pairs.append({"dz2011": i, "dz2022": j, "uprn_count": n})

    kept, raw_u_i, kept_u_i = _e8_filter_pairs(pairs)

    # Numerator / denominator of A_i (m²).
    num: dict[str, float] = defaultdict(float)
    den: dict[str, float] = defaultdict(float)
    for e in kept:
        j = e["dz2022"]
        if j not in plot_by_j:
            continue
        ha, homes = plot_by_j[j]
        w = float(e["w"])
        num[e["dz2011"]] += w * ha * 10_000.0
        den[e["dz2011"]] += w * homes

    out: dict[str, float] = {}
    for i, nsum in num.items():
        raw = raw_u_i.get(i, 0)
        kept_u = kept_u_i.get(i, 0)
        if raw <= 0 or (kept_u / raw) < UPRN_KEEP_SHARE_MIN:
            continue
        d = den.get(i, 0.0)
        if d <= 0:
            continue
        a = nsum / d
        if a <= 0:
            continue
        out[i] = a
    return out


def iqr(values: Sequence[float]) -> float:
    if not values:
        return float("nan")
    xs = sorted(values)
    n = len(xs)

    def _q(p: float) -> float:
        if n == 1:
            return xs[0]
        pos = p * (n - 1)
        lo = int(math.floor(pos))
        hi = int(math.ceil(pos))
        if lo == hi:
            return xs[lo]
        w = pos - lo
        return xs[lo] * (1.0 - w) + xs[hi] * w

    return _q(0.75) - _q(0.25)


def cell_estimable(zones: Sequence[ZoneRow]) -> bool:
    if len(zones) < MIN_ZONES:
        return False
    ln_a = [math.log(z.a_z_m2) for z in zones if z.a_z_m2 > 0]
    if len(ln_a) < MIN_ZONES:
        return False
    return iqr(ln_a) >= MIN_IQR_LN_A


def build_zone_rows(
    *,
    fit_counts: Mapping[str, int],
    a_z: Mapping[str, float],
    ur6: Mapping[str, int],
    ca_itl3: Mapping[str, tuple[str, str]],
) -> list[ZoneRow]:
    rows: list[ZoneRow] = []
    for dz in sorted(set(fit_counts) & set(a_z) & set(ur6) & set(ca_itl3)):
        ca, itl = ca_itl3[dz]
        u6 = int(ur6[dz])
        rows.append(
            ZoneRow(
                dz2011=dz,
                ca2019=ca,
                itl3=itl,
                ur6=u6,
                ur3=ur6_to_ur3(u6),
                a_z_m2=float(a_z[dz]),
                n_sales_fit=int(fit_counts[dz]),
            )
        )
    return rows


def assign_merge_cells(zones: Sequence[ZoneRow]) -> list[dict[str, object]]:
    """Apply §2.2 merge ladder; return sorted merge-map rows."""
    by_ca: dict[tuple[str, str], list[ZoneRow]] = defaultdict(list)
    for z in zones:
        by_ca[(z.ca2019, z.ur3)].append(z)

    # Level 1: CA × UR3
    ca_pass: dict[tuple[str, str], bool] = {
        k: cell_estimable(v) for k, v in by_ca.items()
    }

    # Zones that fail CA cell go to ITL3 × UR3 pools.
    by_itl: dict[tuple[str, str], list[ZoneRow]] = defaultdict(list)
    for key, members in by_ca.items():
        if ca_pass[key]:
            continue
        for z in members:
            by_itl[(z.itl3, z.ur3)].append(z)

    itl_pass: dict[tuple[str, str], bool] = {
        k: cell_estimable(v) for k, v in by_itl.items()
    }

    # Failures at ITL3 go to national UR3.
    by_nat: dict[str, list[ZoneRow]] = defaultdict(list)
    for key, members in by_itl.items():
        if itl_pass[key]:
            continue
        for z in members:
            by_nat[z.ur3].append(z)

    out: list[dict[str, object]] = []
    for z in zones:
        ca_key = (z.ca2019, z.ur3)
        cell_ca = cell_id(z.ca2019, z.ur3)
        cell_itl = cell_id(z.itl3, z.ur3)
        cell_nat = cell_id("NATIONAL", z.ur3)
        if ca_pass[ca_key]:
            final, level = cell_ca, "ca"
        else:
            itl_key = (z.itl3, z.ur3)
            if itl_pass.get(itl_key, False):
                final, level = cell_itl, "itl3"
            else:
                final, level = cell_nat, "national"
        out.append(
            {
                "dz2011": z.dz2011,
                "ca2019": z.ca2019,
                "itl3": z.itl3,
                "ur6": z.ur6,
                "ur3": z.ur3,
                "a_z_m2": f"{z.a_z_m2:.8f}",
                "n_sales_fit": z.n_sales_fit,
                "cell_ca": cell_ca,
                "cell_itl3": cell_itl,
                "cell_final": final,
                "merge_level": level,
            }
        )
    out.sort(key=lambda r: str(r["dz2011"]))
    return out


def serialize_merge_map(rows: Sequence[Mapping[str, object]]) -> bytes:
    """Stable UTF-8 CSV: fixed columns, sorted rows, LF newlines, no extras."""
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=list(MERGE_MAP_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({c: row[c] for c in MERGE_MAP_COLUMNS})
    return buf.getvalue().encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_merge_map(path: Path, rows: Sequence[Mapping[str, object]]) -> str:
    """Write merge map outside git-friendly callers; return sha256 hex."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = serialize_merge_map(rows)
    path.write_bytes(payload)
    digest = sha256_bytes(payload)
    path.with_suffix(path.suffix + ".sha256").write_text(digest + "\n", encoding="utf-8")
    return digest


def build_merge_map_from_paths(
    *,
    counts_path: Path,
    plot_split_path: Path,
    uprn_weights_path: Path,
    ur_path: Path,
    spd_zip: Path,
    seed: int,
) -> list[dict[str, object]]:
    fit = load_fit_window_counts(counts_path)
    a_z = load_a_z_m2(plot_split_path, uprn_weights_path)
    ur6 = load_ur6_lookup(ur_path)
    ca_itl3 = load_ca_itl3_from_spd(spd_zip, seed=seed)
    zones = build_zone_rows(fit_counts=fit, a_z=a_z, ur6=ur6, ca_itl3=ca_itl3)
    return assign_merge_cells(zones)


# Production pins for the merge-map run that produced sha256 581b0aa1…5947.
# Paths are host/repo-relative as used on the build VM; sha256 is of file bytes.
PRODUCTION_INPUT_PINS: dict[str, dict[str, object]] = {
    "counts": {
        "path": "data/processed/methods_code_1/pr1/ros_dz2011_sales_n_2019_2023.csv",
        "sha256": "37fe46da5e647b29a966bd70713de21ae8514b95dfbe1e95b43a62e060eeeb50",
        "columns": ["code", "year", "sales_n", "suppressed"],
        "note": (
            "Count columns only (no price/mean/median). Extract from RoS "
            "house_sales.csv sha256 702c9ada0b26dad9904e97f00ea7aa3357e1bf449e724e83292b5265f0549cf2."
        ),
    },
    "ur": {
        "path": "scotland-rules/ur6/dz2011_urban_rural_6fold_2020.csv",
        "sha256": "1f32a81532912334e3cd071e2f12f523e66068d14c73e5db4ae51add239b1a92",
        "vintage": "DZ2011 URC 2020",
        "note": (
            "Pinned in v14_prereg_freeze.json inputs.ur6_dz2011 (DRAFT_NOT_FROZEN). "
            "SG Urban Rural Classification 2020 for DZ2011."
        ),
    },
    "plot_split": {
        "path": "omm-inputs/dz2022_plot_split_v13.csv (Project store)",
        "sha256": "09e2082d801b15203794974aea802cc7e5c5c403761365b69bd4b695d7a0638c",
    },
    "uprn_weights": {
        "path": "omm-inputs/dz2011_dz2022_uprn_weights.csv (Project store)",
        "sha256": "7690bcbebf9968ca9b02cf898832aa9be8fca56f3eb9af70b20e25b5d23e13e4",
    },
    "spd": {
        "path": "data/external/raw/spd_postcodeindex_cut_26_2_csv.zip",
        "sha256": "4e93069ddb9c39c211cafdc56eeb16c4b0ed4872c9a95c20e23ec73c3b499057",
    },
    "merge_map": {
        "sha256": "581b0aa1647c5af7ce5b9617e35fcfa73982bc8712a42eb63242243ee6a95947",
        "zones": 6188,
    },
}
