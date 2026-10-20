"""V14-SPEC-A2b: 2023 NOT_SCORED, reconcile, am2 types, T8/T16-T23/T25 primary.

SYNTHETIC fixtures only (T24 is in test_v14_a2_am2_real.py). No 2024 prices.
A2b scope: T8, T16-T20, T22-T23, T25 via build_v14_primary_2023.main.
TE gaps: red-first for T16-18, T22; census mutations beyond M19 header-only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.build_v14_primary_2023 import (
    ABSENT_FROM_FILE_ZONES,
    NOT_SCORED_REASONS,
    classify_not_scored,
    main as primary_main,
)

SENTINEL = "SENTINEL_7Q"
ZONE = "S01006506"
C14_COLLISION_ZONE = "S01006564"  # first DZ2011 in collision_excluded_dz2011.csv
PINNED = ("S01007788", "S01010206", "S01010226", "S01010462", "S01010493", "S01011598")


def _sale(zone: str, year: object, price: object, count: object = "2") -> dict:
    return {
        "zone": zone,
        "year": year,
        "n_sales": count,
        "price": price,
        "median_price": price,
    }


def _am2(
    *,
    excluded: list | None = None,
    zones_present: list | None = None,
    skipped_geography: dict | None = None,
) -> dict:
    return {
        "label": "excluding price-suppressed zone-years (AM-2)",
        "excluded": excluded if excluded is not None else [],
        "excluded_by_year": {},
        "zones_present": zones_present if zones_present is not None else [],
        "skipped_geography": skipped_geography if skipped_geography is not None else {},
        "fit_window_no_complete_row": [],
    }


def _write_b2(
    tmp_path: Path,
    sales: list[dict],
    *,
    am2: object | None = ...,
    name: str = "b2.json",
) -> Path:
    payload: dict = {"label": "SYNTHETIC", "house_sales": sales}
    if am2 is not ...:
        payload["am2"] = am2  # type: ignore[assignment]
    path = tmp_path / name
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _write_drc(tmp_path: Path, drc: dict[str, float], name: str = "drc.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(drc) + "\n", encoding="utf-8")
    return path


def _write_census(path: Path, rows: list[tuple[str, str]], *, header: str = "zone,reason") -> Path:
    lines = [header]
    for zone, reason in rows:
        lines.append(f"{zone},{reason}")
    path.write_text("\n".join(lines) + ("\n" if rows or header else ""), encoding="utf-8")
    return path


def _run(
    b2: Path,
    drc: Path,
    primary: Path,
    builder: Path,
    *,
    not_scored: Path | None = None,
    census: Path | None = None,
) -> int:
    argv = [
        "--b2-out",
        str(b2),
        "--drc",
        str(drc),
        "--primary-out",
        str(primary),
        "--builder-out",
        str(builder),
    ]
    if not_scored is not None:
        argv.extend(["--not-scored-out", str(not_scored)])
    if census is not None:
        argv.extend(["--reconcile-census", str(census)])
    return primary_main(argv)


# --- T8 suppressed 2023 zone NOT_SCORED ---


def test_t8_suppressed_2023_not_scored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T8: 2023 suppressed zone absent from primary; not_scored suppressed_price; spy 0 for it."""
    priced = ZONE
    suppressed = "S01006507"
    sales = [_sale(priced, 2023, "100", "6")]
    am2 = _am2(
        excluded=[
            {
                "zone": suppressed,
                "year": 2023,
                "reason": "suppressed_price",
                "count": 3,
            }
        ],
        zones_present=[priced, suppressed],
    )
    calls = {"n": 0, "values": []}

    def spy(value: object) -> object:
        calls["n"] += 1
        calls["values"].append(value)
        return value

    monkeypatch.setattr("scripts.build_v14_primary_2023.read_price_field", spy)
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(),
    )
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {priced: 40.0, suppressed: 40.0})
    primary = tmp_path / "primary.json"
    builder = tmp_path / "builder.json"
    not_scored = tmp_path / "not_scored.json"
    assert _run(b2, drc, primary, builder, not_scored=not_scored) == 0
    zones = {row["zone"] for row in json.loads(primary.read_text(encoding="utf-8"))["zones"]}
    assert priced in zones
    assert suppressed not in zones
    payload = json.loads(not_scored.read_text(encoding="utf-8"))
    assert {"zone": suppressed, "reason": "suppressed_price"} in payload["not_scored"]
    # No sales row for suppressed => its price was never read.
    assert calls["n"] == 1
    assert calls["values"] == ["100"]


