"""B2 input adapters. Renames and projections, plus the bedrooms crosswalk.

Mapped fields equal the source fields. The only arithmetic is the bedrooms
rebuild under O-D1. A field with no frozen citation is refused.
"""

from __future__ import annotations

import csv
import json
from decimal import Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Iterable, Mapping, Sequence

# Frozen citations. COLUMN_MAP grows only by fields that appear here.
FIELD_CITATIONS = {
    "iz": "e1ab6d0a §3.6 O-H iz",
    "ca": "e1ab6d0a §3.6 O-H ca",
    "ur3": "e1ab6d0a §3.6 O-H ur3",
    "flat_share": "e1ab6d0a §3.6 O-H flat_share",
    "pt_flat_share": "e1ab6d0a §3.6 O-H pt_flat_share",
    "pt_maisonette_share": "e1ab6d0a §3.6 O-H pt_maisonette_share",
    "ratio_mean": "e1ab6d0a §3.6 O-H ratio_mean",
    "other_land_per_home": "e1ab6d0a §3.6 O-H other_land_per_home",
    "low_parcel_coverage": "963d6755 L50 frozen by e1ab6d0a §3.6 L123",
}
COLUMN_MAP = tuple(FIELD_CITATIONS)
FIDELITY_ADAPTATION = "bedrooms_o_d1"
LOW_PARCEL_TOKEN = "low_parcel_coverage_lt0.5"
# e1ab6d0a §3.6 L166 RoS Price-Mean. Volume is the Sales column. Median is S-x5.
HOUSE_SALES_MEASUREMENT_LABELS = (
    "Count",
    "Mean",
    "Median",
    "Lower Quartile",
    "Upper Quartile",
)
HOUSE_SALES_PRICE_LABEL = "Mean"
HOUSE_SALES_MEDIAN_LABEL = "Median"
HOUSE_SALES_HEADERS = (
    "GeographyCode",
    "GeographyName",
    "GeographyType",
    "DateCode",
    "Measurement",
    "Units",
    "Value",
    "Sales",
)
SCHEMA_HEADERS = {
    "house_sales": HOUSE_SALES_HEADERS,
    "plot_split": ("dz2022_code", "method_flags"),
    "crosswalk": ("dz2011_code", "dz2022_code", "uprn_count"),
    "sold_tfa": ("code", "year", "sold_tfa_mean"),
    "access": ("code", "vintage", "job_access"),
    "bedrooms": ("dz2022_code", "households_total", "share_1", "share_3", "share_4plus"),
}
SCHEMA_TOKEN = {
    "house_sales": "HOUSE_SALES",
    "plot_split": "PLOT_SPLIT",
    "crosswalk": "CROSSWALK",
    "sold_tfa": "SOLD_TFA",
    "access": "ACCESS",
    "bedrooms": "BEDROOMS",
}
BEDROOM_BANDS = ("share_1", "share_3", "share_4plus")
# Production DZ2022 flag count from D4. Tests pass the fixture's own K.
PIN_TABLE: dict[str, int] = {"low_parcel_count": 1038}


class B2Error(ValueError):
    """A B2 adapter refused a file, header, or field."""


def read_value_cell(value: str) -> str:
    """Value-column hook. The label scan and the year screen do not call it."""
    return value


