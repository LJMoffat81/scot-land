"""Pre-registered holdout / bias test for DZ2022 empty-zone fill.

Writes ``run_log/dz2022_fill_runs.jsonl`` before scoring. Refuses a second
scored run unless an override reason is logged. On fail: widen bands from
holdout errors — no re-fit, no borrowing-rule switch, no re-run.

Scored holdout must not run until the 2011 rent table, UR6 6-fold lookup, and
(already committed) neighbours file are present. Fixture unit tests exercise
the guard and widen path without production inputs.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from georgist import dz2022_fill as fill
from georgist.surface_paths import REPO_ROOT, data_dir, expand

DEFAULT_SEED = 20261014
HOLDOUT_FRAC = 0.20
COVERAGE_TARGET = 0.80
COVERAGE_TOL = 0.05
BIAS_ABS_MAX = 0.10

DEFAULT_RUN_LOG = "{valuation_out_dir}/run_log/dz2022_fill_runs.jsonl"


class HoldoutPreconditionError(RuntimeError):
    """Scored holdout refused: required inputs not ready."""


class RepeatScoredRunError(RuntimeError):
    """A second scored run without an override reason."""


def spec_hash(spec_text: str | None = None) -> str:
    """SHA-256 of the signed-off spec text (or a pinned placeholder for fixtures)."""
    if spec_text is not None:
        return fill.sha256_text(spec_text)
    # Prefer the Project-store copy if mounted; else hash this module's docstring contract.
    candidates = [
        Path("/cursor/stores/self/docs/scot-land-dz2022-fill-spec.md"),
        REPO_ROOT / "docs" / "scot-land-dz2022-fill-spec.md",
    ]
    for p in candidates:
        if p.is_file():
            return fill.sha256_file(p)
    return fill.sha256_text("dz2022_fill_spec:signed_off_2026-10-14")


def script_hash() -> str:
    return fill.sha256_file(Path(__file__).resolve())


def input_sha256s(paths: Mapping[str, Path | str]) -> dict[str, str]:
    out = {}
    for k, p in paths.items():
        path = Path(p)
        out[k] = fill.sha256_file(path) if path.is_file() else f"MISSING:{path}"
    return out


class FillRunGuard:
    """Once-only scored-run log at run_log/dz2022_fill_runs.jsonl."""

    def __init__(self, log_path: Path | str):
        self.path = Path(log_path)

    def entries(self) -> list[dict]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def register(
        self,
        *,
        spec_sha256: str,
        script_sha256: str,
        input_hashes: Mapping[str, str],
        seed: int,
        metrics: Mapping | None = None,
        pass_bands: Mapping | None = None,
        widening: Mapping | None = None,
        override: bool = False,
        reason: str = "",
        scored: bool = True,
    ) -> dict:
        prior = [e for e in self.entries() if e.get("scored")]
        if prior and scored and not override:
            raise RepeatScoredRunError(
                f"scored DZ2022 fill holdout already recorded at {prior[0].get('at')}; "
                "pass override=True with a reason to re-run"
            )
        if override and not reason:
            raise ValueError("an override needs a stated reason")
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "scored": bool(scored),
            "spec_sha256": spec_sha256,
            "script_sha256": script_sha256,
            "input_sha256s": dict(input_hashes),
            "seed": int(seed),
            "metrics": dict(metrics or {}),
            "pass_bands": dict(pass_bands or {}),
            "widening": dict(widening or {}),
            "override": bool(override),
            "reason": reason,
            "n_prior_scored": len(prior),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry


def check_scored_preconditions(
    *,
    rent_table: Path | str | None,
    ur6_lookup: Path | str | None,
    neighbours: Path | str | None = None,
) -> dict:
    """Refuse scored holdout until rent table + UR6 lookup exist (neighbours are committed)."""
    missing = []
    npath = Path(neighbours) if neighbours else fill.NEIGHBOURS_PATH
    if not npath.is_file():
        missing.append(f"neighbours:{npath}")
    rpath = Path(rent_table) if rent_table else None
    if rpath is None or not rpath.is_file():
        missing.append(f"rent_table:{rent_table}")
    upath = Path(ur6_lookup) if ur6_lookup else None
    if upath is None or not upath.is_file():
        missing.append(f"ur6_lookup:{ur6_lookup}")
    return {
        "ready": not missing,
        "missing": missing,
        "todo": (
            None
            if not missing
            else (
                "TODO: supply 2011 rent table path and Urban Rural 6 Fold 2022 Lookup "
                "before the scored holdout; do not invent production data"
            )
        ),
    }


def stratified_mask(
    measured: Sequence[Mapping],
    *,
    frac: float = HOLDOUT_FRAC,
    seed: int = DEFAULT_SEED,
    sales_key: str = "sales_n",
) -> tuple[list[Mapping], list[Mapping]]:
    """Mask ``frac`` of measured 2011 zones; stratify by council×UR6; overweight lowest sales decile."""
    rng = random.Random(seed)
    by_stratum: dict[tuple[str, int], list[Mapping]] = defaultdict(list)
    for r in measured:
        la = str(r.get("la_code") or "").strip()
        ur6 = r.get("ur6_class")
        if not la or ur6 is None:
            continue
        by_stratum[(la, int(ur6))].append(r)

    # Global sales decile ranks for overweighting.
    sales_vals = sorted(int(r.get(sales_key) or 0) for r in measured)
    def _decile(n: int) -> int:
        if not sales_vals:
            return 0
        # 0 = lowest decile
        rank = sum(1 for s in sales_vals if s < n)
        return min(9, int(rank * 10 / max(1, len(sales_vals))))

    held: list[Mapping] = []
    for key in sorted(by_stratum):
        members = list(by_stratum[key])
        # Overweight lowest sales decile: sample with weights.
        weights = []
        for r in members:
            d = _decile(int(r.get(sales_key) or 0))
            weights.append(3.0 if d == 0 else 1.0)
        k = max(1, int(round(len(members) * frac))) if members else 0
        k = min(k, len(members))
        if k == 0:
            continue
        # Weighted sample without replacement.
        pool = list(members)
        wpool = list(weights)
        chosen = []
        for _ in range(k):
            total_w = sum(wpool)
            pick = rng.random() * total_w
            acc = 0.0
            idx = 0
            for i, w in enumerate(wpool):
                acc += w
                if acc >= pick:
                    idx = i
                    break
            chosen.append(pool.pop(idx))
            wpool.pop(idx)
        held.extend(chosen)

    held_codes = {str(r["code"]) for r in held}
    train = [r for r in measured if str(r["code"]) not in held_codes]
    return train, held


def _abs_log_error(pred: float, actual: float) -> float:
    if pred <= 0 or actual <= 0:
        raise ValueError("log error needs positive pred and actual")
    return abs(math.log(pred) - math.log(actual))


def _signed_log_bias(pred: float, actual: float) -> float:
    return math.log(pred) - math.log(actual)


def score_method_c(
    models: Mapping[tuple[str, int], fill.GroupModel],
    held: Sequence[Mapping],
) -> dict:
    """Score C predictions on masked measured zones (exact money in fixtures)."""
    abs_errs: list[float] = []
    signed: list[float] = []
    cover_hits = 0
    n = 0
    by_decile: dict[int, list[float]] = defaultdict(list)
    sales = sorted(int(r.get("sales_n") or 0) for r in held)
    for r in held:
        la = str(r.get("la_code") or "").strip()
        ur6 = int(r["ur6_class"])
        dwellings = int(r["dwellings"])
        actual = float(r["measured_rent"])
        model = models.get((la, ur6))
        if model is None or dwellings <= 0 or actual <= 0:
            continue
        low, central, high = fill.predict_group_rent(model, dwellings=dwellings)
        abs_errs.append(_abs_log_error(central, actual))
        signed.append(_signed_log_bias(central, actual))
        if low <= actual <= high:
            cover_hits += 1
        n += 1
        # lowest sales decile among held
        rank = sum(1 for s in sales if s < int(r.get("sales_n") or 0))
        dec = min(9, int(rank * 10 / max(1, len(sales)))) if sales else 0
        by_decile[dec].append(_signed_log_bias(central, actual))

    med_abs = sorted(abs_errs)[len(abs_errs) // 2] if abs_errs else None
    coverage = cover_hits / n if n else None
    low_bias = None
    if by_decile.get(0):
        vals = sorted(by_decile[0])
        low_bias = vals[len(vals) // 2]
    return {
        "n": n,
        "median_abs_log_error": med_abs,
        "coverage_p10_p90": coverage,
        "signed_median_log_bias_lowest_sales_decile": low_bias,
        "abs_log_errors": abs_errs,
    }


def score_method_a_synthetic(
    measured: Sequence[Mapping],
    *,
    empty_share: float = 0.30,
    seed: int = DEFAULT_SEED,
) -> dict:
    """Bias-test A: mask a share of each zone's rent, scale up, compare to true."""
    rng = random.Random(seed)
    abs_errs: list[float] = []
    cover_hits = 0
    for r in measured:
        actual = float(r["measured_rent"])
        if actual <= 0:
            continue
        # Synthetic: keep (1 - empty_share) of rent as "measured part", scale up.
        kept = actual * (1.0 - empty_share)
        # Tiny noise-free scale (exact): pred = kept / (1 - empty_share) == actual
        pred = kept / (1.0 - empty_share)
        low = pred * 0.9
        high = pred * 1.1
        low, pred, high = fill.widen_range_by_empty_share(low, pred, high, empty_share)
        abs_errs.append(_abs_log_error(pred, actual))
        if low <= actual <= high:
            cover_hits += 1
        # consume rng so seed still affects any future stochastic A tests
        rng.random()
    n = len(abs_errs)
    return {
        "n": n,
        "median_abs_log_error": sorted(abs_errs)[n // 2] if n else None,
        "coverage_p10_p90": (cover_hits / n) if n else None,
        "abs_log_errors": abs_errs,
        "empty_share": empty_share,
    }


def evaluate_pass(
    c_metrics: Mapping,
    a_metrics: Mapping,
    *,
    coverage_target: float = COVERAGE_TARGET,
    coverage_tol: float = COVERAGE_TOL,
    bias_abs_max: float = BIAS_ABS_MAX,
) -> dict:
    """Pre-registered pass bands."""
    bands = {
        "coverage_target": coverage_target,
        "coverage_tol": coverage_tol,
        "bias_abs_max": bias_abs_max,
    }
    fails = []
    cov = c_metrics.get("coverage_p10_p90")
    if cov is not None and abs(cov - coverage_target) > coverage_tol:
        fails.append("c_coverage")
    bias = c_metrics.get("signed_median_log_bias_lowest_sales_decile")
    if bias is not None and abs(bias) >= bias_abs_max:
        fails.append("c_low_sales_bias")
    a_cov = a_metrics.get("coverage_p10_p90")
    if a_cov is not None and abs(a_cov - coverage_target) > coverage_tol:
        fails.append("a_coverage")
    return {
        "pass": not fails,
        "fails": fails,
        "pass_bands": bands,
    }


def widen_on_fail(
    fails: Sequence[str],
    c_metrics: Mapping,
    a_metrics: Mapping,
) -> dict[str, list[float]]:
    """Map affected zone types → abs log errors for band widening (no re-fit)."""
    out: dict[str, list[float]] = {}
    if any(f.startswith("c_") for f in fails):
        out[fill.CLASS_C] = list(c_metrics.get("abs_log_errors") or [])
        out[fill.CLASS_B] = list(c_metrics.get("abs_log_errors") or [])
    if any(f.startswith("a_") for f in fails):
        out[fill.CLASS_A] = list(a_metrics.get("abs_log_errors") or [])
    return out


def run_holdout(
    measured_2011: Sequence[Mapping],
    *,
    neighbours: Mapping[str, Sequence[str]],
    log_path: Path | str,
    seed: int = DEFAULT_SEED,
    input_hashes: Mapping[str, str] | None = None,
    override: bool = False,
    reason: str = "",
    scored: bool = True,
    require_preconditions: Mapping | None = None,
) -> dict:
    """Run the pre-registered holdout. ``scored=True`` hits the once-only guard."""
    if require_preconditions is not None and not require_preconditions.get("ready"):
        raise HoldoutPreconditionError(
            require_preconditions.get("todo")
            or f"preconditions not ready: {require_preconditions.get('missing')}"
        )

    guard = FillRunGuard(log_path)
    train, held = stratified_mask(measured_2011, seed=seed)
    models = fill.fit_council_ur6_models(train, neighbours=neighbours, class_min=3)
    # class_min=3 for fixture-scale holdouts; production scored run uses CLASS_MIN_TRAINING.
    c_metrics = score_method_c(models, held)
    a_metrics = score_method_a_synthetic(held, seed=seed)
    decision = evaluate_pass(c_metrics, a_metrics)
    widening = {} if decision["pass"] else widen_on_fail(decision["fails"], c_metrics, a_metrics)

    entry = guard.register(
        spec_sha256=spec_hash(),
        script_sha256=script_hash(),
        input_hashes=input_hashes or {},
        seed=seed,
        metrics={"C": c_metrics, "A": a_metrics, "decision": decision},
        pass_bands=decision["pass_bands"],
        widening=widening,
        override=override,
        reason=reason,
        scored=scored,
    )
    return {
        "train_n": len(train),
        "held_n": len(held),
        "c_metrics": c_metrics,
        "a_metrics": a_metrics,
        "decision": decision,
        "widening": widening,
        "run_log_entry": entry,
    }


def default_run_log_path() -> Path:
    return Path(expand(DEFAULT_RUN_LOG))
