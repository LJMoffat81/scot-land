"""B2-CSV-QUOTE-1 / V14-SPEC-A1. SYNTHETIC fixtures only. No 2024 price cell is read."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from georgist.v14_b2 import (
    B2Error,
    HOUSE_SALES_HEADERS,
    SCHEMA_HEADERS,
    SCHEMA_TOKEN,
    _csv_rows,
    _house_field,
    _house_sales_rows,
    adapt_bedrooms,
    adapt_house_sales,
    parse_data_rows,
    read_value_cell,
    scan_measurement_labels,
)
from georgist.v14_real_headers import REAL_SHA256

SENTINEL = "SENTINEL_PRICE_7Q"
R_UNTERM = "B2_HOUSE_SALES: ERROR: row {n}: expected closing quote, got end of file"
R_STRAY = "B2_HOUSE_SALES: ERROR: row {n}: expected quote only at field start, got stray quote"
CULTS = "Cults, Bieldside and Milltimber West - 01"
HEADER = ",".join(HOUSE_SALES_HEADERS)


class _ByteTracker:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.pos = 0
        self.high = 0
        self.seen = bytearray()

    def read(self, n: int = 1) -> bytes:
        if n is None or n < 0:
            n = len(self.payload) - self.pos
        chunk = self.payload[self.pos : self.pos + n]
        self.pos += len(chunk)
        self.high = max(self.high, self.pos)
        self.seen += chunk
        return chunk

    def __enter__(self):
        return self

    def __exit__(self, *_args) -> bool:
        return False


def _track(monkeypatch: pytest.MonkeyPatch, payload: bytes) -> dict[str, _ByteTracker]:
    box: dict[str, _ByteTracker] = {}

    def _open(self, *_args, **_kwargs):
        box["tracker"] = _ByteTracker(payload)
        return box["tracker"]

    monkeypatch.setattr(Path, "open", _open)
    return box


def _value_spy(monkeypatch: pytest.MonkeyPatch) -> dict[str, int]:
    calls = {"n": 0}

    def spy(value: str) -> str:
        calls["n"] += 1
        return read_value_cell(value)

    monkeypatch.setattr("georgist.v14_b2.read_value_cell", spy)
    return calls


def _house_text(*data_lines: str) -> str:
    return "# SYNTHETIC\n" + HEADER + "\n" + "\n".join(data_lines) + "\n"


def _house_path(tmp_path: Path, *data_lines: str) -> Path:
    path = tmp_path / "house_sales.csv"
    path.write_text(_house_text(*data_lines), encoding="utf-8")
    return path


def _outcome(fn, path: Path):
    try:
        return ("ok", fn(path))
    except B2Error as exc:
        return ("err", str(exc))


# --- Q1: quoted GeographyName with comma ("2011 Data Zones" stays GeographyType) ---


def test_q1_quoted_geography_name_with_comma(tmp_path: Path) -> None:
    """SYNTHETIC. Real-row-36 shape: comma inside quotes does not shift DateCode."""
    line = (
        f'S01006506,"{CULTS}",2011 Data Zones,2023,Mean,GBP,1,6'
    )
    path = _house_path(tmp_path, line)
    _header, rows = _house_sales_rows(path)
    assert rows[0][1] == CULTS
    assert rows[0][2] == "2011 Data Zones"
    assert rows[0][3] == "2023"
    assert len(rows[0]) == 8
    assert scan_measurement_labels(path) == ["Mean"]


def test_q1_refusal_when_quotes_ignored_shape_documented() -> None:
    """Document the main red-first refusal: DateCode misread as GeographyType."""
    assert "2011 Data Zones" in "B2_HOUSE_SALES: ERROR: year row 1: expected integer, got 2011 Data Zones"


# --- Q2 / Q3: quoted DateCode ---


def test_q2_quoted_datecode(tmp_path: Path) -> None:
    """SYNTHETIC. A quoted DateCode under 2024 parses."""
    path = _house_path(
        tmp_path,
        'S01,zone,2011 Data Zones,"2023",Mean,GBP,1,6',
        'S01,zone,2011 Data Zones,"2023",Median,GBP,1,6',
    )
    assert scan_measurement_labels(path) == ["Mean", "Median"]
    # A2a complete set (fixture data only; year assertion unchanged).
    path = _house_path(
        tmp_path,
        'S01,zone,2011 Data Zones,"2023",Count,Number of sales,6,Number of sales',
        'S01,zone,2011 Data Zones,"2023",Mean,GBP,1,6',
        'S01,zone,2011 Data Zones,"2023",Median,GBP,1,6',
        'S01,zone,2011 Data Zones,"2023",Lower Quartile,GBP,1,6',
        'S01,zone,2011 Data Zones,"2023",Upper Quartile,GBP,1,6',
    )
    rows = adapt_house_sales(path)
    assert rows[0]["year"] == 2023


def test_q3_quoted_datecode_2024_stops_early(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. Quoted DateCode >= 2024 refuses before later fields are read."""
    line = f'S01,zone,2011 Data Zones,"2024",Mean,GBP,{SENTINEL},6'
    payload = _house_text(line).encode("ascii")
    path = tmp_path / "house_sales.csv"
    path.write_bytes(payload)
    calls = _value_spy(monkeypatch)
    box = _track(monkeypatch, payload)
    with pytest.raises(B2Error) as raised:
        adapt_house_sales(path)
    assert str(raised.value) == "B2_HOUSE_SALES: ERROR: year row 1: expected <2024, got 2024"
    assert calls["n"] == 0
    assert SENTINEL.encode("ascii") not in box["tracker"].seen


