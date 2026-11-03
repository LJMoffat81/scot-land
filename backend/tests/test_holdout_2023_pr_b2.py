"""HOLDOUT-2023-RUN PR-B2: zone status, ruling 2/3/5 tests. SYNTHETIC only (codes, toy numbers)."""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
import pytest

from georgist import v14_hedonic as hedonic
from scripts import build_v14_zone_status_2023 as zs
from scripts.build_v14_b2 import fit_window_gaps

CELLED = [f"ZC{i:03d}" for i in range(6)]


def _inputs(n_no_cell: int = 419) -> dict:
    no_cell = [f"ZN{i:04d}" for i in range(n_no_cell)]
    priced = CELLED + no_cell
    price = {z: 100.0 for z in priced}
    price["ZC000"] = 10.0  # central residual negative -> P unavailable
    corners = {z: {"drc_low": 20.0, "drc_central": 50.0, "drc_high": 80.0} for z in priced}
    corners["ZC001"] = {"drc_low": 20.0, "drc_central": 50.0, "drc_high": 120.0}  # P_L unavailable only
    corners["ZC002"] = {"drc_low": 10.0, "drc_central": 40.0, "drc_high": 70.0}
    corners["ZC003"] = {"drc_low": 15.0, "drc_central": 50.0, "drc_high": 95.0}  # wide spread
    from georgist import surface_rent as sr

    primary = {}
    for z in priced:
        r = sr.residual_land_value(price[z], corners[z]["drc_central"])
        primary[z] = {"zone": z, "land_per_home": r.land_value,
                      "unavailable": sr.estimate_label_for_residual(r) == "unavailable"}
    per_zone = {z: {"zone": z, "land_per_home": float(i), "unavailable": False, "model_failure": False}
                for i, z in enumerate(CELLED)}
    per_zone["ZC003"]["model_failure"] = True
    per_zone["ZC004"]["unavailable"] = True
    return {
        "primary": primary,
        "builder": {z: {"zone": z, "price": price[z]} for z in priced},
        "corners": corners,
        "per_zone": per_zone,
        "not_scored": {"ZX001": "suppressed_price"},
        "merge_map": {z: {} for z in CELLED},
        "iz_lookup": {z: {"CA": "CA1" if z < "ZN0100" else "CA2"} for z in priced + ["ZX001"]},
    }


def _by_zone(rows):
    return {row["zone"]: row for row in rows}


def test_status_enum_exhaustive_and_precedence() -> None:
    rows = _by_zone(zs.build_status(**_inputs()))
    assert {r["status_S"] for r in rows.values()} == {"estimated", "unavailable", "model_failure", "no_cell", "not_scored"}
    assert {r["status_P"] for r in rows.values()} == {"estimated", "unavailable", "not_scored"}
    assert set(zs.STATUSES) == {"estimated", "unavailable", "model_failure", "no_cell", "not_scored"}
    assert rows["ZX001"]["status_P"] == rows["ZX001"]["status_S"] == "not_scored"
    assert rows["ZX001"]["not_scored_reason"] == "suppressed_price"
    assert rows["ZN0000"]["status_S"] == "no_cell" and rows["ZN0000"]["status_P"] == "estimated"
    assert rows["ZC003"]["status_S"] == "model_failure"
    assert rows["ZC004"]["status_S"] == "unavailable"
    assert rows["ZC000"]["status_P"] == "unavailable" and rows["ZC000"]["rank_P_C"] is None
    assert len(rows) == 1 + 6 + 419


@pytest.mark.parametrize("value", ["foo", "Estimated", None])
def test_unknown_status_refused(value) -> None:
    rows = zs.build_status(**_inputs())
    rows[0]["status_S"] = value
    with pytest.raises(zs.StatusError) as raised:
        zs.assert_rows(rows)
    assert str(raised.value) == f"B7_ZONE_STATUS: REFUSED: status_S {rows[0]['zone']}: expected enum, got {value}"


