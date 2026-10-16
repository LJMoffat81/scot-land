"""PR-A primary estimator inputs. Synthetic fixtures only. No price file."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import pytest

from georgist import surface_costs as sc
from georgist import surface_rent as sr
from georgist import surface_v13 as v13
from georgist import surface_v14 as v14
from georgist.ros_c14_input import (
    COST_AVAILABILITY_RULE,
    build_inputs,
    load_cost_availability,
)
from georgist.ros_c14_prices import MEDIAN_SENSITIVITY, PriceColumnError, requested_columns
from georgist.v14_primary_inputs import (
    DepreciationMethodError,
    age_mix_remaining,
    depreciated_replacement_cost,
    remaining_factor_at_age,
    sensitivity_lines,
    v14_depreciation,
    zone_drc_v14,
)
from scripts.build_v14_primary_inputs import main

SENTINELS = (
    "SENTINEL_MEDIAN_9f3a",
    "SENTINEL_LQ_9f3a",
    "SENTINEL_UQ_9f3a",
    "SENTINEL_TV_9f3a",
)
HEADER = [
    "Calendar year",
    "Data zone",
    "Data zone code",
    "Median",
    "Lower quartile",
    "Upper quartile",
    "Volume",
    "Total value",
]
COST_INPUTS = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "surface_costs_dz2011_inputs"
)


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(cell) for cell in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _c14(path: Path, body: list[list]) -> None:
    rows = [[2024, "Scotland", "S92000003", *SENTINELS[:3], 1000, ""]]
    rows.extend(body)
    _write_csv(path, HEADER, rows)


def _row(code: str, name: str, volume, total) -> list:
    return [2024, name, code, *SENTINELS[:3], volume, total]


def _lookup(path: Path, codes: list[str], names: dict[str, str] | None = None) -> None:
    names = names or {}
    _write_csv(path, ["code", "name"], [[code, names.get(code, code)] for code in codes])


def _crosswalk(path: Path, pairs: list[tuple[str, str, int]]) -> None:
    _write_csv(path, ["dz2011", "dz2022", "uprn_count"], [list(pair) for pair in pairs])


def _merge(path: Path, codes: list[str]) -> None:
    _write_csv(path, ["dz2011"], [[code] for code in codes])


def _ur(path: Path, codes: list[str]) -> None:
    _write_csv(path, ["dz2011", "ur6"], [[code, 1] for code in codes])


def _paths(tmp: Path, body: list[list], lookup_codes: list[str], pairs, scored: list[str], names=None):
    c14 = tmp / "c14.csv"
    _c14(c14, body)
    lookup = tmp / "lookup.csv"
    _lookup(lookup, lookup_codes, names)
    cross = tmp / "cross.csv"
    _crosswalk(cross, pairs)
    merge = tmp / "merge.csv"
    _merge(merge, scored)
    ur = tmp / "ur.csv"
    dz2011 = sorted({pair[0] for pair in pairs})
    _ur(ur, dz2011)
    return {
        "c14": c14,
        "lookup": lookup,
        "crosswalk": cross,
        "merge": merge,
        "ur": ur,
    }


def test_refuses_any_method_other_than_straight_line_v14():
    dep = v14_depreciation()
    assert dep["method"] == "straight_line_v14"
    compounding = dict(dep)
    compounding["method"] = "compounding_v13"
    with pytest.raises(DepreciationMethodError):
        remaining_factor_at_age(20, compounding)
    missing = dict(dep)
    del missing["method"]
    with pytest.raises(DepreciationMethodError):
        remaining_factor_at_age(20, missing)


def test_remaining_factor_at_stated_ages():
    dep = v14_depreciation()
    assert remaining_factor_at_age(0, dep) == 1.0
    assert format(remaining_factor_at_age(20, dep), ".3f") == "0.930"
    assert format(remaining_factor_at_age(68, dep), ".3f") == "0.762"
    assert format(remaining_factor_at_age(100, dep), ".3f") == "0.762"


def test_no_age_mix_zone_uses_frozen_factor():
    dep = v14_depreciation()
    cfg = sr.load_config()
    remaining = age_mix_remaining(None, dep, 2025, cfg)
    assert remaining == v14.no_age_mix_remaining(cfg)
    assert format(remaining, ".3f") == "0.762"
    rebuild = 1000.0
    drc = depreciated_replacement_cost(rebuild, None, dep, 2025, cfg)
    assert drc == rebuild * remaining


def test_surface_costs_no_age_mix_matches_frozen_factor():
    cfg = sr.load_config()
    code = "S01006524"
    epc = pd.read_csv(COST_INPUTS / "epc_dz_rollup.csv").set_index("code")
    nrs = pd.read_csv(COST_INPUTS / "nrs_dwelling_mix_2011_fallback.csv").set_index("code")
    estate_rows = {
        str(row["code"]): row
        for row in json.loads((COST_INPUTS / "estate_rows.json").read_text(encoding="utf-8"))
    }
    row = epc.loc[code].to_dict()
    for key in list(row):
        if "age_" in key and key.endswith("_share"):
            row[key] = 0
    central = zone_drc_v14(
        code=code,
        epc_row=row,
        nrs2017_row=nrs.loc[code].to_dict() if code in nrs.index else None,
        estate_row=estate_rows.get(code),
        cfg=cfg,
        band=sr.rebuild_band(cfg, sr.rebuild_price_base_year(cfg)),
        valuation_year=2025,
        defaults=sc.agr_aligned_defaults(cfg),
    )
    frozen = v14.no_age_mix_remaining(cfg)
    assert central.remaining_factor == frozen
    assert central.drc_gbp == central.rebuild_new_gbp * frozen
    assert format(frozen, ".3f") == "0.762"


def test_sensitivities_are_labelled_and_do_not_gate():
    lines = sensitivity_lines()
    text = "\n".join(lines)
    for label in (
        "rate_0.5pct_straight_line",
        "v13_0.276pct_compounding",
        "rate_0.7pct_straight_line",
        "exhibit2_six_band",
        "rate_1.33pct",
        "rate_0.86pct",
        "no 55% cap; 68-yr age cap applied",
        "band_end_0pct",
        "band_end_1.0pct",
    ):
        assert label in text
    assert text.count("no 55% cap; 68-yr age cap applied") == 2
    assert "rate_1.33pct_no_cap" not in text
    assert "rate_0.86pct_no_cap" not in text
    assert "rate=0.0133" in text
    assert "rate=0.0086" in text
    assert text.count("label=exhibit2_six_band") == 6
    assert all("gates=false" in line for line in lines)
    assert v14_depreciation()["rate_building"]["central"] == 0.0035


def test_default_mode_never_requests_total_value(tmp_path: Path, capsys, caplog):
    counts = requested_columns(scored_run=False, price_columns=False)
    assert "total value" not in counts
    with pytest.raises(PriceColumnError):
        requested_columns(scored_run=False, price_columns=True)
    body = [_row("S01013482", "Left", 10, "SENTINEL_TV_9f3a")]
    paths = _paths(
        tmp_path,
        body,
        ["S01013482"],
        [("S01007001", "S01013482", 20)],
        ["S01007001"],
    )
    out = tmp_path / "out"
    with caplog.at_level(logging.DEBUG):
        rc = main(
            [
                "--out-dir",
                str(out),
                "--c14",
                str(paths["c14"]),
                "--lookup",
                str(paths["lookup"]),
                "--crosswalk",
                str(paths["crosswalk"]),
                "--merge-map",
                str(paths["merge"]),
                "--ur",
                str(paths["ur"]),
            ]
        )
    captured = capsys.readouterr()
    assert rc == 0
    blob = captured.out + captured.err + caplog.text
    for path in out.rglob("*"):
        if path.is_file():
            blob += path.read_text(encoding="utf-8")
    for sentinel in SENTINELS:
        assert sentinel not in blob
    assert "total value" not in blob
    assert not (out / "cost_availability.json").exists()
    assert (out / "median_sensitivity.txt").read_text(encoding="utf-8").strip() == MEDIAN_SENSITIVITY


def test_scored_run_keeps_sentinels_out_of_stdout(tmp_path: Path, capsys, caplog):
    body = [
        _row("S01013482", "Left", 10, 1000),
        _row("S01013483", "Right", 10, 200),
        _row("S01013484", "Low", 4, "SENTINEL_TV_9f3a"),
    ]
    names = {
        "S01013485": "Twin",
        "S01013486": "Twin",
    }
    paths = _paths(
        tmp_path,
        body + [
            _row("S01013485", "Twin", 10, 888888),
            _row("S01013486", "Twin", 10, 888888),
        ],
        ["S01013482", "S01013483", "S01013484", "S01013485", "S01013486", "S01013487"],
        [
            ("S01007010", "S01013482", 750),
            ("S01007011", "S01013482", 250),
            ("S01007010", "S01013483", 400),
            ("S01007010", "S01013484", 1),
            ("S01007010", "S01013485", 1),
            ("S01007010", "S01013486", 1),
            ("S01007010", "S01013487", 1),
            ("S01007012", "S01013484", 10),
        ],
        ["S01007010", "S01007011", "S01007012"],
        names,
    )
    drc = tmp_path / "drc.json"
    drc.write_text(
        json.dumps({"S01007010": 10, "S01007011": 10, "S01007012": 10}),
        encoding="utf-8",
    )
    out = tmp_path / "scored"
    with caplog.at_level(logging.DEBUG):
        rc = main(
            [
                "--scored-run",
                "--synthetic-fixtures",
                "--out-dir",
                str(out),
                "--c14",
                str(paths["c14"]),
                "--lookup",
                str(paths["lookup"]),
                "--crosswalk",
                str(paths["crosswalk"]),
                "--merge-map",
                str(paths["merge"]),
                "--ur",
                str(paths["ur"]),
                "--drc-json",
                str(drc),
            ]
        )
    captured = capsys.readouterr()
    assert rc == 0, captured.err
    outside = captured.out + captured.err + caplog.text
    info = (out / "depreciation_sensitivities.txt").read_text(encoding="utf-8")
    median = (out / "median_sensitivity.txt").read_text(encoding="utf-8")
    outside += info + median
    for sentinel in SENTINELS:
        assert sentinel not in outside
    costs = json.loads((out / "cost_availability.json").read_text(encoding="utf-8"))
    encoded = json.dumps(costs)
    for sentinel in SENTINELS:
        assert sentinel not in encoded
    weight = 75 / 100
    expected = (weight * 1000 + 200) / (weight * 10 + 10)
    assert costs["S01007010"]["price"] == expected
    assert costs["S01007011"]["price"] == 1000 / 10
    assert "S01007012" not in costs
    assert "888888" not in encoded
    assert "999999" not in encoded


def test_negative_residual_is_unavailable_in_the_share_list(tmp_path: Path):
    body = [
        _row("S01013482", "Ok", 10, 1000),
        _row("S01013483", "Ok2", 10, 500),
    ]
    paths = _paths(
        tmp_path,
        body,
        ["S01013482", "S01013483"],
        [
            ("S01007001", "S01013482", 20),
            ("S01007002", "S01013483", 20),
        ],
        ["S01007001", "S01007002"],
    )
    drc = {"S01007001": 40.0, "S01007002": 80.0}
    drc_path = tmp_path / "drc.json"
    drc_path.write_text(json.dumps(drc), encoding="utf-8")
    out = tmp_path / "neg"
    rc = main(
        [
            "--scored-run",
            "--synthetic-fixtures",
            "--out-dir",
            str(out),
            "--c14",
            str(paths["c14"]),
            "--lookup",
            str(paths["lookup"]),
            "--crosswalk",
            str(paths["crosswalk"]),
            "--merge-map",
            str(paths["merge"]),
            "--ur",
            str(paths["ur"]),
            "--drc-json",
            str(drc_path),
        ]
    )
    assert rc == 0
    costs = load_cost_availability(out / "cost_availability.json")
    estimates = json.loads((out / "primary_estimates.json").read_text(encoding="utf-8"))
    assert estimates["S01007002"] == 0.0
    result = build_inputs(
        c14_path=paths["c14"],
        lookup_path=paths["lookup"],
        crosswalk_path=paths["crosswalk"],
        merge_map_path=paths["merge"],
        ur_path=paths["ur"],
        scored_run=True,
        estimates=estimates,
        cost_availability=costs,
        check_pins=False,
    )
    by_code = {zone["dz2011"]: zone for zone in result["dz2011"]}
    assert by_code["S01007002"]["status"] == "unavailable"
    assert by_code["S01007002"]["unavailable_from"] == COST_AVAILABILITY_RULE
    assert result["share_list"] == [0.6, 0.0]
    check = v13.check_1d_zero_mass(result["share_list"], max_share=0.10)
    assert check["n"] == 2
    assert check["n_at_0"] == 1
    assert "0%" not in json.dumps(result["share_list"])


def test_median_sensitivity_has_no_value(tmp_path: Path):
    out = tmp_path / "info"
    rc = main(["--out-dir", str(out)])
    assert rc == 0
    text = (out / "median_sensitivity.txt").read_text(encoding="utf-8").strip()
    assert text == "not_crosswalkable"
    assert text == MEDIAN_SENSITIVITY
    assert any(ch.isdigit() for ch in text) is False