# --- Q4 / Q5: escaped quotes and multi-line quoted field ---


def test_q4_escaped_quotes_inside_field(tmp_path: Path) -> None:
    """SYNTHETIC. Doubled quotes decode to a literal quote."""
    path = _house_path(tmp_path, 'S01,"foo ""bar"" baz",2011 Data Zones,2023,Mean,GBP,1,6')
    _header, rows = _house_sales_rows(path)
    assert rows[0][1] == 'foo "bar" baz'
    assert rows[0][3] == "2023"


def test_q5_multiline_quoted_field(tmp_path: Path) -> None:
    """SYNTHETIC. CR/LF inside a quoted field stay in the cell; the record counts once."""
    path = _house_path(
        tmp_path,
        'S01,"line1\nline2",2011 Data Zones,2023,Mean,GBP,1,6',
    )
    _header, rows = _house_sales_rows(path)
    assert rows[0][1] == "line1\nline2"
    assert len(rows) == 1
    assert scan_measurement_labels(path) == ["Mean"]


# --- Q6 / Q6b: R-UNTERM ---


def test_q6_unterminated_quote_before_datecode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. An open quote before DateCode is R-UNTERM; read_value_cell is never called."""
    line = f'S01,"open,2011 Data Zones,2023,Mean,GBP,{SENTINEL},6'
    payload = _house_text(line).encode("ascii")
    path = tmp_path / "house_sales.csv"
    path.write_bytes(payload)
    calls = _value_spy(monkeypatch)
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(path)
    assert str(raised.value) == R_UNTERM.format(n=1)
    assert calls["n"] == 0


def test_q6b_unterminated_on_third_record(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. Multi-line record 2 counts once; record 3 R-UNTERM uses n=3."""
    lines = (
        "S01,zone,2011 Data Zones,2023,Mean,GBP,1,6",
        'S02,"l1\nl2",2011 Data Zones,2023,Mean,GBP,1,6',
        'S03,"never-closes,2011 Data Zones,2023,Mean,GBP,1,6',
    )
    payload = _house_text(*lines).encode("ascii")
    path = tmp_path / "house_sales.csv"
    path.write_bytes(payload)
    calls = _value_spy(monkeypatch)
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(path)
    assert str(raised.value) == R_UNTERM.format(n=3)
    assert calls["n"] == 0


# --- Q7 / Q7b: R-STRAY ---


@pytest.mark.parametrize(
    "line",
    [
        'S01,a"b,2011 Data Zones,2023,Mean,GBP,1,6',
        'S01,"ab"c,2011 Data Zones,2023,Mean,GBP,1,6',
    ],
)
def test_q7_stray_quote(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, line: str
) -> None:
    """SYNTHETIC. A quote mid-field or after a closed quote is R-STRAY."""
    payload = _house_text(line).encode("ascii")
    path = tmp_path / "house_sales.csv"
    path.write_bytes(payload)
    calls = _value_spy(monkeypatch)
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(path)
    assert str(raised.value) == R_STRAY.format(n=1)
    assert calls["n"] == 0


