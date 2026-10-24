"""SRC-C CREDIT-1 / PII-1 — credit checker negatives (N1–N13) and crofting N17."""

from __future__ import annotations

import io
import os
import re
from contextlib import redirect_stderr
from pathlib import Path

import pytest

from layers.credit_check import (
    REPO_ROOT,
    CreditError,
    check,
    load_requirements,
    main,
)

REQUIREMENTS = REPO_ROOT / "data" / "config" / "credit_requirements.yaml"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_real_requirements_pass():
    reqs = load_requirements(REQUIREMENTS)
    assert len(reqs) == 10
    check(reqs, REPO_ROOT)


def test_n1_requirements_file_not_found(tmp_path):
    missing = tmp_path / "nope.yaml"
    with pytest.raises(CreditError, match=r"^CREDIT: requirements file not found: .+$"):
        load_requirements(missing)


def test_n2_requirements_empty(tmp_path):
    path = _write(tmp_path / "empty.yaml", "")
    with pytest.raises(CreditError, match=r"^CREDIT: requirements empty: .+$"):
        load_requirements(path)


def test_n3_requirements_invalid_yaml(tmp_path):
    path = _write(tmp_path / "bad.yaml", "a: [")
    with pytest.raises(
        CreditError, match=r"^CREDIT: requirements not valid YAML: .+$"
    ):
        load_requirements(path)


@pytest.mark.parametrize(
    "body,typename",
    [
        ("- a\n", "list"),
        ("hello\n", "str"),
        ("1\n", "int"),
        ("1.5\n", "float"),
        ("true\n", "bool"),
    ],
    ids=["list", "str", "int", "float", "bool"],
)
def test_n4_requirements_must_be_mapping(tmp_path, body, typename):
    path = _write(tmp_path / "top.yaml", body)
    with pytest.raises(
        CreditError,
        match=rf"^CREDIT: requirements must be a mapping, got {typename}$",
    ):
        load_requirements(path)


@pytest.mark.parametrize(
    "phrases",
    [True, 1.5, "x", [], [1]],
    ids=["bool", "float", "str", "empty", "int_item"],
)
def test_n5_phrases_must_be_nonempty_string_list(tmp_path, phrases):
    reqs = {"registry:dz2022": phrases}
    with pytest.raises(
        CreditError,
        match=(
            r"^CREDIT: registry:dz2022: "
            r"phrases must be a non-empty list of strings$"
        ),
    ):
        check(reqs, tmp_path)


def test_n6_unknown_locator_kind(tmp_path):
    reqs = {"foo:bar": ["x"]}
    with pytest.raises(
        CreditError, match=r"^CREDIT: foo:bar: unknown locator kind 'foo'$"
    ):
        check(reqs, tmp_path)


def test_n7_registry_missing_entry(tmp_path):
    reg = tmp_path / "backend" / "layers" / "registry"
    reg.mkdir(parents=True)
    reqs = {"registry:nope": ["Ordnance Survey"]}
    with pytest.raises(
        CreditError, match=r"^CREDIT: registry:nope: no such registry entry$"
    ):
        check(reqs, tmp_path)


def test_n8_sources_key_not_found(tmp_path):
    cfg = tmp_path / "data" / "config"
    cfg.mkdir(parents=True)
    _write(cfg / "sources.yaml", "community_ownership:\n  attribution: ok\n")
    reqs = {"sources:missing.key": ["Royal Mail"]}
    with pytest.raises(
        CreditError, match=r"^CREDIT: sources:missing\.key: key not found$"
    ):
        check(reqs, tmp_path)


@pytest.mark.parametrize(
    "value,typename",
    [
        ("true", "bool"),
        ("1.5", "float"),
        ("null", "NoneType"),
    ],
    ids=["bool", "float", "null"],
)
def test_n8bcd_sources_value_must_be_string(tmp_path, value, typename):
    cfg = tmp_path / "data" / "config"
    cfg.mkdir(parents=True)
    _write(cfg / "sources.yaml", f"x: {value}\n")
    reqs = {"sources:x": ["hi"]}
    with pytest.raises(
        CreditError,
        match=rf"^CREDIT: sources:x: value must be a string, got {typename}$",
    ):
        check(reqs, tmp_path)


