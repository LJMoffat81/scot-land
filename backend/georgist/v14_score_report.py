"""v1.4 run report, holdout lock, and the code/text disagreement table.

The 2023 holdout is labelled seen, not out-of-sample. Nothing in this module
reads a 2023 outcome back into a setting.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Mapping, Sequence

from georgist import surface_rent as sr
from georgist.surface_paths import REPO_ROOT
from georgist.v14_hedonic import BOOTSTRAP_SEED

EXPECTED_SHA8 = {
    "backend/georgist/surface_rent.py": "dc07f4fe",
    "backend/georgist/surface_v14.py": "a81d627c",
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
)
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


def assert_merge_map(path: Path, expected: str = MERGE_MAP_SHA256) -> str:
    got = sha256_file(path)
    if got != expected:
        raise MergeMapError(f"merge map sha256 {got} != {expected}")
    return got


def _line_number(rel: str, needle: str) -> int:
    lines = (REPO_ROOT / rel).read_text(encoding="utf-8").splitlines()
    for number, line in enumerate(lines, start=1):
        if needle in line:
            return number
    raise ReportAbort(f"{needle!r} is not in {rel}")


def code_text_disagreements() -> list[dict[str, str]]:
    """Places the protected scorer does not match the frozen text.

    New modules follow the frozen text. These rows are the remaining gaps.
    Rulings stay pending until the Statistician rules, outcome-blind.
    """
    scorer = "backend/georgist/surface_v14.py"
    return [
        {
            "file": scorer,
            "line": str(_line_number(scorer, '"check_1d": c1d')),
            "code": "score_estimators records check_1, check_1d and check_1e",
            "frozen_text": (
                "Every gating check (1, 1a, 1b, 1d, 3, 4, 6) and every information "
                "check is reported for both estimators in one table, whatever the outcome."
            ),
            "ruling": "pending",
        },
        {
            "file": scorer,
            "line": str(_line_number(scorer, 'outcome = "publish_neither_report_both"')),
            "code": "primary fail with secondary pass uses the same outcome string as both fail",
            "frozen_text": (
                "Primary fails + secondary passes → report both; publish neither as official. "
                "Both fail → publish neither; report both."
            ),
            "ruling": "pending",
        },
    ]


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
    return "\n".join(lines)


def write_disagreement_table(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(disagreement_markdown(), encoding="utf-8")
    return path


def holdout_lock_path(score_dir: Path) -> Path:
    return score_dir / "holdout_2023.lock"


def prepare_holdout_2023(
    score_dir: Path,
    *,
    inputs_sha256: str,
    commit: str,
    allow_incident: str | None = None,
) -> dict:
    """Write the disagreement table, then refuse a second run.

    Scoring is the caller's next step. This function does not take a 2023
    outcome and does not change a setting.
    """
    table = write_disagreement_table(score_dir / "code_text_disagreements.md")
    lock = holdout_lock_path(score_dir)
    if lock.is_file() and not allow_incident:
        raise HoldoutLockError("second 2023 holdout run refused")
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


def write_holdout_lock(score_dir: Path, *, inputs_sha256: str, commit: str) -> Path:
    path = holdout_lock_path(score_dir)
    path.write_text(
        json.dumps({"inputs_sha256": inputs_sha256, "commit": commit, "label": HOLDOUT_LABEL}, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    return path


def assert_2024_allowed(score_dir: Path) -> None:
    """The 2024 entry point refuses unless the 2023 lock exists."""
    if not holdout_lock_path(score_dir).is_file():
        raise HoldoutLockError("2024 run refused unless the holdout lock exists")


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
    for name, prefix in INPUT_SHA256_PREFIXES.items():
        path = None if not paths else paths.get(name)
        if path is None or not Path(path).is_file():
            pins[name] = {"expected_prefix": prefix, "present": False, "sha256": None}
            continue
        digest = sha256_file(Path(path))
        if not digest.startswith(prefix):
            raise ReportAbort(f"{name} sha256 {digest} does not start with {prefix}")
        pins[name] = {"expected_prefix": prefix, "present": True, "sha256": digest}
    return pins


def build_report(
    *,
    root: Path | None = None,
    input_paths: Mapping[str, Path] | None = None,
    status_counts: Mapping[str, int] | None = None,
    price_columns_read: Mapping[str, bool] | None = None,
    disagreement_rows: Sequence[Mapping[str, str]] | None = None,
    commit: str | None = None,
) -> dict:
    """Assemble the run report. Missing method or sha8, or a bad sha8, aborts."""
    root = root or REPO_ROOT
    cfg = sr.load_config()
    method = str((cfg.get("v14") or {}).get("depreciation", {}).get("method") or "")
    if method != "straight_line_v14":
        raise ReportAbort(f"depreciation.method must be straight_line_v14, got {method!r}")
    sha8 = assert_expected_sha8(root=root)
    for rel in RECORDED_FILES:
        sha8[rel] = sha8_file(root / rel)
    if not sha8 or "backend/georgist/surface_rent.py" not in sha8:
        raise ReportAbort("report is missing sha8")
    rows = list(code_text_disagreements() if disagreement_rows is None else disagreement_rows)
    report = {
        "depreciation": {"method": method},
        "sha8": sha8,
        "commit": commit or _git_commit(),
        "input_sha256": _input_pins(input_paths),
        "seed": BOOTSTRAP_SEED,
        "status_counts": dict(status_counts or {}),
        "price_columns_read": dict(price_columns_read or {}),
        "disclosures": dict(DISCLOSURES),
        "code_text_disagreements": rows,
        "holdout_label": HOLDOUT_LABEL,
        "gbp_display": False,
    }
    if report["depreciation"].get("method") != "straight_line_v14" or not report["sha8"]:
        raise ReportAbort("report is missing method or sha8")
    return report


def write_report(path: Path, report: Mapping) -> None:
    """Write the report. A missing method or sha8 leaves no file."""
    method = str((report.get("depreciation") or {}).get("method") or "")
    sha8 = report.get("sha8")
    if method != "straight_line_v14" or not sha8:
        raise ReportAbort("report is missing method or sha8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
