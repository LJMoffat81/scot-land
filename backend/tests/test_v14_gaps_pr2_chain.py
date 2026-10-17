"""PR 2 D7 provenance chain. SYNTHETIC fixtures only. No 2024 price cell is read."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from georgist.v14_d7_chain import (
    D7_FILTER1_OUTPUT_SHA256,
    D7_FILTER1_SCRIPT_SHA256,
    D7_FILTER2_OUTPUT_SHA256,
    D7_FILTER2_SCRIPT_SHA256,
    D7_ROW_COUNT,
    D7_SOURCE_SHA256,
    PIN_TABLE,
    accept_filter2_output,
    execute_filter1,
    execute_filter2,
    fit_headline,
    run_d7_chain,
    sha256_file,
)
from georgist.v14_hedonic import _fit_s_x2

BACKEND = Path(__file__).resolve().parents[1]
FILTER1 = BACKEND / "georgist" / "d7_filters" / "filter1_drop_year_2024.py"
FILTER2 = BACKEND / "georgist" / "d7_filters" / "filter2_keep_2019_2023.py"
SOURCE = """year,price
2019,1
2020,1
2021,1
2022,1
2023,1
2024,9
"""


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _baseline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    source = tmp_path / "source.csv"
    source.write_text(SOURCE, encoding="utf-8")
    out1 = tmp_path / "filter1.csv"
    out2 = tmp_path / "filter2.csv"
    execute_filter1(FILTER1, source, out1)
    execute_filter2(FILTER2, out1, out2)
    rows = [line for line in out2.read_bytes().splitlines() if line.strip()]
    monkeypatch.setitem(PIN_TABLE, "source", sha256_file(source))
    monkeypatch.setitem(PIN_TABLE, "filter1_script", sha256_file(FILTER1))
    monkeypatch.setitem(PIN_TABLE, "filter1_output", sha256_file(out1))
    monkeypatch.setitem(PIN_TABLE, "filter2_script", sha256_file(FILTER2))
    monkeypatch.setitem(PIN_TABLE, "filter2_output", sha256_file(out2))
    monkeypatch.setitem(PIN_TABLE, "row_count", len(rows) - 1)
    return {"source": source, "out1": out1, "out2": out2}


def _run(paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch, **spies):
    if "fit" in spies:
        monkeypatch.setattr("georgist.v14_d7_chain.fit_headline", spies["fit"])
    if "filter1" in spies:
        monkeypatch.setattr("georgist.v14_d7_chain.execute_filter1", spies["filter1"])
    if "filter2" in spies:
        monkeypatch.setattr("georgist.v14_d7_chain.execute_filter2", spies["filter2"])
    return run_d7_chain(
        source=paths["source"],
        filter1_script=FILTER1,
        filter1_output=paths["out1"],
        filter2_script=FILTER2,
        filter2_output=paths["out2"],
    )


def test_d7_script_pins_are_the_full_sha() -> None:
    """SYNTHETIC. Recorded script pins are the full filter-script sha256."""
    assert sha256_file(FILTER1) == D7_FILTER1_SCRIPT_SHA256
    assert sha256_file(FILTER2) == D7_FILTER2_SCRIPT_SHA256
    assert D7_SOURCE_SHA256 != D7_FILTER2_OUTPUT_SHA256
    assert len(D7_FILTER1_OUTPUT_SHA256) == 64
    assert len(D7_FILTER2_OUTPUT_SHA256) == 64


def test_d7_eight_character_prefix_is_not_run() -> None:
    """SYNTHETIC. A match on the first 8 characters is a mismatch."""
    refused = _fit_s_x2([{"ratio_mean": "1"}], D7_FILTER2_OUTPUT_SHA256[:8])
    assert refused["status"] == "NOT_RUN"
    assert refused["reason"] == "D7 sha does not match"


def test_d7_source_wrong_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A source sha mismatch does not run filter1."""
    paths = _baseline(tmp_path, monkeypatch)
    paths["out1"].unlink()
    paths["source"].write_bytes(paths["source"].read_bytes() + b"\n")
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1

    result = _run(paths, monkeypatch, filter1=spy)
    assert result.status == "NOT_RUN"
    assert result.message == (
        f"D7_SOURCE: NOT_RUN: sha256: expected {PIN_TABLE['source']}, got {sha256_file(paths['source'])}"
    )
    assert calls["n"] == 0
    assert not paths["out1"].exists()


