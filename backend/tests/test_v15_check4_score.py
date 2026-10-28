"""V15-CHECK4-SCORE synthetic tests (S1-S8): non-GBP Check 4 score summary, rerun_v14_score --check4-f8 wiring, and committed report guard."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from georgist.surface_paths import REPO_ROOT
from georgist.v14_check4_route import (
    ADDENDUM5_DOC,
    ADDENDUM5_SHA256,
    ADDENDUM5_SIGNATURES_DOC,
    ADDENDUM5_SIGNATURES_SHA256,
    BRMA_NAME_DISCLOSURE,
    Check4RouteError,
    PIN_TABLE,
    assert_non_gbp_report,
    build_v15_check4_score_report,
    score_check4_non_gbp,
)
from georgist.v14_score_report import (
    PIN_TABLE as MERGE_PINS,
    RECORDED_FILES,
    build_report,
    sha256_file,
)
from scripts.rerun_v14_score import main as score_main
from test_v14_gaps_pr2_lock import _args, _layout

COMMITTED_REPORT = REPO_ROOT / "data" / "processed" / "methods_code_1" / "v15_check4_score" / "report.json"


def _synthetic_zones(*, pass_check4: bool = True, sentinel_offset: float = 0.0) -> list[dict]:
    zones: list[dict] = []
    for idx in range(12):
        ur6 = (idx % 6) + 1
        cap = 100.0 + float(idx) + sentinel_offset
        res = (105.0 + float(idx) + sentinel_offset) if pass_check4 else (0.0 if ur6 == 6 else 30.0)
        zones.append(
            {
                "zone": f"S0100{idx:04d}",
                "year": 2023,
                "ur6": ur6,
                "price": 250.0 + float(idx),
                "share": 0.22,
                "share_low": 0.15,
                "share_central": 0.22,
                "share_high": 0.30,
                "land_per_home": res,
                "residual_land": res,
                "capitalised_land": cap,
                "dz2022": f"S0101{idx:04d}",
                "detached_plot_m2": 200.0,
                "house_plot_m2": 100.0,
                "pass_at_all_homes": {20: True, 30: True, 40: True},
                "pass_at_dz22": {20: True, 30: True, 40: True},
                "unavailable": bool(not pass_check4 and ur6 == 6),
                "model_failure": False,
                "count_in_1d": True,
            }
        )
    return zones


def test_s1_score_check4_non_gbp_strips_money_medians_and_preserves_verdict() -> None:
    """S1: score_check4_non_gbp strips residual_median/class_residual_medians and computes exact relative gaps."""
    passing = score_check4_non_gbp(_synthetic_zones(pass_check4=True))
    assert passing["check"] == "4"
    assert passing["status"] == "pass"
    assert passing["pass"] is True
    assert passing["reason"] is None
    assert passing["n_zones"] == 12
    assert passing["n_unavailable"] == 0
    assert passing["residual_median_positive"] is True
    assert passing["national_within_band"] is True
    assert all(passing["class_residual_median_positive"][str(k)] is True for k in range(1, 7))
    assert all(passing["by_ur6"][str(k)]["within_class_band"] is True for k in range(1, 7))
    assert "residual_median" not in passing
    assert "class_residual_medians" not in passing

    failing = score_check4_non_gbp(_synthetic_zones(pass_check4=False))
    assert failing["status"] == "fail"
    assert failing["pass"] is False
    assert failing["reason"] == "residual_route_median_non_positive_ur6_6"
    assert failing["n_unavailable"] == 2
    assert failing["class_residual_median_positive"]["6"] is False
    assert failing["by_ur6"]["6"]["within_class_band"] is False
    assert failing["national_within_band"] is False
    assert "residual_median" not in failing
    assert "class_residual_medians" not in failing


def test_s2_build_v15_check4_score_report_and_refusals() -> None:
    """S2: build_v15_check4_score_report enforces schema, cancellation <= 1e-12, and coverage identities."""
    p_zones = _synthetic_zones(pass_check4=True)
    s_zones = _synthetic_zones(pass_check4=False)
    report = build_v15_check4_score_report(
        primary_zones=p_zones,
        secondary_zones=s_zones,
        pins=PIN_TABLE,
        year=2023,
        lookup_zones=15,
        not_scored_zones=3,
        secondary_scored_zones=10,
        secondary_no_cell_zones=2,
        brma_count=18,
        bands_per_brma=4,
        plus4_applied_zones=4,
        cancellation_zones_checked=12,
        cancellation_max_rel_err=1e-14,
    )
    assert report["kind"] == "v15_check4_score_report_v1"
    assert report["publish_level"] == "internal"
    assert report["gbp_display"] is False
    assert report["status"] == "scored"
    assert report["previous_v14_status"] == "NOT_RUN"
    assert report["method_authority"] == {
        "addendum": ADDENDUM5_DOC,
        "addendum_sha256": ADDENDUM5_SHA256,
        "signatures": ADDENDUM5_SIGNATURES_DOC,
        "signatures_sha256": ADDENDUM5_SIGNATURES_SHA256,
    }
    assert report["cancellation_identity"]["pass"] is True
    assert report["primary"]["pass"] is True
    assert report["secondary"]["pass"] is False
    assert report["publication"]["outcome"] == "publish_primary_only"
    assert report["disclosures"]["brma_name_map"] == BRMA_NAME_DISCLOSURE

    with pytest.raises(Check4RouteError) as exc_cancel:
        build_v15_check4_score_report(
            primary_zones=p_zones,
            secondary_zones=s_zones,
            pins=PIN_TABLE,
            year=2023,
            lookup_zones=15,
            not_scored_zones=3,
            secondary_scored_zones=10,
            secondary_no_cell_zones=2,
            cancellation_max_rel_err=2e-12,
        )
    assert (
        str(exc_cancel.value)
        == "V14_CHECK4: REFUSED: cancellation identity: expected rel_err <= 1e-12, got out of range"
    )

    with pytest.raises(Check4RouteError) as exc_cov:
        build_v15_check4_score_report(
            primary_zones=p_zones,
            secondary_zones=s_zones,
            pins=PIN_TABLE,
            year=2023,
            lookup_zones=16,
            not_scored_zones=3,
            secondary_scored_zones=10,
            secondary_no_cell_zones=2,
        )
    assert (
        str(exc_cov.value)
        == "V14_CHECK4: ERROR: coverage: expected lookup minus not_scored == priced_zones, got mismatch"
    )


def test_s3_assert_non_gbp_report_refuses_money_keys_and_currency_tokens() -> None:
    """S3: assert_non_gbp_report refuses money keys and currency substrings."""
    for bad_key in ("residual_median", "class_residual_medians", "land_per_home", "total_gbp"):
        with pytest.raises(Check4RouteError) as exc:
            assert_non_gbp_report({"nested": {bad_key: 1.0}})
        assert str(exc.value) == f"V14_CHECK4: REFUSED: report key {bad_key}: expected non-GBP summary key, got money key"

    for bad_val in ("\u00a3100", "100 GBP", "100 Pounds"):
        with pytest.raises(Check4RouteError) as exc_v:
            assert_non_gbp_report({"note": bad_val})
        assert str(exc_v.value) == "V14_CHECK4: REFUSED: report text: expected non-GBP text, got currency token"


def test_s4_recorded_files_includes_v14_check4_route() -> None:
    """S4: v14_score_report RECORDED_FILES includes backend/georgist/v14_check4_route.py."""
    rel = "backend/georgist/v14_check4_route.py"
    assert rel in RECORDED_FILES
    report = build_report(commit="abc12345")
    assert rel in report["sha8"]
    assert report["sha8"][rel] == sha256_file(REPO_ROOT / rel)[:8]


def test_s5_rerun_v14_score_accepts_check4_f8_and_writes_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S5: rerun_v14_score --holdout-2023 accepts --check4-f8 and --check4-summary-out."""
    paths = _layout(tmp_path)
    zones = _synthetic_zones(pass_check4=True)
    paths["checks"].write_text(
        json.dumps({"primary_zones": zones, "secondary_zones": zones}),
        encoding="utf-8",
    )
    f8_file = tmp_path / "check4_f8.json"
    f8_file.write_text(
        json.dumps(
            {
                "schema": "v14_check4_f8_v1",
                "zones": [
                    {
                        "zone": z["zone"],
                        "capitalised_property": 200.0,
                        "drc": 100.0,
                        "capitalised_land": 100.0,
                    }
                    for z in zones
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(paths["merge_map"]))
    out = tmp_path / "holdout" / "report.json"
    summary_out = tmp_path / "holdout" / "check4_summary.json"
    argv = [
        "--out",
        str(out),
        "--holdout-2023",
        "--check-inputs",
        str(paths["checks"]),
        "--lock-path",
        str(paths["lock"]),
        "--merge-map",
        str(paths["merge_map"]),
        "--hedonic-coefs",
        str(paths["coefs"]),
        "--sha8-block",
        str(paths["sha8"]),
        "--check3-plot-passes",
        str(paths["check3"]),
        "--check4-f8",
        str(f8_file),
        "--ur6",
        str(paths["ur6"]),
        "--dz2022-keys",
        str(paths["dz"]),
        "--check4-summary-out",
        str(summary_out),
    ]
    assert score_main(argv) == 0
    assert out.is_file()
    assert summary_out.is_file()
    assert paths["lock"].is_file()
    summary = json.loads(summary_out.read_text(encoding="utf-8"))
    assert summary["kind"] == "v15_check4_score_summary_v1"
    assert summary["status"] == "scored"
    assert summary["gbp_display"] is False
    assert summary["primary"]["pass"] is True
    assert summary["secondary"]["pass"] is True
    assert summary["publication"] == "publish_range_both"
    rep = json.loads(out.read_text(encoding="utf-8"))
    assert rep["check4_summary"] == summary
    assert rep["input_sha256"]["check4_f8"]["sha256"] == sha256_file(f8_file)


def test_s6_rerun_v14_score_refuses_both_check4_flags_or_invalid_f8(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """S6: rerun_v14_score refuses when both --check4-rent-route and --check4-f8 are given or --check4-f8 is invalid."""
    paths = _layout(tmp_path)
    zones = _synthetic_zones(pass_check4=True)
    paths["checks"].write_text(
        json.dumps({"primary_zones": zones, "secondary_zones": zones}),
        encoding="utf-8",
    )
    monkeypatch.setitem(MERGE_PINS, "merge_map", sha256_file(paths["merge_map"]))
    f8_file = tmp_path / "check4_f8.json"
    f8_file.write_text('{"zones": [{"zone": "S01000000", "capitalised_land": 100.0}]}\n', encoding="utf-8")

    calls = {"n": 0}
    monkeypatch.setattr(
        "scripts.rerun_v14_score._score_holdout",
        lambda *_a, **_kw: calls.__setitem__("n", calls["n"] + 1),
    )
    out = tmp_path / "holdout" / "report.json"
    argv_both = _args(paths, out, holdout=True, score=False) + ["--check4-f8", str(f8_file)]
    assert score_main(argv_both) == 1
    assert (
        capsys.readouterr().err
        == "V14_SCORE: REFUSED: check4 route: expected one of --check4-rent-route or --check4-f8, got both\n"
    )
    assert calls["n"] == 0
    assert not out.exists()
    assert not paths["lock"].exists()

    bad_f8 = tmp_path / "bad_f8.json"
    bad_f8.write_text("{not valid json\n", encoding="utf-8")
    argv_bad = [
        "--out",
        str(out),
        "--holdout-2023",
        "--check-inputs",
        str(paths["checks"]),
        "--lock-path",
        str(paths["lock"]),
        "--merge-map",
        str(paths["merge_map"]),
        "--hedonic-coefs",
        str(paths["coefs"]),
        "--sha8-block",
        str(paths["sha8"]),
        "--check3-plot-passes",
        str(paths["check3"]),
        "--check4-f8",
        str(bad_f8),
        "--ur6",
        str(paths["ur6"]),
        "--dz2022-keys",
        str(paths["dz"]),
    ]
    assert score_main(argv_bad) == 1
    assert capsys.readouterr().err == "V14_CHECK4: ERROR: check4_f8: expected JSON object, got invalid\n"
    assert calls["n"] == 0
    assert not out.exists()
    assert not paths["lock"].exists()


def test_s7_committed_v15_check4_score_report_is_non_gbp_and_complete() -> None:
    """S7: committed data/processed/methods_code_1/v15_check4_score/report.json is valid, non-GBP, and complete."""
    assert COMMITTED_REPORT.is_file()
    raw_text = COMMITTED_REPORT.read_text(encoding="utf-8")
    assert "\u00a3" not in raw_text
    assert "_gbp" not in raw_text
    assert "GBP" not in raw_text
    assert "Pounds" not in raw_text

    payload = json.loads(raw_text)
    assert_non_gbp_report(payload)
    assert payload["kind"] == "v15_check4_score_report_v1"
    assert payload["publish_level"] == "internal"
    assert payload["methods_alignment"] == "v1.5"
    assert payload["gbp_display"] is False
    assert payload["year"] == 2023
    assert payload["status"] == "scored"
    assert payload["previous_v14_status"] == "NOT_RUN"
    assert payload["method_authority"]["addendum_sha256"] == ADDENDUM5_SHA256
    assert payload["method_authority"]["signatures_sha256"] == ADDENDUM5_SIGNATURES_SHA256

    cov = payload["coverage"]
    assert cov["lookup_zones"] == 6976
    assert cov["not_scored_zones"] == 730
    assert cov["priced_zones"] == 6246
    assert cov["secondary_scored_zones"] + cov["secondary_no_cell_zones"] == 6246
    assert cov["brma_count"] == 18
    assert cov["bands_per_brma"] == 4
    assert cov["plus4_applied_zones"] == 1101
    assert cov["positive_capitalised_land_zones"] == 5704
    assert cov["non_positive_capitalised_land_zones"] == 542

    cancel = payload["cancellation_identity"]
    assert cancel["pass"] is True
    assert cancel["all_within_tolerance"] is True
    assert cancel["zones_checked"] == 6246
    assert cancel["tolerance"] == 1e-12

    for est_key in ("primary", "secondary"):
        est = payload[est_key]
        assert est["check"] == "4"
        assert est["n_zones"] == 6246
        assert est["status"] in ("pass", "fail")
        assert isinstance(est["pass"], bool)
        assert "residual_median" not in est
        assert "class_residual_medians" not in est
        assert set(est["by_ur6"].keys()) == {"1", "2", "3", "4", "5", "6"}
        assert sum(est["by_ur6"][k]["n"] for k in ("1", "2", "3", "4", "5", "6")) == 6246

    assert payload["publication"]["outcome"] == "both_fail_publish_neither"
    assert payload["publication"]["publish_primary"] is False
    assert payload["publication"]["publish_secondary"] is False


def test_s8_sentinel_money_levels_never_appear_in_score_summary() -> None:
    """S8: zone money levels (SENTINEL 987654321.125) never leak into score_check4_non_gbp output."""
    sentinel = 987654321.125
    zones = _synthetic_zones(pass_check4=True, sentinel_offset=sentinel)
    scored = score_check4_non_gbp(zones)
    serialized = json.dumps(scored, sort_keys=True)
    assert "987654321" not in serialized
    assert "\u00a3" not in serialized