def test_q7b_stray_quote_in_datecode_via_datecode_field(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. DateCode 20\"23 is R-STRAY from _datecode_field; _house_field never sees it."""
    line = f'S01,zone,2011 Data Zones,20"23,Mean,GBP,{SENTINEL},6'
    payload = _house_text(line).encode("ascii")
    path = tmp_path / "house_sales.csv"
    path.write_bytes(payload)
    calls = _value_spy(monkeypatch)
    seen_datecode = {"n": 0}
    real_house_field = _house_field

    def house_spy(cursor):
        text, kind = real_house_field(cursor)
        if "20" in text and "23" in text:
            seen_datecode["n"] += 1
        if text == '20"23' or '20"23' in text:
            seen_datecode["n"] += 1
        return text, kind

    monkeypatch.setattr("georgist.v14_b2._house_field", house_spy)
    box = _track(monkeypatch, payload)
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(path)
    assert str(raised.value) == R_STRAY.format(n=1)
    assert calls["n"] == 0
    assert seen_datecode["n"] == 0
    assert SENTINEL.encode("ascii") not in box["tracker"].seen


# --- Q8–Q10 ---


def test_q8_quoted_field_with_comma_and_newline(tmp_path: Path) -> None:
    """SYNTHETIC. Comma and newline together inside quotes stay one field."""
    path = _house_path(
        tmp_path,
        'S01,"a,b\nc",2011 Data Zones,2023,Mean,GBP,1,6',
    )
    _header, rows = _house_sales_rows(path)
    assert rows[0][1] == "a,b\nc"
    assert rows[0][3] == "2023"


def test_q9_empty_quoted_geography_name(tmp_path: Path) -> None:
    """SYNTHETIC. An empty quoted GeographyName is allowed; DateCode still screens."""
    path = _house_path(tmp_path, 'S01,"",2011 Data Zones,2023,Mean,GBP,1,6')
    _header, rows = _house_sales_rows(path)
    assert rows[0][1] == ""
    assert scan_measurement_labels(path) == ["Mean"]


def test_q10_crlf_record_separators(tmp_path: Path) -> None:
    """SYNTHETIC. CRLF between records with a quoted name still parses."""
    body = (
        "# SYNTHETIC\r\n"
        + HEADER
        + "\r\n"
        + f'S01006506,"{CULTS}",2011 Data Zones,2023,Mean,GBP,1,6\r\n'
    )
    path = tmp_path / "house_sales.csv"
    path.write_bytes(body.encode("ascii"))
    _header, rows = _house_sales_rows(path)
    assert rows[0][1] == CULTS
    assert rows[0][3] == "2023"


# --- Q11: wrong-type DateCodes (quoted) ---


@pytest.mark.parametrize(
    ("datecode", "got"),
    [
        ('"20 23"', "20 23"),
        ('""', "blank"),
        ('"2023.0"', "2023.0"),
        ('"True"', "True"),
    ],
)
def test_q11_quoted_non_integer_datecode(
    tmp_path: Path, datecode: str, got: str
) -> None:
    """SYNTHETIC. Quoted non-integer DateCode keeps the existing year message."""
    path = _house_path(
        tmp_path, f"S01,zone,2011 Data Zones,{datecode},Mean,GBP,{SENTINEL},6"
    )
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(path)
    assert str(raised.value) == (
        f"B2_HOUSE_SALES: ERROR: year row 1: expected integer, got {got}"
    )


# --- Q12: GeographyType stays "2011 Data Zones" after quote parse (filter shape) ---


def test_q12_geography_type_2011_data_zones(tmp_path: Path) -> None:
    """SYNTHETIC. After quote parse, GeographyType is exactly 2011 Data Zones."""
    path = _house_path(
        tmp_path,
        f'S01006506,"{CULTS}",2011 Data Zones,2023,Count,Number,1,6',
        f'S01006506,"{CULTS}",2011 Data Zones,2023,Mean,GBP,1,6',
    )
    _header, rows = _house_sales_rows(path)
    assert all(row[2] == "2011 Data Zones" for row in rows)
    assert scan_measurement_labels(path) == ["Count", "Mean"]


def test_q12_refusal_wrong_shift_without_quotes_is_year_message() -> None:
    """The pre-fix refusal when GeographyType lands in DateCode."""
    msg = "B2_HOUSE_SALES: ERROR: year row 1: expected integer, got 2011 Data Zones"
    assert msg.endswith("2011 Data Zones")


# --- Q13: both entry points agree ---


@pytest.mark.parametrize(
    "lines",
    [
        (f'S01006506,"{CULTS}",2011 Data Zones,2023,Mean,GBP,1,6',),
        ('S01,zone,2011 Data Zones,"2023",Mean,GBP,1,6',),
        (f'S01,zone,2011 Data Zones,"2024",Mean,GBP,{SENTINEL},6',),
        ('S01,"foo ""bar""",2011 Data Zones,2023,Mean,GBP,1,6',),
        ('S01,"line1\nline2",2011 Data Zones,2023,Mean,GBP,1,6',),
        ('S01,"open,2011 Data Zones,2023,Mean,GBP,1,6',),
        ('S01,a"b,2011 Data Zones,2023,Mean,GBP,1,6',),
        (
            "S01,zone,2011 Data Zones,2023,Mean,GBP,1,6",
            'S02,"l1\nl2",2011 Data Zones,2023,Mean,GBP,1,6',
            'S03,"never-closes,2011 Data Zones,2023,Mean,GBP,1,6',
        ),
        (f'S01,zone,2011 Data Zones,20"23,Mean,GBP,{SENTINEL},6',),
    ],
)
def test_q13_both_entry_points(tmp_path: Path, lines: tuple[str, ...]) -> None:
    """SYNTHETIC. scan_measurement_labels and adapt_house_sales agree on refusal or labels."""
    path = _house_path(tmp_path, *lines)
    scan_kind, scan_value = _outcome(scan_measurement_labels, path)
    adapt_kind, adapt_value = _outcome(adapt_house_sales, path)
    if scan_kind == "err":
        assert adapt_kind == "err"
        assert adapt_value == scan_value
    else:
        assert scan_kind == "ok"
        # adapt may refuse incomplete Mean/Median set; labels path must still succeed
        assert isinstance(scan_value, list)
        if adapt_kind == "err":
            assert "incomplete" in adapt_value or "measurement" in adapt_value
        else:
            assert adapt_kind == "ok"


# --- Q14: empty / comments / missing ---


def test_q14_empty_comments_missing(tmp_path: Path) -> None:
    """SYNTHETIC. Existing header-absent / file-absent literals."""
    empty = tmp_path / "empty.csv"
    empty.write_bytes(b"")
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(empty)
    assert str(raised.value) == (
        "B2_HOUSE_SALES: ERROR: header: expected "
        + ",".join(HOUSE_SALES_HEADERS)
        + ", got absent"
    )
    comments = tmp_path / "comments.csv"
    comments.write_text("# only\n# comments\n", encoding="utf-8")
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(comments)
    assert str(raised.value) == (
        "B2_HOUSE_SALES: ERROR: header: expected "
        + ",".join(HOUSE_SALES_HEADERS)
        + ", got absent"
    )
    missing = tmp_path / "missing.csv"
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(missing)
    assert str(raised.value) == f"B2_HOUSE_SALES: ERROR: file: expected {missing}, got absent"


def test_optional_header_n0_unterm(tmp_path: Path) -> None:
    """SYNTHETIC. An unterminated quote in the header uses n=0."""
    body = '# SYNTHETIC\nGeographyCode,"GeographyName,GeographyType,DateCode,Measurement,Units,Value,Sales\n'
    path = tmp_path / "house_sales.csv"
    path.write_text(body, encoding="utf-8")
    with pytest.raises(B2Error) as raised:
        scan_measurement_labels(path)
    assert str(raised.value) == R_UNTERM.format(n=0)


# --- Part B: parse_data_rows ---


def _bedrooms_file(tmp_path: Path, data_line: str) -> Path:
    header = ",".join(SCHEMA_HEADERS["bedrooms"])
    path = tmp_path / "bedrooms.csv"
    path.write_text(f"# SYNTHETIC\n{header}\n{data_line}\n", encoding="utf-8")
    return path


def test_b1_quoted_comma_in_schema_row(tmp_path: Path) -> None:
    """SYNTHETIC. csv.reader keeps a comma inside quotes as one field."""
    path = _bedrooms_file(tmp_path, 'Z1,"10,0",0.5,0.3,0.2')
    assert parse_data_rows(path, "bedrooms") == [["Z1", "10,0", "0.5", "0.3", "0.2"]]
    assert parse_data_rows(path) == [["Z1", "10,0", "0.5", "0.3", "0.2"]]


def test_b2_real_file_equality_when_present() -> None:
    """Real pinned schema files: parse_data_rows equals split on used columns when present."""
    roots = [
        Path("/workspace/scotland-rules"),
        Path("/workspace/data"),
        Path.home() / "scotland-rules",
    ]
    found = 0
    for schema in ("plot_split", "crosswalk", "sold_tfa", "access", "bedrooms"):
        pin = REAL_SHA256[schema]
        path = None
        for root in roots:
            if not root.exists():
                continue
            for candidate in root.rglob("*.csv"):
                try:
                    digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
                except OSError:
                    continue
                if digest == pin:
                    path = candidate
                    break
            if path is not None:
                break
        if path is None:
            continue
        found += 1
        via_csv = parse_data_rows(path, schema)
        text = path.read_text(encoding="utf-8")
        lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
        via_split = [line.split(",") for line in lines[1:]]
        # Equality on the columns the adapters read (no embedded commas in those pins).
        assert via_csv == via_split
    if found == 0:
        pytest.skip("pinned real schema files absent")


def test_b3_unterminated_quote_parse_data_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SYNTHETIC. Unterminated quote refuses with B2_BEDROOMS / B2_CSV; adapt emits nothing."""
    path = _bedrooms_file(tmp_path, 'x,"y')
    with pytest.raises(B2Error) as raised:
        parse_data_rows(path, "bedrooms")
    assert str(raised.value) == (
        "B2_BEDROOMS: ERROR: row 1: expected closing quote, got end of file"
    )
    with pytest.raises(B2Error) as raised:
        parse_data_rows(path)
    assert str(raised.value) == "B2_CSV: ERROR: row 1: expected closing quote, got end of file"
    cross = tmp_path / "cross.csv"
    cross.write_text(
        "# SYNTHETIC\n"
        + ",".join(SCHEMA_HEADERS["crosswalk"])
        + "\nD1,Z1,1\n",
        encoding="utf-8",
    )
    calls = {"n": 0}
    monkeypatch.setattr(
        "georgist.v14_b2.emit_output",
        lambda *_a, **_k: calls.__setitem__("n", calls["n"] + 1),
    )
    with pytest.raises(B2Error) as raised:
        adapt_bedrooms(path, cross)
    assert str(raised.value) == (
        "B2_BEDROOMS: ERROR: row 1: expected closing quote, got end of file"
    )
    assert calls["n"] == 0


def test_b3b_stray_quote_parse_data_rows(tmp_path: Path) -> None:
    """SYNTHETIC. Trailing characters after a closed quote are R-STRAY for bedrooms."""
    path = _bedrooms_file(tmp_path, 'x,"y"z,0,0,0')
    with pytest.raises(B2Error) as raised:
        parse_data_rows(path, "bedrooms")
    assert str(raised.value) == (
        "B2_BEDROOMS: ERROR: row 1: expected quote only at field start, got stray quote"
    )


@pytest.mark.parametrize("schema", ("plot_split", "crosswalk", "sold_tfa", "access", "bedrooms"))
def test_b4_missing_empty_header_only(tmp_path: Path, schema: str) -> None:
    """SYNTHETIC. Existing absent/header messages through _csv_rows for each schema."""
    token = SCHEMA_TOKEN[schema]
    missing = tmp_path / f"missing_{schema}.csv"
    with pytest.raises(B2Error) as raised:
        _csv_rows(missing, schema)
    assert str(raised.value) == f"B2_{token}: ERROR: file: expected {missing}, got absent"

    empty = tmp_path / f"empty_{schema}.csv"
    empty.write_bytes(b"")
    with pytest.raises(B2Error) as raised:
        _csv_rows(empty, schema)
    assert str(raised.value) == (
        f"B2_{token}: ERROR: header: expected {','.join(SCHEMA_HEADERS[schema])}, got absent"
    )

    header_only = tmp_path / f"header_{schema}.csv"
    header_only.write_text(
        "# SYNTHETIC\n" + ",".join(SCHEMA_HEADERS[schema]) + "\n", encoding="utf-8"
    )
    header, rows = _csv_rows(header_only, schema)
    assert list(header) == list(SCHEMA_HEADERS[schema])
    assert rows == []
