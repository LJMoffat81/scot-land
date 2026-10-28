"""CHECK4-ROUTE: Synthetic unit, refusal, estimator-dependence, and cancellation tests (Q1–Q15, Q_CANCEL, E1–E8)."""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

import georgist.v14_check4_route as c4r
from georgist import surface_v13 as v13
from georgist import surface_v14_checks as checks
from georgist.v14_check4_route import (
    ADDENDUM5_DEDUCTION_DISCLOSURE,
    BRMA_NAME_DISCLOSURE,
    BRMA_NAME_MAP,
    EXPECTED_HEADERS,
    Check4RouteError,
    assert_check4_yield,
    bridge_bedroom_shares_for_zone,
    capitalised_by_zone,
    check_cancellation_identity,
    copy_f8_pins,
    sha256_file,
)
from scripts.build_v14_check_inputs import (
    CheckInputError,
    build_v14_check_inputs,
    load_check4_f8,
    main as check_inputs_main,
)
from scripts.build_v14_check_sources import (
    CheckSourceError,
    build_check4_f8,
    main as check_sources_main,
    save_check4_f8,
)

SENTINEL = "SENTINEL_7Q"


def _write_csv(path: Path, header: tuple[str, ...] | list[str], rows: list[list[Any]]) -> Path:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    for r in rows:
        w.writerow(r)
    path.write_text(buf.getvalue(), encoding="utf-8")
    return path


def _default_rent_rows(
    brma: str = "Greater Glasgow",
    medians: tuple[str, str, str, str] = ("600", "800", "1000", "1400"),
    *,
    year: str = "2025",
    include_shared: bool = True,
    shared_val: str = "9999",
    include_scotland: bool = True,
    extra_rows: list[list[str]] | None = None,
) -> list[list[str]]:
    beds = ("1 Bedroom", "2 Bedroom", "3 Bedroom", "4 Bedroom")
    rows: list[list[str]] = []
    if include_scotland:
        for b in (*beds, "1 Bedroom shared"):
            rows.append(["Scotland", year, "Median", b, "-"])
    for b, m in zip(beds, medians):
        rows.append([brma, year, "Median", b, m])
        rows.append([brma, year, "Mean", b, "999.0"])
        rows.append([brma, year, "Lower Quartile", b, "499.0"])
        rows.append([brma, year, "Upper Quartile", b, "1099.0"])
    if include_shared:
        rows.append([brma, year, "Median", "1 Bedroom shared", shared_val])
    if extra_rows:
        rows.extend(extra_rows)
    return rows


def _bedroom_row(
    dz22: str = "S01013482",
    hh: str = "100",
    shares: tuple[str, str, str, str] = ("0.1", "0.4", "0.3", "0.2"),
) -> list[str]:
    s1, s2, s3, s4 = shares
    return [
        dz22,
        hh,
        s1,
        s2,
        s3,
        s4,
        "0.5",
        "0.5",
        s1,
        s2,
        s3,
        s4,
        s1,
        s2,
        s3,
        s4,
        "50",
        "50",
        "SYNTHETIC",
        "OGL-3.0",
    ]


def _make_f8_fixture(
    tmp_path: Path,
    *,
    rent_rows: list[list[str]] | None = None,
    share_rows: list[list[str]] | None = None,
    bedroom_rows: list[list[str]] | None = None,
    cw_rows: list[list[str]] | None = None,
    ur6_rows: list[list[str]] | None = None,
) -> tuple[dict[str, Path], dict[str, str]]:
    p_rents = _write_csv(
        tmp_path / "brma_rents.csv",
        EXPECTED_HEADERS["brma_rents"],
        rent_rows if rent_rows is not None else _default_rent_rows(),
    )
    p_share = _write_csv(
        tmp_path / "brma_share.csv",
        EXPECTED_HEADERS["brma_share"],
        share_rows
        if share_rows is not None
        else [["S01006506", "2011", "S33000007", "Greater Glasgow", "1", "100", "synth"]],
    )
    p_bed = _write_csv(
        tmp_path / "bedroom_bands.csv",
        EXPECTED_HEADERS["bedroom_bands"],
        bedroom_rows if bedroom_rows is not None else [_bedroom_row()],
    )
    p_cw = _write_csv(
        tmp_path / "crosswalk.csv",
        EXPECTED_HEADERS["crosswalk"],
        cw_rows
        if cw_rows is not None
        else [["S01006506", "S01013482", "100", "1.0", "1.0", "False", "uprn"]],
    )
    p_ur6 = _write_csv(
        tmp_path / "ur6.csv",
        EXPECTED_HEADERS["ur6"],
        ur6_rows
        if ur6_rows is not None
        else [["S01006506", "2", "Other Urban", "2", "SG", "OGL"]],
    )
    paths = {
        "brma_rents": p_rents,
        "brma_share": p_share,
        "bedroom_bands": p_bed,
        "crosswalk": p_cw,
        "ur6": p_ur6,
    }
    pins = {k: sha256_file(p) for k, p in paths.items()}
    return paths, pins