def test_p_cannot_carry_s_only_statuses() -> None:
    rows = zs.build_status(**_inputs())
    rows[0]["status_P"] = "no_cell"
    with pytest.raises(zs.StatusError):
        zs.assert_rows(rows)


@pytest.mark.parametrize(("n", "diff"), [(418, "-1"), (420, "+1")])
def test_no_cell_count_other_than_419_is_not_run(n, diff) -> None:
    with pytest.raises(zs.StatusError) as raised:
        zs.build_status(**_inputs(n))
    assert str(raised.value) == f"B7_ZONE_STATUS: NOT_RUN: no_cell: expected 419, got {n} (diff {diff})"


def test_no_cell_419_passes() -> None:
    rows = zs.build_status(**_inputs(419))
    assert sum(r["status_S"] == "no_cell" for r in rows) == 419


def test_columns_are_ranks_and_flags_only() -> None:
    rows = zs.build_status(**_inputs())
    assert all(tuple(r) == zs.COLUMNS for r in rows)
    for banned in ("price", "share", "land_per_home", "drc", "value"):
        assert not any(banned in column for column in zs.COLUMNS)
    rows[0]["price"] = 1
    with pytest.raises(zs.StatusError) as raised:
        zs.assert_rows(rows)
    assert str(raised.value).startswith("B7_ZONE_STATUS: REFUSED: columns: expected ")


def test_corner_ranks_and_corner_mapping() -> None:
    rows = _by_zone(zs.build_status(**_inputs()))
    # ZC001: P_L corner (high DRC) is negative -> no P_L rank, still ranked at P_C and P_H.
    assert rows["ZC001"]["rank_P_L"] is None and rows["ZC001"]["rank_P_C"] is not None
    # ZC002 has the lowest DRC at every corner, so the highest land at every corner.
    est = [r for r in rows.values() if r["rank_P_H"] is not None]
    assert rows["ZC002"]["rank_P_H"] == max(r["rank_P_H"] for r in est)
    assert rows["ZC002"]["rank_P_L"] == max(r["rank_P_L"] for r in est if r["rank_P_L"] is not None)
    # ZC003: second-highest land at P_H (low DRC) but lowest at P_L (high DRC).
    p_h = sorted(r["rank_P_H"] for r in est)
    assert rows["ZC003"]["rank_P_H"] == p_h[-2]
    assert rows["ZC003"]["rank_P_L"] == min(r["rank_P_L"] for r in est if r["rank_P_L"] is not None)
    # S estimated: ZC000 (0.0, zero-filled -> unranked), ZC001 (1), ZC002 (2), ZC005 (5).
    assert rows["ZC000"]["rank_S_C"] is None
    assert rows["ZC005"]["rank_S_C"] == 3


def test_p_c_must_match_primary_file() -> None:
    data = _inputs()
    data["primary"]["ZC005"]["land_per_home"] += 1.0
    with pytest.raises(zs.StatusError) as raised:
        zs.build_status(**data)
    assert str(raised.value) == "B7_ZONE_STATUS: REFUSED: P_C zone ZC005: expected equal to primary file, got different"


def test_bad_not_scored_reason_refused() -> None:
    data = _inputs()
    data["not_scored"]["ZX001"] = "other"
    with pytest.raises(zs.StatusError) as raised:
        zs.build_status(**data)
    assert str(raised.value) == "B7_ZONE_STATUS: REFUSED: not_scored reason ZX001: expected enum, got other"


