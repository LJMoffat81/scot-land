"""Natural capital ledger — rows, checks, exclusions, and benchmarks.

Authoritative ROWS / CHECKS / SCEPTIC NEEDS live in the project store
``docs/georgist-ledger-accounting-rules.md`` (FRONTEND_IA). This module is the
machine-readable catalogue the Data section and place stack consume. It is not
a map-panel layer dump and never publishes plot-level £.

Public modelled AGR / rent £ stay withheld until ECONOMIC_RULES is approved.
``not_yet`` rows never emit a £0 range. Blocked zones publish nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Mapping

from georgist import db
from georgist import dz_lookup

logger = logging.getLogger(__name__)

# Georgist C-cap ratio (rules 2026-10-13): land rent ≤ gross rent; 0.494 now, pass.
C_CAP_RATIO = 0.494

# docs/ECONOMIC_RULES.md is DRAFT — flip only when Laurie approves that document.
ECONOMIC_RULES_APPROVED = False

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

ROW_ORDER = ("1", "1a", "2", "3", "4", "5", "6", "7", "8", "9", "10")

ROW_STATUSES = frozenset({"counted", "partial", "not_yet", "excluded"})
ROW_TAGS = frozenset({"market", "proxy", "shadow", "reported"})


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


def _row(
    row_id: str,
    *,
    label: str,
    tag: str,
    status: str,
    source: str,
    licence: str,
    licence_url: str | None,
    vintage: str | int | None,
    coverage_pct: float | None,
    range_band: dict[str, Any] | None,
    note: str,
    nested_under: str | None = None,
    never_added: bool = False,
    outside_scottish_total: bool = False,
    stack: str = "headline",
) -> dict[str, Any]:
    if tag not in ROW_TAGS:
        raise ValueError(f"unknown ledger tag for row {row_id}: {tag}")
    if status not in ROW_STATUSES:
        raise ValueError(f"unknown ledger status for row {row_id}: {status}")
    if stack not in ("headline", "shadow", "outside"):
        raise ValueError(f"unknown stack for row {row_id}: {stack}")
    if status == "not_yet" and range_band is not None:
        raise ValueError(f"row {row_id}: not_yet must not carry a £ range (never £0)")
    if status == "not_yet" and range_band is None:
        # Explicit null — UI must not invent £0.
        pass
    out: dict[str, Any] = {
        "id": row_id,
        "label": label,
        "tag": tag,
        "status": status,
        "source": source,
        "licence": licence,
        "licence_url": licence_url,
        "vintage": vintage,
        "coverage_pct": coverage_pct,
        "range": range_band,
        "stack": stack,
        "note": note,
    }
    if nested_under is not None:
        out["nested_under"] = nested_under
        out["never_added"] = True
    elif never_added:
        out["never_added"] = True
    if outside_scottish_total:
        out["outside_scottish_total"] = True
    return out


def ledger_rows(*, internal: bool = False) -> list[dict[str, Any]]:
    """Rows 1–10 (+ nested 1a). Public: no modelled AGR £ until ECONOMIC_RULES approved.

    ``internal`` is reserved for attaching zone valuation bands once approved;
    today both paths keep ``range`` null so not_yet is never shown as £0.
    """
    del internal  # no GBP bands wired yet; keep signature for callers/tests

    ogl = "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/"
    rows = [
        _row(
            "1",
            label="Surface site rent",
            tag="proxy",
            status="not_yet",
            source="RoS price spine / surface_rent_dz (zone grain); best permitted use",
            licence="OGL-3.0",
            licence_url=ogl,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note=(
                "Best permitted use; idle/derelict = best use minus remediation. "
                "Public modelled £ withheld until ECONOMIC_RULES approved."
            ),
            stack="headline",
        ),
        _row(
            "1a",
            label="Planning uplift",
            tag="proxy",
            status="not_yet",
            source="LDP / Housing Land Audit / planning sites (attribution)",
            licence="OGL-3.0",
            licence_url=ogl,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note="NESTED in row 1 — never added as a sibling total (C-planning).",
            nested_under="1",
            stack="headline",
        ),
        _row(
            "2",
            label="Mineral rent",
            tag="proxy",
            status="not_yet",
            source="BritPits OGL quarry index only (full BritPits / BGS excluded)",
            licence="OGL-3.0",
            licence_url=ogl,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note="Royalty/tonne, below ground; extraction only in this row (C-mineral).",
            stack="headline",
        ),
        _row(
            "3",
            label="Onshore wind + hydro resource rent",
            tag="proxy",
            status="partial",
            source="REPD onshore wind; SEPA / hydro sites inventory",
            licence="OGL-3.0",
            licence_url=ogl,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note=(
                "Site rent minus footprint surface rent (C-turbine). Spatial inventory "
                "partial; resource rent £ not yet published."
            ),
            stack="headline",
        ),
        _row(
            "4",
            label="Seabed & foreshore",
            tag="market",
            status="not_yet",
            source="CES ScotWind/INTOG, cables, moorings, foreshore (CES OGL credit)",
            licence="OGL-3.0",
            licence_url=ogl,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note="Crown Estate Scotland offshore wind, cables, moorings, foreshore.",
            stack="headline",
        ),
        _row(
            "5",
            label="Aquaculture licence rent",
            tag="shadow",
            status="not_yet",
            source="CES aquaculture seabed; licence economics minus CES seabed paid",
            licence="OGL-3.0",
            licence_url=ogl,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note="Shadow stack; total licence rent minus CES seabed paid (C-aqua).",
            stack="shadow",
        ),
        _row(
            "6",
            label="Fisheries quota",
            tag="shadow",
            status="not_yet",
            source="ICES landings / quota — market if lease prices, else shadow",
            licence="OGL-3.0",
            licence_url=ogl,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note="No public lease-price series yet — treated as shadow until priced.",
            stack="shadow",
        ),
        _row(
            "7",
            label="Water scarcity",
            tag="shadow",
            status="not_yet",
            source="SEPA CAR / water (inventory); scarcity rent ~0 when modelled",
            licence="OGL-3.0",
            licence_url=ogl,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note=(
                "Accounting position ~0 when modelled — status remains not_yet so "
                "the UI never shows a placeholder £0."
            ),
            stack="shadow",
        ),
        _row(
            "8",
            label="Unpriced peat/soil carbon",
            tag="shadow",
            status="not_yet",
            source="Peatland ACTION; Carbon & Peatland 2016 (unpriced only)",
            licence="mixed (OGL Peatland ACTION; Carbon & Peatland non-commercial)",
            licence_url=None,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note="Only unpriced carbon; priced timber/credits stay in row 1 (C-forest).",
            stack="shadow",
        ),
        _row(
            "9",
            label="Oil & gas",
            tag="reported",
            status="not_yet",
            source="NSTA licences / fields (NSTA credit) — UK-reserved",
            licence="NSTA",
            licence_url=None,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note="Reported beside the ledger; OUTSIDE Scottish headline and shadow totals.",
            outside_scottish_total=True,
            stack="outside",
        ),
        _row(
            "10",
            label="Ecosystem services",
            tag="shadow",
            status="not_yet",
            source="Eco module (later)",
            licence="TBD",
            licence_url=None,
            vintage=None,
            coverage_pct=None,
            range_band=None,
            note="Later — shadow stack; not yet modelled.",
            stack="shadow",
        ),
    ]
    ids = tuple(r["id"] for r in rows)
    if ids != ROW_ORDER:
        raise RuntimeError(f"ledger row order drifted: {ids}")
    return rows


def ledger_totals_policy(*, rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Headline = market+proxy; shadow separate; oil & gas + benchmarks outside both."""
    rows = rows if rows is not None else ledger_rows()
    headline_ids = [
        r["id"]
        for r in rows
        if r.get("stack") == "headline" and not r.get("never_added") and not r.get("outside_scottish_total")
    ]
    shadow_ids = [r["id"] for r in rows if r.get("stack") == "shadow"]
    outside_ids = [r["id"] for r in rows if r.get("stack") == "outside" or r.get("outside_scottish_total")]

    # Until any counted market/proxy range exists, totals stay not_yet (never £0).
    headline_ready = any(
        r["status"] == "counted" and r.get("range") is not None and r["id"] in headline_ids for r in rows
    )
    shadow_ready = any(
        r["status"] == "counted" and r.get("range") is not None and r["id"] in shadow_ids for r in rows
    )

    return {
        "headline": {
            "tiers": ["market", "proxy"],
            "row_ids": headline_ids,
            "status": "counted" if headline_ready else "not_yet",
            "range": None,  # never invent £0 for not_yet
            "note": "Sum of market+proxy rows only; nested 1a never added.",
        },
        "shadow": {
            "row_ids": shadow_ids,
            "status": "counted" if shadow_ready else "not_yet",
            "range": None,
            "never_summed_into_headline": True,
            "note": "Shadow stack drawn separately; never added into the headline.",
        },
        "outside": {
            "oil_gas": {
                "row_ids": outside_ids,
                "status": "not_yet",
                "range": None,
                "note": "UK-reserved — outside Scottish headline and shadow totals.",
            },
            "benchmarks": "benchmark only, not inputs",
        },
    }