def test_q1_q2_f8_arithmetic_and_drc_deduction(tmp_path: Path) -> None:
    """Q1 & Q2: 12x monthly factor, F8 weighted rent / 0.045, and Addendum 5 DRC deduction."""
    paths, pins = _make_f8_fixture(tmp_path)
    # shares = (0.1, 0.4, 0.3, 0.2), Medians = (600, 800, 1000, 1400) -> expected_rent = 960.0
    exp_rent_dec = (
        Decimal("0.1") * Decimal("600")
        + Decimal("0.4") * Decimal("800")
        + Decimal("0.3") * Decimal("1000")
        + Decimal("0.2") * Decimal("1400")
    )
    assert exp_rent_dec == Decimal("960.0")
    cap_prop_dec = (Decimal("12") * exp_rent_dec) / Decimal("0.045")
    drc_dec = Decimal("100000.0")
    cap_land_dec = cap_prop_dec - drc_dec

    res = capitalised_by_zone(
        ["S01006506"],
        brma_rents_path=paths["brma_rents"],
        brma_share_path=paths["brma_share"],
        bedroom_bands_path=paths["bedroom_bands"],
        crosswalk_path=paths["crosswalk"],
        ur6_path=paths["ur6"],
        drc_map={"S01006506": float(drc_dec)},
        pins=pins,
    )
    z = res["zones"]["S01006506"]
    assert abs(z["capitalised_property"] - float(cap_prop_dec)) / float(cap_prop_dec) <= 1e-9
    assert abs(z["capitalised_land"] - float(cap_land_dec)) / float(cap_land_dec) <= 1e-9
    # Q2: factor is 12x, not 1x or 52x
    assert abs(z["capitalised_property"] - 256000.0) <= 1e-6
    assert abs(z["capitalised_land"] - 156000.0) <= 1e-6


def test_q_cancel_building_cost_cancellation_identity() -> None:
    """AM-2 Addendum 5 §4: for residual estimator (P - DRC), DRC cancels in (residual_land - capitalised_land) to <= 1e-12."""
    for price, rent, drc in [
        (280000.0, 960.0, 165000.0),
        (140000.0, 720.0, 195000.0),
        (520000.0, 1850.0, 310000.0),
        (95000.0, 510.0, 0.0),
    ]:
        out = check_cancellation_identity(price, rent, drc, yield_rate=0.045)
        assert out["rel_err"] <= 1e-12
        assert abs(out["lhs"] - out["rhs"]) <= 1e-12 * max(1.0, abs(price))

    for bad in [True, False, None, "100", float("nan"), float("inf")]:
        with pytest.raises(Check4RouteError) as exc:
            check_cancellation_identity(bad, 960.0, 100000.0)  # type: ignore[arg-type]
        assert type(exc.value) is Check4RouteError