def _jsonable(value):
    if isinstance(value, Decimal):
        return quantize(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def emit_output(path: Path, payload: Mapping) -> None:
    """Write the adapter payload. Negative tests spy on this and on the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(payload), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _token(schema: str) -> str:
    return SCHEMA_TOKEN[schema]


def _error(schema: str, check: str, expected: object, actual: object) -> B2Error:
    return B2Error(f"B2_{_token(schema)}: ERROR: {check}: expected {expected}, got {actual}")


def extend_column_map(fields: Sequence[str]) -> tuple[str, ...]:
    """Add fields only when each one cites a frozen section."""
    for name in fields:
        if name not in FIELD_CITATIONS:
            raise B2Error(
                "B2_FIELDS: ERROR: frozen definition: expected cited section, got none for " + name
            )
    return tuple(dict.fromkeys((*COLUMN_MAP, *fields)))


def _read_text(path: Path, schema: str) -> str:
    if not path.is_file():
        raise _error(schema, "file", path, "absent")
    return path.read_text(encoding="utf-8")


def _csv_rows(path: Path, schema: str) -> tuple[list[str], list[list[str]]]:
    text = _read_text(path, schema)
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    if not lines:
        raise _error(schema, "header", ",".join(SCHEMA_HEADERS[schema]), "absent")
    header = lines[0].split(",")
    rows = [line.split(",") for line in lines[1:]]
    return header, rows


def _check_header(schema: str, header: Sequence[str]) -> None:
    required = SCHEMA_HEADERS[schema]
    found = list(header)
    for column in required:
        if column in found:
            continue
        extras = [name for name in found if name not in required and name != "note"]
        got = extras[0] if extras else "absent"
        raise _error(schema, "header", column, got)


def _field(row: Sequence[str], index: int) -> str | None:
    if index >= len(row):
        return None
    return row[index]


def _require_width(schema: str, header: Sequence[str], row: Sequence[str], row_number: int) -> None:
    if len(row) < len(header):
        raise B2Error(
            f"B2_{_token(schema)}: ERROR: row {row_number}: expected {len(header)} fields, got {len(row)}"
        )


def _require_value(schema: str, column: str, value: str | None, row_number: int) -> str:
    if value is None or value.strip() == "":
        raise B2Error(
            f"B2_{_token(schema)}: ERROR: {column} row {row_number}: expected value, got blank"
        )
    return value.strip()


def _year_text(row: Sequence[str], year_index: int) -> str | None:
    """Read the year field and stop. Later fields are not inspected here."""
    if year_index >= len(row):
        return None
    return row[year_index]


def screen_house_sales_year(row: Sequence[str], header: Sequence[str], row_number: int) -> int:
    """DateCode is read before Measurement, Value, or Sales."""
    if "DateCode" not in header:
        raise _error("house_sales", "header", "DateCode", "absent")
    year_index = list(header).index("DateCode")
    if len(row) <= year_index:
        raise B2Error(
            f"B2_HOUSE_SALES: ERROR: year row {row_number}: expected integer, got short"
        )
    text = row[year_index].strip()
    if text == "":
        raise B2Error(
            f"B2_HOUSE_SALES: ERROR: year row {row_number}: expected integer, got blank"
        )
    if not text.isdigit():
        raise B2Error(
            f"B2_HOUSE_SALES: ERROR: year row {row_number}: expected integer, got {text}"
        )
    return int(text)


def scan_measurement_labels(path: Path) -> list[str]:
    """Distinct Measurement labels. The Value column is left unread."""
    header, rows = _csv_rows(path, "house_sales")
    _check_header("house_sales", header)
    index = header.index("Measurement")
    labels: list[str] = []
    for row_number, row in enumerate(rows, start=1):
        screen_house_sales_year(row, header, row_number)
        if index >= len(row):
            raise B2Error(
                f"B2_HOUSE_SALES: ERROR: row {row_number}: expected {len(header)} fields, got {len(row)}"
            )
        label = row[index].strip()
        if label not in labels:
            labels.append(label)
    return labels


def _label_list() -> str:
    return ", ".join(HOUSE_SALES_MEASUREMENT_LABELS)


def adapt_house_sales(path: Path) -> list[dict]:
    """Long SDMX rows to zone, year, n_sales, price, median_price."""
    header, rows = _csv_rows(path, "house_sales")
    _check_header("house_sales", header)
    grouped: dict[tuple[str, int], dict] = {}
    order: list[tuple[str, int]] = []
    for row_number, row in enumerate(rows, start=1):
        year = screen_house_sales_year(row, header, row_number)
        _require_width("house_sales", header, row, row_number)
        label = _require_value("house_sales", "Measurement", _field(row, header.index("Measurement")), row_number)
        if label not in HOUSE_SALES_MEASUREMENT_LABELS:
            raise B2Error(
                f"B2_HOUSE_SALES: ERROR: measurement: expected one of {_label_list()}, got {label}"
            )
        zone = _require_value("house_sales", "GeographyCode", _field(row, header.index("GeographyCode")), row_number)
        key = (zone, year)
        if key not in grouped:
            grouped[key] = {"zone": zone, "year": year}
            order.append(key)
            for name in header:
                if name in HOUSE_SALES_HEADERS or name == "note":
                    continue
                cell = _field(row, header.index(name))
                if cell is not None and cell.strip() != "":
                    grouped[key][name] = cell.strip()
        item = grouped[key]
        if label == HOUSE_SALES_PRICE_LABEL:
            item["price"] = read_value_cell(_require_value("house_sales", "Value", _field(row, header.index("Value")), row_number))
            item["n_sales"] = _require_value("house_sales", "Sales", _field(row, header.index("Sales")), row_number)
        elif label == HOUSE_SALES_MEDIAN_LABEL:
            item["median_price"] = read_value_cell(
                _require_value("house_sales", "Value", _field(row, header.index("Value")), row_number)
            )
    projected = []
    for key in order:
        item = grouped[key]
        if "price" not in item or "n_sales" not in item or "median_price" not in item:
            raise _error("house_sales", "measurement", _label_list(), "incomplete")
        projected.append(item)
    return projected


def _flagged(method_flags: str) -> int:
    tokens = [token.strip() for token in method_flags.split(";")]
    return 1 if LOW_PARCEL_TOKEN in tokens else 0


def adapt_plot_split(path: Path, *, expected_count: int | None = None) -> list[dict]:
    """Rename dz2022_code to code and read the plot-split flag."""
    header, rows = _csv_rows(path, "plot_split")
    _check_header("plot_split", header)
    code_i = header.index("dz2022_code")
    flag_i = header.index("method_flags")
    projected = []
    count = 0
    for row_number, row in enumerate(rows, start=1):
        _require_width("plot_split", header, row, row_number)
        code = _require_value("plot_split", "dz2022_code", _field(row, code_i), row_number)
        flags = _require_value("plot_split", "method_flags", _field(row, flag_i), row_number)
        flag = _flagged(flags)
        count += flag
        item = {"code": code, "low_parcel_coverage": flag, "method_flags": flags}
        for name in header:
            if name in {"dz2022_code", "method_flags", "note"}:
                continue
            cell = _field(row, header.index(name))
            if cell is not None and cell.strip() != "":
                item[name] = cell.strip()
        projected.append(item)
    expected = PIN_TABLE["low_parcel_count"] if expected_count is None else expected_count
    if count != expected:
        raise B2Error(
            f"B2_PLOT_SPLIT: ERROR: low_parcel_count: expected {expected}, got {count}"
        )
    return projected


def dz2011_low_parcel_flags(plot_rows: Sequence[Mapping], crosswalk_rows: Sequence[Mapping]) -> dict[str, int]:
    """L123: DZ2011 flag is 1 when the apportioned flagged share is >= 0.5."""
    flags = {str(row["code"]): int(row["low_parcel_coverage"]) for row in plot_rows}
    num: dict[str, Decimal] = {}
    den: dict[str, Decimal] = {}
    for edge in crosswalk_rows:
        dz2022 = str(edge["dz2022"])
        dz2011 = str(edge["dz2011"])
        if dz2022 not in flags:
            continue
        weight = Decimal(str(edge["uprn_count"]))
        num[dz2011] = num.get(dz2011, Decimal(0)) + weight * Decimal(flags[dz2022])
        den[dz2011] = den.get(dz2011, Decimal(0)) + weight
    out: dict[str, int] = {}
    for dz2011, denominator in den.items():
        if denominator <= 0:
            continue
        share = num[dz2011] / denominator
        out[dz2011] = 1 if share >= Decimal("0.5") else 0
    return out


def adapt_crosswalk(path: Path) -> list[dict]:
    header, rows = _csv_rows(path, "crosswalk")
    _check_header("crosswalk", header)
    i11 = header.index("dz2011_code")
    i22 = header.index("dz2022_code")
    iu = header.index("uprn_count")
    projected = []
    for row_number, row in enumerate(rows, start=1):
        _require_width("crosswalk", header, row, row_number)
        projected.append(
            {
                "dz2011": _require_value("crosswalk", "dz2011_code", _field(row, i11), row_number),
                "dz2022": _require_value("crosswalk", "dz2022_code", _field(row, i22), row_number),
                "uprn_count": _require_value("crosswalk", "uprn_count", _field(row, iu), row_number),
            }
        )
    return projected


def adapt_sold_tfa(path: Path) -> list[dict]:
    """Rename code to zone. Provenance is enforced by the D7 loader, not here."""
    header, rows = _csv_rows(path, "sold_tfa")
    _check_header("sold_tfa", header)
    code_i = header.index("code")
    year_i = header.index("year")
    floor_i = header.index("sold_tfa_mean")
    projected = []
    for row_number, row in enumerate(rows, start=1):
        _require_width("sold_tfa", header, row, row_number)
        year_text = _require_value("sold_tfa", "year", _field(row, year_i), row_number)
        if not year_text.isdigit():
            raise B2Error(
                f"B2_SOLD_TFA: ERROR: year row {row_number}: expected integer, got {year_text}"
            )
        projected.append(
            {
                "zone": _require_value("sold_tfa", "code", _field(row, code_i), row_number),
                "year": int(year_text),
                "sold_tfa_mean": _require_value("sold_tfa", "sold_tfa_mean", _field(row, floor_i), row_number),
            }
        )
    return projected


def adapt_access(path: Path) -> list[dict]:
    """Rename code to zone and keep vintage 2011 only."""
    header, rows = _csv_rows(path, "access")
    _check_header("access", header)
    code_i = header.index("code")
    vintage_i = header.index("vintage")
    access_i = header.index("job_access")
    projected = []
    for row_number, row in enumerate(rows, start=1):
        _require_width("access", header, row, row_number)
        vintage = _require_value("access", "vintage", _field(row, vintage_i), row_number)
        if vintage != "2011":
            continue
        projected.append(
            {
                "zone": _require_value("access", "code", _field(row, code_i), row_number),
                "job_access": _require_value("access", "job_access", _field(row, access_i), row_number),
                "vintage": vintage,
            }
        )
    return projected


def _decimal(value: str) -> Decimal:
    return Decimal(value)


def _band_counts(total: str, shares: Mapping[str, str]) -> dict[str, Decimal]:
    households = _decimal(total)
    return {band: households * _decimal(shares[band]) for band in BEDROOM_BANDS}


def adapt_bedrooms(path: Path, crosswalk_path: Path) -> dict:
    """Rebuild DZ2022 counts, crosswalk them on O-D1 weights, recompute shares.

    A blank total or share suppresses that DZ2022 zone. A DZ2011 zone whose
    missing-data weight is above 1 percent, or that draws on 5 or more
    data-less DZ2022 zones, is incomplete_suppressed and emits no row.
    """
    header, rows = _csv_rows(path, "bedrooms")
    _check_header("bedrooms", header)
    crosswalk = adapt_crosswalk(crosswalk_path)
    totals: dict[str, dict[str, Decimal]] = {}
    suppressed: set[str] = set()
    seen: set[str] = set()
    for row_number, row in enumerate(rows, start=1):
        _require_width("bedrooms", header, row, row_number)
        code = _require_value("bedrooms", "dz2022_code", _field(row, header.index("dz2022_code")), row_number)
        seen.add(code)
        total = _field(row, header.index("households_total"))
        shares = {band: _field(row, header.index(band)) for band in BEDROOM_BANDS}
        if total is None or total.strip() == "" or any(value is None or value.strip() == "" for value in shares.values()):
            suppressed.add(code)
            continue
        totals[code] = _band_counts(total.strip(), {band: str(shares[band]).strip() for band in BEDROOM_BANDS})
    incoming: dict[str, list[tuple[str, Decimal]]] = {}
    outgoing: dict[str, Decimal] = {}
    for edge in crosswalk:
        dz2022 = str(edge["dz2022"])
        dz2011 = str(edge["dz2011"])
        weight = _decimal(str(edge["uprn_count"]))
        incoming.setdefault(dz2011, []).append((dz2022, weight))
        outgoing[dz2022] = outgoing.get(dz2022, Decimal(0)) + weight
    built: list[dict] = []
    for dz2011, edges in incoming.items():
        total_weight = sum((weight for _code, weight in edges), Decimal(0))
        if total_weight <= 0:
            continue
        missing_weight = Decimal(0)
        affected = 0
        for code, weight in edges:
            if code not in totals:
                missing_weight += weight
                affected += 1
        share_missing = missing_weight / total_weight
        if share_missing > Decimal("0.01") or affected >= 5:
            continue
        counts = {band: Decimal(0) for band in BEDROOM_BANDS}
        for code, weight in edges:
            if code not in totals or outgoing.get(code, Decimal(0)) <= 0:
                continue
            portion = weight / outgoing[code]
            for band in BEDROOM_BANDS:
                counts[band] += totals[code][band] * portion
        denominator = sum(counts.values(), Decimal(0))
        if denominator <= 0:
            continue
        item = {
            "dz2011": dz2011,
            "fidelity_adaptation": FIDELITY_ADAPTATION,
        }
        for band in BEDROOM_BANDS:
            item[band] = counts[band]
            item[band + "_share"] = counts[band] / denominator
        built.append(item)
    dz2022_shares = {}
    for code, counts in totals.items():
        denominator = sum(counts.values(), Decimal(0))
        if denominator <= 0:
            continue
        dz2022_shares[code] = {band: counts[band] / denominator for band in BEDROOM_BANDS}
    return {
        "rows": built,
        "fidelity_adaptation": FIDELITY_ADAPTATION,
        "suppressed_dz2022": sorted(suppressed),
        "seen_dz2022": sorted(seen),
        "dz2022_shares": dz2022_shares,
    }


def project_cited_fields(row: Mapping[str, str]) -> dict[str, str]:
    """Copy cited fields. An uncited name is listed and refused."""
    unknown = [name for name in row if name not in FIELD_CITATIONS and name != "note"]
    if unknown:
        raise B2Error(
            "B2_FIELDS: ERROR: frozen definition: expected cited section, got none for " + unknown[0]
        )
    return {name: row[name] for name in COLUMN_MAP if name in row}


def quantize(value: Decimal) -> str:
    """Half-even to 10 decimal places, the bedrooms rounding used in tests."""
    return str(value.quantize(Decimal("0.0000000001"), rounding=ROUND_HALF_EVEN))


def write_adapter(schema: str, path: Path, dest: Path, *, crosswalk: Path | None = None, expected_count: int | None = None) -> dict:
    """Run one adapter and write dest. Errors leave dest absent."""
    if schema == "house_sales":
        payload = {"rows": adapt_house_sales(path)}
    elif schema == "plot_split":
        payload = {"rows": adapt_plot_split(path, expected_count=expected_count)}
    elif schema == "crosswalk":
        payload = {"rows": adapt_crosswalk(path)}
    elif schema == "sold_tfa":
        payload = {"rows": adapt_sold_tfa(path)}
    elif schema == "access":
        payload = {"rows": adapt_access(path)}
    elif schema == "bedrooms":
        if crosswalk is None:
            raise _error(schema, "file", "crosswalk", "absent")
        payload = adapt_bedrooms(path, crosswalk)
    else:
        raise _error(schema, "header", "known schema", schema)
    emit_output(dest, payload)
    return payload


def load_bedrooms_crosswalk_weights(rows: Iterable[Mapping]) -> list[dict]:
    return [dict(row) for row in rows]