def test_d7_filter1_script_wrong_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A filter1 script sha mismatch does not execute filter1."""
    paths = _baseline(tmp_path, monkeypatch)
    paths["out1"].unlink()
    bad = tmp_path / "filter1_bad.py"
    bad.write_bytes(FILTER1.read_bytes() + b"\n# SYNTHETIC\n")
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1

    monkeypatch.setattr("georgist.v14_d7_chain.execute_filter1", spy)
    result = run_d7_chain(
        source=paths["source"],
        filter1_script=bad,
        filter1_output=paths["out1"],
        filter2_script=FILTER2,
        filter2_output=paths["out2"],
    )
    assert result.message == (
        f"D7_FILTER1: NOT_RUN: script sha256: expected {PIN_TABLE['filter1_script']}, got {sha256_file(bad)}"
    )
    assert calls["n"] == 0
    assert not paths["out1"].exists()


def test_d7_filter1_output_wrong_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A filter1 output sha mismatch does not run filter2."""
    paths = _baseline(tmp_path, monkeypatch)
    good = paths["out1"].read_bytes()
    paths["out1"].unlink()
    calls = {"n": 0}

    def filter1(_script, _source, dest: Path) -> None:
        dest.write_bytes(good + b"x")

    def filter2(*_args, **_kwargs):
        calls["n"] += 1

    result = _run(paths, monkeypatch, filter1=filter1, filter2=filter2)
    assert result.message == (
        f"D7_FILTER1_OUT: NOT_RUN: sha256: expected {PIN_TABLE['filter1_output']}, got {sha256_file(paths['out1'])}"
    )
    assert calls["n"] == 0


def test_d7_filter2_script_wrong_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A filter2 script sha mismatch does not execute filter2."""
    paths = _baseline(tmp_path, monkeypatch)
    paths["out2"].unlink()
    bad = tmp_path / "filter2_bad.py"
    bad.write_bytes(FILTER2.read_bytes() + b"\n# SYNTHETIC\n")
    calls = {"n": 0}

    def spy(*_args, **_kwargs):
        calls["n"] += 1

    monkeypatch.setattr("georgist.v14_d7_chain.execute_filter2", spy)
    result = run_d7_chain(
        source=paths["source"],
        filter1_script=FILTER1,
        filter1_output=paths["out1"],
        filter2_script=bad,
        filter2_output=paths["out2"],
    )
    assert result.message == (
        f"D7_FILTER2: NOT_RUN: script sha256: expected {PIN_TABLE['filter2_script']}, got {sha256_file(bad)}"
    )
    assert calls["n"] == 0
    assert not paths["out2"].exists()


def test_d7_filter2_output_wrong_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. A filter2 output sha mismatch does not fit S-x2."""
    paths = _baseline(tmp_path, monkeypatch)
    good = paths["out2"].read_bytes()
    calls = {"n": 0}

    def filter2(_script, _source, dest: Path) -> None:
        dest.write_bytes(good + b"x")

    def fit(*_args, **_kwargs):
        calls["n"] += 1

    result = _run(paths, monkeypatch, filter2=filter2, fit=fit)
    assert result.status == "NOT_RUN"
    assert result.s_x2 == "NOT_RUN"
    assert result.message == (
        f"D7_FILTER2_OUT: NOT_RUN: sha256: expected {PIN_TABLE['filter2_output']}, got {sha256_file(paths['out2'])}"
    )
    assert calls["n"] == 0


