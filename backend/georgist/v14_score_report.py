"""v1.4 run report, holdout lock, and the code/text disagreement table.

The 2023 holdout is labelled seen, not out-of-sample. Nothing in this module
reads a 2023 outcome back into a setting.
"""

from __future__ import annotations

import ast
import hashlib
import json
import math
import os
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

import scipy
import statsmodels

from georgist import surface_rent as sr
from georgist import surface_v14 as v14
from georgist import surface_v14_checks as checks
from georgist.surface_paths import REPO_ROOT
from georgist.v14_hedonic import (
    BOOTSTRAP_SEED,
    FIDELITY_LIMITATION,
    MEDIAN_2024_REASON,
    S_C3_GTOL,
    S_C3_MAXITER,
    S_C3_METHOD,
    S_G1_REASON,
    SENSITIVITY_IDS,
    land_share_for_zone,
    sensitivity_manifest,
)
from georgist.v14_primary_inputs import DepreciationMethodError, remaining_factor_at_age, v14_depreciation

EXPECTED_SHA8 = {
    "backend/georgist/surface_rent.py": "dc07f4fe",
    "backend/georgist/surface_v14.py": "4f7a407a",
    "data/config/surface.yaml": "0ad64260",
    "backend/georgist/ros_c14_input.py": "ca8718fa",
}
RECORDED_FILES = (
    "backend/scripts/rerun_v14_score.py",
    "backend/georgist/ros_c14_prices.py",
    "backend/georgist/v14_primary_inputs.py",
    "backend/georgist/v14_hedonic.py",
    "backend/georgist/surface_v14_checks.py",
    "backend/georgist/v14_score_report.py",
    "backend/scripts/build_v14_drc.py",
    "backend/scripts/build_v14_hedonic_rows.py",
    "backend/scripts/build_v14_check_inputs.py",
    "backend/scripts/build_v14_primary_inputs.py",
    "backend/scripts/build_ros_c14_v14_inputs.py",
    "backend/scripts/build_v14_drc_components.py",
    "backend/scripts/fit_v14_hedonic.py",
    "backend/scripts/build_v14_primary_2023.py",
    "backend/scripts/build_v14_check_sources.py",
    "backend/georgist/v14_check4_route.py",
)
# PR 3 writers are recorded once they exist. They are not hashed while absent.
# PR 3b records the fit CLI and the check-source writer on every run.
PR3_RECORDED_WHEN_PRESENT = frozenset()
S_C3_OPTIMIZER = {
    "method": S_C3_METHOD,
    "pgtol": S_C3_GTOL,
    "factr": "default",
    "maxiter": S_C3_MAXITER,
}
S_C3_GTOL_MAPPING = "gtol=1e-8 maps to L-BFGS-B pgtol=1e-8"
INPUT_SHA256_PREFIXES = {
    "workbook": "194fa678",
    "exclusion_list": "13a870fe",
    "lookup": "3c1779cc",
    "crosswalk": "7690bcbe",
    "merge_map": "581b0aa1",
    "frozen_plan": "e1ab6d0a",
    "house_sales": "702c9ada",
    "plot_split_readme": "0f1fc011",
    "epc_rollup": "13a5f647",
}
MERGE_MAP_SHA256 = "581b0aa1647c5af7ce5b9617e35fcfa73982bc8712a42eb63242243ee6a95947"
# Test-only hook. The driver replaces merge_map for a synthetic frozen set.
PIN_TABLE = {"merge_map": MERGE_MAP_SHA256}
FROZEN_SET_KEYS = (
    "merge_map",
    "hedonic_coefs_2021_22",
    "code_sha8_block",
    "b6_pins",
)
B6_PIN_KEYS = (
    "check3_plot_passes",
    "check4_rent_route",
    "ur6",
    "dz2022_keys",
)
YEAR_FILE_KEYS = (
    "builder_output",
    "primary_estimates",
    "fitted_per_zone",
)
HOLDOUT_LABEL = "seen, not out-of-sample"
DISCLOSURES = {
    "vintage": "decided from codes",
    "registration_dates": "recorded",
    "collision_absent_zones": "under the existing suppressed treatment",
    "scored_zones": 5489,
    "lost_to_ordinary_suppression": 590,
}


class ReportAbort(RuntimeError):
    """The run stops and does not write a report."""


class HoldoutLockError(RuntimeError):
    """The 2023 holdout was already run, or 2024 was requested with no lock."""


class MergeMapError(RuntimeError):
    """The pinned merge map sha256 does not match."""


