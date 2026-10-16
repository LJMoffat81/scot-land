#!/usr/bin/env python3
"""v1.4 scoring harness — pins frozen MD/JSON shas, both estimators, no-switch rule.

£ display off. Outputs under out/ (gitignored). No re-tuning after results.
Synthetic or precomputed share lists only in CI; no public £.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from georgist import surface_rent as sr
from georgist import surface_v14 as v14
from georgist.surface_paths import REPO_ROOT


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out", type=Path, default=REPO_ROOT / "out" / "v14_score" / "report.json")
    p.add_argument(
        "--primary-shares-json",
        type=Path,
        help="JSON list of primary (cost) land shares. Unavailable zones as 0.0.",
    )
    p.add_argument(
        "--secondary-shares-json",
        type=Path,
        help="JSON list of secondary (hedonic) land shares.",
    )
    args = p.parse_args(argv)
    cfg = sr.load_config()
    pins = v14.pin_frozen_inputs(cfg)
    dep = v14.v14_depreciation(cfg)

    report = {
        "pins": pins,
        "gbp_display": False,
        "depreciation": {
            "method": dep.get("method"),
            "age_cap_years": dep.get("age_cap_years"),
            "rate_building": dep.get("rate_building"),
            "max_depreciation": dep.get("max_depreciation"),
        },
        "no_age_mix_remaining_factor": v14.no_age_mix_remaining(cfg),
        "no_switch_publication_rule": v14.NO_SWITCH_PUBLICATION_RULE,
        "note": (
            "Valuation runs the scored pass once on merged main. "
            "Both estimators are scored; publication follows the no-switch rule. "
            "No re-tuning in this PR."
        ),
    }

    if args.primary_shares_json and args.primary_shares_json.is_file():
        primary = json.loads(args.primary_shares_json.read_text(encoding="utf-8"))
        secondary = None
        if args.secondary_shares_json and args.secondary_shares_json.is_file():
            secondary = json.loads(args.secondary_shares_json.read_text(encoding="utf-8"))
        report["scores"] = v14.score_estimators(
            primary_shares=list(primary),
            secondary_shares=None if secondary is None else list(secondary),
            cfg=cfg,
        )
    else:
        report["scores"] = {
            "status": "pending_inputs",
            "reason": "pass --primary-shares-json (and optional --secondary-shares-json)",
        }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.out}")
    if not pins.get("prereg_sha256"):
        print(
            "frozen prereg file absent locally; prefix pin only "
            f"({v14.PREREG_SHA256_PREFIX}…)",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