def test_seeded_ranks_exclude_zero_and_break_ties_by_seed() -> None:
    import numpy as np

    values = {"a": 1.0, "b": 2.0, "c": 2.0, "d": 9.0, "z": 0.0}
    ranks = zs.seeded_ranks(values)
    assert "z" not in ranks
    assert ranks["a"] == 1 and ranks["d"] == 4
    assert sorted((ranks["b"], ranks["c"])) == [2, 3]
    kept = ["a", "b", "c", "d"]
    perm = np.random.default_rng(20261015).permutation(4)
    expect_b_first = perm[kept.index("b")] < perm[kept.index("c")]
    assert (ranks["b"] < ranks["c"]) == expect_b_first
    assert zs.TIE_SEED == 20261015
    assert zs.seeded_ranks(values) == ranks  # deterministic


def test_seeded_ranks_tie_order_depends_on_seed(monkeypatch) -> None:
    values = {f"t{i:02d}": 5.0 for i in range(20)}
    base = zs.seeded_ranks(values)
    monkeypatch.setattr(zs, "TIE_SEED", 1)
    assert zs.seeded_ranks(values) != base
    assert sorted(base.values()) == list(range(1, 21))


def test_rank_metric_pinned(tmp_path: Path, monkeypatch) -> None:
    assert zs.RANK_METRIC == "residual_land_value_per_dwelling"
    data = _inputs()
    monkeypatch.setattr(zs, "_load", lambda path, name: {
        "not_scored": {"not_scored": [{"zone": z, "reason": r} for z, r in data["not_scored"].items()]},
        "primary": {"zones": list(data["primary"].values())},
        "builder": {"zones": list(data["builder"].values())},
        "drc_corners": {"zones": data["corners"]},
        "per_zone": {"zones": list(data["per_zone"].values())},
    }[name])
    monkeypatch.setattr(zs, "read_merge_map", lambda _p: data["merge_map"])
    monkeypatch.setattr(zs, "read_iz_lookup", lambda _p: data["iz_lookup"])
    out = tmp_path / "zone_status_2023.json"
    argv = [x for n in ("primary", "builder", "drc-corners", "per-zone", "not-scored", "merge-map", "iz-lookup")
            for x in (f"--{n}", "x")] + ["--out", str(out)]
    assert zs.main(argv) == 0
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["rank_metric"] == "residual_land_value_per_dwelling"
    assert "20261015" in payload["rank_rule"]


def test_corner_order_holds_in_memory_before_ranking(monkeypatch) -> None:
    seen = {}
    original = zs.assert_corner_order

    def spy(land):
        seen["land"] = {k: dict(v) for k, v in land.items()}
        original(land)

    monkeypatch.setattr(zs, "assert_corner_order", spy)
    zs.build_status(**_inputs())
    land = seen["land"]
    assert land["P_C"]
    for zone, central in land["P_C"].items():
        if zone in land["P_L"]:
            assert land["P_L"][zone] <= central
        if zone in land["P_H"]:
            assert central <= land["P_H"][zone]
    assert any(land["P_L"][z] < land["P_H"][z] for z in land["P_L"] if z in land["P_H"])


def test_corner_order_violation_refused_exact() -> None:
    land = {"P_L": {"Z1": 5.0}, "P_C": {"Z1": 4.0}, "P_H": {"Z1": 6.0}}
    with pytest.raises(zs.StatusError) as raised:
        zs.assert_corner_order(land)
    assert str(raised.value) == "B7_ZONE_STATUS: REFUSED: corner order zone Z1: expected P_L<=P_C<=P_H, got other"


def test_counts_by_council_sum() -> None:
    rows = zs.build_status(**_inputs())
    counts = zs.counts_by_council(rows)
    assert sum(sum(c["S"].values()) for c in counts.values()) == len(rows)
    assert counts["CA1"]["S"]["no_cell"] + counts["CA2"]["S"]["no_cell"] == 419


# --- ruling 3: degenerate MixedLM -----------------------------------------------

SING = "Random effects covariance is singular"
HESS = "The Hessian matrix at the estimated parameter values is not positive definite."