PRICE_READ_STAGES = (
    "primary_inputs",
    "hedonic_fit",
    "holdout_2023",
    "score_2024",
)
ROW_IDS = (
    "G1",
    "G2",
    "V1",
    "V2",
    "V3",
    "V4",
    "V5",
    "V6",
    "V7",
    "V8",
    "V9",
    "V10",
    "V11",
    "V12",
    "V13",
    "V14",
    "V15",
    "V16",
)


class PriceColumnReadLog:
    """Flags set by reader functions. A stage stays false until its reader returns."""

    def __init__(self) -> None:
        self._flags = {stage: False for stage in PRICE_READ_STAGES}

    def mark(self, stage: str) -> None:
        if stage not in self._flags:
            raise KeyError(stage)
        self._flags[stage] = True

    def snapshot(self) -> dict[str, bool]:
        return dict(self._flags)


def apply_price_reader(log: PriceColumnReadLog, stage: str, reader):
    """Call ``reader`` and record ``stage`` only after it returns."""
    result = reader()
    log.mark(stage)
    return result


def git_commit() -> str:
    return _git_commit()


def require_commit_sha(commit: str) -> str:
    """Refuse a missing commit and the placeholder ``pending``."""
    text = str(commit or "").strip()
    if not text or text == "pending":
        raise ReportAbort("prepare step refuses a pending or empty commit")
    return text


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha8_file(path: Path) -> str:
    return sha256_file(path)[:8]


def assert_expected_sha8(expected: Mapping[str, str] | None = None, root: Path | None = None) -> dict[str, str]:
    """Abort when a pinned file's sha8 differs. Returns the sha8s that matched."""
    root = root or REPO_ROOT
    pins = dict(EXPECTED_SHA8 if expected is None else expected)
    found: dict[str, str] = {}
    for rel, want in pins.items():
        path = root / rel
        got = sha8_file(path)
        if got != want:
            raise ReportAbort(f"{rel} sha8 {got} != {want}")
        found[rel] = got
    return found


def assert_merge_map(path: Path, expected: str | None = None) -> str:
    want = PIN_TABLE["merge_map"] if expected is None else expected
    got = sha256_file(path)
    if got != want:
        raise MergeMapError(f"merge map sha256 {got} != {want}")
    return got