# --- T16 reconcile OK ---


def test_t16_reconcile_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T16: census equals classification; rc 0; counts line exact."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset({"S01007788"}),
    )
    priced = ZONE
    suppressed = "S01006507"
    absent = "S01007788"
    sales = [_sale(priced, 2023, "100", "6")]
    am2 = _am2(
        excluded=[
            {
                "zone": suppressed,
                "year": 2023,
                "reason": "suppressed_price",
                "count": 3,
            }
        ],
        zones_present=[priced, suppressed],
    )
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {priced: 40.0, suppressed: 40.0, absent: 40.0})
    census = _write_census(
        tmp_path / "census.csv",
        [(suppressed, "suppressed_price"), (absent, "absent_from_file")],
    )
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    not_scored = tmp_path / "ns.json"
    assert _run(b2, drc, primary, builder, not_scored=not_scored, census=census) == 0
    out = capsys.readouterr().out
    assert "not_scored suppressed_price=1 no_sales=0 no_2023_row=0 absent_from_file=1\n" in out
    assert "zones=1\n" in out
    payload = json.loads(not_scored.read_text(encoding="utf-8"))
    assert payload["denominator"] == 1
    assert payload["counts"] == {
        "suppressed_price": 1,
        "no_sales": 0,
        "no_2023_row": 0,
        "absent_from_file": 1,
    }


# --- T17 reconcile mismatch ---