def test_n9_ts_regex_file_not_found(tmp_path):
    reqs = {"ts_regex:nofile.ts::(x)": ["x"]}
    with pytest.raises(
        CreditError, match=r"^CREDIT: ts_regex:nofile\.ts: file not found$"
    ):
        check(reqs, tmp_path)


@pytest.mark.parametrize(
    "body,count",
    [
        ("nope\n", 0),
        ("x\nx\n", 2),
    ],
    ids=["zero", "two"],
)
def test_n10_ts_regex_expected_one_match(tmp_path, body, count):
    _write(tmp_path / "f.ts", body)
    reqs = {"ts_regex:f.ts::(x)": ["x"]}
    with pytest.raises(
        CreditError,
        match=rf"^CREDIT: ts_regex:f\.ts: expected 1 match, got {count}$",
    ):
        check(reqs, tmp_path)


def test_n11_ts_regex_invalid_regex(tmp_path):
    _write(tmp_path / "f.ts", "x\n")
    reqs = {"ts_regex:f.ts::(": ["x"]}
    with pytest.raises(
        CreditError, match=r"^CREDIT: ts_regex:f\.ts: invalid regex$"
    ):
        check(reqs, tmp_path)


def test_n11b_ts_regex_must_have_exactly_one_group(tmp_path):
    _write(tmp_path / "f.ts", "x\n")
    reqs = {"ts_regex:f.ts::x": ["x"]}
    with pytest.raises(
        CreditError,
        match=r"^CREDIT: ts_regex:f\.ts: regex must have exactly 1 group$",
    ):
        check(reqs, tmp_path)


def test_n12_missing_phrase(tmp_path):
    reg = tmp_path / "backend" / "layers" / "registry"
    reg.mkdir(parents=True)
    _write(
        reg / "x.yaml",
        "id: x\nattribution: Contains public sector information only.\n",
    )
    reqs = {"registry:x": ["Ordnance Survey"]}
    with pytest.raises(
        CreditError,
        match=r"^CREDIT: registry:x: missing phrase 'Ordnance Survey'$",
    ):
        check(reqs, tmp_path)


def test_n13_main_returns_codes(tmp_path):
    missing = tmp_path / "absent.yaml"
    err = io.StringIO()
    with redirect_stderr(err):
        code = main([str(missing)])
    assert code == 1
    assert re.fullmatch(
        r"CREDIT: requirements file not found: .+\n", err.getvalue()
    )

    good_err = io.StringIO()
    with redirect_stderr(good_err):
        good_code = main([str(REQUIREMENTS)])
    assert good_code == 0
    assert good_err.getvalue() == ""


def test_n17_croft_name_not_stored(tmp_path, monkeypatch):
    """C4: load_holdings writes NULL croft_name even when CroftName is present."""
    url = os.getenv("WEALTH_TEST_DATABASE_URL") or os.getenv("DATABASE_URL") or ""
    if not url:
        pytest.skip("WEALTH_TEST_DATABASE_URL / DATABASE_URL not set")

    monkeypatch.setenv("DATABASE_URL", url)

    from etl.ingest_crofting import ensure_tables, load_holdings
    from georgist import db

    csv_path = tmp_path / "holdings.csv"
    csv_path.write_text(
        "HoldingID,CroftName,StatusA,StatusB,StatusC,Croft_Let,"
        "MainLocationCode,CroftFileNumber,RegisterNumber,TotalArea,"
        "ParishID,Parish,Township,CroftingRegistrationNumber,"
        "Consent_to_Be_Absent_until\n"
        "1,SYNTH CROFT,Tenanted,,,,,,,,,,,,\n",
        encoding="utf-8",
    )

    conn = db.connect()
    try:
        ensure_tables(conn)
        n = load_holdings(conn, csv_path)
        conn.commit()
        assert n == 1
        with conn.cursor() as cur:
            cur.execute(
                "SELECT croft_name, status_a FROM croft_holdings WHERE holding_id = 1"
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] is None
        assert row[1] == "Tenanted"
    finally:
        conn.close()