@pytest.mark.parametrize(
    ("messages", "expected"),
    [([SING, HESS], True), ([SING], False), ([HESS], False), ([], False),
     (["The random effects covariance matrix is singular.", HESS], True),
     (["Random effects covariance is on the boundary", HESS], False)],
)
def test_degenerate_truth_table(messages, expected) -> None:
    assert hedonic.degenerate_mixedlm(messages) is expected


class _Result:
    converged = True
    fe_params = np.array([0.0, 0.5])


def _rows():
    return [{"price": "100", "a_m2": str(40 + i), "ur3": "urban" if i % 2 else "rural"} for i in range(8)]


@pytest.mark.parametrize(("emit", "status"), [((SING, HESS), "NOT_CONVERGED"), ((SING,), "fit"), ((HESS,), "fit"), ((), "fit")])
def test_s_c3_flags_exactly_the_degenerate_state(monkeypatch, emit, status) -> None:
    def fake(*_a, **_k):
        for text in emit:
            warnings.warn(text)
        return _Result()

    monkeypatch.setattr(hedonic, "_fit_mixedlm", fake)
    row = hedonic._fit_s_c3(_rows())
    assert row["status"] == status
    if status == "NOT_CONVERGED":
        assert row["reason"] == hedonic.DEGENERATE_REASON


def test_not_converged_s_c3_makes_every_s_zone_model_failure(monkeypatch) -> None:
    from scripts import fit_v14_hedonic as fit

    fitted = {"sensitivities": [{"id": "S-c3", "status": "NOT_CONVERGED"}]}
    monkeypatch.setattr(fit, "land_share_for_zone", lambda _f, row: {
        "zone": row["zone"], "share": 0.1, "land_per_home": 1.0, "unavailable": False,
        "model_failure": False, "count_in_1d": True})
    records = fit.project_records(fitted, [{"zone": "Z1", "year": 2022}, {"zone": "Z2", "year": 2022}])
    assert all(r["model_failure"] and r["unavailable"] for r in records)


# --- ruling 2: disclosure -------------------------------------------------------


def test_fit_window_gap_disclosed_not_imputed() -> None:
    sales = [{"zone": "Z1", "year": 2021}, {"zone": "Z1", "year": 2022}, {"zone": "Z2", "year": 2023}]
    floors = [{"zone": "Z1", "year": 2022}]
    assert fit_window_gaps(sales, floors) == [{"zone": "Z1", "year": 2021, "missing": "sold_tfa_mean (f_m2)"}]


def test_cli_writes_counts_and_refuses_on_missing_file(tmp_path: Path, capsys) -> None:
    code = zs.main([f"--{n}" if i % 2 == 0 else str(tmp_path / "absent.json")
                    for name in ("primary", "builder", "drc-corners", "per-zone", "not-scored", "merge-map", "iz-lookup", "out")
                    for i, n in enumerate((name, name))])
    assert code == 1
    assert capsys.readouterr().err.strip() == "B7_ZONE_STATUS: REFUSED: not_scored: expected file, got absent"


def test_b2_main_prints_disclosure_after_write(tmp_path: Path, monkeypatch, capsys) -> None:
    import scripts.build_v14_b2 as b2

    payload = {"label": "SYNTHETIC", "fit_window_disclosure": [
        "B2_FIT_ROWS: DISCLOSE: zone Z1 year 2021: missing sold_tfa_mean (f_m2)",
        "B2_FIT_ROWS: RECONCILE: complete fit-window zone-years 2 = fit rows 1 + no sold-TFA floor 1",
    ]}
    monkeypatch.setattr(b2, "build", lambda _args: payload)
    out = tmp_path / "b2.json"
    argv = ["--out", str(out)] + [x for n in ("house-sales", "plot-split", "crosswalk", "sold-tfa", "access",
            "bedrooms", "filter1-script", "filter1-output", "filter2-script", "filter2-output") for x in (f"--{n}", "x")]
    assert b2.main(argv) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[:2] == payload["fit_window_disclosure"]
    assert out.exists()