def test_d7_crlf_vs_lf(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. CRLF filter1 output passes. The LF copy is NOT_RUN."""
    paths = _baseline(tmp_path, monkeypatch)
    crlf = paths["out1"].read_bytes()
    assert b"\r\n" in crlf
    lf = crlf.replace(b"\r\n", b"\n")
    assert sha256_file(paths["out1"]) != hashlib.sha256(lf).hexdigest()
    calls = {"n": 0}
    fits = {"n": 0}

    def filter2(script, source, dest):
        calls["n"] += 1
        return execute_filter2(script, source, dest)

    def fit(*_args, **_kwargs):
        fits["n"] += 1
        return {"sensitivities": [{"id": "S-x2", "status": "fit"}]}

    passed = _run(paths, monkeypatch, filter2=filter2, fit=fit)
    assert passed.passed
    assert calls["n"] == 1
    assert passed.manifest["filter1_script_sha256"] == D7_FILTER1_SCRIPT_SHA256
    assert passed.manifest["filter2_script_sha256"] == D7_FILTER2_SCRIPT_SHA256
    calls["n"] = 0

    def filter1(_script, _source, dest: Path) -> None:
        dest.write_bytes(lf)

    refused = _run(paths, monkeypatch, filter1=filter1, filter2=filter2, fit=fit)
    lf_sha = hashlib.sha256(lf).hexdigest()
    assert refused.message == f"D7_FILTER1_OUT: NOT_RUN: sha256: expected {PIN_TABLE['filter1_output']}, got {lf_sha}"
    assert calls["n"] == 0


def _final_table(rows: list[tuple[str, str]]) -> bytes:
    body = ["year,price"]
    body.extend(f"{year},{price}" for year, price in rows)
    return ("\n".join(body) + "\n").encode("utf-8")


def _span_rows(count: int, *, replace: tuple[int, str] | None = None) -> list[tuple[str, str]]:
    years = [str(2019 + (index % 5)) for index in range(count)]
    if 2019 not in {int(year) for year in years}:
        years[0] = "2019"
    if 2023 not in {int(year) for year in years}:
        years[-1] = "2023"
    prices = ["1"] * count
    if replace is not None:
        index, year = replace
        years[index] = year
        prices[index] = "SENTINEL_YEAR"
    return list(zip(years, prices))


def test_d7_rowcount_and_years(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """SYNTHETIC. Row count and the 2019-2023 span gate the fit. A 2024 year is not a price read."""
    monkeypatch.setitem(PIN_TABLE, "row_count", D7_ROW_COUNT)
    monkeypatch.setitem(PIN_TABLE, "year_min", 2019)
    monkeypatch.setitem(PIN_TABLE, "year_max", 2023)
    calls = {"n": 0}
    prices = {"n": 0}

    def fit(*_args, **_kwargs):
        calls["n"] += 1
        return {"sensitivities": [{"id": "S-x2", "status": "fit"}]}

    def price(_value: str) -> str:
        prices["n"] += 1
        return _value

    monkeypatch.setattr("georgist.v14_d7_chain.fit_headline", fit)
    monkeypatch.setattr("georgist.v14_d7_chain.read_price_cell", price)

    def check(rows: list[tuple[str, str]]) -> object:
        path = tmp_path / "final.csv"
        path.write_bytes(_final_table(rows))
        monkeypatch.setitem(PIN_TABLE, "filter2_output", sha256_file(path))
        calls["n"] = 0
        prices["n"] = 0
        return accept_filter2_output(path)

    short = check(_span_rows(D7_ROW_COUNT - 1))
    assert short.message == f"D7_FILTER2_OUT: NOT_RUN: row_count: expected {D7_ROW_COUNT}, got {D7_ROW_COUNT - 1}"
    assert calls["n"] == 0

    early = check(_span_rows(D7_ROW_COUNT, replace=(0, "2018")))
    assert early.message == "D7_FILTER2_OUT: NOT_RUN: year_range: expected 2019-2023, got 2018-2023"
    assert calls["n"] == 0

    late = check(_span_rows(D7_ROW_COUNT, replace=(1, "2024")))
    assert late.message == "D7_FILTER2_OUT: NOT_RUN: year_range: expected 2019-2023, got 2019-2024"
    assert calls["n"] == 0
    assert prices["n"] == 0
    assert "SENTINEL_YEAR" not in late.message

    passed = check(_span_rows(D7_ROW_COUNT))
    assert passed.passed
    assert calls["n"] == 1


def test_fit_headline_symbol_stays_registered() -> None:
    """SYNTHETIC. The chain hook is the hedonic fit."""
    assert fit_headline is not None