@pytest.mark.parametrize(
    "case,census_rows,expect_a,expect_b",
    [
        (
            "missing_zone",
            [("S01007788", "absent_from_file")],
            1,
            0,
        ),
        (
            "extra_zone",
            [
                ("S01006507", "suppressed_price"),
                ("S01007788", "absent_from_file"),
                ("S01006508", "no_2023_row"),
            ],
            0,
            1,
        ),
        (
            "reason_swapped",
            [
                ("S01006507", "no_sales"),
                ("S01007788", "absent_from_file"),
            ],
            1,
            1,
        ),
    ],
)
def test_t17_reconcile_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    case: str,
    census_rows: list[tuple[str, str]],
    expect_a: int,
    expect_b: int,
) -> None:
    """T17: mismatch message; neither primary nor not_scored written."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset({"S01007788"}),
    )
    priced = ZONE
    suppressed = "S01006507"
    absent = "S01007788"
    sales = [_sale(priced, 2023, "100", "6")]
    am2 = _am2(
        excluded=[
            {
                "zone": suppressed,
                "year": 2023,
                "reason": "suppressed_price",
                "count": 3,
            }
        ],
        zones_present=[priced, suppressed],
    )
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {priced: 40.0, suppressed: 40.0, absent: 40.0})
    census = _write_census(tmp_path / f"{case}.csv", census_rows)
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    not_scored = tmp_path / "ns.json"
    assert _run(b2, drc, primary, builder, not_scored=not_scored, census=census) == 1
    err = capsys.readouterr().err
    assert err.startswith("B4_PRIMARY_2023: REFUSED: not_scored reconcile:")
    assert f"only_in_s5={expect_a}" in err
    assert f"only_in_census={expect_b}" in err
    assert not primary.exists()
    assert not builder.exists()
    assert not not_scored.exists()


# --- T18 census missing / empty / header-only / bad header / bad reason / 3 columns ---


def test_t18_census_refusals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T18: each census refusal exact message; nothing written."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset({"S01007788"}),
    )
    priced = ZONE
    sales = [_sale(priced, 2023, "100", "6")]
    am2 = _am2(zones_present=[priced])
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {priced: 40.0})

    cases: list[tuple[str, Path, str]] = []

    missing = tmp_path / "missing.csv"
    cases.append(
        (
            "missing",
            missing,
            f"B4_PRIMARY_2023: ERROR: census: expected {missing}, got absent",
        )
    )

    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    cases.append(
        (
            "empty",
            empty,
            "B4_PRIMARY_2023: ERROR: census header: expected zone,reason, got absent",
        )
    )

    header_only = tmp_path / "header_only.csv"
    header_only.write_text("zone,reason\n", encoding="utf-8")
    cases.append(
        (
            "header_only",
            header_only,
            "B4_PRIMARY_2023: ERROR: census header: expected zone,reason, got absent",
        )
    )

    bad_header = tmp_path / "bad_header.csv"
    bad_header.write_text("zone,code\nS01007788,absent_from_file\n", encoding="utf-8")
    cases.append(
        (
            "bad_header",
            bad_header,
            "B4_PRIMARY_2023: ERROR: census header: expected zone,reason, got other header",
        )
    )

    bad_reason = tmp_path / "bad_reason.csv"
    bad_reason.write_text("zone,reason\nS01007788,mystery\n", encoding="utf-8")
    cases.append(
        (
            "bad_reason",
            bad_reason,
            "B4_PRIMARY_2023: ERROR: census row: expected zone,reason, got malformed",
        )
    )

    three_col = tmp_path / "three.csv"
    three_col.write_text("zone,reason\nS01007788,absent_from_file,x\n", encoding="utf-8")
    cases.append(
        (
            "three_col",
            three_col,
            "B4_PRIMARY_2023: ERROR: census row: expected zone,reason, got malformed",
        )
    )

    for name, census_path, message in cases:
        case_dir = tmp_path / name
        case_dir.mkdir()
        case_b2 = _write_b2(case_dir, sales, am2=am2)
        case_drc = _write_drc(case_dir, {priced: 40.0})
        primary = case_dir / "p.json"
        builder = case_dir / "b.json"
        not_scored = case_dir / "ns.json"
        assert _run(case_b2, case_drc, primary, builder, not_scored=not_scored, census=census_path) == 1
        assert capsys.readouterr().err == message + "\n"
        assert not primary.exists()
        assert not builder.exists()
        assert not not_scored.exists()


# --- T19 C14 exclusions not applied ---


def test_t19_c14_exclusions_not_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T19: C14 collision DZ2011 with complete 2023 row is scored under am2."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(),
    )
    sales = [_sale(C14_COLLISION_ZONE, 2023, "100", "6")]
    am2 = _am2(zones_present=[C14_COLLISION_ZONE])
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {C14_COLLISION_ZONE: 40.0})
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    assert _run(b2, drc, primary, builder) == 0
    zones = {row["zone"] for row in json.loads(primary.read_text(encoding="utf-8"))["zones"]}
    assert C14_COLLISION_ZONE in zones


# --- T20 legacy path ---


def test_t20_legacy_path_without_am2(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """T20: payload without am2 keeps DroppedRows behaviour (pr3a)."""
    sales = [_sale("Z1", 2023, "80", "2"), _sale("Z2", 2023, "80", "2")]
    b2 = _write_b2(tmp_path, sales)  # no am2 key
    drc = _write_drc(tmp_path, {"Z1": 40.0, "Z2": 20.0, "Z3": 10.0})
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    assert _run(b2, drc, primary, builder) == 1
    assert capsys.readouterr().out == "dropped_no_price=1 dropped_no_cost=0\n"
    assert not primary.exists()


# --- T22 am2 payload types ---


@pytest.mark.parametrize(
    "am2,message",
    [
        ([], "B4_PRIMARY_2023: ERROR: am2: expected object, got list"),
        (
            {
                "excluded": [{"zone": ZONE, "year": "2023", "reason": "suppressed_price", "count": 3}],
                "zones_present": [ZONE],
            },
            "B4_PRIMARY_2023: ERROR: year row am2: expected integer, got str",
        ),
        (
            {
                "excluded": [{"zone": ZONE, "year": 2023.0, "reason": "suppressed_price", "count": 3}],
                "zones_present": [ZONE],
            },
            "B4_PRIMARY_2023: ERROR: year row am2: expected integer, got float",
        ),
        (
            {
                "excluded": [{"zone": ZONE, "year": True, "reason": "suppressed_price", "count": 3}],
                "zones_present": [ZONE],
            },
            "B4_PRIMARY_2023: ERROR: year row am2: expected integer, got bool",
        ),
    ],
)
def test_t22_am2_payload_types(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    am2: object,
    message: str,
) -> None:
    """T22: am2 list / year str/float/bool refuse; type(v) is int; outputs absent."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(),
    )
    sales = [_sale(ZONE, 2023, "100", "6")]
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {ZONE: 40.0})
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    not_scored = tmp_path / "ns.json"
    assert _run(b2, drc, primary, builder, not_scored=not_scored) == 1
    assert capsys.readouterr().err == message + "\n"
    assert not primary.exists()
    assert not builder.exists()
    assert not not_scored.exists()


