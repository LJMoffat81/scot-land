"""Tax scenario tools: internal-only, blocked, £ triples at DZ; approved defaults v0.1."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from georgist.surface_settings import YIELD_SOURCE, yield_placeholder
from georgist.tax_scenarios import (
    BLOCKED_REASON,
    CAPTURE_NOTE,
    DISCLAIMER,
    INTERNAL_WARNING,
    LENS,
    MONEY_GRAIN,
    POLICY_CONFIG,
    PUBLICATION_STATUS,
    TaxScenarioError,
    ZoneRentRow,
    aggregate_by_council,
    apply_deferral,
    assert_no_aggregate_gbp,
    build_aggregate_rollup,
    illustrated_collection,
    load_draft_defaults,
    money_triple,
    parse_capture_rate,
    phase_in_fraction,
    phase_in_schedule,
    resolve_revenue_sharing,
    solve_s1_per_council,
    stamp_blocked,
    zone_illustration,
    zone_row_from_db,
)

API_DIR = Path(__file__).resolve().parents[2] / "api"
PUBLIC_TAX_PATHS = ("/georgist/tax-scenario", "/georgist/tax-scenario/zone")
INTERNAL_TAX_PATHS = (
    "/internal/georgist/tax-scenario",
    "/internal/georgist/tax-scenario/zone",
)
FRONTEND_ROOT = Path(__file__).resolve().parents[3] / "frontend"
CONFIG_ROOT = Path(__file__).resolve().parents[3] / "data" / "config"
GBP_KEYS = ("measured_rent_total_gbp", "illustrated_collection_gbp", "measured_rent_gbp")


def _row(
    code: str = "S01008677",
    la_code: str = "S12000036",
    la_name: str = "City of Edinburgh",
    rent: float = 100_000.0,
    price_year: int = 2025,
    value_tier: str = "proxy",
    deferral_eligible: bool = False,
) -> ZoneRentRow:
    return ZoneRentRow(
        code=code,
        vintage=2011,
        la_code=la_code,
        la_name=la_name,
        measured_rent=rent,
        price_year=price_year,
        value_tier=value_tier,
        deferral_eligible=deferral_eligible,
    )


def _penny(n: float) -> float:
    return round(float(n), 2)


def _internal_client(monkeypatch, *, enabled=True, token: str | None = "test-secret-token"):
    from fastapi.testclient import TestClient

    from api.main import create_app

    if enabled:
        monkeypatch.setenv("ENABLE_INTERNAL_ENDPOINTS", "1")
    else:
        monkeypatch.delenv("ENABLE_INTERNAL_ENDPOINTS", raising=False)
    if token is None:
        monkeypatch.delenv("INTERNAL_API_TOKEN", raising=False)
    else:
        monkeypatch.setenv("INTERNAL_API_TOKEN", token)
    return TestClient(create_app())


def _mini_defaults(edi_target: float, glasgow_target: float) -> dict:
    """Minimal approved defaults for two councils (S1 solve tests)."""
    return {
        "status": "approved_defaults",
        "label": "approved defaults (v0.1, Oct 2026)",
        "approval": "approved_laurie_v0_1_oct_2026",
        "version": "0.1",
        "approved": "2026-10",
        "configurable": True,
        "owner": "Georgist",
        "exemptions": {"ownership_based": False, "shadow_taxed": False},
        "deferral": {"low_income_home_owners": True, "rate": 0.0262},
        "phase_in": {"points_per_year": 10},
        "revenue_sharing": {"council_share": 0.5, "dividend_share": 0.5},
        "display_while_blocked": {
            "gbp_grain": "data_zone_only",
            "council_views": "counts_only",
            "build_council_scotland_rollup": True,
        },
        "scenarios": {
            "S1": {
                "id": "S1",
                "mode": "revenue_swap_solved_rate",
                "scope": "per_council",
                "national_single_rate": {"enabled": False, "id": "S1_national"},
            },
            "S2": {"id": "S2", "mode": "fixed_capture_rate", "capture_rate": 0.50},
            "S3": {"id": "S3", "mode": "fixed_capture_rate", "capture_rate": 0.85},
        },
        "fiscal_targets": {
            "by_council": [
                {
                    "la_code": "S12000036",
                    "la_name": "City of Edinburgh",
                    "council_tax_gbp": edi_target / 2,
                    "business_rates_gbp": edi_target / 2,
                },
                {
                    "la_code": "S12000049",
                    "la_name": "Glasgow City",
                    "council_tax_gbp": glasgow_target / 2,
                    "business_rates_gbp": glasgow_target / 2,
                },
            ],
        },
    }


def test_parse_capture_rate_bounds():
    assert parse_capture_rate(0) == 0.0
    assert parse_capture_rate("0.5") == 0.5
    assert parse_capture_rate(1) == 1.0
    with pytest.raises(TaxScenarioError) as exc:
        parse_capture_rate(1.01)
    assert exc.value.code == "invalid_capture_rate"


def test_illustrated_collection_is_product():
    assert illustrated_collection(100_000.0, 0.25) == 25_000.0


def test_money_triple_scales_with_yield_band():
    t = money_triple(100.0, yield_central=0.04499, band_low=0.0398, band_high=0.0450)
    assert t["central"] == 100.0
    assert t["low"] == round(100.0 * 0.0398 / 0.04499, 2)
    assert t["high"] == round(100.0 * 0.0450 / 0.04499, 2)


def test_aggregate_money_is_data_zone_only_not_council_sums():
    rows = [
        _row("S01008677", rent=100_000.0),
        _row("S01008678", rent=50_000.0),
        _row("S01009000", la_code="S12000049", la_name="Glasgow City", rent=200_000.0),
    ]
    defaults = _mini_defaults(edi_target=75_000.0, glasgow_target=100_000.0)
    out = aggregate_by_council(rows, capture_rate=0.5, scenario_id="S2", defaults=defaults)
    assert out["lens"] == LENS
    assert out["disclaimer"] == DISCLAIMER
    assert out["capture_note"] == CAPTURE_NOTE
    assert out["publication_status"] == PUBLICATION_STATUS == "blocked"
    assert out["internal"] is True
    assert out["money_grain"] == MONEY_GRAIN == "data_zone"
    assert "surface.yaml" in out["blocked_reason"]
    assert "hardcode" in out["blocked_reason"]
    shared = yield_placeholder()
    assert out["yield_placeholder"]["status"] == "placeholder"
    assert out["yield_placeholder"]["land_yield"] == shared["land_yield"]
    assert out["yield_placeholder"]["central"] == shared["central"]
    assert out["yield_placeholder"]["owner"] == "Valuation"
    assert out["yield_placeholder"]["source"] == YIELD_SOURCE
    assert "PLACEHOLDER" in out["yield_placeholder"]["note"].upper() or "placeholder" in out["yield_placeholder"]["note"].lower()
    assert out["warning"] == INTERNAL_WARNING
    assert out["policy_config"]["status"] == "approved_defaults"
    assert out["policy_config"]["label"] == "approved defaults (v0.1, Oct 2026)"
    assert out["policy_config"]["approval"] == "approved_laurie_v0_1_oct_2026"
    assert out["policy_config"]["version"] == "0.1"
    assert out["policy_config"]["configurable"] is True
    assert out["policy_config"]["owner"] == "Georgist"
    assert out["policy_config"]["separate_from_measured_land_values"] is True
    assert out["policy_config"]["exemptions"]["ownership_based"] is False
    assert out["policy_config"]["exemptions"]["shadow_taxed"] is False
    assert out["policy_config"]["deferral"]["rate"] == pytest.approx(0.0262)
    assert out["policy_config"]["phase_in"]["points_per_year"] == 10
    assert out["revenue_sharing"]["council_share"] == 0.5
    assert out["revenue_sharing"]["dividend_share"] == 0.5

    # National / council: counts only — no £
    assert out["national"]["zone_count"] == 3
    for key in GBP_KEYS:
        assert key not in out["national"]
    for c in out["by_council"]:
        for key in GBP_KEYS:
            assert key not in c
        assert c["zone_count"] >= 1
        assert c["zone_codes"]

    # £ only on by_zone as low/central/high triples + tags
    by_code = {z["code"]: z for z in out["by_zone"]}
    z = by_code["S01008677"]
    assert set(z["measured_rent_gbp"]) == {"low", "central", "high"}
    assert z["measured_rent_gbp"]["central"] == 100_000.0
    assert set(z["illustrated_collection_gbp"]) == {"low", "central", "high"}
    assert z["illustrated_collection_gbp"]["central"] == 50_000.0  # S2 = 50%
    assert z["value_tier"] == "proxy"
    assert z["tag"] == "proxy"
    assert z["money_grain"] == "data_zone"
    assert_no_aggregate_gbp(out)

    # Roll-up built behind TEMP setting; Σ councils = Scotland (exact to the penny)
    rollup = out["blocked_aggregate_rollup"]
    sum_c = _penny(sum(c["measured_rent_gbp"]["central"] for c in rollup["by_council"]))
    assert sum_c == rollup["scotland"]["measured_rent_gbp"]["central"]
    assert rollup["zone_count"] == 3


def test_zone_illustration_gbp_on_zone_only():
    z = _row(rent=25_000.0)
    defaults = _mini_defaults(12_500.0, 1.0)
    out = zone_illustration(z, capture_rate=0.2, council_zone_count=4, scenario_id="S2", defaults=defaults)
    assert out["zone"]["illustrated_collection_gbp"]["central"] == 12_500.0  # S2 forces 50%
    assert out["zone"]["measured_rent_gbp"]["central"] == 25_000.0
    assert out["zone"]["tag"] == "proxy"
    assert out["publication_status"] == "blocked"
    assert out["money_grain"] == "data_zone"
    assert out["yield_placeholder"]["source"] == YIELD_SOURCE
    for key in GBP_KEYS:
        assert key not in out["council"]
    assert out["council"]["zone_count"] == 4
    assert_no_aggregate_gbp(out)


def test_shadow_never_taxed():
    rows = [
        _row("S01008677", rent=100_000.0, value_tier="proxy"),
        _row("S01008678", rent=80_000.0, value_tier="shadow"),
    ]
    defaults = _mini_defaults(50_000.0, 1.0)
    out = aggregate_by_council(rows, scenario_id="S2", defaults=defaults)
    by_code = {z["code"]: z for z in out["by_zone"]}
    assert by_code["S01008677"]["illustrated_collection_gbp"]["central"] == 50_000.0
    assert by_code["S01008678"]["taxable"] is False
    assert by_code["S01008678"]["tag"] == "shadow"
    assert by_code["S01008678"]["illustrated_collection_gbp"]["central"] == 0.0


def test_s1_rate_differs_by_council_and_revenue_equals_ct_plus_nbr():
    """Done-when: S1 rate differs by council; each council S1 revenue = CT + business rates."""
    rows = [
        _row("S01008677", la_code="S12000036", la_name="City of Edinburgh", rent=200_000.0),
        _row("S01008678", la_code="S12000036", la_name="City of Edinburgh", rent=100_000.0),
        _row("S01009000", la_code="S12000049", la_name="Glasgow City", rent=400_000.0),
        _row("S01009001", la_code="S12000049", la_name="Glasgow City", rent=100_000.0, value_tier="shadow"),
    ]
    # Edinburgh taxable 300k → target 60k → rate 0.2
    # Glasgow taxable 400k (shadow excluded) → target 200k → rate 0.5
    defaults = _mini_defaults(edi_target=60_000.0, glasgow_target=200_000.0)
    solved = solve_s1_per_council(rows, defaults=defaults)
    assert solved["S12000036"]["s1_rate"] == pytest.approx(0.2)
    assert solved["S12000049"]["s1_rate"] == pytest.approx(0.5)
    assert solved["S12000036"]["s1_rate"] != solved["S12000049"]["s1_rate"]
    assert solved["S12000036"]["s1_revenue_central_gbp"] == pytest.approx(60_000.0)
    assert solved["S12000049"]["s1_revenue_central_gbp"] == pytest.approx(200_000.0)
    assert solved["S12000036"]["s1_revenue_central_gbp"] == pytest.approx(
        solved["S12000036"]["council_tax_gbp"] + solved["S12000036"]["business_rates_gbp"]
    )
    assert solved["S12000049"]["s1_revenue_central_gbp"] == pytest.approx(
        solved["S12000049"]["council_tax_gbp"] + solved["S12000049"]["business_rates_gbp"]
    )

    out = aggregate_by_council(rows, scenario_id="S1", defaults=defaults)
    assert out["s1_national_single_rate"]["enabled"] is False
    assert out["s1_national_single_rate"]["default"] is False
    rates = {c["la_code"]: c["s1_rate"] for c in out["by_council"]}
    assert rates["S12000036"] != rates["S12000049"]
    by_code = {z["code"]: z for z in out["by_zone"]}
    assert by_code["S01008677"]["illustrated_collection_gbp"]["central"] == pytest.approx(40_000.0)
    assert by_code["S01009001"]["illustrated_collection_gbp"]["central"] == 0.0  # shadow


def test_rollup_councils_sum_to_scotland_each_zone_once():
    rows = [
        _row("S01010117", la_code="S12000049", la_name="Glasgow City", rent=10_000.0),  # spine example
        _row("S01008677", rent=20_000.0),
        _row("S01008678", rent=5_000.0),
    ]
    rate_by_zone = {r.code: 0.5 for r in rows}
    rollup = build_aggregate_rollup(rows, rate_by_zone=rate_by_zone)
    sum_c = _penny(sum(c["measured_rent_gbp"]["central"] for c in rollup["by_council"]))
    assert sum_c == rollup["scotland"]["measured_rent_gbp"]["central"]
    assert sum_c == 35_000.0
    all_codes = [code for c in rollup["by_council"] for code in c["zone_codes"]]
    assert len(all_codes) == len(set(all_codes)) == 3
    glasgow = next(c for c in rollup["by_council"] if c["la_code"] == "S12000049")
    assert "S01010117" in glasgow["zone_codes"]


def test_phase_in_year_by_year_schedule_applied_at_data_zone():
    """10 pts/year schedule produces LCH triples; year 3 applies 30% of full collection."""
    assert phase_in_fraction(1, 10) == 0.1
    assert phase_in_fraction(10, 10) == 1.0
    assert phase_in_fraction(11, 10) == 1.0
    full = {"low": 886.0, "central": 1000.0, "high": 1002.0}
    schedule = phase_in_schedule(full, points_per_year=10)
    assert len(schedule) == 10
    assert schedule[0]["year"] == 1 and schedule[0]["points"] == 10
    assert schedule[0]["illustrated_collection_gbp"] == {"low": 88.6, "central": 100.0, "high": 100.2}
    assert schedule[2]["year"] == 3 and schedule[2]["applied_fraction"] == 0.3
    assert schedule[2]["illustrated_collection_gbp"]["central"] == 300.0
    assert schedule[-1]["illustrated_collection_gbp"] == full

    defaults = _mini_defaults(1.0, 1.0)
    out = aggregate_by_council(
        [_row(rent=10_000.0)],
        scenario_id="S2",
        defaults=defaults,
        phase_in_year=3,
    )
    z = out["by_zone"][0]
    # S2 = 50% → full collection 5000; year 3 = 30% → 1500
    assert z["illustrated_collection_full_gbp"]["central"] == 5_000.0
    assert z["illustrated_collection_gbp"]["central"] == 1_500.0
    assert z["phase_in"]["applied_year"] == 3
    assert z["phase_in"]["applied_fraction"] == 0.3
    assert len(z["phase_in"]["schedule"]) == 10
    assert z["phase_in"]["schedule"][0]["illustrated_collection_gbp"]["central"] == 500.0
    assert out["phase_in"]["applied_year"] == 3


def test_deferral_eligibility_amount_and_accrual():
    """Eligible low-income home owner: defer collection; accrue at 2.62%/year."""
    collection = {"low": 886.0, "central": 1000.0, "high": 1002.0}
    deferred = apply_deferral(collection, eligible=True, rate=0.0262, enabled=True)
    assert deferred["deferral_eligible"] is True
    assert deferred["deferral_applied"] is True
    assert deferred["deferred_gbp"] == collection
    assert deferred["cash_collected_gbp"] == {"low": 0.0, "central": 0.0, "high": 0.0}
    assert deferred["accrual_gbp_per_year"] == {
        "low": _penny(886.0 * 0.0262),
        "central": _penny(1000.0 * 0.0262),
        "high": _penny(1002.0 * 0.0262),
    }
    not_eligible = apply_deferral(collection, eligible=False, rate=0.0262, enabled=True)
    assert not_eligible["deferral_applied"] is False
    assert not_eligible["deferred_gbp"]["central"] == 0.0
    assert not_eligible["cash_collected_gbp"] == collection

    defaults = _mini_defaults(1.0, 1.0)
    out = aggregate_by_council(
        [_row(rent=10_000.0, deferral_eligible=True)],
        scenario_id="S2",
        defaults=defaults,
        phase_in_year=10,  # fully phased
    )
    z = out["by_zone"][0]
    # S2 50% of 10k = 5000 deferred
    assert z["deferral"]["deferral_eligible"] is True
    assert z["deferral"]["deferred_gbp"]["central"] == 5_000.0
    assert z["deferral"]["accrual_gbp_per_year"]["central"] == _penny(5_000.0 * 0.0262)
    assert z["deferral"]["cash_collected_gbp"]["central"] == 0.0


def test_revenue_share_override_must_sum_to_one_and_splits_per_dz():
    defaults = _mini_defaults(1.0, 1.0)
    with pytest.raises(TaxScenarioError) as exc:
        resolve_revenue_sharing(defaults, {"council_share": 0.6, "dividend_share": 0.5})
    assert exc.value.code == "invalid_revenue_share"

    sharing = resolve_revenue_sharing(defaults, {"council_share": 0.6, "dividend_share": 0.4})
    assert sharing["council_share"] == 0.6
    assert sharing["dividend_share"] == 0.4
    assert sharing["source"] == "request"

    out = aggregate_by_council(
        [_row(rent=10_000.0)],
        scenario_id="S2",
        defaults=defaults,
        revenue_sharing={"council_share": 0.6, "dividend_share": 0.4},
    )
    assert out["revenue_sharing"]["council_share"] == 0.6
    assert out["revenue_sharing"]["source"] == "request"
    z = out["by_zone"][0]
    # S2 → 5000 collection; 60/40 split
    assert z["revenue_sharing"]["council_share_gbp"]["central"] == 3_000.0
    assert z["revenue_sharing"]["dividend_share_gbp"]["central"] == 2_000.0
    assert (
        z["revenue_sharing"]["council_share_gbp"]["central"]
        + z["revenue_sharing"]["dividend_share_gbp"]["central"]
        == z["illustrated_collection_gbp"]["central"]
    )


def test_surface_yaml_has_no_land_yield_005():
    raw = (CONFIG_ROOT / "surface.yaml").read_text(encoding="utf-8")
    cfg = yaml.safe_load(raw)["surface_rent"]["yield"]
    assert "land_yield" not in cfg
    assert "land_yield: 0.05" not in yaml.dump(cfg)
    assert cfg["central"] == pytest.approx(0.04499)
    assert cfg["band"]["low"] == pytest.approx(0.0398)
    assert cfg["band"]["high"] == pytest.approx(0.0450)
    assert 0.05 not in (cfg["central"], cfg["band"]["low"], cfg["band"]["high"])
    assert cfg["central_at_cap"] is True
    assert cfg["band_clipped_outer"] is True
    assert cfg["bed_mapping_sensitive"] is True
    assert cfg["result_hash"] == "4654e513"


def test_draft_defaults_file_loads():
    cfg = load_draft_defaults()
    assert cfg["status"] == "approved_defaults"
    assert cfg["approval"] == "approved_laurie_v0_1_oct_2026"
    assert cfg["label"] == "approved defaults (v0.1, Oct 2026)"
    assert cfg["version"] == "0.1"
    assert cfg["configurable"] is True
    assert cfg["scenarios"]["S2"]["capture_rate"] == 0.5
    assert cfg["scenarios"]["S3"]["capture_rate"] == 0.85
    assert cfg["scenarios"]["S1"]["national_single_rate"]["enabled"] is False
    assert cfg["deferral"]["rate"] == pytest.approx(0.0262)
    assert cfg["phase_in"]["points_per_year"] == 10
    fiscal = cfg["fiscal_targets"]
    assert fiscal["targets_status"] == "loaded"
    assert fiscal["status"] == "sg_local_government_finance"
    assert fiscal["council_tax"]["year"] == "2024-25"
    assert "OGL" in fiscal["council_tax"]["source"]
    assert "SLGFS" in fiscal["council_tax"]["source"] or "Table I" in fiscal["council_tax"]["source"]
    assert "OGL" in fiscal["business_rates"]["source"]
    assert len(fiscal["by_council"]) == 32
    for row in fiscal["by_council"]:
        assert row["council_tax_gbp"] > 0
        assert row["business_rates_gbp"] > 0
        assert row["council_tax_year"]
        assert row["business_rates_year"]
        assert row["council_tax_source"]
        assert row["business_rates_source"]
    ct = sum(r["council_tax_gbp"] for r in fiscal["by_council"])
    nbr = sum(r["business_rates_gbp"] for r in fiscal["by_council"])
    assert ct == fiscal["national"]["council_tax_gbp"] == 2_996_849_000
    assert nbr == fiscal["national"]["business_rates_gbp"] == 3_079_138_735
    # S1 must not carry the placeholder-targets label once SG figures are loaded
    from georgist.tax_scenarios import policy_config_payload

    pc = policy_config_payload(cfg)
    assert pc["fiscal_targets_status"] == "sg_local_government_finance"
    assert "placeholder targets" not in pc["scenarios"]["S1"]["label"].lower()
    assert "placeholder targets" not in pc["note"].lower()


def test_s1_placeholder_targets_label_when_fiscal_not_loaded():
    defaults = _mini_defaults(60_000.0, 200_000.0)
    # mini defaults omit SG status → placeholder_targets
    from georgist.tax_scenarios import policy_config_payload

    pc = policy_config_payload(defaults)
    assert pc["fiscal_targets_status"] == "placeholder_targets"
    assert "placeholder targets" in pc["scenarios"]["S1"]["label"].lower()
    out = aggregate_by_council(
        [_row(rent=300_000.0)],
        scenario_id="S1",
        defaults=defaults,
    )
    assert out["s1_targets_status"] == "placeholder_targets"
    assert "placeholder targets" in out["s1_label"].lower()


def test_assert_no_aggregate_gbp_refuses_council_money():
    with pytest.raises(TaxScenarioError) as exc:
        assert_no_aggregate_gbp({"council": {"illustrated_collection_gbp": 1.0}})
    assert exc.value.code == "aggregate_gbp_forbidden"


def test_stamp_blocked_includes_yield_placeholder_and_policy_config():
    stamped = stamp_blocked({"national": {}, "by_council": [{"la_code": "S"}]})
    assert stamped["publication_status"] == "blocked"
    assert stamped["yield_placeholder"]["source"] == YIELD_SOURCE
    assert "yield_calibration_pending" in stamped["blocked_reason"]
    assert BLOCKED_REASON == stamped["blocked_reason"]
    assert stamped["policy_config"]["status"] == "approved_defaults"
    assert stamped["policy_config"]["approval"] == "approved_laurie_v0_1_oct_2026"
    assert "v0.1" in CAPTURE_NOTE or "v0.1" in stamped["policy_config"]["note"]


def test_tax_scenarios_does_not_hardcode_land_yield():
    """Defer to shared surface.yaml; do not embed a numeric yield rate in this module."""
    src = (API_DIR.parent / "georgist" / "tax_scenarios.py").read_text(encoding="utf-8")
    assert "land_yield\": 0.05" not in src
    assert "land_yield\": 0.0399" not in src
    assert '"land_yield": 0.05' not in src
    assert "configured 5%" not in src
    assert "yield_placeholder" in src and "from georgist.surface_settings import yield_placeholder" in src


def test_yield_placeholder_reads_shared_config_and_v3_passthrough():
    from georgist.surface_settings import yield_placeholder as yp_fn

    base = yp_fn()
    assert base["status"] == "placeholder" and base["owner"] == "Valuation"
    assert base["central"] == pytest.approx(0.04499)
    assert base["land_yield"] == pytest.approx(0.04499)
    assert base["land_yield_band"] == [0.0398, 0.0450]
    assert base["result_hash"] == "4654e513"
    assert base["central_at_cap"] is True
    assert abs(base["land_yield"] - 0.05) > 1e-12
    with_v3 = yp_fn({
        "yield": {
            "central": 0.04499,
            "land_yield_band": [0.0398, 0.0450],
            "result_hash": "4654e513",
            "calibration_version": 3,
            "central_at_cap": True,
            "band_clipped_outer": True,
            "bed_mapping_sensitive": True,
        },
    })
    assert with_v3["land_yield"] == pytest.approx(0.04499)
    assert with_v3["land_yield_band"] == [0.0398, 0.0450]
    assert with_v3["result_hash"] == "4654e513"
    assert with_v3["central_at_cap"] is True
    assert with_v3["band_clipped_outer"] is True
    assert with_v3["bed_mapping_sensitive"] is True
    assert set(with_v3["flags"]) == {
        "central_at_cap", "band_clipped_outer", "bed_mapping_sensitive",
    }


def test_aggregate_refuses_mixed_price_years():
    rows = [_row(price_year=2025), _row("S01008678", price_year=2024)]
    with pytest.raises(TaxScenarioError) as exc:
        aggregate_by_council(rows, capture_rate=1.0, defaults=_mini_defaults(1.0, 1.0))
    assert exc.value.code == "mixed_price_years"


def test_aggregate_la_filter():
    rows = [
        _row(rent=10_000.0),
        _row("S01009000", la_code="S12000049", la_name="Glasgow City", rent=99_000.0),
    ]
    out = aggregate_by_council(
        rows, capture_rate=1.0, la_code="S12000036", scenario_id="S3",
        defaults=_mini_defaults(1.0, 1.0),
    )
    assert out["national"]["zone_count"] == 1
    assert len(out["by_zone"]) == 1
    assert out["by_zone"][0]["measured_rent_gbp"]["central"] == 10_000.0
    assert out["by_zone"][0]["illustrated_collection_gbp"]["central"] == 8_500.0  # S3 85%


def test_zone_row_from_db_filters_unpublishable_and_zero_dwellings():
    base = {
        "code": "S01008677",
        "vintage": 2011,
        "measured_rent": 12_000.0,
        "price_year": 2025,
        "quality": "derived",
        "publish_level": "public_zone",
        "publication_status": "ok",
        "value_tier": "market",
        "la_code": "S12000036",
        "la_name": "City of Edinburgh",
        "flags": "",
    }
    z = zone_row_from_db(base)
    assert z is not None and z.value_tier == "market"
    assert zone_row_from_db({**base, "quality": "placeholder"}) is None
    assert zone_row_from_db({**base, "flags": "zero_dwellings"}) is None


def test_public_tax_scenario_paths_absent_from_default_app():
    from api.main import app, registered_routes

    paths = {p for _, p in registered_routes(app)}
    for path in PUBLIC_TAX_PATHS:
        assert path not in paths
    for path in INTERNAL_TAX_PATHS:
        assert path not in paths


def test_public_tax_scenario_paths_not_declared_as_public_layers():
    from georgist import publication_rules as pr

    for path in PUBLIC_TAX_PATHS:
        assert path not in pr.PUBLIC_ROUTE_RULES
    assert pr.undeclared(list(INTERNAL_TAX_PATHS)) == []


def test_wealth_routes_source_has_no_tax_scenario_decorators():
    tree = ast.parse((API_DIR / "wealth_routes.py").read_text(encoding="utf-8"))
    decorated = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                if (
                    isinstance(dec, ast.Call)
                    and dec.args
                    and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)
                    and "tax-scenario" in dec.args[0].value
                ):
                    decorated.append(dec.args[0].value)
    assert decorated == []


def test_internal_tax_routes_registered_when_enabled(monkeypatch):
    from api.main import registered_routes

    c = _internal_client(monkeypatch, enabled=True, token="tok")
    paths = {p for _, p in registered_routes(c.app)}
    for path in INTERNAL_TAX_PATHS:
        assert path in paths
    for path in PUBLIC_TAX_PATHS:
        assert path not in paths


def test_public_paths_404_even_when_internal_enabled(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="tok")
    for path in PUBLIC_TAX_PATHS:
        r = c.get(path, headers={"Authorization": "Bearer tok"})
        assert r.status_code == 404, path


def test_internal_tax_scenario_requires_auth(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="correct")
    r = c.get("/internal/georgist/tax-scenario")
    assert r.status_code == 401


def test_internal_tax_scenario_flag_off_is_404(monkeypatch):
    c = _internal_client(monkeypatch, enabled=False, token="correct")
    assert c.get("/internal/georgist/tax-scenario", headers={"Authorization": "Bearer correct"}).status_code == 404


def test_internal_tax_scenario_503_without_db(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="correct")
    bad = c.get(
        "/internal/georgist/tax-scenario",
        params={"capture_rate": 2},
        headers={"Authorization": "Bearer correct"},
    )
    assert bad.status_code == 422
    r = c.get(
        "/internal/georgist/tax-scenario",
        params={"vintage": "2011", "capture_rate": 0.5, "scenario_id": "S2"},
        headers={"Authorization": "Bearer correct"},
    )
    assert r.status_code == 503


def test_internal_tax_scenario_zone_rejects_unknown_zone(monkeypatch):
    c = _internal_client(monkeypatch, enabled=True, token="correct")
    r = c.get(
        "/internal/georgist/tax-scenario/zone",
        params={"zone_id": "unknown"},
        headers={"Authorization": "Bearer correct"},
    )
    assert r.status_code == 422


def test_frontend_has_no_public_tax_scenario_panel():
    inspector = (FRONTEND_ROOT / "components" / "WealthInspector.tsx").read_text(encoding="utf-8")
    assert "TaxScenarioPanel" not in inspector
    assert not (FRONTEND_ROOT / "components" / "TaxScenarioPanel.tsx").exists()
    wealth_api = (FRONTEND_ROOT / "lib" / "useWealthApi.ts").read_text(encoding="utf-8")
    assert "/georgist/tax-scenario" not in wealth_api
    assert "fetchTaxScenario" not in wealth_api
    # Internal-only panel (gated like ledger-panel; not under app/internal/ — public repo).
    panel_page = FRONTEND_ROOT / "app" / "tax-scenario-panel" / "page.tsx"
    assert panel_page.exists()
    text = panel_page.read_text(encoding="utf-8")
    assert "blocked" in text.lower()
    assert "approved defaults (v0.1, oct 2026)" in text.lower()
    view = (FRONTEND_ROOT / "components" / "InternalTaxScenarioView.tsx").read_text(encoding="utf-8")
    assert "ConfidenceTag" in view
    assert "confidence-tag" in view or 'data-testid="confidence-tag"' in view or "ConfidenceTag" in view
    # No tracked frontend path may use an internal/ folder (publishability).
    assert not (FRONTEND_ROOT / "app" / "internal").exists()


def test_internal_frontend_gated_and_no_hardcoded_demo_gbp():
    """BLOCKS DEPLOY: tax-scenario panel gated; must not hard-code demo £."""
    layout = FRONTEND_ROOT / "app" / "tax-scenario-panel" / "layout.tsx"
    assert layout.exists()
    layout_text = layout.read_text(encoding="utf-8")
    assert "internalUiEnabled" in layout_text
    assert "notFound" in layout_text

    page = (FRONTEND_ROOT / "app" / "tax-scenario-panel" / "page.tsx").read_text(encoding="utf-8")
    for banned in ("8860", "10000", "10022", "17720", "20000", "20045", "4430", "5000", "5011"):
        assert banned not in page, f"hard-coded demo amount {banned} must not appear on /tax-scenario-panel"
    assert "DEMO_ZONES" not in page
    assert "measured_rent_gbp" not in page  # no inline demo triples
    # Public site cannot reach the panel without the flag (gate is the layout).
    ui = (FRONTEND_ROOT / "lib" / "internalUi.ts").read_text(encoding="utf-8")
    assert "NEXT_PUBLIC_ENABLE_INTERNAL_UI" in ui
    assert "=== \"1\"" in ui or "=== '1'" in ui
    # Publishability: no tracked file under an internal/ folder.
    assert not (FRONTEND_ROOT / "app" / "internal").exists()
