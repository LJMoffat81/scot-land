"""V14-SPEC-A1 AC-1 and b2 stderr wrap. SYNTHETIC fixtures; no 2024 price cell."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from georgist.v14_b2 import PIN_TABLE as B2_PINS
from georgist.v14_d7_chain import (
    D7_FILTER2_OUTPUT_SHA256,
    D7_ROW_COUNT,
    D7ChainResult,
    run_d7_chain,
)
from scripts.build_v14_b2 import main

SENTINEL = "SENTINEL_PRICE_7Q"
WITHHELD = {
    "ValueError": (
        "B2: ERROR: build: expected B2Error, got ValueError (message withheld)\n"
    ),
    "KeyError": (
        "B2: ERROR: build: expected B2Error, got KeyError (message withheld)\n"
    ),
    "OSError": (
        "B2: ERROR: build: expected B2Error, got OSError (message withheld)\n"
    ),
}
FILTER2_CANDIDATES = (
    Path("/workspace/scotland-rules/v13_sold_vs_stock/sold_vs_stock_dz11_zone_year_2019_2023.csv"),
    Path.home() / "scotland-rules/v13_sold_vs_stock/sold_vs_stock_dz11_zone_year_2019_2023.csv",
)


def _filter2_path() -> Path | None:
    for path in FILTER2_CANDIDATES:
        if path.is_file():
            return path
    return None


def test_d1_row_count_constant() -> None:
    """AC-1: D7_ROW_COUNT is 34659; real filter2 matches when present."""
    assert D7_ROW_COUNT == 34659
    path = _filter2_path()
    if path is None:
        pytest.skip("filter2 output absent")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == D7_FILTER2_OUTPUT_SHA256
    text = path.read_text(encoding="utf-8")
    data_rows = [line for line in text.splitlines() if line.strip()][1:]
    assert len(data_rows) == D7_ROW_COUNT


def test_d2_run_d7_chain_when_filter2_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Real filter2 through run_d7_chain(..., run_fit=False) passes when files exist."""
    filter2 = _filter2_path()
    if filter2 is None:
        pytest.skip("filter2 output absent")
    # Upstream pins must also be present; otherwise skip.
    source = filter2.parent / "sold_vs_stock_dz11_zone_year.csv"
    out1 = filter2.parent / "sold_vs_stock_dz11_zone_year_no2024.csv"
    script1 = Path("/workspace/backend/georgist/d7_filters/filter1_drop_year_2024.py")
    script2 = Path("/workspace/backend/georgist/d7_filters/filter2_keep_2019_2023.py")
    if not all(p.is_file() for p in (source, out1, script1, script2)):
        pytest.skip("full D7 chain inputs absent")
    result = run_d7_chain(
        source=source,
        filter1_script=script1,
        filter1_output=out1,
        filter2_script=script2,
        filter2_output=filter2,
        run_fit=False,
    )
    assert result.passed is True


def _main_argv(out: Path) -> list[str]:
    return [
        "--out",
        str(out),
        "--house-sales",
        "x",
        "--plot-split",
        "x",
        "--crosswalk",
        "x",
        "--sold-tfa",
        "x",
        "--access",
        "x",
        "--bedrooms",
        "x",
        "--filter1-script",
        "x",
        "--filter1-output",
        "x",
        "--filter2-script",
        "x",
        "--filter2-output",
        "x",
    ]


@pytest.mark.parametrize(
    ("exc_type", "message"),
    [
        (ValueError, f"could not convert string to float: '{SENTINEL}'"),
        (KeyError, SENTINEL),
        (OSError, SENTINEL),
    ],
)
def test_s1_sentinel_withheld(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    exc_type: type[BaseException],
    message: str,
) -> None:
    """Non-B2Error from build: type name only; sentinel never reaches stderr/stdout."""

    def boom(*_args, **_kwargs):
        raise exc_type(message)

    monkeypatch.setattr("scripts.build_v14_b2.build", boom)
    out = tmp_path / "out.json"
    rc = main(_main_argv(out))
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == WITHHELD[exc_type.__name__]
    assert SENTINEL not in captured.out
    assert SENTINEL not in captured.err
    assert not out.exists()


