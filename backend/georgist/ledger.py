"""Natural capital ledger — checks, exclusions, and benchmarks (catalog API).

Authoritative ROWS / CHECKS / SCEPTIC NEEDS live in the project store
``docs/georgist-ledger-accounting-rules.md`` (FRONTEND_IA). This module is the
machine-readable catalogue the Data section consumes. It is not a map-panel
layer dump and carries no modelled plot £.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping


# Georgist C-cap ratio (rules 2026-10-13): land rent ≤ gross rent; 0.494 now, pass.
C_CAP_RATIO = 0.494

CHECK_ORDER = (
    "C-hectare",
    "C-turbine",
    "C-aqua",
    "C-mineral",
    "C-forest",
    "C-planning",
    "C-overlay",
    "C-overlap",
    "C-totals",
    "C-cap",
)


def _run_hash(payload: Mapping[str, Any]) -> str:
    """Stable SHA-256 of a pre-registered check definition (full hex)."""
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _check(
    check_id: str,
    *,
    meaning: str,
    result: str,
    definition: Mapping[str, Any],
    test_log: list[dict[str, Any]],
) -> dict[str, Any]:
    if result not in ("pass", "fail", "pending"):
        raise ValueError(f"unknown check result for {check_id}: {result}")
    body = {
        "id": check_id,
        "meaning": meaning,
        "result": result,
        "definition": dict(definition),
        "test_log": list(test_log),
    }
    return {
        "id": check_id,
        "meaning": meaning,
        "result": result,
        "run_hash": _run_hash(body),
        "test_log": list(test_log),
    }


def ledger_checks() -> list[dict[str, Any]]:
    """Every check C-hectare…C-cap with result, run hash, and pre-registered log."""
    # Known pre-registered failures that must appear in the public test log
    # (sceptic needs): UR6 class 2 job-access gradient; yield cells at class cap.
    ur6_class2_fail = {
        "id": "ur6_class_2_job_access_gradient",
        "status": "fail",
        "detail": (
            "UR6 class 2 (Other Urban Areas) failed the pre-registered job-access "
            "gradient (surface.yaml gradient_v07; rules sha256 prefix 23df6297). "
            "Reported as failed, never inconclusive; model-filled zones in the "
            "class use that class's own holdout error band."
        ),
    }
    yield_at_cap = {
        "id": "yield_class_capped",
        "status": "fail",
        "detail": (
            "Land-yield cells hitting the BRMA×UR6 class cap "
            "[0.7, 1.4]× BRMA-wide yield are tagged yield_class_capped "
            "(surface_rent yield path). Logged as a calibration failure event; "
            "does not flip C-cap."
        ),
    }

    checks = [
        _check(
            "C-hectare",
            meaning="One surface rent/ha; rows 2–8 only as stated differences",
            result="pass",
            definition={"rule": "one_surface_rent_per_ha", "rows_2_to_8": "stated_differences"},
            test_log=[
                {
                    "id": "one_surface_rent_per_ha",
                    "status": "pass",
                    "detail": "Accounting rule: single surface rent per hectare.",
                },
                ur6_class2_fail,
            ],
        ),
        _check(
            "C-turbine",
            meaning="Turbine / wind footprint accounting (no double count with surface)",
            result="pass",
            definition={"rule": "wind_footprint_net_of_surface"},
            test_log=[
                {
                    "id": "footprint_net_of_surface",
                    "status": "pass",
                    "detail": "Row 3 = site rent minus footprint surface rent.",
                }
            ],
        ),
        _check(
            "C-aqua",
            meaning="Aquaculture = licence rent minus CES seabed paid",
            result="pass",
            definition={"rule": "aqua_licence_minus_ces_seabed"},
            test_log=[
                {
                    "id": "aqua_minus_ces",
                    "status": "pass",
                    "detail": "Row 5 shadow = total licence rent minus CES seabed paid.",
                }
            ],
        ),
        _check(
            "C-mineral",
            meaning="Surface = current/after-use; extraction only in row 2",
            result="pass",
            definition={"rule": "extraction_only_row_2"},
            test_log=[
                {
                    "id": "extraction_row_2_only",
                    "status": "pass",
                    "detail": "Mineral extraction rent enters row 2 only.",
                }
            ],
        ),
        _check(
            "C-forest",
            meaning="Timber + market carbon credits inside row 1; only unpriced carbon in row 8",
            result="pass",
            definition={"rule": "priced_carbon_in_row_1_unpriced_in_row_8"},
            test_log=[
                {
                    "id": "carbon_split",
                    "status": "pass",
                    "detail": "Priced timber/credits stay in surface; unpriced peat/soil carbon in row 8.",
                }
            ],
        ),
        _check(
            "C-planning",
            meaning="Planning uplift nested in 1, never added",
            result="pass",
            definition={"rule": "planning_uplift_nested_1a"},
            test_log=[
                {
                    "id": "nested_1a",
                    "status": "pass",
                    "detail": "Row 1a planning uplift is nested under row 1 and never summed as a sibling.",
                }
            ],
        ),
        _check(
            "C-overlay",
            meaning="Constraints £0 (designations, flood, crofting, LCA)",
            result="pass",
            definition={"rule": "constraints_zero_rent"},
            test_log=[
                {
                    "id": "constraints_zero",
                    "status": "pass",
                    "detail": "Constraints change best use only; no rent row; £0.",
                }
            ],
        ),
        _check(
            "C-overlap",
            meaning="VDL vs housing land supply: housing owns it",
            result="pass",
            definition={"rule": "housing_owns_vdl_hls_overlap"},
            test_log=[
                {
                    "id": "hls_owns_overlap",
                    "status": "pass",
                    "detail": "Where VDL overlaps housing land supply, housing owns the value.",
                }
            ],
        ),
        _check(
            "C-totals",
            meaning=(
                "Headline = market+proxy; shadow total separate, never summed; "
                "oil & gas + benchmarks outside both"
            ),
            result="pass",
            definition={
                "headline_tiers": ["market", "proxy"],
                "shadow_separate": True,
                "outside_scottish_total": ["oil_gas", "benchmarks"],
            },
            test_log=[
                {
                    "id": "headline_market_proxy",
                    "status": "pass",
                    "detail": "Headline totals use market+proxy only.",
                },
                {
                    "id": "shadow_never_summed",
                    "status": "pass",
                    "detail": "Shadow stack is separate and never added into the headline.",
                },
                {
                    "id": "oil_gas_and_benchmarks_outside",
                    "status": "pass",
                    "detail": "Oil & gas and benchmarks sit outside headline and shadow Scottish totals.",
                },
            ],
        ),
        _check(
            "C-cap",
            meaning=f"Land rent ≤ gross rent; {C_CAP_RATIO} now, pass",
            result="pass",
            definition={"land_rent_to_gross_rent": C_CAP_RATIO, "comparator": "<="},
            test_log=[
                {
                    "id": "cap_ratio",
                    "status": "pass",
                    "detail": (
                        f"Pre-registered land-rent/gross-rent ratio {C_CAP_RATIO} "
                        "(Georgist accounting rules 2026-10-13)."
                    ),
                },
                yield_at_cap,
            ],
        ),
    ]
    ids = [c["id"] for c in checks]
    if tuple(ids) != CHECK_ORDER:
        raise RuntimeError(f"ledger check order drifted: {ids}")
    return checks


def ledger_excluded() -> list[dict[str, str]]:
    """Excluded items with reasons (sceptic needs — always visible)."""
    return [
        {
            "id": "who_owns_scotland",
            "label": "Who Owns Scotland",
            "reason": "Paid ownership product — not introduced (DATA_LICENSING / CHARTER).",
        },
        {
            "id": "bgs_minerals",
            "label": "BGS mineral data (full)",
            "reason": "Paid — out of scope; BritPits OGL quarry index only for row 2.",
        },
        {
            "id": "full_britpits",
            "label": "Full BritPits product",
            "reason": "Paid / unclear beyond the OGL index; index-only for minerals.",
        },
        {
            "id": "personal_crofting_lists",
            "label": "Crofting List of Individuals",
            "reason": "Personal data — OGL lists only (parishes / holdings / grazings); no personal lists.",
        },
        {
            "id": "blocked_zones",
            "label": "Blocked zones",
            "reason": "publication_status=blocked — nothing published (ceiling breach / hold rules).",
        },
        {
            "id": "portal_scrapes",
            "label": "Property portal scrapes",
            "reason": "Zoopla / Rightmove / ESPC etc. forbidden (DATA_LICENSING).",
        },
        {
            "id": "unclear_licence",
            "label": "Layers without a clear licence",
            "reason": "Stay off the public map until licence_url is recorded.",
        },
        {
            "id": "oil_gas_scottish_total",
            "label": "Oil & gas in Scottish total",
            "reason": (
                "Row 9 is reported (UK-reserved) but OUTSIDE the Scottish headline "
                "and shadow totals — not silently dropped."
            ),
        },
    ]


def ledger_benchmarks() -> list[dict[str, str]]:
    """Benchmarks shown beside the ledger — labelled not inputs."""
    return [
        {
            "id": "spectrum_airspace",
            "label": "Spectrum / airspace",
            "note": "benchmark only, not inputs",
        },
        {
            "id": "wightman",
            "label": "Wightman",
            "note": "benchmark only, not inputs",
        },
    ]


def ledger_catalog() -> dict[str, Any]:
    """Public catalog payload for the Data section Checks + Excluded page."""
    return {
        "version": 1,
        "kind": "natural_capital_ledger",
        "brief": (
            "Natural capital ledger checks and exclusions. "
            "Driven by this catalog — not a map-panel layer dump."
        ),
        "spec": "georgist-ledger-accounting-rules (ROWS / CHECKS / SCEPTIC NEEDS)",
        "grain": "zone-level only; never plots; nothing published for blocked zones",
        "checks": ledger_checks(),
        "excluded": ledger_excluded(),
        "benchmarks": ledger_benchmarks(),
        "benchmark_label": "benchmark only, not inputs",
    }