def _zone_surface_status(code: str, vintage: int) -> dict[str, Any]:
    """Read latest surface_rent_dz publication fields for a zone (or missing)."""
    sql = (
        "SELECT publication_status, publish_level, quality "
        "FROM surface_rent_dz WHERE code = %s AND vintage = %s "
        "ORDER BY valuation_date DESC LIMIT 1"
    )
    with db.cursor() as cur:
        cur.execute(sql, (code, vintage))
        row = cur.fetchone()
    if row is None:
        return {
            "code": code,
            "vintage": vintage,
            "publication_status": "missing",
            "publish_level": None,
            "quality": None,
        }
    return {
        "code": code,
        "vintage": vintage,
        "publication_status": row.get("publication_status") or "ok",
        "publish_level": row.get("publish_level"),
        "quality": row.get("quality"),
    }


def resolve_ledger_zone(zone_id: str, vintage: int | None = None) -> tuple[str, int]:
    """Validate zone_id → (code, vintage). Raises ValueError with a stable error code."""
    code = (zone_id or "").strip().upper()
    if not dz_lookup.DZ_CODE_RE.match(code):
        raise ValueError("invalid_zone_id")
    inferred = dz_lookup.vintage_for_code(code)
    if inferred is None:
        raise ValueError("zone_id_out_of_range")
    if vintage is not None and vintage != inferred:
        raise ValueError("vintage_mismatch")
    return code, inferred


