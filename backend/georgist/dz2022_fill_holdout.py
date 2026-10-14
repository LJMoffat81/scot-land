"""Pre-registered holdout / bias test for DZ2022 empty-zone fill.

Before scoring, writes a pre-registration entry (spec/script/input hashes, seed,
pass bands, empty metrics — no results) to ``run_log/dz2022_fill_runs.jsonl``.
After scoring, appends the result entry. Refuses a second scored run unless an
override reason is logged. On fail: widen bands from holdout errors — no re-fit.

Scored holdout must not run until the 2011 rent table and UR6 6-fold lookup are
present. ``class_min`` comes from settings (default 10); only tests may override.
"""

from __future__ import annotations

import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from georgist import dz2022_fill as fill
from georgist.surface_paths import REPO_ROOT, expand

DEFAULT_SEED = 20261014
HOLDOUT_FRAC = 0.20
COVERAGE_TARGET = 0.80
COVERAGE_TOL = 0.05
BIAS_ABS_MAX = 0.10

DEFAULT_RUN_LOG = "{valuation_out_dir}/run_log/dz2022_fill_runs.jsonl"
SPEC_PATH = REPO_ROOT / "docs" / "dz2022_empty_fill_spec.md"


class HoldoutPreconditionError(RuntimeError):
    """Scored holdout refused: required inputs not ready."""


class RepeatScoredRunError(RuntimeError):
    """A second scored run without an override reason."""


class MissingSpecError(RuntimeError):
    """Signed-off spec file required for hashing — no fixed-string fallback."""


def default_pass_bands() -> dict:
    return {
        "coverage_target": COVERAGE_TARGET,
        "coverage_tol": COVERAGE_TOL,
        "bias_abs_max": BIAS_ABS_MAX,
    }


def spec_hash(spec_text: str | None = None, *, spec_path: Path | str | None = None) -> str:
    """SHA-256 of the signed-off spec. Requires the real file (or explicit text)."""
    if spec_text is not None:
        return fill.sha256_text(spec_text)
    path = Path(spec_path) if spec_path is not None else SPEC_PATH
    if not path.is_file():
        raise MissingSpecError(
            f"signed-off DZ2022 fill spec missing: {path} "
            "(commit docs/dz2022_empty_fill_spec.md; no fixed-string fallback)"
        )
    return fill.sha256_file(path)


def script_hash() -> str:
    return fill.sha256_file(Path(__file__).resolve())


def input_sha256s(paths: Mapping[str, Path | str]) -> dict[str, str]:
    out = {}
    for k, p in paths.items():
        path = Path(p)
        out[k] = fill.sha256_file(path) if path.is_file() else f"MISSING:{path}"
    return out