def test_q3_q4_q5_q6s_measure_year_shared_scotland(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Q3 (Median only), Q4 (Year 2025 only; 2024 Value never read), Q5 (shared excluded), Q6s (Scotland skipped)."""
    read_calls: list[str] = []
    real_hook = c4r.read_rent_value_cell

    def spy_hook(val: str) -> str:
        read_calls.append(val)
        return real_hook(val)

    monkeypatch.setattr(c4r, "read_rent_value_cell", spy_hook)

    extra = [
        # 2024 rows with SENTINEL and non-numeric 'abc' must be skipped before Measure/Value are read
        ["Greater Glasgow", "2024", "Median", "1 Bedroom", SENTINEL],
        ["Greater Glasgow", "2024", "Median", "2 Bedroom", "abc"],
        # Scotland row with numeric value must still never be used
        ["Scotland", "2025", "Median", "1 Bedroom", "99999"],
    ]
    paths, pins = _make_f8_fixture(
        tmp_path,
        rent_rows=_default_rent_rows(
            medians=("600", "800", "1000", "1400"),
            include_shared=True,
            shared_val="88888",
            include_scotland=False,
            extra_rows=extra,
        ),
    )
    res1 = capitalised_by_zone(
        ["S01006506"],
        brma_rents_path=paths["brma_rents"],
        brma_share_path=paths["brma_share"],
        bedroom_bands_path=paths["bedroom_bands"],
        crosswalk_path=paths["crosswalk"],
        ur6_path=paths["ur6"],
        pins=pins,
    )
    assert SENTINEL not in read_calls
    assert "abc" not in read_calls
    assert "88888" not in read_calls
    assert res1["zones"]["S01006506"]["capitalised_property"] == pytest.approx(256000.0)


def test_q6_plus4_uplift_classes_5_and_6_only(tmp_path: Path) -> None:
    """Q6: x1.15 on 4 Bedroom in UR6 classes 5 and 6 only; unadjusted always no-uplift."""
    for ur6_cls, expect_uplift in [(4, False), (5, True), (6, True)]:
        sub = tmp_path / f"u{ur6_cls}"
        sub.mkdir()
        paths, pins = _make_f8_fixture(
            sub,
            ur6_rows=[["S01006506", str(ur6_cls), "Class", str(ur6_cls), "SG", "OGL"]],
        )
        res = capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            drc_map={"S01006506": 50000.0},
            pins=pins,
        )
        z = res["zones"]["S01006506"]
        assert z["plus4_applied"] is expect_uplift
        assert z["capitalised_property_unadjusted"] == pytest.approx(256000.0)
        assert z["capitalised_land_unadjusted"] == pytest.approx(206000.0)
        if expect_uplift:
            # 0.2 * 1400 * 0.15 = 42 monthly uplift -> 42 * 12 / 0.045 = 11200
            assert z["capitalised_property"] == pytest.approx(267200.0)
            assert z["capitalised_land"] == pytest.approx(217200.0)
        else:
            assert z["capitalised_property"] == pytest.approx(256000.0)
            assert z["capitalised_land"] == pytest.approx(206000.0)


def test_q7_q8_q13_split_brma_and_bedroom_bridge(tmp_path: Path) -> None:
    """Q7 (0.6/0.4 split BRMA) and Q8/Q13 (household-weighted DZ2022->DZ2011 bedroom bridge)."""
    rent_rows = _default_rent_rows("BRMA_A", ("500", "700", "900", "1100")) + _default_rent_rows(
        "BRMA_B", ("700", "900", "1100", "1300"), include_scotland=False
    )
    share_rows = [
        ["S01006506", "2011", "S33000001", "BRMA_A", "0.6", "60", "synth"],
        ["S01006506", "2011", "S33000002", "BRMA_B", "0.4", "40", "synth"],
    ]
    bed_rows = [
        _bedroom_row("S01013482", "100", ("0.2", "0.3", "0.3", "0.2")),
        _bedroom_row("S01013483", "300", ("0.1", "0.5", "0.2", "0.2")),
    ]
    cw_rows = [
        ["S01006506", "S01013482", "50", "0.5", "0.25", "False", "uprn"],
        ["S01006506", "S01013483", "50", "0.5", "0.75", "False", "uprn"],
    ]
    paths, pins = _make_f8_fixture(
        tmp_path,
        rent_rows=rent_rows,
        share_rows=share_rows,
        bedroom_rows=bed_rows,
        cw_rows=cw_rows,
    )
    res = capitalised_by_zone(
        ["S01006506"],
        brma_rents_path=paths["brma_rents"],
        brma_share_path=paths["brma_share"],
        bedroom_bands_path=paths["bedroom_bands"],
        crosswalk_path=paths["crosswalk"],
        ur6_path=paths["ur6"],
        pins=pins,
    )
    z = res["zones"]["S01006506"]
    # wh1 = 0.5*100 = 50, wh2 = 0.5*300 = 150, denom = 200
    # s1 = (50*0.2 + 150*0.1)/200 = 0.125; s2 = (50*0.3 + 150*0.5)/200 = 0.45; s3 = (50*0.3 + 150*0.2)/200 = 0.225; s4 = 0.2
    assert abs(z["bedroom_shares"]["1"] - 0.125) <= 1e-12
    assert abs(z["bedroom_shares"]["2"] - 0.45) <= 1e-12
    assert abs(z["bedroom_shares"]["3"] - 0.225) <= 1e-12
    assert abs(z["bedroom_shares"]["4+"] - 0.2) <= 1e-12


def test_q9_q9r_brma_name_map_and_refusals(tmp_path: Path) -> None:
    """Q9 & Q9r: exact 'Ayrshire' -> 'Ayrshires' maps; any other unmapped name refuses with code only."""
    assert BRMA_NAME_MAP == {"Ayrshire": "Ayrshires"}
    paths, pins = _make_f8_fixture(
        tmp_path,
        rent_rows=_default_rent_rows("Ayrshires", ("500", "650", "800", "1100")),
        share_rows=[["S01006506", "2011", "S33000003", "Ayrshire", "1", "100", "synth"]],
    )
    res = capitalised_by_zone(
        ["S01006506"],
        brma_rents_path=paths["brma_rents"],
        brma_share_path=paths["brma_share"],
        bedroom_bands_path=paths["bedroom_bands"],
        crosswalk_path=paths["crosswalk"],
        ur6_path=paths["ur6"],
        pins=pins,
    )
    assert res["disclosure"]["brma_name_map"] == BRMA_NAME_DISCLOSURE
    assert res["disclosure"]["addendum5_deduction"] == ADDENDUM5_DEDUCTION_DISCLOSURE

    for bad_name in ["Ayrshirez", "ayrshire", "Ayrshire ", "Glasgow", SENTINEL]:
        sub = tmp_path / f"bad_{hash(bad_name)}"
        sub.mkdir(exist_ok=True)
        bpaths, bpins = _make_f8_fixture(
            sub,
            rent_rows=_default_rent_rows("Ayrshires", ("500", "650", "800", "1100")),
            share_rows=[["S01006506", "2011", "S33000003", bad_name, "1", "100", "synth"]],
        )
        with pytest.raises(Check4RouteError) as exc:
            capitalised_by_zone(
                ["S01006506"],
                brma_rents_path=bpaths["brma_rents"],
                brma_share_path=bpaths["brma_share"],
                bedroom_bands_path=bpaths["bedroom_bands"],
                crosswalk_path=bpaths["crosswalk"],
                ur6_path=bpaths["ur6"],
                pins=bpins,
            )
        assert type(exc.value) is Check4RouteError
        assert str(exc.value) == "V14_CHECK4: ERROR: brma S33000003: expected rent BRMA, got absent"
        assert SENTINEL not in str(exc.value)


@pytest.mark.parametrize("source", ["brma_rents", "brma_share", "bedroom_bands", "crosswalk", "ur6"])
def test_q10_file_missing_sha_empty_header_refusals(tmp_path: Path, source: str) -> None:
    """Q10: missing file, bad sha, empty file, and bad header for each of the 5 F8 sources."""
    paths, pins = _make_f8_fixture(tmp_path)
    joined = ",".join(EXPECTED_HEADERS[source])

    # 1. Missing file
    missing_paths = dict(paths)
    missing_paths[source] = tmp_path / f"absent_{source}.csv"
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=missing_paths["brma_rents"],
            brma_share_path=missing_paths["brma_share"],
            bedroom_bands_path=missing_paths["bedroom_bands"],
            crosswalk_path=missing_paths["crosswalk"],
            ur6_path=missing_paths["ur6"],
            pins=pins,
        )
    assert type(exc.value) is Check4RouteError
    assert str(exc.value) == f"V14_CHECK4: ERROR: {source} file: expected {missing_paths[source]}, got absent"

    # 2. Bad sha
    bad_pins = dict(pins)
    bad_pins[source] = "0" * 64
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            pins=bad_pins,
        )
    assert type(exc.value) is Check4RouteError
    assert str(exc.value) == f"V14_CHECK4: REFUSED: {source} sha256: expected {'0'*64}, got {pins[source]}"

    # 3. Empty file
    paths[source].write_text("", encoding="utf-8")
    pins[source] = sha256_file(paths[source])
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            pins=pins,
        )
    assert type(exc.value) is Check4RouteError
    assert str(exc.value) == f"V14_CHECK4: ERROR: {source} header: expected {joined}, got absent"

    # 4. Wrong header
    paths[source].write_text(f"wrong,{SENTINEL}\n1,2\n", encoding="utf-8")
    pins[source] = sha256_file(paths[source])
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            pins=pins,
        )
    assert type(exc.value) is Check4RouteError
    assert str(exc.value) == f"V14_CHECK4: ERROR: {source} header: expected {joined}, got other header"
    assert SENTINEL not in str(exc.value)


@pytest.mark.parametrize(
    ("bad_val", "expected_suffix"),
    [
        (SENTINEL, "got non-numeric"),
        ("True", "got non-numeric"),
        ("nan", "got non-finite"),
        ("inf", "got non-finite"),
        ("-inf", "got non-finite"),
        ("0", "got out of range"),
        ("-0.0", "got out of range"),
        ("-10", "got out of range"),
    ],
)
def test_q10_q11_rent_value_refusals_and_sentinel(
    tmp_path: Path, bad_val: str, expected_suffix: str
) -> None:
    """Q10 & Q11a: invalid rent Value cells refuse with exact message and never leak SENTINEL."""
    paths, pins = _make_f8_fixture(
        tmp_path,
        rent_rows=_default_rent_rows(medians=(bad_val, "800", "1000", "1400")),
    )
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            pins=pins,
        )
    assert type(exc.value) is Check4RouteError
    assert str(exc.value) == (
        f"V14_CHECK4: ERROR: brma_rents Greater Glasgow 1 Bedroom: expected positive number, {expected_suffix}"
    )
    assert SENTINEL not in str(exc.value)


def test_q10_year_median_sum_hh0_zone_yield_refusals(tmp_path: Path) -> None:
    """Q10 & Q15: non-integer Year, missing/duplicate Median, share sums, hh=0, absent zone, and yaml yield mismatch."""
    # 1. Non-integer Year
    for bad_yr in ["2025.0", " 2025", "abc", SENTINEL]:
        sub = tmp_path / f"yr_{hash(bad_yr)}"
        sub.mkdir(exist_ok=True)
        paths, pins = _make_f8_fixture(
            sub,
            rent_rows=[["Greater Glasgow", bad_yr, "Median", "1 Bedroom", "600"]],
        )
        with pytest.raises(Check4RouteError) as exc:
            capitalised_by_zone(
                ["S01006506"],
                brma_rents_path=paths["brma_rents"],
                brma_share_path=paths["brma_share"],
                bedroom_bands_path=paths["bedroom_bands"],
                crosswalk_path=paths["crosswalk"],
                ur6_path=paths["ur6"],
                pins=pins,
            )
        assert str(exc.value) == "V14_CHECK4: ERROR: brma_rents Year row 1: expected integer, got non-integer"
        assert SENTINEL not in str(exc.value)

    # 2. Duplicate 2025 Median
    sub_dup = tmp_path / "dup_med"
    sub_dup.mkdir()
    paths, pins = _make_f8_fixture(
        sub_dup,
        rent_rows=_default_rent_rows(
            extra_rows=[["Greater Glasgow", "2025", "Median", "1 Bedroom", "650"]]
        ),
    )
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            pins=pins,
        )
    assert str(exc.value) == "V14_CHECK4: ERROR: brma_rents Greater Glasgow 1 Bedroom: expected one 2025 Median, got duplicate"

    # 3. Missing 2025 Median for 4 Bedroom
    sub_abs = tmp_path / "abs_med"
    sub_abs.mkdir()
    rows_abs = [r for r in _default_rent_rows() if not (r[0] == "Greater Glasgow" and r[2] == "Median" and r[3] == "4 Bedroom")]
    paths, pins = _make_f8_fixture(sub_abs, rent_rows=rows_abs)
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            pins=pins,
        )
    assert str(exc.value) == "V14_CHECK4: ERROR: brma_rents Greater Glasgow 4 Bedroom: expected one 2025 Median, got absent"

    # 4. Share sum off by 2e-5 refuses; 1+1e-5 passes
    sub_sum_ok = tmp_path / "sum_ok"
    sub_sum_ok.mkdir()
    paths, pins = _make_f8_fixture(
        sub_sum_ok,
        share_rows=[["S01006506", "2011", "S33000007", "Greater Glasgow", "1.000009", "100", "synth"]],
    )
    capitalised_by_zone(
        ["S01006506"],
        brma_rents_path=paths["brma_rents"],
        brma_share_path=paths["brma_share"],
        bedroom_bands_path=paths["bedroom_bands"],
        crosswalk_path=paths["crosswalk"],
        ur6_path=paths["ur6"],
        pins=pins,
    )

    sub_sum_bad = tmp_path / "sum_bad"
    sub_sum_bad.mkdir()
    paths, pins = _make_f8_fixture(
        sub_sum_bad,
        share_rows=[["S01006506", "2011", "S33000007", "Greater Glasgow", "1.00002", "100", "synth"]],
    )
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            pins=pins,
        )
    assert str(exc.value) == "V14_CHECK4: ERROR: brma_share S01006506: expected shares summing to 1, got out of range"

    # 5. All households 0 for a DZ2011
    sub_hh0 = tmp_path / "hh0"
    sub_hh0.mkdir()
    paths, pins = _make_f8_fixture(
        sub_hh0,
        bedroom_rows=[_bedroom_row("S01013482", "0", ("0", "0", "0", "0"))],
    )
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=paths["brma_rents"],
            brma_share_path=paths["brma_share"],
            bedroom_bands_path=paths["bedroom_bands"],
            crosswalk_path=paths["crosswalk"],
            ur6_path=paths["ur6"],
            pins=pins,
        )
    assert str(exc.value) == "V14_CHECK4: ERROR: bedroom_bands S01006506: expected positive households, got out of range"

    # 6. Yaml yield mismatch Checked BEFORE any file is opened (Rule 1)
    bad_yaml = tmp_path / "bad_surface.yaml"
    bad_yaml.write_text(
        "surface_rent:\n  v13:\n    check4:\n      capitalisation_yield: 0.045\n  v14:\n    check4:\n      capitalisation_yield: 0.05\n",
        encoding="utf-8",
    )
    with pytest.raises(Check4RouteError) as exc:
        capitalised_by_zone(
            ["S01006506"],
            brma_rents_path=tmp_path / "never_opened.csv",
            brma_share_path=tmp_path / "never_opened.csv",
            bedroom_bands_path=tmp_path / "never_opened.csv",
            crosswalk_path=tmp_path / "never_opened.csv",
            ur6_path=tmp_path / "never_opened.csv",
            surface_yaml=bad_yaml,
        )
    assert str(exc.value) == "V14_CHECK4: REFUSED: yield: expected 0.045 in v13.check4 and v14.check4, got mismatch"


def test_q14_static_ast_no_rent_table_or_central_low() -> None:
    """Q14: v14_check4_route never imports build_v14_check_sources or reads rent_table central/low."""
    src = Path(c4r.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "capitalised_by_zone":
            arg_names = [a.arg for a in node.args.args + node.args.kwonlyargs]
            assert "rent_table" not in arg_names
            assert "estimator" not in arg_names
    assert "build_v14_check_sources" not in src
    assert "two_route_lands" not in src


def test_e1_e2_e3_e4_e5_e6_e8_estimator_dependence_and_check_inputs(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """E1–E6, E8: primary vs secondary land_per_home, no_cell=0.0, unavailable=0.0, E5 old route refused, E6 refusals."""
    # E5: --year 2023 --rent-table without --no-price is refused
    rc_old = check_sources_main(
        ["--year", "2023", "--rent-table", str(tmp_path / "r.csv"), "--check4-out", str(tmp_path / "c4.json")]
    )
    assert rc_old == 1
    assert capsys.readouterr().err == (
        "B5_CHECK4: REFUSED: rent_table route: expected F8 route for 2023, got v13 pooled table\n"
    )

    # E1, E2, E3, E4: build_v14_check_inputs with check4_f8
    tables = {
        "builder_output": {
            "Z1": {"price": 200000.0, "count_in_1d": True, "unavailable": False, "model_failure": False, "hla": False},
            "Z2": {"price": 180000.0, "count_in_1d": True, "unavailable": False, "model_failure": False, "hla": False},
            "Z3": {"price": 150000.0, "count_in_1d": True, "unavailable": True, "model_failure": False, "hla": False},
        },
        "primary_estimates": {
            "Z1": {"share": 0.25, "land_per_home": 50000.0, "unavailable": False, "count_in_1d": True},
            "Z2": {"share": 0.20, "land_per_home": 36000.0, "unavailable": False, "count_in_1d": True},
            "Z3": {"share": 0.0, "land_per_home": -10000.0, "unavailable": True, "count_in_1d": True},
        },
        "fitted_hedonic": {
            "Z1": {"share": 0.40, "land_per_home": 80000.0, "unavailable": False, "model_failure": False, "count_in_1d": True},
            "Z2": {"no_cell": True, "count_in_1d": True},
            "Z3": {"share": 0.30, "land_per_home": 45000.0, "unavailable": False, "model_failure": False, "count_in_1d": True},
        },
        "check3_plot_passes": {
            "Z1": {"pass_at": {"20": True, "30": True, "40": True}},
            "Z2": {"pass_at": {"20": True, "30": True, "40": True}},
            "Z3": {"pass_at": {"20": True, "30": True, "40": True}},
        },
        "check4_f8": {
            "Z1": {"capitalised_land": 52000.0, "drc": 150000.0, "capitalised_property": 202000.0},
            "Z2": {"capitalised_land": 38000.0, "drc": 144000.0, "capitalised_property": 182000.0},
            "Z3": {"capitalised_land": 44000.0, "drc": 160000.0, "capitalised_property": 204000.0},
        },
        "dz2022_keys": {
            "Z1": {"dz2022": "D1", "share_low": 0.1, "share_central": 0.25, "share_high": 0.4},
            "Z2": {"dz2022": "D2", "share_low": 0.1, "share_central": 0.20, "share_high": 0.3},
            "Z3": {"dz2022": "D3", "share_low": 0.0, "share_central": 0.0, "share_high": 0.1},
        },
        "ur6": {
            "Z1": {"ur6": 1},
            "Z2": {"ur6": 1},
            "Z3": {"ur6": 2},
        },
    }
    built = build_v14_check_inputs(tables)
    prim = {r["zone"]: r for r in built["primary_zones"]}
    sec = {r["zone"]: r for r in built["secondary_zones"]}

    # E1: primary and secondary get their own land_per_home as residual_land
    assert prim["Z1"]["residual_land"] == 50000.0
    assert sec["Z1"]["residual_land"] == 80000.0
    assert prim["Z1"]["residual_land"] != sec["Z1"]["residual_land"]

    # E2: capitalised_land is identical for both estimators
    for zc in ("Z1", "Z2", "Z3"):
        assert prim[zc]["capitalised_land"] == sec[zc]["capitalised_land"]

    # E3: secondary no_cell zone gets residual_land == 0.0, while primary keeps 36000.0
    assert prim["Z2"]["residual_land"] == 36000.0
    assert sec["Z2"]["residual_land"] == 0.0

    # E4: primary unavailable zone Z3 gets residual_land == 0.0
    assert prim["Z3"]["residual_land"] == 0.0
    assert checks.check_4(built["primary_zones"]) != checks.check_4(built["secondary_zones"])

    # E6: check4_f8 refusals
    for bad_cap, expected_msg in [
        (True, "V14_CHECK_INPUTS: ERROR: check4_f8 Z1: expected positive number, got bool"),
        ("str", "V14_CHECK_INPUTS: ERROR: check4_f8 Z1: expected positive number, got str"),
        (float("nan"), "V14_CHECK_INPUTS: ERROR: check4_f8 Z1: expected positive number, got non-finite"),
        (float("inf"), "V14_CHECK_INPUTS: ERROR: check4_f8 Z1: expected positive number, got non-finite"),
        (0.0, "V14_CHECK_INPUTS: ERROR: check4_f8 Z1: expected positive number, got out of range"),
        (-5.0, "V14_CHECK_INPUTS: ERROR: check4_f8 Z1: expected positive number, got out of range"),
    ]:
        bad_tables = json.loads(json.dumps(tables, default=str))
        bad_tables["check4_f8"]["Z1"] = {"capitalised_land": bad_cap}
        with pytest.raises(CheckInputError) as exc:
            build_v14_check_inputs(bad_tables)
        assert type(exc.value) is CheckInputError
        assert str(exc.value) == expected_msg
