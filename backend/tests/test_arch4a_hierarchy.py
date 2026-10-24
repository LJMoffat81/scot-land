"""ARCH-4a: ref.unit / ref.unit_hierarchy loader + DZ value lineage."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2
import pytest
from fastapi.testclient import TestClient

from etl.load_unit_hierarchy import (
    CROSSWALK_CSV,
    SPINE_CSV,
    HierarchyError,
    build_unit_hierarchy_rows,
    load_unit_hierarchy,
    main,
    parse_crosswalk_people,
    parse_zone_spine,
)
from layers.dz_context import (
    METRIC_DEFS,
    METRICS_CSV,
    _metrics_csv_sha8,
    build_metrics_payload,
    dz_values_lineage,
)

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"

_SPINE_HEADER = "code,vintage,name,iz_code,la_code,la_name"
_CW_HEADER = "dz2011,dz2022,weight,method"


def _dsn() -> str:
    dsn = os.environ.get("ARCH1_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ARCH1_TEST_DSN not set")
    return dsn


def _spine_row(
    *,
    code: str = "S01013482",
    vintage: str = "2022",
    name: str = "Zone A",
    iz_code: str = "S02001236",
    la_code: str = "S12000033",
    la_name: str = "Aberdeen City",
) -> str:
    return f"{code},{vintage},{name},{iz_code},{la_code},{la_name}"


def _write_spine(path: Path, rows: list[str]) -> Path:
    path.write_text(_SPINE_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _write_cw(path: Path, rows: list[str]) -> Path:
    path.write_text(_CW_HEADER + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _minimal_pair(tmp_path: Path) -> tuple[Path, Path]:
    """One dz2011 + one dz2022 with matching crosswalk weight 1."""
    spine = _write_spine(
        tmp_path / "spine.csv",
        [
            _spine_row(
                code="S01006506",
                vintage="2011",
                name="Old A",
                iz_code="S02001236",
                la_code="S12000033",
                la_name="Aberdeen City",
            ),
            _spine_row(
                code="S01013482",
                vintage="2022",
                name="New A",
                iz_code="S02001236",
                la_code="S12000033",
                la_name="Aberdeen City",
            ),
        ],
    )
    cw = _write_cw(
        tmp_path / "cw.csv",
        ["S01006506,S01013482,1,pop_hhres_2022"],
    )
    return spine, cw


# ---------------------------------------------------------------------------
# Positive: real committed CSVs + CLI
# ---------------------------------------------------------------------------


def test_real_committed_counts() -> None:
    built = build_unit_hierarchy_rows(SPINE_CSV, CROSSWALK_CSV)
    c = built["counts"]
    assert c["units_total"] == 15735
    assert c["scotland"] == 1
    assert c["council"] == 32
    assert c["iz2022"] == 1334
    assert c["dz2022"] == 7392
    assert c["dz2011"] == 6976
    assert c["hierarchy_total"] == 26623
    assert c["dz2022_to_iz2022"] == 7392
    assert c["iz2022_to_council"] == 1334
    assert c["dz2022_to_council"] == 7392
    assert c["council_to_scotland"] == 32
    assert c["dz2011_to_dz2022"] == 10473
    assert len(built["units"]) == 15735
    assert len(built["hierarchy"]) == 26623
    edge_pairs = {(row[0], row[2]) for row in built["hierarchy"]}
    assert edge_pairs == {
        ("dz2022", "iz2022"),
        ("iz2022", "council"),
        ("dz2022", "council"),
        ("council", "scotland"),
        ("dz2011", "dz2022"),
    }
    unit_types = {row[0] for row in built["units"]}
    assert unit_types == {
        "scotland",
        "council",
        "iz2022",
        "dz2022",
        "dz2011",
    }


def test_cli_check_passes(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--check"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {
        "council": 32,
        "council_to_scotland": 32,
        "dz2011": 6976,
        "dz2011_to_dz2022": 10473,
        "dz2022": 7392,
        "dz2022_to_council": 7392,
        "dz2022_to_iz2022": 7392,
        "hierarchy_total": 26623,
        "iz2022": 1334,
        "iz2022_to_council": 1334,
        "ok": True,
        "scotland": 1,
        "units_total": 15735,
    }


@pytest.mark.parametrize("argv", [[], ["--check", "--load"]])
def test_cli_requires_exact_mode(
    argv: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    rc = main(argv)
    assert rc == 2
    assert "HIERARCHY: specify exactly one of --check or --load" in (
        capsys.readouterr().err
    )


def test_cli_hierarchy_error_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    missing = tmp_path / "nope.csv"
    rc = main(["--check", "--spine", str(missing)])
    assert rc == 1
    assert "HIERARCHY: zone_spine not found" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# parse_zone_spine negatives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, True, False, 1, 1.5, [], {}])
def test_parse_zone_spine_rejects_bad_path_type(bad: Any) -> None:
    with pytest.raises(HierarchyError, match=r"^HIERARCHY: spine_path must be a Path or str$"):
        parse_zone_spine(bad)  # type: ignore[arg-type]


def test_parse_zone_spine_missing_file(tmp_path: Path) -> None:
    with pytest.raises(HierarchyError, match=r"^HIERARCHY: zone_spine not found:"):
        parse_zone_spine(tmp_path / "missing.csv")


def test_parse_zone_spine_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(HierarchyError, match=r"^HIERARCHY: zone_spine is empty:"):
        parse_zone_spine(path)


@pytest.mark.parametrize(
    "col",
    ["code", "vintage", "name", "iz_code", "la_code", "la_name"],
)
def test_parse_zone_spine_missing_column(tmp_path: Path, col: str) -> None:
    cols = [c for c in ("code", "vintage", "name", "iz_code", "la_code", "la_name") if c != col]
    path = tmp_path / "spine.csv"
    path.write_text(",".join(cols) + "\n", encoding="utf-8")
    with pytest.raises(
        HierarchyError, match=rf"^HIERARCHY: zone_spine missing column '{col}'$"
    ):
        parse_zone_spine(path)


def test_parse_zone_spine_invalid_vintage(tmp_path: Path) -> None:
    path = _write_spine(
        tmp_path / "spine.csv",
        [_spine_row(vintage="2012")],
    )
    with pytest.raises(
        HierarchyError, match=r"^HIERARCHY: zone_spine row 2: invalid vintage '2012'$"
    ):
        parse_zone_spine(path)


@pytest.mark.parametrize(
    ("code", "vintage"),
    [
        ("S01006505", "2011"),
        ("S01013482", "2011"),
        ("S01013481", "2022"),
        ("S01020874", "2022"),
        ("S02001236", "2022"),
        ("bad", "2022"),
    ],
)
def test_parse_zone_spine_invalid_code(
    tmp_path: Path, code: str, vintage: str
) -> None:
    path = _write_spine(
        tmp_path / "spine.csv",
        [_spine_row(code=code, vintage=vintage)],
    )
    with pytest.raises(
        HierarchyError,
        match=rf"^HIERARCHY: zone_spine row 2: invalid code '{code}' for vintage {vintage}$",
    ):
        parse_zone_spine(path)


def test_parse_zone_spine_duplicate(tmp_path: Path) -> None:
    row = _spine_row(code="S01013482", vintage="2022")
    path = _write_spine(tmp_path / "spine.csv", [row, row])
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: zone_spine: duplicate \(code, vintage\) \('S01013482', 2022\)$",
    ):
        parse_zone_spine(path)


@pytest.mark.parametrize(
    "row",
    [
        _spine_row(name="", la_name="Aberdeen City"),
        _spine_row(name="Zone A", la_name=""),
    ],
)
def test_parse_zone_spine_empty_name_or_la_name(tmp_path: Path, row: str) -> None:
    path = _write_spine(tmp_path / "spine.csv", [row])
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: zone_spine row 2: empty name or la_name$",
    ):
        parse_zone_spine(path)


def test_parse_zone_spine_invalid_iz_code(tmp_path: Path) -> None:
    path = _write_spine(
        tmp_path / "spine.csv",
        [_spine_row(iz_code="S12000033")],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: zone_spine row 2: invalid iz_code 'S12000033'$",
    ):
        parse_zone_spine(path)


def test_parse_zone_spine_invalid_la_code(tmp_path: Path) -> None:
    path = _write_spine(
        tmp_path / "spine.csv",
        [_spine_row(la_code="S02001236")],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: zone_spine row 2: invalid la_code 'S02001236'$",
    ):
        parse_zone_spine(path)


def test_parse_zone_spine_conflicting_council_names(tmp_path: Path) -> None:
    path = _write_spine(
        tmp_path / "spine.csv",
        [
            _spine_row(
                code="S01013482",
                vintage="2022",
                la_code="S12000033",
                la_name="Aberdeen City",
            ),
            _spine_row(
                code="S01013483",
                vintage="2022",
                la_code="S12000033",
                la_name="Other Name",
                iz_code="S02001237",
            ),
        ],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: council S12000033 has conflicting names:",
    ):
        parse_zone_spine(path)


def test_parse_zone_spine_iz_spans_councils(tmp_path: Path) -> None:
    path = _write_spine(
        tmp_path / "spine.csv",
        [
            _spine_row(
                code="S01013482",
                vintage="2022",
                iz_code="S02001236",
                la_code="S12000033",
                la_name="Aberdeen City",
            ),
            _spine_row(
                code="S01013483",
                vintage="2022",
                iz_code="S02001236",
                la_code="S12000034",
                la_name="Aberdeenshire",
            ),
        ],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: iz2022 S02001236 spans multiple councils:",
    ):
        parse_zone_spine(path)


def test_parse_zone_spine_missing_2011(tmp_path: Path) -> None:
    path = _write_spine(
        tmp_path / "spine.csv",
        [_spine_row(code="S01013482", vintage="2022")],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: zone_spine: missing vintage 2011 or 2022 rows$",
    ):
        parse_zone_spine(path)


def test_parse_zone_spine_missing_2022(tmp_path: Path) -> None:
    path = _write_spine(
        tmp_path / "spine.csv",
        [_spine_row(code="S01006506", vintage="2011")],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: zone_spine: missing vintage 2011 or 2022 rows$",
    ):
        parse_zone_spine(path)


# ---------------------------------------------------------------------------
# parse_crosswalk_people negatives
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, True, False, 1, 1.5, [], {}])
def test_parse_crosswalk_rejects_bad_path_type(bad: Any) -> None:
    with pytest.raises(
        HierarchyError, match=r"^HIERARCHY: crosswalk_path must be a Path or str$"
    ):
        parse_crosswalk_people(
            bad,  # type: ignore[arg-type]
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


@pytest.mark.parametrize(
    ("d11", "d22"),
    [
        (None, {"S01013482"}),
        (set(), {"S01013482"}),
        (["S01006506"], {"S01013482"}),
        ({""}, {"S01013482"}),
        ({1}, {"S01013482"}),  # type: ignore[set-item]
        ({"S01006506"}, None),
        ({"S01006506"}, set()),
        ({"S01006506"}, ["S01013482"]),
        ({"S01006506"}, {""}),
        ({"S01006506"}, {1}),  # type: ignore[set-item]
    ],
)
def test_parse_crosswalk_rejects_bad_code_sets(d11: Any, d22: Any) -> None:
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: crosswalk: valid_dz2011 and valid_dz2022 must be non-empty sets of strings$",
    ):
        parse_crosswalk_people(
            CROSSWALK_CSV, valid_dz2011=d11, valid_dz2022=d22
        )


def test_parse_crosswalk_missing_file(tmp_path: Path) -> None:
    with pytest.raises(HierarchyError, match=r"^HIERARCHY: crosswalk not found:"):
        parse_crosswalk_people(
            tmp_path / "missing.csv",
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


def test_parse_crosswalk_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(HierarchyError, match=r"^HIERARCHY: crosswalk is empty:"):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


@pytest.mark.parametrize("col", ["dz2011", "dz2022", "weight", "method"])
def test_parse_crosswalk_missing_column(tmp_path: Path, col: str) -> None:
    cols = [c for c in ("dz2011", "dz2022", "weight", "method") if c != col]
    path = tmp_path / "cw.csv"
    path.write_text(",".join(cols) + "\n", encoding="utf-8")
    with pytest.raises(
        HierarchyError, match=rf"^HIERARCHY: crosswalk missing column '{col}'$"
    ):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


def test_parse_crosswalk_unknown_dz2011(tmp_path: Path) -> None:
    path = _write_cw(tmp_path / "cw.csv", ["S01006507,S01013482,1,pop_hhres_2022"])
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: crosswalk row 2: unknown dz2011 'S01006507'$",
    ):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


def test_parse_crosswalk_unknown_dz2022(tmp_path: Path) -> None:
    path = _write_cw(tmp_path / "cw.csv", ["S01006506,S01013483,1,pop_hhres_2022"])
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: crosswalk row 2: unknown dz2022 'S01013483'$",
    ):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


def test_parse_crosswalk_duplicate_pair(tmp_path: Path) -> None:
    row = "S01006506,S01013482,0.5,pop_hhres_2022"
    path = _write_cw(tmp_path / "cw.csv", [row, row])
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: crosswalk: duplicate pair \('S01006506', 'S01013482'\)$",
    ):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


@pytest.mark.parametrize(
    "weight",
    ["0", "-0.1", "1.01", "NaN", "abc"],
)
def test_parse_crosswalk_bad_weight(tmp_path: Path, weight: str) -> None:
    path = _write_cw(
        tmp_path / "cw.csv",
        [f"S01006506,S01013482,{weight},pop_hhres_2022"],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: crosswalk row 2: weight must be in \(0, 1\], got ",
    ):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


def test_parse_crosswalk_invalid_method(tmp_path: Path) -> None:
    path = _write_cw(
        tmp_path / "cw.csv",
        ["S01006506,S01013482,1,not_a_method"],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: crosswalk row 2: invalid method 'not_a_method'$",
    ):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


def test_parse_crosswalk_weights_not_sum_to_one(tmp_path: Path) -> None:
    path = _write_cw(
        tmp_path / "cw.csv",
        [
            "S01006506,S01013482,0.4,pop_hhres_2022",
            "S01006506,S01013483,0.4,pop_hhres_2022",
        ],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: crosswalk: dz2011 S01006506 weights sum to 0\.800000, expected 1\.0$",
    ):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482", "S01013483"},
        )


def test_parse_crosswalk_zero_rows(tmp_path: Path) -> None:
    path = _write_cw(tmp_path / "cw.csv", [])
    with pytest.raises(HierarchyError, match=r"^HIERARCHY: crosswalk has 0 rows$"):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506"},
            valid_dz2022={"S01013482"},
        )


def test_parse_crosswalk_missing_dz2011_in_sums(tmp_path: Path) -> None:
    """Every spine dz2011 must appear in the crosswalk with weights summing to 1."""
    path = _write_cw(
        tmp_path / "cw.csv",
        ["S01006506,S01013482,1,pop_hhres_2022"],
    )
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: crosswalk: dz2011 S01006507 weights sum to 0\.000000, expected 1\.0$",
    ):
        parse_crosswalk_people(
            path,
            valid_dz2011={"S01006506", "S01006507"},
            valid_dz2022={"S01013482"},
        )


# ---------------------------------------------------------------------------
# load_unit_hierarchy: DSN + PostGIS
# ---------------------------------------------------------------------------


def test_load_unit_hierarchy_missing_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ARCH1_TEST_DSN", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(
        HierarchyError,
        match=r"^HIERARCHY: ARCH1_TEST_DSN or DATABASE_URL not set$",
    ):
        load_unit_hierarchy()


def test_load_unit_hierarchy_postgis(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    dsn = _dsn()
    monkeypatch.setenv("ARCH1_TEST_DSN", dsn)
    spine, cw = _minimal_pair(tmp_path)
    conn = psycopg2.connect(dsn)
    try:
        counts = load_unit_hierarchy(conn, spine_path=spine, crosswalk_path=cw)
        assert counts["units_total"] == 5  # scotland + 1 council + 1 iz + 1 dz22 + 1 dz11
        assert counts["hierarchy_total"] == 5
        with conn.cursor() as cur:
            cur.execute("SELECT unit_type, count(*) FROM ref.unit GROUP BY unit_type ORDER BY 1")
            by_type = {r[0]: int(r[1]) for r in cur.fetchall()}
            assert by_type == {
                "council": 1,
                "dz2011": 1,
                "dz2022": 1,
                "iz2022": 1,
                "scotland": 1,
            }
            cur.execute(
                """
                SELECT child_type, parent_type, count(*), sum(weight)
                FROM ref.unit_hierarchy
                GROUP BY child_type, parent_type
                ORDER BY 1, 2
                """
            )
            edges = {
                (r[0], r[1]): (int(r[2]), Decimal(r[3]))
                for r in cur.fetchall()
            }
            assert edges[("dz2022", "iz2022")] == (1, Decimal("1"))
            assert edges[("iz2022", "council")] == (1, Decimal("1"))
            assert edges[("dz2022", "council")] == (1, Decimal("1"))
            assert edges[("council", "scotland")] == (1, Decimal("1"))
            assert edges[("dz2011", "dz2022")] == (1, Decimal("1"))
            with pytest.raises(psycopg2.errors.CheckViolation):
                cur.execute(
                    """
                    INSERT INTO ref.unit_hierarchy (
                      child_type, child_id, parent_type, parent_id,
                      weight, version, valid_from
                    ) VALUES (
                      'dz2022','S01013482','council','S12000033',
                      0,'bad',%s
                    )
                    """,
                    (date(2022, 1, 1),),
                )
            conn.rollback()
    finally:
        conn.close()


def test_build_unit_hierarchy_rows_minimal(tmp_path: Path) -> None:
    spine, cw = _minimal_pair(tmp_path)
    built = build_unit_hierarchy_rows(spine, cw)
    assert built["counts"]["units_total"] == 5
    assert built["counts"]["hierarchy_total"] == 5
    assert built["units"][0] == (
        "scotland",
        "scotland",
        "scotland",
        "Scotland",
        date(2022, 1, 1),
        None,
    )


# ---------------------------------------------------------------------------
# dz_values_lineage + build_metrics_payload + tiles ?lineage=1
# ---------------------------------------------------------------------------


def test_metrics_csv_sha8_matches_file() -> None:
    expected = hashlib.sha256(METRICS_CSV.read_bytes()).hexdigest()[:8]
    assert _metrics_csv_sha8() == expected


def test_dz_values_lineage_positive() -> None:
    codes = ["S01013483", "S01013482", "S01013482"]
    lin = dz_values_lineage(2022, codes=codes, measure="pop_density")
    ordered = ["S01013482", "S01013483"]
    sha8 = _metrics_csv_sha8()
    assert lin["source_layer_ids"] == ["dz2022"]
    assert lin["dataset_version"] == f"dz2022@2022-01-01-{sha8}"
    assert lin["as_of"] == "2022-01-01"
    assert lin["method"] == "source"
    assert lin["unit"] == "dz2022"
    assert lin["roll_up_to"] == ["council", "scotland"]
    assert lin["child_count"] == 2
    assert lin["child_set_hash"] == hashlib.sha256(
        "\n".join(ordered).encode("utf-8")
    ).hexdigest()


@pytest.mark.parametrize("bad", [None, True, False, 2010, 2022.0, "2022", [], {}])
def test_dz_values_lineage_rejects_bad_vintage(bad: Any) -> None:
    with pytest.raises(ValueError, match=r"^DZ: vintage must be 2011 or 2022"):
        dz_values_lineage(bad, codes=["S01013482"])  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad",
    [None, True, False, 1, 1.5, "", "  ", "nope", [], {}],
)
def test_dz_values_lineage_rejects_bad_measure(bad: Any) -> None:
    with pytest.raises(ValueError, match=r"^DZ: measure must be one of"):
        dz_values_lineage(2022, codes=["S01013482"], measure=bad)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "bad",
    [None, True, False, 1, 1.5, "S01013482", {}, [""], ["  "], [1], [None]],
)
def test_dz_values_lineage_rejects_bad_codes(bad: Any) -> None:
    with pytest.raises(
        ValueError, match=r"^DZ: codes must be a non-empty list of non-empty strings"
    ):
        dz_values_lineage(2022, codes=bad)  # type: ignore[arg-type]


def test_dz_values_lineage_rejects_empty_codes() -> None:
    with pytest.raises(
        ValueError, match=r"^DZ: codes must be a non-empty list of non-empty strings$"
    ):
        dz_values_lineage(2022, codes=[])


def test_build_metrics_payload_attaches_lineage() -> None:
    payload = build_metrics_payload(vintage=2022, include_geometry=False)
    assert payload["features"]
    lin = payload["meta"]["lineage"]
    assert lin is not None
    assert lin["unit"] == "dz2022"
    assert lin["child_count"] == len(
        {str(f["properties"]["code"]) for f in payload["features"]}
    )
    assert lin["method"] == "source"
    assert lin["roll_up_to"] == ["council", "scotland"]
    assert set(lin) == {
        "source_layer_ids",
        "dataset_version",
        "as_of",
        "method",
        "unit",
        "roll_up_to",
        "child_count",
        "child_set_hash",
    }


def test_build_metrics_payload_lineage_none_when_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "layers.dz_context._rows_from_postgis", lambda: []
    )
    monkeypatch.setattr(
        "layers.dz_context.load_metrics_rows", lambda: ()
    )
    payload = build_metrics_payload(vintage=2022, include_geometry=False)
    assert payload["features"] == []
    assert payload["meta"]["lineage"] is None


def _synthetic_metrics(codes: dict[str, float]) -> dict[str, Any]:
    features = [
        {
            "type": "Feature",
            "geometry": None,
            "properties": {
                "code": code,
                "population_density_per_km2": val,
                "vintage": 2022,
            },
        }
        for code, val in codes.items()
    ]
    return {"type": "FeatureCollection", "features": features, "meta": {}}


def test_tiles_values_lineage_query(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Default response stays 4-key; ?lineage=1 attaches lineage + ETag suffix."""
    import importlib.util
    import sys

    helpers_path = BACKEND / "tests" / "fixtures" / "arch2" / "helpers.py"
    spec = importlib.util.spec_from_file_location("arch2_helpers_4a", helpers_path)
    assert spec and spec.loader
    helpers = importlib.util.module_from_spec(spec)
    sys.modules["arch2_helpers_4a"] = helpers
    spec.loader.exec_module(helpers)

    tiles_dir = tmp_path / "tiles"
    tiles_dir.mkdir()
    version = "2026-10-22.abcd1234"
    pm = tiles_dir / f"dz2022.{version}.pmtiles"
    pm.write_bytes(b"pmtiles-stub")
    (tiles_dir / "manifest.json").write_text(
        json.dumps(
            {
                "schema": 1,
                "tilesets": {
                    "dz2022": {
                        "version": version,
                        "file": pm.name,
                        "measure": "pop_density",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    helpers.write_storage_yaml(tmp_path / "storage.yaml", keep_versions=3)
    monkeypatch.setenv("TILES_DIR", str(tiles_dir))

    entry = helpers.make_entry(
        "dz2022",
        title="Data Zones 2022",
        measure="pop_density",
        style={"fill": {"fill-color": "#c6dbef"}},
        legend=[{"label": "10", "color": "#c6dbef"}],
    )
    monkeypatch.setattr("api.tiles_routes.registry", lambda: {"dz2022": entry})
    monkeypatch.setattr(
        "layers.registry.loader.registry", lambda: {"dz2022": entry}
    )

    values_codes = {"S01013482": 12.5, "S01013483": 100.0}
    monkeypatch.setattr(
        "layers.dz_context.build_metrics_payload",
        lambda **_k: _synthetic_metrics(values_codes),
    )

    import api.tiles_routes as tr

    with tr._reader_lock:
        for _key, (fh, _reader) in list(tr._reader_cache.items()):
            try:
                fh.close()
            except OSError:
                pass
        tr._reader_cache.clear()

    from api.main import ROUTER_STATUS, app

    assert ROUTER_STATUS.get("api.tiles_routes", {}).get("loaded") is True
    client = TestClient(app)

    r0 = client.get(f"/v1/tiles/dz2022/{version}/values/pop_density.json")
    assert r0.status_code == 200
    body0 = r0.json()
    assert set(body0) == {"layer", "version", "measure", "values"}
    sha8 = version.rsplit(".", 1)[-1]
    assert r0.headers.get("etag") == f'"{sha8}-values-pop_density"'

    r1 = client.get(
        f"/v1/tiles/dz2022/{version}/values/pop_density.json",
        params={"lineage": "1"},
    )
    assert r1.status_code == 200
    body1 = r1.json()
    assert set(body1) == {"layer", "version", "measure", "values", "lineage"}
    assert body1["values"] == values_codes
    as_of, sha8_ver = version.rsplit(".", 1)
    assert body1["lineage"]["dataset_version"] == f"dz2022@{as_of}-{sha8_ver}"
    assert body1["lineage"]["as_of"] == as_of
    assert body1["lineage"]["child_count"] == 2
    assert r1.headers.get("etag") == f'"{sha8}-values-pop_density-lineage"'


def test_metric_defs_unchanged_for_lineage() -> None:
    assert "pop_density" in METRIC_DEFS
    assert "simd" in METRIC_DEFS
    assert "house_price" in METRIC_DEFS
