"""One-shot DZ2022 fill holdout — runs only through the run guard.

Internal / blocked only. Outputs go under ``{valuation_out_dir}/run_log/``
(outside git). Does not change valuation maths.

Commands
--------
preregister  Write spec/script/input SHA-256s + seed to the run log (no scoring).
run          Refuse if not pre-registered or already scored; then mask, score,
             append results. On fail: widen bands from holdout errors — no re-fit.

Usage (from ``backend/``)::

    python -m scripts.run_dz2022_fill_holdout_oneshot preregister \\
        --rent /path/rent_2011.csv --ur6 /path/ur6.csv
    python -m scripts.run_dz2022_fill_holdout_oneshot run \\
        --rent /path/rent_2011.csv --ur6 /path/ur6.csv
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

from georgist import dz2022_fill as fill
from georgist import dz2022_fill_holdout as ho
from georgist.surface_paths import expand

SCRIPT_PATH = Path(__file__).resolve()
DEFAULT_SEED = ho.DEFAULT_SEED
HOLDOUT_FRAC = ho.HOLDOUT_FRAC
# Fixture / signed-off seed yields k held zones on the CI rent table.
# FILL-ORDER-V12 added Renfrewshire UR2 peers → k=10 (was 8).
EXPECTED_FIXTURE_HELD_N = 10


class NotPreRegisteredError(RuntimeError):
    """Scored run refused: matching preregister entry missing from the run log."""


def oneshot_script_hash() -> str:
    """SHA-256 of this CLI script (the committed entry point)."""
    return fill.sha256_file(SCRIPT_PATH)


def default_log_path() -> Path:
    return Path(expand(ho.DEFAULT_RUN_LOG))


def fingerprint(
    *,
    spec_sha256: str,
    script_sha256: str,
    input_hashes: Mapping[str, str],
    seed: int,
) -> dict:
    return {
        "spec_sha256": spec_sha256,
        "script_sha256": script_sha256,
        "input_sha256s": dict(input_hashes),
        "seed": int(seed),
    }


def _matches(entry: Mapping, fp: Mapping) -> bool:
    return (
        entry.get("spec_sha256") == fp["spec_sha256"]
        and entry.get("script_sha256") == fp["script_sha256"]
        and entry.get("input_sha256s") == fp["input_sha256s"]
        and int(entry.get("seed", -1)) == int(fp["seed"])
    )


def find_preregister(guard: ho.FillRunGuard, fp: Mapping) -> dict | None:
    matches = [
        e
        for e in guard.entries()
        if e.get("phase") == "preregister" and _matches(e, fp)
    ]
    return matches[-1] if matches else None


def find_result(guard: ho.FillRunGuard, fp: Mapping) -> dict | None:
    matches = [
        e for e in guard.entries() if e.get("phase") == "result" and _matches(e, fp)
    ]
    return matches[0] if matches else None


def build_input_hashes(
    *,
    rent_table: Path | str,
    ur6_lookup: Path | str,
    neighbours: Path | str | None = None,
) -> dict[str, str]:
    npath = Path(neighbours) if neighbours else fill.NEIGHBOURS_PATH
    return ho.input_sha256s(
        {
            "rent_table": Path(rent_table),
            "ur6_lookup": Path(ur6_lookup),
            "neighbours": npath,
        }
    )


def preregister_run(
    *,
    rent_table: Path | str,
    ur6_lookup: Path | str,
    log_path: Path | str | None = None,
    seed: int = DEFAULT_SEED,
    neighbours: Path | str | None = None,
    override: bool = False,
    reason: str = "",
) -> dict:
    """Write hashes + seed to the run log before any scoring."""
    pre = ho.check_scored_preconditions(
        rent_table=rent_table, ur6_lookup=ur6_lookup, neighbours=neighbours
    )
    if not pre["ready"]:
        raise ho.HoldoutPreconditionError(pre.get("todo") or str(pre["missing"]))

    hashes = build_input_hashes(
        rent_table=rent_table, ur6_lookup=ur6_lookup, neighbours=neighbours
    )
    log = Path(log_path) if log_path else default_log_path()
    guard = ho.FillRunGuard(log)
    fp = fingerprint(
        spec_sha256=ho.spec_hash(),
        script_sha256=oneshot_script_hash(),
        input_hashes=hashes,
        seed=seed,
    )
    # Refuse re-preregister when a scored result already exists for this fingerprint.
    prior = find_result(guard, fp)
    if prior and not override:
        raise ho.RepeatScoredRunError(
            "scored DZ2022 fill holdout already recorded for this fingerprint; "
            "pass override=True with a reason to re-run"
        )
    entry = guard.preregister(
        spec_sha256=fp["spec_sha256"],
        script_sha256=fp["script_sha256"],
        input_hashes=hashes,
        seed=seed,
        pass_bands=ho.default_pass_bands(),
        override=override,
        reason=reason,
    )
    return {"preregister_entry": entry, "fingerprint": fp, "log_path": str(log)}


def run_scored(
    *,
    rent_table: Path | str,
    ur6_lookup: Path | str,
    log_path: Path | str | None = None,
    seed: int = DEFAULT_SEED,
    neighbours: Path | str | None = None,
    class_min: int | None = None,
    override: bool = False,
    reason: str = "",
) -> dict:
    """Score only if pre-registered and not already run. No valuation-maths edits."""
    pre = ho.check_scored_preconditions(
        rent_table=rent_table, ur6_lookup=ur6_lookup, neighbours=neighbours
    )
    if not pre["ready"]:
        raise ho.HoldoutPreconditionError(pre.get("todo") or str(pre["missing"]))

    hashes = build_input_hashes(
        rent_table=rent_table, ur6_lookup=ur6_lookup, neighbours=neighbours
    )
    log = Path(log_path) if log_path else default_log_path()
    guard = ho.FillRunGuard(log)
    fp = fingerprint(
        spec_sha256=ho.spec_hash(),
        script_sha256=oneshot_script_hash(),
        input_hashes=hashes,
        seed=seed,
    )

    if not find_preregister(guard, fp) and not override:
        raise NotPreRegisteredError(
            "DZ2022 fill holdout is not pre-registered for this fingerprint; "
            "run the preregister command first"
        )
    prior_result = find_result(guard, fp)
    if prior_result and not override:
        raise ho.RepeatScoredRunError(
            f"scored DZ2022 fill holdout already recorded at "
            f"{prior_result.get('at')}; pass override=True with a reason"
        )
    if override and not reason:
        raise ValueError("an override needs a stated reason")

    rows = fill.load_2011_rent_table(Path(rent_table))
    measured = [r for r in rows if fill._is_measured(r)]
    neigh = fill.load_neighbouring_councils(
        Path(neighbours) if neighbours else fill.NEIGHBOURS_PATH
    )
    cm = int(class_min) if class_min is not None else fill.class_min_from_settings()

    train, held = ho.stratified_mask(measured, frac=HOLDOUT_FRAC, seed=seed)
    models = fill.fit_council_ur6_models(train, neighbours=neigh, class_min=cm)
    c_metrics = ho.score_method_c(models, held)
    a_metrics = ho.score_method_a_synthetic(held, seed=seed)
    decision = ho.evaluate_pass(c_metrics, a_metrics)
    widening: dict = {}
    if not decision["pass"]:
        widening = ho.widen_on_fail(decision["fails"], c_metrics, a_metrics)

    held_codes = sorted(str(r["code"]) for r in held)
    metrics = {
        "C": c_metrics,
        "A": a_metrics,
        "decision": decision,
        "held_n": len(held),
        "train_n": len(train),
        "held_codes": held_codes,
        "k": len(held),
        "frac": HOLDOUT_FRAC,
        "seed": int(seed),
        "class_min": cm,
    }

    result_entry = guard.append_result(
        spec_sha256=fp["spec_sha256"],
        script_sha256=fp["script_sha256"],
        input_hashes=hashes,
        seed=seed,
        metrics=metrics,
        pass_bands=decision["pass_bands"],
        widening=widening,
        override=override,
        reason=reason,
    )
    return {
        "train_n": len(train),
        "held_n": len(held),
        "held_codes": held_codes,
        "k": len(held),
        "class_min": cm,
        "c_metrics": c_metrics,
        "a_metrics": a_metrics,
        "decision": decision,
        "widening": widening,
        "run_log_entry": result_entry,
        "fingerprint": fp,
        "log_path": str(log),
    }


def fixed_split_codes(
    measured: Sequence[Mapping],
    *,
    seed: int = DEFAULT_SEED,
    frac: float = HOLDOUT_FRAC,
) -> list[str]:
    """Deterministic held-zone codes for a seed (exact split for tests)."""
    _train, held = ho.stratified_mask(measured, frac=frac, seed=seed)
    return sorted(str(r["code"]) for r in held)


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="One-shot DZ2022 fill holdout (internal run guard only)."
    )
    sub = p.add_subparsers(dest="command", required=True)

    def _add_common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--rent", required=True, help="2011 rent table CSV (never committed)")
        sp.add_argument("--ur6", required=True, help="Urban Rural 6 Fold 2022 Lookup CSV")
        sp.add_argument(
            "--log",
            default=None,
            help="run_log JSONL path (default: valuation_out_dir/run_log/...)",
        )
        sp.add_argument("--seed", type=int, default=DEFAULT_SEED)
        sp.add_argument("--neighbours", default=None)
        sp.add_argument("--override", action="store_true")
        sp.add_argument("--reason", default="")

    pr = sub.add_parser("preregister", help="Write hashes + seed before scoring")
    _add_common(pr)

    rn = sub.add_parser("run", help="Score once if pre-registered and not already run")
    _add_common(rn)
    rn.add_argument(
        "--class-min",
        type=int,
        default=None,
        help="Override class_min (tests only; production uses settings default 10)",
    )
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(list(argv) if argv is not None else None)
    try:
        if args.command == "preregister":
            out = preregister_run(
                rent_table=args.rent,
                ur6_lookup=args.ur6,
                log_path=args.log,
                seed=args.seed,
                neighbours=args.neighbours,
                override=args.override,
                reason=args.reason,
            )
        elif args.command == "run":
            out = run_scored(
                rent_table=args.rent,
                ur6_lookup=args.ur6,
                log_path=args.log,
                seed=args.seed,
                neighbours=args.neighbours,
                class_min=args.class_min,
                override=args.override,
                reason=args.reason,
            )
        else:
            raise SystemExit(f"unknown command {args.command!r}")
    except (
        NotPreRegisteredError,
        ho.RepeatScoredRunError,
        ho.HoldoutPreconditionError,
        ho.MissingSpecError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # Metrics are internal-only (publish_level=internal); stdout is for operators.
    # Never ship this JSON on a public route or page.
    print(json.dumps(out, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