class FillRunGuard:
    """Once-only scored-run log at run_log/dz2022_fill_runs.jsonl.

    Pre-registration (phase=preregister) is written before masking/scoring with
    hashes, seed and pass bands but no results. The result line is appended after.
    """

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

    def _append(self, entry: dict) -> dict:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def preregister(
        self,
        *,
        spec_sha256: str,
        script_sha256: str,
        input_hashes: Mapping[str, str],
        seed: int,
        pass_bands: Mapping | None = None,
        override: bool = False,
        reason: str = "",
    ) -> dict:
        """Write pre-registration before scoring (no result metrics)."""
        prior_scored = [e for e in self.entries() if e.get("phase") == "result" or (
            e.get("scored") and e.get("phase") != "preregister"
        )]
        # Also refuse if a completed result already exists.
        prior_results = [e for e in self.entries() if e.get("phase") == "result"]
        if (prior_scored or prior_results) and not override:
            raise RepeatScoredRunError(
                "scored DZ2022 fill holdout already recorded; "
                "pass override=True with a reason to re-run"
            )
        if override and not reason:
            raise ValueError("an override needs a stated reason")
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "phase": "preregister",
            "scored": True,
            "spec_sha256": spec_sha256,
            "script_sha256": script_sha256,
            "input_sha256s": dict(input_hashes),
            "seed": int(seed),
            "metrics": {},  # no results before scoring
            "pass_bands": dict(pass_bands or default_pass_bands()),
            "widening": {},
            "override": bool(override),
            "reason": reason,
            "n_prior_results": len(prior_results),
        }
        return self._append(entry)

    def append_result(
        self,
        *,
        spec_sha256: str,
        script_sha256: str,
        input_hashes: Mapping[str, str],
        seed: int,
        metrics: Mapping,
        pass_bands: Mapping,
        widening: Mapping | None = None,
        override: bool = False,
        reason: str = "",
    ) -> dict:
        """Append scored results after masking and scoring."""
        prior_results = [e for e in self.entries() if e.get("phase") == "result"]
        if prior_results and not override:
            raise RepeatScoredRunError(
                f"scored DZ2022 fill holdout result already recorded at "
                f"{prior_results[0].get('at')}; pass override=True with a reason"
            )
        if override and not reason:
            raise ValueError("an override needs a stated reason")
        prereg = [e for e in self.entries() if e.get("phase") == "preregister"]
        if not prereg and not override:
            raise HoldoutPreconditionError(
                "holdout result requires a prior preregister entry in the run log"
            )
        entry = {
            "at": datetime.now(timezone.utc).isoformat(),
            "phase": "result",
            "scored": True,
            "spec_sha256": spec_sha256,
            "script_sha256": script_sha256,
            "input_sha256s": dict(input_hashes),
            "seed": int(seed),
            "metrics": dict(metrics),
            "pass_bands": dict(pass_bands),
            "widening": dict(widening or {}),
            "override": bool(override),
            "reason": reason,
            "n_prior_results": len(prior_results),
        }
        return self._append(entry)

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
        phase: str = "result",
    ) -> dict:
        """Back-compat helper used by unit tests for non-scored widen logging."""
        if phase == "preregister":
            return self.preregister(
                spec_sha256=spec_sha256,
                script_sha256=script_sha256,
                input_hashes=input_hashes,
                seed=seed,
                pass_bands=pass_bands,
                override=override,
                reason=reason,
            )
        if not scored:
            entry = {
                "at": datetime.now(timezone.utc).isoformat(),
                "phase": "diagnostic",
                "scored": False,
                "spec_sha256": spec_sha256,
                "script_sha256": script_sha256,
                "input_sha256s": dict(input_hashes),
                "seed": int(seed),
                "metrics": dict(metrics or {}),
                "pass_bands": dict(pass_bands or {}),
                "widening": dict(widening or {}),
                "override": bool(override),
                "reason": reason,
                "n_prior_results": 0,
            }
            return self._append(entry)
        return self.append_result(
            spec_sha256=spec_sha256,
            script_sha256=script_sha256,
            input_hashes=input_hashes,
            seed=seed,
            metrics=metrics or {},
            pass_bands=pass_bands or default_pass_bands(),
            widening=widening,
            override=override,
            reason=reason,
        )


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

    sales_vals = sorted(int(r.get(sales_key) or 0) for r in measured)

    def _decile(n: int) -> int:
        if not sales_vals:
            return 0
        rank = sum(1 for s in sales_vals if s < n)
        return min(9, int(rank * 10 / max(1, len(sales_vals))))

    held: list[Mapping] = []
    for key in sorted(by_stratum):
        members = list(by_stratum[key])
        weights = [3.0 if _decile(int(r.get(sales_key) or 0)) == 0 else 1.0 for r in members]
        k = max(1, int(round(len(members) * frac))) if members else 0
        k = min(k, len(members))
        if k == 0:
            continue
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
        if low <= actual <= high:
            cover_hits += 1
        n += 1
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
        kept = actual * (1.0 - empty_share)
        pred = kept / (1.0 - empty_share)
        low = pred * 0.9
        high = pred * 1.1
        low, pred, high = fill.widen_range_by_empty_share(low, pred, high, empty_share)
        abs_errs.append(_abs_log_error(pred, actual))
        if low <= actual <= high:
            cover_hits += 1
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
    class_min: int | None = None,
) -> dict:
    """Run the pre-registered holdout.

    Pre-registration is written **before** masking/scoring. ``class_min`` defaults
    to settings (10); only tests may pass a smaller value.
    """
    if require_preconditions is not None and not require_preconditions.get("ready"):
        raise HoldoutPreconditionError(
            require_preconditions.get("todo")
            or f"preconditions not ready: {require_preconditions.get('missing')}"
        )

    cm = int(class_min) if class_min is not None else fill.class_min_from_settings()
    hashes = dict(input_hashes or {})
    bands = default_pass_bands()
    spec_sha = spec_hash()
    script_sha = script_hash()
    guard = FillRunGuard(log_path)

    pre_entry = None
    if scored:
        # 1) Pre-register BEFORE masking and scoring (no results).
        pre_entry = guard.preregister(
            spec_sha256=spec_sha,
            script_sha256=script_sha,
            input_hashes=hashes,
            seed=seed,
            pass_bands=bands,
            override=override,
            reason=reason,
        )

    # 2) Mask and score.
    train, held = stratified_mask(measured_2011, seed=seed)
    models = fill.fit_council_ur6_models(train, neighbours=neighbours, class_min=cm)
    c_metrics = score_method_c(models, held)
    a_metrics = score_method_a_synthetic(held, seed=seed)
    decision = evaluate_pass(c_metrics, a_metrics)
    widening = {} if decision["pass"] else widen_on_fail(decision["fails"], c_metrics, a_metrics)

    result_entry = None
    if scored:
        # 3) Append results after scoring.
        result_entry = guard.append_result(
            spec_sha256=spec_sha,
            script_sha256=script_sha,
            input_hashes=hashes,
            seed=seed,
            metrics={"C": c_metrics, "A": a_metrics, "decision": decision},
            pass_bands=decision["pass_bands"],
            widening=widening,
            override=override,
            reason=reason,
        )
    else:
        result_entry = guard.register(
            spec_sha256=spec_sha,
            script_sha256=script_sha,
            input_hashes=hashes,
            seed=seed,
            metrics={"C": c_metrics, "A": a_metrics, "decision": decision},
            pass_bands=decision["pass_bands"],
            widening=widening,
            scored=False,
        )

    return {
        "train_n": len(train),
        "held_n": len(held),
        "class_min": cm,
        "c_metrics": c_metrics,
        "a_metrics": a_metrics,
        "decision": decision,
        "widening": widening,
        "preregister_entry": pre_entry,
        "run_log_entry": result_entry,
    }


def default_run_log_path() -> Path:
    return Path(expand(DEFAULT_RUN_LOG))