def test_s2_synthetic_end_to_end_withheld(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """SYNTHETIC Mean Value cell through real build/fit_headline; message withheld."""
    sales = tmp_path / "house_sales.csv"
    header = (
        "GeographyCode,GeographyName,GeographyType,DateCode,Measurement,Units,"
        "Value,Sales,cell,a_m2,ratio_mean,iz,ca,ur3,flat_share"
    )
    # Mean carries the sentinel; other measures are numeric so only Mean triggers float().
    # A2a complete set: Count + Mean + Median + LQ + UQ (fixture data only; assertions unchanged).
    rows = [
        "Z1,SYNTHETIC zone,2011 Data Zones,2021,Count,Number of sales,6,Number of sales,c,40,1.0,IZ1,CA1,urban,0.2",
        f"Z1,SYNTHETIC zone,2011 Data Zones,2021,Mean,GBP,{SENTINEL},6,c,40,1.0,IZ1,CA1,urban,0.2",
        "Z1,SYNTHETIC zone,2011 Data Zones,2021,Median,GBP,9,6,c,40,1.0,IZ1,CA1,urban,0.2",
        "Z1,SYNTHETIC zone,2011 Data Zones,2021,Lower Quartile,GBP,8,6,c,40,1.0,IZ1,CA1,urban,0.2",
        "Z1,SYNTHETIC zone,2011 Data Zones,2021,Upper Quartile,GBP,12,6,c,40,1.0,IZ1,CA1,urban,0.2",
    ]
    sales.write_text("# SYNTHETIC\n" + header + "\n" + "\n".join(rows) + "\n", encoding="utf-8")
    out = tmp_path / "out.json"

    monkeypatch.setattr("scripts.build_v14_b2.assert_house_sales_pin", lambda _p: None)
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_plot_split",
        lambda *_a, **_k: [{"code": "Z1", "low_parcel_coverage": 0, "method_flags": "x"}],
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_crosswalk",
        lambda *_a, **_k: [{"dz2011": "D1", "dz2022": "Z1", "uprn_count": "1"}],
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_access",
        lambda *_a, **_k: [{"zone": "Z1", "job_access": "1.5", "vintage": "2011"}],
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_bedrooms",
        lambda *_a, **_k: {"rows": []},
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.run_d7_chain",
        lambda **_k: D7ChainResult(
            status="passed",
            d7_sha256="a" * 64,
            message="",
            manifest={},
        ),
    )
    monkeypatch.setattr(
        "scripts.build_v14_b2.adapt_sold_tfa",
        lambda *_a, **_k: [{"zone": "Z1", "year": 2021, "sold_tfa_mean": "50"}],
    )

    def fit_from_adapted(rows, d7_sha256=None):
        # Prove adapt_house_sales handed the Mean Value through, then refuse like float().
        assert any(str(row.get("price")) == SENTINEL for row in rows)
        float(SENTINEL)

    monkeypatch.setattr("scripts.build_v14_b2.fit_headline", fit_from_adapted)

    argv = _main_argv(out)
    # Point --house-sales at the synthetic file.
    argv[argv.index("--house-sales") + 1] = str(sales)
    rc = main(argv)
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.out == ""
    assert captured.err == WITHHELD["ValueError"]
    assert SENTINEL not in captured.out
    assert SENTINEL not in captured.err
    assert not out.exists()


def test_s3_b2error_path_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Missing house_sales still prints the existing B2_HOUSE_SALES sha256 absent message."""
    out = tmp_path / "out.json"
    missing = tmp_path / "absent_house_sales.csv"
    expected = str(B2_PINS["house_sales"])
    argv = _main_argv(out)
    argv[argv.index("--house-sales") + 1] = str(missing)
    rc = main(argv)
    captured = capsys.readouterr()
    assert rc == 1
    assert captured.err == (
        f"B2_HOUSE_SALES: ERROR: sha256: expected {expected}, got absent\n"
    )
    assert captured.out == ""
    assert not out.exists()
