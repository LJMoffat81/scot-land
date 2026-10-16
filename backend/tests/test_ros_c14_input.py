"""Synthetic fixtures for the RoS C14 input builder. No RoS file."""

from __future__ import annotations

import json
from pathlib import Path

import openpyxl
import pytest

from georgist.ros_c14_input import (
    BLIND_COLUMNS,
    PRICE_COLUMNS,
    InputBuildError,
    build_inputs,
    requested_columns,
)
from scripts.build_ros_c14_v14_inputs import main

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


def _write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    lines = [",".join(header)]
    for row in rows:
        lines.append(",".join(str(cell) for cell in row))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _c14(path: Path, body: list[list], *, scotland: tuple = (2024, "Scotland", "S92000003", 1000)) -> None:
    rows = [[scotland[0], scotland[1], scotland[2], "", "", "", scotland[3], ""]]
    rows.extend(body)
    _write_csv(path, HEADER, rows)


def _row(code: str, name: str, volume, year: int = 2024) -> list:
    return [year, name, code, *SENTINELS[:3], volume, SENTINELS[3]]


def _lookup(path: Path, codes: list[str]) -> None:
    _write_csv(path, ["code"], [[code] for code in codes])


def _crosswalk(path: Path, pairs: list[tuple[str, str, int]]) -> None:
    _write_csv(path, ["dz2011", "dz2022", "uprn_count"], [list(pair) for pair in pairs])


def _merge(path: Path, codes: list[str]) -> None:
    _write_csv(path, ["dz2011"], [[code] for code in codes])


def _ur(path: Path, rows: list[tuple]) -> None:
    _write_csv(path, ["dz2011", "ur6", "unavailable"], [list(row) for row in rows])


def _build(tmp: Path, **kwargs):
    return build_inputs(
        c14_path=kwargs["c14"],
        lookup_path=kwargs["lookup"],
        crosswalk_path=kwargs["crosswalk"],
        merge_map_path=kwargs["merge"],
        ur_path=kwargs["ur"],
        frozen_plan_path=kwargs.get("frozen"),
        scored_run=kwargs.get("scored_run", False),
        estimates=kwargs.get("estimates"),
        main_commit_sha="abc123",
        check_pins=kwargs.get("check_pins", False),
    )


def _statuses(result) -> dict[str, str]:
    return {zone["dz2011"]: zone["status"] for zone in result["dz2011"]}


def test_reader_requests_only_the_four_columns():
    assert requested_columns(False) == BLIND_COLUMNS
    assert requested_columns(True) == BLIND_COLUMNS
    for name in PRICE_COLUMNS:
        assert name not in requested_columns(False)
        assert name not in requested_columns(True)