def test_t22_am2_year_int_accepted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """T22: year 2023 int accepted on excluded rows."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(),
    )
    sales = [_sale(ZONE, 2023, "100", "6")]
    am2 = _am2(
        excluded=[
            {
                "zone": "S01006507",
                "year": 2023,
                "reason": "suppressed_price",
                "count": 3,
            }
        ],
        zones_present=[ZONE, "S01006507"],
    )
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {ZONE: 40.0, "S01006507": 40.0})
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    assert _run(b2, drc, primary, builder) == 0
    assert primary.exists()


# --- T23 absent_from_file pinned ---


def test_t23a_absent_not_pinned_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T23(a): DRC zone absent and not in pinned 6 refuses."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(PINNED),
    )
    sales = [_sale(ZONE, 2023, "100", "6")]
    am2 = _am2(zones_present=[ZONE])
    unknown = "S01009999"
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {ZONE: 40.0, unknown: 40.0})
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    assert _run(b2, drc, primary, builder) == 1
    assert capsys.readouterr().err == (
        "B4_PRIMARY_2023: REFUSED: absent_from_file: expected one of "
        "S01007788, S01010206, S01010226, S01010462, S01010493, S01011598, "
        f"got {unknown}\n"
    )
    assert not primary.exists()


def test_t23b_pinned_present_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T23(b): pinned zone present in house_sales refuses."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(PINNED),
    )
    pinned = "S01007788"
    sales = [_sale(ZONE, 2023, "100", "6"), _sale(pinned, 2021, "90", "6")]
    am2 = _am2(zones_present=[ZONE, pinned])
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {ZONE: 40.0, pinned: 40.0})
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    assert _run(b2, drc, primary, builder) == 1
    assert capsys.readouterr().err == (
        f"B4_PRIMARY_2023: REFUSED: absent_from_file {pinned}: "
        "expected absent from house_sales, got present\n"
    )
    assert not primary.exists()


def test_t23c_pinned_six_absent_classified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """T23(c): pinned 6 absent classify as absent_from_file."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(PINNED),
    )
    sales = [_sale(ZONE, 2023, "100", "6")]
    am2 = _am2(zones_present=[ZONE])
    drc_map = {ZONE: 40.0}
    for code in PINNED:
        drc_map[code] = 40.0
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, drc_map)
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    not_scored = tmp_path / "ns.json"
    assert _run(b2, drc, primary, builder, not_scored=not_scored) == 0
    payload = json.loads(not_scored.read_text(encoding="utf-8"))
    assert payload["counts"]["absent_from_file"] == 6
    reasons = {row["zone"]: row["reason"] for row in payload["not_scored"]}
    for code in PINNED:
        assert reasons[code] == "absent_from_file"


# --- T25 SENTINEL via primary.main ---


def test_t25_sentinel_via_primary_main(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """T25 via build_v14_primary_2023.main: SENTINEL_7Q absent from streams on refusal."""
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(),
    )
    sales = [_sale(ZONE, 2024, SENTINEL, "6")]
    am2 = _am2(zones_present=[ZONE])
    b2 = _write_b2(tmp_path, sales, am2=am2)
    drc = _write_drc(tmp_path, {ZONE: 40.0})
    primary = tmp_path / "p.json"
    builder = tmp_path / "b.json"
    assert _run(b2, drc, primary, builder) == 1
    captured = capsys.readouterr()
    assert SENTINEL not in captured.out
    assert SENTINEL not in captured.err
    assert not primary.exists()
    assert not builder.exists()


def test_not_scored_reasons_constant() -> None:
    assert NOT_SCORED_REASONS == (
        "suppressed_price",
        "no_sales",
        "no_2023_row",
        "absent_from_file",
    )
    assert ABSENT_FROM_FILE_ZONES == frozenset(PINNED)


def test_classify_not_scored_no_2023_row(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.build_v14_primary_2023.ABSENT_FROM_FILE_ZONES",
        frozenset(),
    )
    am2 = {
        "excluded": [],
        "zones_present": ["Z1", "Z2"],
    }
    rows = classify_not_scored(am2, {"Z1", "Z2"}, {"Z1"})
    assert rows == [{"zone": "Z2", "reason": "no_2023_row"}]


def test_ci_ignores_real_test_glob() -> None:
    """TE X1: CI Full backend suite ignores *_real.py by path."""
    ci = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
    text = ci.read_text(encoding="utf-8")
    assert "--ignore-glob=*_real.py" in text or "--ignore-glob='*_real.py'" in text