def b6_pins_sha256(paths: Mapping[str, Path]) -> str:
    """One digest over the four year-invariant B6 sources, in pin order."""
    digest = hashlib.sha256()
    for name in B6_PIN_KEYS:
        digest.update(name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(Path(paths[name]).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def frozen_set_members(paths: Mapping[str, Path]) -> dict[str, str]:
    """Year-invariant frozen set. Year files are not members."""
    return {
        "merge_map": sha256_file(Path(paths["merge_map"])),
        "hedonic_coefs_2021_22": sha256_file(Path(paths["hedonic_coefs_2021_22"])),
        "code_sha8_block": sha256_file(Path(paths["code_sha8_block"])),
        "b6_pins": b6_pins_sha256(paths),
    }


def frozen_set_lock_hash(members: Mapping[str, str]) -> str:
    payload = json.dumps({key: members[key] for key in FROZEN_SET_KEYS}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def frozen_set_refusal(key: str, expected: str, actual: str) -> str:
    return f"SCORE_2024: REFUSED: frozen_set {key} sha256: expected {expected}, got {actual}"


def missing_lock_message(path: Path) -> str:
    return f"SCORE_2024: REFUSED: lock: expected {path}, got absent"


def read_price_cell(value: str) -> str:
    """Price-cell hook for the 2024 year screen. A non-2024 year never calls it."""
    return value


def _csv_field(line: str, index: int) -> str:
    """One CSV field. Reading stops at the end of that field."""
    field_index = 0
    buf: list[str] = []
    for char in line:
        if char == ",":
            if field_index == index:
                return "".join(buf)
            field_index += 1
            buf = []
            continue
        if field_index == index:
            buf.append(char)
        elif field_index > index:
            return "".join(buf)
    return "".join(buf) if field_index == index else ""


def read_year_files(paths: Sequence[Path]) -> list[int]:
    """Years from synthetic year files. Price cells are read only when every year is 2024."""
    parsed: list[tuple[list[str], int | None, list[int]]] = []
    years: list[int] = []
    for path in paths:
        text = Path(path).read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
        if not lines:
            continue
        header = lines[0].split(",")
        if "year" not in header:
            raise HoldoutLockError("SCORE_2024: REFUSED: input_years: expected [2024], got []")
        year_index = header.index("year")
        price_index = header.index("price") if "price" in header else None
        file_years: list[int] = []
        for line in lines[1:]:
            raw = _csv_field(line, year_index).strip()
            if not raw.isdigit():
                got = raw or "blank"
                raise HoldoutLockError(f"SCORE_2024: REFUSED: input_year: expected 2024, got {got}")
            year = int(raw)
            file_years.append(year)
            years.append(year)
        parsed.append((lines[1:], price_index, file_years))
    if years and all(year == 2024 for year in years):
        for lines, price_index, _file_years in parsed:
            if price_index is None:
                continue
            for line in lines:
                read_price_cell(_csv_field(line, price_index))
    return years


def assert_score_years(years: Sequence[int]) -> None:
    """Score-2024 accepts input_years of exactly [2024]."""
    unique = sorted(set(int(year) for year in years))
    if unique == [2023]:
        raise HoldoutLockError("SCORE_2024: REFUSED: input_year: expected 2024, got 2023")
    if unique != [2024]:
        rendered = "[" + ", ".join(str(year) for year in unique) + "]"
        raise HoldoutLockError(f"SCORE_2024: REFUSED: input_years: expected [2024], got {rendered}")


def assert_frozen_set(locked: Mapping[str, str], current: Mapping[str, str]) -> None:
    for key in FROZEN_SET_KEYS:
        if current[key] != locked[key]:
            raise HoldoutLockError(frozen_set_refusal(key, locked[key], current[key]))


def _line_number(rel: str, needle: str) -> int:
    lines = (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        if needle in line:
            return number
    raise ReportAbort(f"{needle!r} is not in {rel}")


def _source(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def _calls_in_order(rel: str, function: str) -> list[str]:
    tree = ast.parse(_source(rel))
    target = None
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function:
            target = node
            break
    if target is None:
        return []
    names: list[str] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.append(func.id)
            elif isinstance(func, ast.Attribute):
                names.append(func.attr)
        for child in ast.iter_child_nodes(node):
            visit(child)

    visit(target)
    return names


def _status_g1() -> str:
    scored = v14.score_estimators(primary_shares=[0.2], secondary_shares=[0.2])
    gating = ("1", "1a", "1b", "1d", "3", "4", "6")
    information = ("1c", "1e", "2", "3-all", "3-dz22", "5", "7", "agreement", "gis_plot_median_ratio")
    for block in (scored["primary"], scored["secondary"]):
        for name in gating:
            if name not in block["gating"]:
                return "pending"
        for name in information:
            if name not in block["information"]:
                return "pending"
        if block["gating"]["1a"].get("status") != "pending":
            return "pending"
    return "fixed"


def _status_g2() -> str:
    outcomes = [
        v14.apply_no_switch_publication(primary_gating_pass=left, secondary_gating_pass=right)["outcome"]
        for left, right in ((True, True), (True, False), (False, True), (False, False))
    ]
    expected = [
        "publish_range_both",
        "publish_primary_only",
        "primary_fail_secondary_pass_publish_neither_until_v15",
        "both_fail_publish_neither",
    ]
    if outcomes == expected and len(set(outcomes)) == 4:
        return "fixed"
    return "pending"


def _status_v1() -> str:
    fit = {
        "beta_by_cell": {"c": 0.25},
        "model_failure_by_cell": {"c": False},
        "informative_by_cell": {"c": True},
        "coefficient_names": ["alpha[c]", "beta[c]"],
        "coefficients": [math.log(80.0), 0.25],
    }
    row = {"zone": "Z1", "cell": "c", "price": 10.0, "a_m2": math.e, "year": 2021}
    share = land_share_for_zone(fit, row)
    observed = 0.25 * float(row["price"])
    if share["land_per_home"] != observed and share["fitted_price"] != float(row["price"]):
        return "fixed"
    return "pending"


def _status_v2() -> str:
    zones = [
        {"zone": "Z1", "share": 0.0, "count_in_1d": False, "ur6": 1, "price": 1.0, "land_per_home": 0.0},
        {"zone": "Z2", "share": 0.2, "count_in_1d": True, "ur6": 1, "price": 2.0, "land_per_home": 1.0},
    ]
    # The other checks need a fuller zone. Probe the 1d helper directly.
    result = checks._check_1d(zones)
    if result["n"] == 2 and result["n_at_0"] == 0 and result["numerator_n"] == 1:
        return "fixed"
    return "pending"


def _status_v3() -> str:
    text = _source("backend/georgist/v14_hedonic.py")
    if "Fidelity limitation:" in text and "only β̂ ≤0 is applied" in text:
        return "limitation_disclosed"
    return "pending"


def _status_v4() -> str:
    tied = checks.check_1a(
        [
            {"zone": "A", "ur6": 1, "land_per_home": 3.0},
            {"zone": "B", "ur6": 2, "land_per_home": 3.0},
        ]
    )
    return "fixed" if tied.get("pass") is False else "pending"


def _status_v5() -> str:
    try:
        checks.check_6_zone_range([{"zone": "S01000001", "share_low": 0.1, "share_central": 0.2, "share_high": 0.3}])
    except ValueError:
        return "fixed"
    return "pending"


def _status_v6() -> str:
    primary = [{"zone": "A", "ur6": 1, "share": 0.2}, {"zone": "B", "ur6": 2, "share": 0.3}]
    result = checks.agreement(primary, primary)
    keys = set(result.get("by_ur6") or {})
    if keys == {str(klass) for klass in range(1, 7)} and "national" in result:
        return "fixed"
    return "pending"


def _status_v7() -> str:
    zones = [
        {"zone": "A", "ur6": 1, "detached_plot_m2": 40.0, "house_plot_m2": 10.0},
        {"zone": "B", "ur6": 1, "detached_plot_m2": 40.0, "house_plot_m2": 20.0},
        {"zone": "C", "ur6": 1, "detached_plot_m2": 40.0, "house_plot_m2": 90.0},
    ]
    ratios = checks.gis_plot_median_ratio(zones)["ratio_by_ur6"]["1"]
    pooled = ratios["ratio_pooled_denominator"]
    zone_median = ratios["ratio_zone_median_denominator"]
    if pooled is not None and zone_median is not None and pooled != zone_median:
        return "fixed"
    return "pending"


def _status_v8() -> str:
    if checks.HBU_NOT_RUN.startswith("NOT_RUN:") and checks.hbu_line([{"zone": "A", "hla": True}])[0]["gates"] is False:
        return "NOT_RUN"
    return "pending"


def _status_v9() -> str:
    manifest = sensitivity_manifest()
    ids = [item["id"] for item in manifest]
    if ids != list(SENSITIVITY_IDS):
        return "pending"
    allowed = {"fit", "NOT_RUN"}
    if any(item["status"] not in allowed or item["gates"] or item["swapped_in"] for item in manifest):
        return "pending"
    declared = {item["id"]: item for item in manifest}
    if declared["S-g1"]["status"] != "NOT_RUN" or declared["S-g1"]["reason"] != S_G1_REASON:
        return "pending"
    text = _source("backend/georgist/v14_hedonic.py")
    if "MixedLM" not in text or 'method=S_C3_METHOD' not in text:
        return "pending"
    if "S_C3_METHOD = \"lbfgs\"" not in text or "S_C3_MAXITER = 1000" not in text or "S_C3_GTOL = 1e-8" not in text:
        return "pending"
    if "S_C3_REML = True" not in text:
        return "pending"
    return "fixed"


def _status_v10() -> str:
    rel = "backend/scripts/rerun_v14_score.py"
    names = _calls_in_order(rel, "_extended_main")
    if "write_report" not in names or "write_holdout_lock" not in names:
        return "pending"
    if names.index("write_report") > names.index("write_holdout_lock"):
        return "pending"
    if "_score_holdout" not in names:
        return "pending"
    return "fixed"


def _status_v11() -> str:
    try:
        require_commit_sha("pending")
    except ReportAbort:
        if 'commit="pending"' not in _source("backend/scripts/rerun_v14_score.py"):
            return "fixed"
    return "pending"


def _status_v12() -> str:
    text = _source("backend/scripts/rerun_v14_score.py")
    if '"primary_inputs": False' in text or "'primary_inputs': False" in text:
        return "pending"
    log = PriceColumnReadLog()
    if log.snapshot()["hedonic_fit"] is not False:
        return "pending"
    apply_price_reader(log, "hedonic_fit", lambda: None)
    if log.snapshot()["hedonic_fit"] is True and log.snapshot()["primary_inputs"] is False:
        return "fixed"
    return "pending"


def _status_v13() -> str:
    path = REPO_ROOT / "backend/scripts/build_v14_check_inputs.py"
    if not path.is_file():
        return "pending"
    text = path.read_text(encoding="utf-8")
    if "def build_v14_check_inputs" not in text or "primary_zones" not in text or "secondary_zones" not in text:
        return "pending"
    if "inputs without a pinned sha" not in text or "field not in the frozen text" not in text:
        return "pending"
    return "fixed"


def _status_v14() -> str:
    path = REPO_ROOT / "backend/scripts/build_v14_hedonic_rows.py"
    if not path.is_file():
        return "pending"
    text = path.read_text(encoding="utf-8")
    if "def build_v14_hedonic_rows" not in text or "702c9ada" not in text:
        return "pending"
    if "year >= 2024 refused" not in text or "COLUMN_MAP" not in text:
        return "pending"
    return "fixed"


def _status_v15() -> str:
    path = REPO_ROOT / "backend/scripts/build_v14_drc.py"
    if not path.is_file():
        return "pending"
    text = path.read_text(encoding="utf-8")
    if "zone_drc_v14" not in text or "straight_line_v14" not in text:
        return "pending"
    try:
        remaining_factor_at_age(0, {"method": "compounding_v13"})
    except DepreciationMethodError:
        factors = v14_depreciation()
        age0 = remaining_factor_at_age(0, factors)
        age20 = remaining_factor_at_age(20, factors)
        age68 = remaining_factor_at_age(68, factors)
        age100 = remaining_factor_at_age(100, factors)
        if (
            age0 == 1.0
            and f"{age20:.3f}" == "0.930"
            and f"{age68:.3f}" == "0.762"
            and f"{age100:.3f}" == "0.762"
        ):
            return "fixed"
    return "pending"


def _status_v16() -> str:
    text = _source("backend/scripts/build_v14_primary_inputs.py")
    if "--exclusion-list" not in text or "EXCLUSION_LIST_SHA256" not in text:
        return "pending"
    return "fixed"


_STATUS = {
    "G1": _status_g1,
    "G2": _status_g2,
    "V1": _status_v1,
    "V2": _status_v2,
    "V3": _status_v3,
    "V4": _status_v4,
    "V5": _status_v5,
    "V6": _status_v6,
    "V7": _status_v7,
    "V8": _status_v8,
    "V9": _status_v9,
    "V10": _status_v10,
    "V11": _status_v11,
    "V12": _status_v12,
    "V13": _status_v13,
    "V14": _status_v14,
    "V15": _status_v15,
    "V16": _status_v16,
}

_ROW_TEXT = {
    "G1": (
        "backend/georgist/surface_v14.py",
        "def score_estimators",
        "score_estimators reports every gating and information check for both estimators",
        "Every gating check (1, 1a, 1b, 1d, 3, 4, 6) and every information check is reported for both estimators.",
    ),
    "G2": (
        "backend/georgist/surface_v14.py",
        "primary_fail_secondary_pass_publish_neither_until_v15",
        "primary-fail and both-fail use distinct outcome strings",
        "Primary fails + secondary passes → publish neither. Both fail → publish neither.",
    ),
    "V1": (
        "backend/georgist/v14_hedonic.py",
        "def fitted_price",
        "land per home uses the fitted headline price",
        "L̂_z = β̂_c × fitted P̂_z from the headline log model.",
    ),
    "V2": (
        "backend/georgist/surface_v14_checks.py",
        "def _check_1d",
        "check 1d denominator is every scoring zone",
        "Uninformative cells are reported and left out of the numerator.",
    ),
    "V3": (
        "backend/georgist/v14_hedonic.py",
        "FIDELITY_LIMITATION",
        "only β̂ ≤0 is applied",
        "β̂ ≤0 or negative location premium is a model-failure flag.",
    ),
    "V4": (
        "backend/georgist/surface_v14_checks.py",
        "def check_1a",
        "check 1a uses a strict greater-than",
        "Class 1 has the highest median land per home. A tie fails.",
    ),
    "V5": (
        "backend/georgist/surface_v14_checks.py",
        "def check_6_zone_range",
        "check 6 keys on dz2022 only",
        "A row lacking dz2022 raises. There is no DZ2011 fallback.",
    ),
    "V6": (
        "backend/georgist/surface_v14_checks.py",
        "def agreement",
        "agreement is national and by UR6",
        "Spearman, median difference and Bland-Altman, nationally and by UR6.",
    ),
    "V7": (
        "backend/georgist/surface_v14_checks.py",
        "def gis_plot_median_ratio",
        "GIS ratios use pooled and zone-median denominators",
        "Report both the pooled and the zone-median denominators.",
    ),
    "V8": (
        "backend/georgist/surface_v14_checks.py",
        "HBU_NOT_RUN",
        "HBU line is separate and does not gate",
        "HLA zones only, separate line, never in checks 1–7.",
    ),
    "V9": (
        "backend/georgist/v14_hedonic.py",
        "def sensitivity_table",
        "every listed sensitivity is fit or NOT_RUN and none gates",
        "Every listed sensitivity is computed, information only.",
    ),
    "V10": (
        "backend/scripts/rerun_v14_score.py",
        "def _extended_main",
        "holdout scores both estimators and writes the lock last",
        "Estimate and score both estimators and every check, then write the lock last, only on success.",
    ),
    "V11": (
        "backend/scripts/rerun_v14_score.py",
        "def _extended_main",
        "prepare records a real commit sha",
        "A pending or empty commit is refused.",
    ),
    "V12": (
        "backend/scripts/rerun_v14_score.py",
        "PriceColumnReadLog",
        "price-column flags come from the readers",
        "price_columns_read is set by the reader functions.",
    ),
    "V13": (
        "backend/scripts/build_v14_check_inputs.py",
        "build_v14_check_inputs",
        "check-input builder writes primary_zones and secondary_zones",
        "Build primary_zones and secondary_zones for --check-inputs.",
    ),
    "V14": (
        "backend/scripts/build_v14_hedonic_rows.py",
        "build_v14_hedonic_rows",
        "hedonic-row builder asserts the pinned shas and refuses year >= 2024",
        "Build hedonic rows and refuse any year at or after 2024.",
    ),
    "V15": (
        "backend/scripts/build_v14_drc.py",
        "straight_line_v14",
        "DRC writer asserts straight_line_v14",
        "Write depreciated replacement cost per DZ2011. No prices.",
    ),
    "V16": (
        "backend/scripts/build_v14_primary_inputs.py",
        "--exclusion-list",
        "exclusion list is required and its sha256 is asserted",
        "Pass the pinned exclusion list through to build_inputs.",
    ),
}


def predeclared_not_run() -> list[dict[str, str]]:
    """HBU and the sensitivities declared NOT_RUN before the 2023 run."""
    return [
        {
            "id": "HBU",
            "status": "NOT_RUN",
            "reason": checks.HBU_NOT_RUN,
        },
        {
            "id": "S-g1",
            "status": "NOT_RUN",
            "reason": S_G1_REASON,
        },
        {
            "id": "median_price_2024",
            "status": "NOT_RUN",
            "reason": MEDIAN_2024_REASON,
        },
    ]


def code_text_disagreements() -> list[dict[str, str]]:
    """One row per frozen-text gap. Status comes from the checks, not a fixed ruling list."""
    rows: list[dict[str, str]] = []
    for row_id in ROW_IDS:
        rel, needle, code, frozen = _ROW_TEXT[row_id]
        try:
            line = str(_line_number(rel, needle))
        except (ReportAbort, OSError):
            line = "0"
        status = _STATUS[row_id]()
        rows.append(
            {
                "id": row_id,
                "file": rel,
                "line": line,
                "code": code,
                "frozen_text": frozen,
                "ruling": status,
                "status": status,
            }
        )
    return rows


def disagreement_markdown(rows: Sequence[Mapping[str, str]] | None = None) -> str:
    items = list(code_text_disagreements() if rows is None else rows)
    lines = [
        "# Code and frozen text disagreements",
        "",
        "| file:line | code | frozen text | ruling |",
        "|---|---|---|---|",
    ]
    for row in items:
        lines.append(
            f"| {row['file']}:{row['line']} | {row['code']} | {row['frozen_text']} | {row['ruling']} |"
        )
    lines.append("")
    lines.append("## Pre-declared")
    lines.append("")
    for item in predeclared_not_run():
        status = item["status"]
        reason = item["reason"]
        if reason.startswith(f"{status}:"):
            lines.append(f"- {item['id']}: {reason}")
        else:
            lines.append(f"- {item['id']}: {status}: {reason}")
    lines.append("")
    return "\n".join(lines)


def write_disagreement_table(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(disagreement_markdown(), encoding="utf-8")
    return path


def holdout_lock_path(score_dir: Path, lock_path: Path | None = None) -> Path:
    if lock_path is not None:
        return Path(lock_path)
    return score_dir / "holdout_2023.lock"


def prepare_holdout_2023(
    score_dir: Path,
    *,
    inputs_sha256: str,
    commit: str,
    allow_incident: str | None = None,
    lock_path: Path | None = None,
) -> dict:
    """Write the disagreement table, then refuse a second run.

    Scoring is the caller's next step. This function does not take a 2023
    outcome and does not change a setting. ``commit`` must be the real sha.
    """
    commit = require_commit_sha(commit)
    table = write_disagreement_table(score_dir / "code_text_disagreements.md")
    lock = holdout_lock_path(score_dir, lock_path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.is_file() and not allow_incident:
        raise HoldoutLockError(
            f"HOLDOUT_2023: REFUSED: lock: expected absent, got {lock}"
        )
    if lock.is_file() and allow_incident:
        with (score_dir / "fidelity_bug.log").open("a", encoding="utf-8") as handle:
            handle.write(f"allow-rerun-for-fidelity-bug {allow_incident}\n")
    return {
        "label": HOLDOUT_LABEL,
        "disagreement_table": str(table),
        "inputs_sha256": inputs_sha256,
        "commit": commit,
        "allow_incident": allow_incident,
    }


def write_holdout_lock(
    score_dir: Path,
    *,
    inputs_sha256: str,
    commit: str,
    report_sha256: str | None = None,
    lock_path: Path | None = None,
    frozen_set: Mapping[str, str] | None = None,
) -> Path:
    path = holdout_lock_path(score_dir, lock_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "inputs_sha256": inputs_sha256,
        "commit": require_commit_sha(commit),
        "label": HOLDOUT_LABEL,
    }
    if frozen_set is not None:
        members = {key: frozen_set[key] for key in FROZEN_SET_KEYS}
        payload["frozen_set"] = members
        payload["frozen_set_sha256"] = frozen_set_lock_hash(members)
    if report_sha256:
        payload["report_sha256"] = report_sha256
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def assert_2024_allowed(
    score_dir: Path | None = None,
    *,
    lock_path: Path | None = None,
    inputs_sha256: str | None = None,
    years: Sequence[int] | None = None,
) -> None:
    """The 2024 entry point is score-once and refuses a bad lock or year."""
    if score_dir is None and lock_path is None:
        raise HoldoutLockError(missing_lock_message(Path("holdout_2023.lock")))
    path = holdout_lock_path(score_dir or Path("."), lock_path)
    if not path.is_file():
        raise HoldoutLockError(missing_lock_message(path))
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("score_2024") is True:
        raise HoldoutLockError("second 2024 run refused")
    if inputs_sha256 is not None and payload.get("inputs_sha256") != inputs_sha256:
        raise HoldoutLockError("2024 run refused: inputs sha differs")
    if years is not None and (not years or any(int(year) != 2024 for year in years)):
        raise HoldoutLockError("2024 run refused: input year is not 2024")


def mark_score_2024(lock_path: Path) -> None:
    """Record that the 2024 entry point has been entered. The write is atomic."""
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["score_2024"] = True
    temporary = lock_path.with_name(f".{lock_path.name}.tmp")
    try:
        temporary.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(temporary, lock_path)
    finally:
        if temporary.exists():
            temporary.unlink()


def input_years(path: Path) -> list[int]:
    """Year fields only. A missing or non-2024 year refuses before scoring."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    years: list[int] = []
    found = False
    for key in ("primary_zones", "secondary_zones"):
        for row in payload.get(key) or []:
            found = True
            if not isinstance(row, dict) or "year" not in row:
                raise HoldoutLockError("2024 run refused: input year is not 2024")
            value = row["year"]
            if value is None or (isinstance(value, str) and not value.strip()):
                raise HoldoutLockError("2024 run refused: input year is not 2024")
            if isinstance(value, bool) or isinstance(value, float):
                raise HoldoutLockError("2024 run refused: input year is not 2024")
            if isinstance(value, str):
                text = value.strip()
                if not text.isdigit():
                    raise HoldoutLockError("2024 run refused: input year is not 2024")
                value = int(text)
            elif not isinstance(value, int):
                raise HoldoutLockError("2024 run refused: input year is not 2024")
            years.append(int(value))
    if not found:
        raise HoldoutLockError("2024 run refused: input year is not 2024")
    return years


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReportAbort("main commit is missing") from exc
    commit = result.stdout.strip()
    if not commit:
        raise ReportAbort("main commit is missing")
    return commit


def _input_pins(paths: Mapping[str, Path] | None) -> dict[str, dict]:
    pins: dict[str, dict] = {}
    names = list(INPUT_SHA256_PREFIXES)
    if paths:
        for name in paths:
            if name not in names:
                names.append(name)
    for name in names:
        prefix = INPUT_SHA256_PREFIXES.get(name)
        path = None if not paths else paths.get(name)
        if path is None or not Path(path).is_file():
            item: dict = {"present": False, "sha256": None}
            if prefix is not None:
                item["expected_prefix"] = prefix
            pins[name] = item
            continue
        digest = sha256_file(Path(path))
        if prefix is not None and not digest.startswith(prefix):
            raise ReportAbort(f"{name} sha256 {digest} does not start with {prefix}")
        item = {"present": True, "sha256": digest}
        if prefix is not None:
            item["expected_prefix"] = prefix
        pins[name] = item
    return pins


def _pins_from_check_inputs(path: Path) -> dict[str, dict]:
    """B6 pins carried in the check-input file."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload.get("pins")
    if not isinstance(raw, dict):
        return {}
    return {str(name): {"present": True, "sha256": str(digest)} for name, digest in raw.items()}


def secondary_estimator_fields(path: Path) -> dict:
    """Sha, sensitivity table and S-c3 convergence from the secondary JSON."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    table = payload.get("sensitivities")
    if table is None:
        table = payload.get("sensitivity_table") or []
    converged = payload.get("s_c3_converged")
    if converged is None and isinstance(table, list):
        for item in table:
            if isinstance(item, dict) and item.get("id") == "S-c3":
                converged = item.get("converged")
                break
    return {
        "sha256": sha256_file(path),
        "sensitivity_table": table,
        "s_c3_converged": converged,
    }


def _record_sha8(root: Path) -> dict[str, str]:
    sha8 = assert_expected_sha8(root=root)
    for rel in RECORDED_FILES:
        path = root / rel
        if not path.is_file():
            if rel in PR3_RECORDED_WHEN_PRESENT:
                continue
            raise ReportAbort(f"recorded file missing: {rel}")
        sha8[rel] = sha8_file(path)
    return sha8


def build_report(
    *,
    root: Path | None = None,
    input_paths: Mapping[str, Path] | None = None,
    status_counts: Mapping[str, int] | None = None,
    price_columns_read: Mapping[str, bool] | None = None,
    disagreement_rows: Sequence[Mapping[str, str]] | None = None,
    commit: str | None = None,
    secondary_estimator: Mapping | None = None,
) -> dict:
    """Assemble the run report. Missing method or sha8, or a bad sha8, aborts."""
    root = root or REPO_ROOT
    cfg = sr.load_config()
    method = str((cfg.get("v14") or {}).get("depreciation", {}).get("method") or "")
    if method != "straight_line_v14":
        raise ReportAbort(f"depreciation.method must be straight_line_v14, got {method!r}")
    sha8 = _record_sha8(root)
    if not sha8 or "backend/georgist/surface_rent.py" not in sha8:
        raise ReportAbort("report is missing sha8")
    rows = list(code_text_disagreements() if disagreement_rows is None else disagreement_rows)
    recorded = _input_pins(input_paths)
    check_path = None if not input_paths else input_paths.get("check_inputs")
    if check_path is not None and Path(check_path).is_file():
        for name, item in _pins_from_check_inputs(Path(check_path)).items():
            recorded.setdefault(name, item)
    secondary = dict(secondary_estimator or {})
    report = {
        "depreciation": {"method": method},
        "sha8": sha8,
        "input_paths": {
            name: {"sha256": item.get("sha256"), "present": bool(item.get("present"))}
            for name, item in recorded.items()
        },
        "commit": commit or _git_commit(),
        "input_sha256": recorded,
        "seed": BOOTSTRAP_SEED,
        "s_c3_statsmodels_version": statsmodels.__version__,
        "s_c3_optimizer": dict(S_C3_OPTIMIZER),
        "s_c3_gtol_mapping": S_C3_GTOL_MAPPING,
        "scipy_version": scipy.__version__,
        "secondary_estimator_sha256": secondary.get("sha256"),
        "sensitivity_table": secondary.get("sensitivity_table"),
        "s_c3_converged": secondary.get("s_c3_converged"),
        "fidelity_limitation": FIDELITY_LIMITATION,
        "status_counts": dict(status_counts or {}),
        "price_columns_read": dict(price_columns_read or {stage: False for stage in PRICE_READ_STAGES}),
        "disclosures": dict(DISCLOSURES),
        "code_text_disagreements": rows,
        "holdout_label": HOLDOUT_LABEL,
        "gbp_display": False,
    }
    if report["depreciation"].get("method") != "straight_line_v14" or not report["sha8"]:
        raise ReportAbort("report is missing method or sha8")
    return report


def write_report(path: Path, report: Mapping) -> None:
    """Write the report. A missing method or an empty sha8 block leaves no file.

    ``--record-sha8s`` absent means the sha8 block is omitted. An empty
    sha8 block still aborts.
    """
    method = str((report.get("depreciation") or {}).get("method") or "")
    if method != "straight_line_v14":
        raise ReportAbort("report is missing method or sha8")
    if "sha8" in report and not report.get("sha8"):
        raise ReportAbort("report is missing method or sha8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