def ledger_zone_payload(
    zone_id: str,
    vintage: int | None = None,
    *,
    zone_status: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Zone-level ledger. Blocked zones return an empty published=false stub — no £0."""
    code, vin = resolve_ledger_zone(zone_id, vintage)
    status = dict(zone_status) if zone_status is not None else _zone_surface_status(code, vin)
    pub = status.get("publication_status") or "ok"

    if pub == "blocked":
        return {
            "version": 2,
            "kind": "natural_capital_ledger",
            "published": False,
            "reason": "publication_status=blocked — nothing published",
            "grain": "zone-level only; never plots; nothing published for blocked zones",
            "zone": {
                "code": code,
                "vintage": vin,
                "publication_status": "blocked",
            },
            "rows": [],
            "totals": None,
            "checks": [],
            "excluded": [],
            "benchmarks": [],
        }

    rows = ledger_rows(internal=False)
    totals = ledger_totals_policy(rows=rows)
    return {
        **ledger_catalog_base(),
        "published": True,
        "zone": {
            "code": code,
            "vintage": vin,
            "publication_status": pub,
            "publish_level": status.get("publish_level"),
            "quality": status.get("quality"),
        },
        "rows": rows,
        "totals": totals,
        "checks": ledger_checks(),
        "excluded": ledger_excluded(),
        "benchmarks": ledger_benchmarks(),
    }


def ledger_catalog_base() -> dict[str, Any]:
    return {
        "version": 2,
        "kind": "natural_capital_ledger",
        "brief": (
            "Natural capital ledger rows (1–10 + nested 1a), checks, and exclusions. "
            "Driven by this catalog — not a map-panel layer dump."
        ),
        "spec": "georgist-ledger-accounting-rules (ROWS / CHECKS / SCEPTIC NEEDS)",
        "grain": "zone-level only; never plots; nothing published for blocked zones",
        "economic_rules": {
            "approved": ECONOMIC_RULES_APPROVED,
            "document": "docs/ECONOMIC_RULES.md",
            "modelled_agr_gbp_public": ECONOMIC_RULES_APPROVED,
            "note": (
                "Public responses carry row metadata and null ranges until "
                "ECONOMIC_RULES is approved; not_yet is never shown as £0."
            ),
        },
        "benchmark_label": "benchmark only, not inputs",
    }


def ledger_catalog() -> dict[str, Any]:
    """Public catalog payload for the Data section and map ledger HUD."""
    rows = ledger_rows(internal=False)
    return {
        **ledger_catalog_base(),
        "rows": rows,
        "totals": ledger_totals_policy(rows=rows),
        "checks": ledger_checks(),
        "excluded": ledger_excluded(),
        "benchmarks": ledger_benchmarks(),
    }