def test_dz2011_code_exits_nonzero(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(c14, [_row("S01006506", "Old zone", 10)])
    lookup = tmp_path / "lookup.csv"
    _lookup(lookup, ["S01006506"])
    cross = tmp_path / "x.csv"
    _crosswalk(cross, [("S01007000", "S01006506", 10)])
    merge = tmp_path / "m.csv"
    _merge(merge, ["S01007000"])
    ur = tmp_path / "ur.csv"
    _ur(ur, [("S01007000", 1, 0)])
    out = tmp_path / "out.json"
    rc = main(
        [
            "--c14",
            str(c14),
            "--lookup",
            str(lookup),
            "--crosswalk",
            str(cross),
            "--merge-map",
            str(merge),
            "--ur",
            str(ur),
            "--out",
            str(out),
            "--synthetic-fixtures",
        ]
    )
    assert rc != 0
    assert not out.exists()


def test_code_missing_from_lookup_exits_nonzero(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(c14, [_row("S01013482", "Zone", 10)])
    lookup = tmp_path / "lookup.csv"
    _lookup(lookup, ["S01013483"])
    cross = tmp_path / "x.csv"
    _crosswalk(cross, [("S01007000", "S01013483", 10)])
    merge = tmp_path / "m.csv"
    _merge(merge, ["S01007000"])
    ur = tmp_path / "ur.csv"
    _ur(ur, [("S01007000", 1, 0)])
    out = tmp_path / "out.json"
    rc = main(
        [
            "--c14",
            str(c14),
            "--lookup",
            str(lookup),
            "--crosswalk",
            str(cross),
            "--merge-map",
            str(merge),
            "--ur",
            str(ur),
            "--out",
            str(out),
            "--synthetic-fixtures",
        ]
    )
    assert rc != 0
    assert not out.exists()


def test_scotland_row_is_only_on_the_national_line(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(c14, [_row("S01013482", "Zone", 10)], scotland=(2024, "Scotland", "S92000003", 4321))
    paths = _simple(tmp_path, c14, ["S01013482"], [("S01007000", "S01013482", 20)], ["S01007000"])
    result = _build(tmp_path, **paths)
    assert result["national"]["scotland_row_volume"] == 4321
    assert result["national"]["raw_dz_sum"] == 10
    assert all(zone["code"] != "S92000003" for zone in result["dz2022"])


def test_homonym_cartesian_and_single_row(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    body = [
        _row("S01013482", "Shared", 10),
        _row("S01013482", "Shared", 10),
        _row("S01013483", "Shared", 12),
        _row("S01013483", "Shared", 12),
        _row("S01013484", "Muirhouse - 04", 20),
        _row("S01013485", "Muirhouse - 04", 8),
    ]
    _c14(c14, body)
    codes = ["S01013482", "S01013483", "S01013484", "S01013485"]
    paths = _simple(tmp_path, c14, codes, [("S01007000", "S01013482", 10)], ["S01007000"])
    result = _build(tmp_path, **paths)
    by_code = {zone["code"]: zone for zone in result["dz2022"]}
    for code in codes:
        assert by_code[code]["status"] == "ros_name_collision"
        assert by_code[code]["count"] == 0
    assert result["national"]["pair_dedup_sum"] == 10 + 12 + 20 + 8


def test_suppressed_markers_and_volume_4_contribute_nothing(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(
        c14,
        [
            _row("S01013482", "Ok", 10),
            _row("S01013483", "Cee", "[c]"),
            _row("S01013484", "Zee", "[z]"),
            _row("S01013485", "Low", 4),
        ],
    )
    codes = ["S01013482", "S01013483", "S01013484", "S01013485"]
    pairs = [
        ("S01007000", "S01013482", 100),
        ("S01007000", "S01013483", 1),
        ("S01007001", "S01013484", 50),
        ("S01007002", "S01013485", 50),
    ]
    paths = _simple(tmp_path, c14, codes, pairs, ["S01007000", "S01007001", "S01007002"])
    result = _build(tmp_path, **paths)
    by_i = {zone["dz2011"]: zone for zone in result["dz2011"]}
    assert by_i["S01007000"]["count_s"] == 10
    assert by_i["S01007001"]["count_s"] == 0
    assert by_i["S01007002"]["count_s"] == 0
    assert by_i["S01007001"]["passed_to_scorer"] is False
    assert by_i["S01007002"]["passed_to_scorer"] is False


def test_absent_lookup_code_contributes_nothing(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(c14, [_row("S01013482", "Ok", 15)])
    codes = ["S01013482", "S01013483"]
    pairs = [
        ("S01007000", "S01013482", 10),
        ("S01007001", "S01013483", 40),
    ]
    paths = _simple(tmp_path, c14, codes, pairs, ["S01007000", "S01007001"])
    result = _build(tmp_path, **paths)
    by_2022 = {zone["code"]: zone for zone in result["dz2022"]}
    assert by_2022["S01013483"]["status"] == "absent_from_c14"
    assert by_2022["S01013483"]["count"] == 0
    by_i = {zone["dz2011"]: zone for zone in result["dz2011"]}
    assert by_i["S01007001"]["count_s"] == 0
    assert by_i["S01007001"]["absent_from_c14"] is True
    assert result["lookup_codes_absent_from_c14"] == 1


def test_incomplete_threshold_sides(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(
        c14,
        [
            _row("S01013482", "Ok", 10),
            _row("S01013483", "Low", 4),
        ],
    )
    # 0.9% with 4 addresses: 4/445. 1.1% with 4 addresses: 4/360.
    # 4 addresses on a large base stay under both gates. 5 addresses do not.
    pairs = [
        ("S01007001", "S01013482", 441),
        ("S01007001", "S01013483", 4),
        ("S01007002", "S01013482", 356),
        ("S01007002", "S01013483", 4),
        ("S01007003", "S01013482", 9996),
        ("S01007003", "S01013483", 4),
        ("S01007004", "S01013482", 9995),
        ("S01007004", "S01013483", 5),
    ]
    paths = _simple(
        tmp_path,
        c14,
        ["S01013482", "S01013483"],
        pairs,
        ["S01007001", "S01007002", "S01007003", "S01007004"],
    )
    result = _build(tmp_path, **paths)
    by_i = {zone["dz2011"]: zone for zone in result["dz2011"]}
    assert by_i["S01007001"]["incomplete_suppressed"] is False
    assert by_i["S01007002"]["incomplete_suppressed"] is True
    assert by_i["S01007003"]["incomplete_suppressed"] is False
    assert by_i["S01007004"]["incomplete_suppressed"] is True


def test_suppressed_only_zone_is_not_scored(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(c14, [_row("S01013482", "Low", 4), _row("S01013483", "Ok", 9)])
    pairs = [("S01007000", "S01013482", 30)]
    paths = _simple(tmp_path, c14, ["S01013482", "S01013483"], pairs, ["S01007000"])
    result = _build(tmp_path, **paths)
    zone = next(item for item in result["dz2011"] if item["dz2011"] == "S01007000")
    assert zone["count_s"] == 0
    assert zone["passed_to_scorer"] is False
    assert zone["status"] == "incomplete_suppressed"
    assert "mean" not in zone


def test_split_and_merge_have_no_medians(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(
        c14,
        [
            _row("S01013482", "Left", 10),
            _row("S01013483", "Right", 10),
            _row("S01013484", "Join", 10),
            _row("S01013485", "Join2", 10),
        ],
    )
    pairs = [
        ("S01007001", "S01013482", 50),
        ("S01007002", "S01013482", 50),
        ("S01007003", "S01013484", 40),
        ("S01007003", "S01013485", 40),
    ]
    paths = _simple(
        tmp_path,
        c14,
        ["S01013482", "S01013483", "S01013484", "S01013485"],
        pairs,
        ["S01007001", "S01007002", "S01007003"],
        scored_codes=["S01007001", "S01007002", "S01007003"],
    )
    result = _build(tmp_path, **paths, scored_run=True)
    by_i = {zone["dz2011"]: zone for zone in result["dz2011"]}
    assert by_i["S01007001"]["case"] == "split"
    assert by_i["S01007002"]["case"] == "split"
    assert by_i["S01007003"]["case"] == "merge"
    encoded = json.dumps({"split": by_i["S01007001"], "merge": by_i["S01007003"]})
    for sentinel in SENTINELS:
        assert sentinel not in encoded
    assert by_i["S01007001"]["medians_quartiles"] == "not_crosswalkable"
    assert by_i["S01007003"]["medians_quartiles"] == "not_crosswalkable"


def test_pair_rows_do_not_change_s_i(tmp_path: Path):
    def run(body: list[list]):
        c14 = tmp_path / f"c14-{len(body)}.csv"
        _c14(c14, body)
        codes = ["S01013482", "S01013483", "S01013484"]
        paths = _simple(tmp_path, c14, codes, [("S01007000", "S01013482", 25)], ["S01007000"])
        return _build(tmp_path, **paths)

    base = run([_row("S01013482", "Ok", 7)])
    extra = run(
        [
            _row("S01013482", "Ok", 7),
            _row("S01013483", "Shared", 10),
            _row("S01013483", "Shared", 10),
            _row("S01013484", "Shared", 12),
            _row("S01013484", "Shared", 12),
        ]
    )
    assert sum(zone["count_s"] for zone in base["dz2011"]) == sum(
        zone["count_s"] for zone in extra["dz2011"]
    )
    assert extra["national"]["pair_dedup_sum"] == 22
    assert base["national"]["pair_dedup_sum"] == 0


def test_blind_mode_hides_sentinels(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    c14 = tmp_path / "c14.csv"
    preamble = tmp_path / "noted.csv"
    _c14(c14, [_row("S01013482", "Ok", 10)])
    raw = c14.read_text(encoding="utf-8")
    preamble.write_text("Notes,only\n" + raw, encoding="utf-8")
    paths = _simple(tmp_path, preamble, ["S01013482"], [("S01007000", "S01013482", 10)], ["S01007000"])
    out = tmp_path / "out.json"
    rc = main(
        [
            "--c14",
            str(preamble),
            "--lookup",
            str(paths["lookup"]),
            "--crosswalk",
            str(paths["crosswalk"]),
            "--merge-map",
            str(paths["merge"]),
            "--ur",
            str(paths["ur"]),
            "--out",
            str(out),
            "--synthetic-fixtures",
            "--scored-run",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    blob = out.read_text(encoding="utf-8") + captured.out + captured.err
    for sentinel in SENTINELS:
        assert sentinel not in blob
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert loaded["reader_requested_columns"] == list(BLIND_COLUMNS)
    assert loaded["price_columns_read"] is False


def test_pins_present_and_mismatch_aborts(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(c14, [_row("S01013482", "Ok", 10)])
    paths = _simple(tmp_path, c14, ["S01013482"], [("S01007000", "S01013482", 10)], ["S01007000"])
    frozen = tmp_path / "plan.md"
    frozen.write_text("synthetic plan\n", encoding="utf-8")
    result = _build(tmp_path, **paths, frozen=frozen)
    pins = result["pins"]
    for key in (
        "c14_sha256",
        "lookup_sha256",
        "crosswalk_sha256",
        "merge_map_sha256",
        "frozen_plan_sha256",
        "main_commit_sha",
    ):
        assert pins[key]
    assert pins["main_commit_sha"] == "abc123"
    assert pins["crosswalk_sha256_expected"].startswith("7690bcbe")
    assert pins["frozen_plan_sha256_prefix_expected"] == "e1ab6d0a"
    with pytest.raises(InputBuildError, match="frozen plan sha"):
        _build(tmp_path, **paths, frozen=frozen, check_pins=True)
    out = tmp_path / "blocked.json"
    rc = main(
        [
            "--c14",
            str(c14),
            "--lookup",
            str(paths["lookup"]),
            "--crosswalk",
            str(paths["crosswalk"]),
            "--merge-map",
            str(paths["merge"]),
            "--ur",
            str(paths["ur"]),
            "--frozen-plan",
            str(frozen),
            "--out",
            str(out),
        ]
    )
    assert rc != 0
    assert not out.exists()


def test_status_unchanged_when_estimate_changes(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(c14, [_row("S01013482", "Ok", 10), _row("S01013483", "Other", 12)])
    codes = ["S01013482", "S01013483"]
    pairs = [
        ("S01007000", "S01013482", 20),
        ("S01007001", "S01013483", 20),
    ]
    paths = _simple(tmp_path, c14, codes, pairs, ["S01007000", "S01007001"])
    ur_rows = [("S01007000", 1, 0), ("S01007001", 2, 1)]
    _ur(paths["ur"], ur_rows)
    low = _build(tmp_path, **paths, scored_run=True, estimates={"S01007000": 0.15, "S01007001": 0.15})
    high = _build(tmp_path, **paths, scored_run=True, estimates={"S01007000": 0.85, "S01007001": 0.85})
    assert _statuses(low) == _statuses(high)
    assert low["dz2022_counts"] == high["dz2022_counts"]
    assert low["dz2011_counts"] == high["dz2011_counts"]
    assert low["share_list"] != high["share_list"]
    by_low = {zone["dz2011"]: zone for zone in low["dz2011"]}
    assert by_low["S01007001"]["status"] == "unavailable"
    assert low["share_list"][1] == 0.0
    assert high["share_list"][1] == 0.0


def test_printout_counts_by_status_and_ur_class(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    c14 = tmp_path / "c14.csv"
    _c14(
        c14,
        [
            _row("S01013482", "Ok", 10),
            _row("S01013483", "Low", 4),
            _row("S01013484", "Flagged", 11),
        ],
    )
    codes = ["S01013482", "S01013483", "S01013484", "S01013485"]
    pairs = [
        ("S01007001", "S01013482", 30),
        ("S01007002", "S01013483", 30),
        ("S01007003", "S01013484", 30),
        ("S01007004", "S01013485", 30),
    ]
    scored = ["S01007001", "S01007002", "S01007003", "S01007004"]
    paths = _simple(tmp_path, c14, codes, pairs, scored)
    _ur(
        paths["ur"],
        [
            ("S01007001", 1, 0),
            ("S01007002", 3, 0),
            ("S01007003", 2, 1),
            ("S01007004", 5, 0),
        ],
    )
    out = tmp_path / "out.json"
    rc = main(
        [
            "--c14",
            str(c14),
            "--lookup",
            str(paths["lookup"]),
            "--crosswalk",
            str(paths["crosswalk"]),
            "--merge-map",
            str(paths["merge"]),
            "--ur",
            str(paths["ur"]),
            "--out",
            str(out),
            "--synthetic-fixtures",
        ]
    )
    captured = capsys.readouterr()
    assert rc == 0
    text = captured.out
    for label in ("scored", "unavailable", "incomplete_suppressed", "absent_from_c14"):
        assert f"ur6 {label} " in text
        assert "class1=" in text
    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["dz2022_counts"]["suppressed"] == 1
    assert result["dz2022_counts"]["absent_from_c14"] == 1
    by_i = {zone["dz2011"]: zone for zone in result["dz2011"]}
    assert by_i["S01007004"]["absent_from_c14"] is True
    assert by_i["S01007004"]["volume_below_5"] is False
    assert by_i["S01007002"]["volume_below_5"] is True
    assert by_i["S01007002"]["absent_from_c14"] is False
    assert result["dz2011_by_ur6"]["scored"]["1"] == 1
    assert result["dz2011_by_ur6"]["unavailable"]["2"] == 1
    assert result["dz2011_by_ur6"]["incomplete_suppressed"]["3"] == 1
    assert result["dz2011_by_ur6"]["absent_from_c14"]["5"] == 1
    for sentinel in SENTINELS:
        assert sentinel not in text


def test_e8_drops_sliver_on_source_zone(tmp_path: Path):
    c14 = tmp_path / "c14.csv"
    _c14(c14, [_row("S01013482", "Ok", 8)])
    pairs = [
        ("S01007001", "S01013482", 1000),
        ("S01007002", "S01013482", 4),
    ]
    paths = _simple(tmp_path, c14, ["S01013482"], pairs, ["S01007001", "S01007002"])
    result = _build(tmp_path, **paths)
    by_i = {zone["dz2011"]: zone for zone in result["dz2011"]}
    assert by_i["S01007001"]["count_s"] == 8
    assert by_i["S01007002"]["count_s"] == 0
    assert by_i["S01007002"]["case"] == "not_applicable"


def test_header_found_in_xlsx_below_row_1(tmp_path: Path):
    path = tmp_path / "c14.xlsx"
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "C14"
    sheet.append(["preamble"])
    sheet.append(HEADER)
    sheet.append([2024, "Scotland", "S92000003", *SENTINELS[:3], 50, SENTINELS[3]])
    sheet.append([2024, "Ok", "S01013482", *SENTINELS[:3], 6, SENTINELS[3]])
    book.save(path)
    paths = _simple(tmp_path, path, ["S01013482"], [("S01007000", "S01013482", 10)], ["S01007000"])
    result = _build(tmp_path, **paths, scored_run=True)
    encoded = json.dumps(result)
    for sentinel in SENTINELS:
        assert sentinel not in encoded
    assert result["national"]["scotland_row_volume"] == 50
    assert result["dz2011"][0]["count_s"] == 6


def _simple(tmp: Path, c14: Path, codes: list[str], pairs: list, scored: list[str], scored_codes=None):
    lookup = tmp / "lookup.csv"
    cross = tmp / "cross.csv"
    merge = tmp / "merge.csv"
    ur = tmp / "ur.csv"
    _lookup(lookup, codes)
    _crosswalk(cross, pairs)
    _merge(merge, scored if scored_codes is None else scored_codes)
    _ur(ur, [(code, 1, 0) for code in (scored if scored_codes is None else scored_codes)])
    return {"c14": c14, "lookup": lookup, "crosswalk": cross, "merge": merge, "ur": ur}
