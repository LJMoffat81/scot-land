#!/usr/bin/env python3
"""Build v1.4 hedonic rows for the 2021-22 fit and the 2023 holdout.

House sales, the plot-split README and CSV, the EPC rollup and the merge map
are sha-asserted, as are the sold-TFA, bedroom, job-access and crosswalk
files the frozen controls need. A missing pin is listed. Nothing is
substituted. Any year at or after 2024 is refused before a price cell is
read. This script does not score.

Usage (from ``backend/``)::

    python -m scripts.build_v14_hedonic_rows --out rows.json \\
        --house-sales house_sales.csv ...
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

from georgist.hedonic_merge_map import load_a_z_m2

PINNED_SHA256 = {
    "house_sales": "702c9ada0b26dad9904e97f00ea7aa3357e1bf449e724e83292b5265f0549cf2",
    "plot_split_readme": "0f1fc0119cdcef3c10e674a25fa4d5783e256e5a8cb150a5c4de748a42548137",
    "plot_split_csv": "09e2082d801b15203794974aea802cc7e5c5c403761365b69bd4b695d7a0638c",
    "epc_rollup": "13a5f647a833d89ec7aad0a82cd3cfc52d375b31b05e3b5ad7f4f12c998e2618",
    "merge_map": "581b0aa1647c5af7ce5b9617e35fcfa73982bc8712a42eb63242243ee6a95947",
    "sold_tfa": "d99b8daa6e03843923799d249714fa850bd360c6e9cd01a922d43b6000ba2d6e",
    "bedrooms": "6d15b887bf7bea4b96488e5374a7ea75f9e2beaa3f2544f275072de674cfa603",
    "job_access": "d50b804b60991a0571d92d85a7e0775d62ace263752140c2c91cb72bad66c9ca",
    "crosswalk": "7690bcbebf9968ca9b02cf898832aa9be8fca56f3eb9af70b20e25b5d23e13e4",
}

FIT_YEARS = (2021, 2022)
HOLDOUT_YEAR = 2023
KEPT_YEARS = FIT_YEARS + (HOLDOUT_YEAR,)

# Output columns. Mid-terrace, age-unknown and bedroom band 2 are omitted.
# SIMD and intermediate-zone fixed effects stay out of the primary row.
COLUMN_MAP = (
    "zone",
    "year",
    "window",
    "cell",
    "price",
    "median_price",
    "n_sales",
    "a_m2",
    "a_r20",
    "a_r40",
    "f_m2",
    "f_imputed",
    "x_bf_detached_share",
    "x_bf_semi_detached_share",
    "x_bf_end_terrace_share",
    "x_bf_enclosed_end_terrace_share",
    "x_bf_enclosed_mid_terrace_share",
    "x_flat_share",
    "x_age_pre1919_share",
    "x_age_1919_1949_share",
    "x_age_1950_1982_share",
    "x_age_1983_2002_share",
    "x_age_2003_share",
    "x_bed_share_1",
    "x_bed_share_3",
    "x_bed_share_4plus",
    "x_log_job_access",
    "x_coverage_share",
    "x_share_lodged_last_10y",
    "x_low_parcel_coverage",
    "x_other_land_share",
    "ur6",
    "itl3",
    "ca2019",
)

OMITTED_CONTROLS = (
    "bf_mid_terrace_share",
    "age_unknown_share",
    "share_2",
    "simd",
    "iz_fe",
)

AGE_BAND_SOURCES = {
    "x_age_pre1919_share": ("age_pre1919_share",),
    "x_age_1919_1949_share": ("age_1919_1929_share", "age_1930_1949_share"),
    "x_age_1950_1982_share": ("age_1950_1964_share", "age_1965_1975_share", "age_1976_1983_share"),
    "x_age_1983_2002_share": ("age_1984_1991_share", "age_1992_1998_share", "age_1999_2002_share"),
    "x_age_2003_share": ("age_2003_2007_share", "age_2008_on_share"),
}

BUILT_FORM_SOURCES = (
    ("bf_detached_share", "x_bf_detached_share"),
    ("bf_semi_detached_share", "x_bf_semi_detached_share"),
    ("bf_end_terrace_share", "x_bf_end_terrace_share"),
    ("bf_enclosed_end_terrace_share", "x_bf_enclosed_end_terrace_share"),
    ("bf_enclosed_mid_terrace_share", "x_bf_enclosed_mid_terrace_share"),
)

HOUSE_SALES_COLUMNS = ("zone", "year", "n_sales", "price", "median_price")
PRICE_COLUMNS = frozenset({"price", "median_price"})


class HedonicRowError(ValueError):
    """A pinned input is missing, or a row is outside the frozen window."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def missing_pins(paths: dict[str, Path | None]) -> list[str]:
    return [name for name in PINNED_SHA256 if paths.get(name) is None]


def assert_pinned(paths: dict[str, Path | None]) -> None:
    missing = missing_pins(paths)
    if missing:
        raise HedonicRowError("inputs without a pinned sha: " + ", ".join(missing))
    for name, expected in PINNED_SHA256.items():
        path = paths[name]
        assert path is not None
        digest = sha256_file(path)
        if not digest.startswith(expected[:8]) or digest != expected:
            raise HedonicRowError(f"{name} sha256 {digest} != {expected}")


class _CsvCursor:
    """One-character CSV cursor with a single-character unread."""

    def __init__(self, handle) -> None:
        self._handle = handle
        self._held: str | None = None

    def read(self) -> str:
        if self._held is not None:
            char = self._held
            self._held = None
            return char
        return _one_char(self._handle)

    def unread(self, char: str) -> None:
        if char == "":
            return
        if self._held is not None:
            raise HedonicRowError("csv cursor overflow")
        self._held = char


def _one_char(handle) -> str:
    """One Unicode character. A binary handle is read a byte at a time."""
    raw = handle.read(1)
    if raw is None or raw == "" or raw == b"":
        return ""
    if isinstance(raw, str):
        return raw
    lead = raw[0]
    if lead < 0x80:
        return chr(lead)
    width = 2 if lead < 0xE0 else 3 if lead < 0xF0 else 4
    buf = bytearray(raw)
    while len(buf) < width:
        more = handle.read(1)
        if not more or isinstance(more, str):
            raise HedonicRowError("truncated utf-8")
        buf += more
    return bytes(buf).decode("utf-8")


def _finish_newline(cursor: _CsvCursor, char: str) -> None:
    if char != "\r":
        return
    nxt = cursor.read()
    if nxt != "\n":
        cursor.unread(nxt)


def _read_field(cursor: _CsvCursor, *, keep: bool) -> tuple[str, bool, bool]:
    """Return ``(text, at_end, eof_before)``.

    ``keep`` False discards the field text while the delimiters are still honoured.
    Quote rules match the CSV reader: a doubled quote is one quote, and
    characters after a closing quote stay in the field until the delimiter.
    """
    char = cursor.read()
    if char == "":
        return "", True, True
    if char in "\r\n":
        _finish_newline(cursor, char)
        return "", True, False
    if char == ",":
        return "", False, False

    pieces: list[str] = []
    quoted = char == '"'

    def take(value: str) -> None:
        if keep:
            pieces.append(value)

    if not quoted:
        take(char)
    while True:
        char = cursor.read()
        if char == "" and quoted:
            return "".join(pieces), True, False
        if quoted:
            if char != '"':
                take(char)
                continue
            char = cursor.read()
            if char == '"':
                take('"')
                continue
            quoted = False
            if char == "":
                return "".join(pieces), True, False
        if char == ",":
            return "".join(pieces), False, False
        if char in "\r\n":
            _finish_newline(cursor, char)
            return "".join(pieces), True, False
        if char == "":
            return "".join(pieces), True, False
        take(char)


def _skip_record(cursor: _CsvCursor) -> None:
    while True:
        _text, at_end, eof_before = _read_field(cursor, keep=False)
        if at_end or eof_before:
            return


def screen_year_column(handle, year_column: str, source_name: str) -> None:
    """Read the year field before any later field on that row.

    A year at or after 2024 raises before the remainder of the record is
    read, so a price cell after the year column never enters memory.
    """
    cursor = _CsvCursor(handle)
    header: list[str] = []
    while True:
        text, at_end, eof_before = _read_field(cursor, keep=True)
        if eof_before and not header:
            raise HedonicRowError(f"{source_name} has no {year_column} column")
        header.append(text.strip())
        if at_end:
            break
    if year_column not in header:
        raise HedonicRowError(f"{source_name} has no {year_column} column")
    year_index = header.index(year_column)
    for name in PRICE_COLUMNS:
        if name in header and header.index(name) < year_index:
            raise HedonicRowError("price column precedes the year column")
    while True:
        year_text: str | None = None
        at_end = False
        for position in range(year_index + 1):
            text, at_end, eof_before = _read_field(cursor, keep=position == year_index)
            if eof_before:
                if position == 0:
                    return
                year_text = None
                break
            if position == year_index:
                year_text = text
            if at_end:
                if position < year_index:
                    year_text = None
                break
        if year_text is not None and year_text.strip() and int(year_text.strip()) >= 2024:
            raise HedonicRowError("year >= 2024 refused")
        if not at_end:
            _skip_record(cursor)


def screen_years(path: Path, year_column: str = "year") -> None:
    """Refuse year >= 2024 before any later price cell is read."""
    with path.open("rb", buffering=0) as handle:
        screen_year_column(handle, year_column, path.name)


def _csv_maps(path: Path, key: str, fields: tuple[str, ...]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = [field for field in fields if field not in columns and field != key]
        if key not in columns or missing:
            raise HedonicRowError(f"{path.name} missing columns: {key if key not in columns else ''} {', '.join(missing)}".strip())
        for row in reader:
            code = str(row[key]).strip()
            if not code:
                continue
            out[code] = {field: row[field] for field in fields if field in row}
    return out


def read_house_sales(path: Path) -> list[dict]:
    """Fit and holdout rows. The year screen has already refused 2024."""
    screen_years(path)
    rows: list[dict] = []
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        absent = [name for name in HOUSE_SALES_COLUMNS if name not in columns]
        if absent:
            raise HedonicRowError("house_sales missing columns: " + ", ".join(absent))
        for row in reader:
            year = int(row["year"])
            if year not in KEPT_YEARS:
                continue
            item = {
                "zone": str(row["zone"]).strip(),
                "year": year,
                "n_sales": float(row["n_sales"]),
                "price": float(row["price"]),
                "median_price": float(row["median_price"]),
            }
            if not item["zone"]:
                continue
            rows.append(item)
    return rows


def _sum_fields(row: dict, names: tuple[str, ...]) -> float:
    total = 0.0
    for name in names:
        if name not in row or str(row[name]).strip() == "":
            raise HedonicRowError(f"missing {name}")
        total += float(row[name])
    return total


def build_v14_hedonic_rows(
    *,
    sales: list[dict],
    areas: dict[str, dict],
    epc: dict[str, dict],
    merge: dict[str, dict],
    sold_tfa: dict[tuple[str, int], dict],
    bedrooms: dict[str, dict],
    access: dict[str, dict],
) -> list[dict]:
    """One row per zone-year. Controls are the frozen §3.6 list."""
    built: list[dict] = []
    for sale in sales:
        year = int(sale["year"])
        if year >= 2024:
            raise HedonicRowError("year >= 2024 refused")
        if year not in KEPT_YEARS:
            continue
        zone = str(sale["zone"])
        area = areas.get(zone)
        certificate = epc.get(zone)
        cell = merge.get(zone)
        floor = sold_tfa.get((zone, year))
        beds = bedrooms.get(zone)
        jobs = access.get(zone)
        if not all((area, certificate, cell, floor, beds, jobs)):
            raise HedonicRowError(f"missing fields for {zone} {year}")
        assert area is not None and certificate is not None and cell is not None
        assert floor is not None and beds is not None and jobs is not None
        row = {
            "zone": zone,
            "year": year,
            "window": "fit" if year in FIT_YEARS else "holdout",
            "cell": str(cell["cell"]),
            "price": float(sale["price"]),
            "median_price": float(sale["median_price"]),
            "n_sales": float(sale["n_sales"]),
            "a_m2": float(area["a_m2"]),
            "a_r20": float(area["a_r20"]),
            "a_r40": float(area["a_r40"]),
            "f_m2": float(floor["f_m2"]),
            "f_imputed": int(floor.get("f_imputed") or 0),
            "x_flat_share": _sum_fields(certificate, ("pt_flat_share", "pt_maisonette_share")),
            "x_log_job_access": float(jobs["log_job_access"]),
            "x_coverage_share": float(certificate["coverage_share"]),
            "x_share_lodged_last_10y": float(certificate["share_lodged_last_10y"]),
            "x_low_parcel_coverage": float(area["low_parcel_coverage"]),
            "x_other_land_share": float(area["other_land_share"]),
            "ur6": int(cell["ur6"]),
            "itl3": str(cell["itl3"]),
            "ca2019": str(cell["ca2019"]),
            "x_bed_share_1": float(beds["share_1"]),
            "x_bed_share_3": float(beds["share_3"]),
            "x_bed_share_4plus": float(beds["share_4plus"]),
        }
        for source, target in BUILT_FORM_SOURCES:
            row[target] = float(certificate[source])
        for target, sources in AGE_BAND_SOURCES.items():
            row[target] = _sum_fields(certificate, sources)
        unknown = [key for key in row if key not in COLUMN_MAP]
        if unknown:
            raise HedonicRowError("field not in the frozen text: " + ", ".join(unknown))
        if any(name in row for name in OMITTED_CONTROLS):
            raise HedonicRowError("an omitted control was written")
        built.append({key: row[key] for key in COLUMN_MAP})
    if not built:
        raise HedonicRowError("no fit or holdout rows")
    return built


def _apportioned_plot_flags(plot_path: Path, crosswalk_path: Path) -> dict[str, dict]:
    """Household-style UPRN weights for the two plot-split controls. No zero fill."""
    plots = _csv_maps(plot_path, "code", ("low_parcel_coverage", "other_land_share", "homes"))
    by_dz2022: dict[str, list[tuple[str, float]]] = {}
    with crosswalk_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            dz2022 = str(row.get("dz2022") or "").strip()
            dz2011 = str(row.get("dz2011") or "").strip()
            if not dz2022 or not dz2011 or dz2022 not in plots:
                continue
            by_dz2022.setdefault(dz2022, []).append((dz2011, float(row["uprn_count"])))
    num_low: dict[str, float] = {}
    num_other: dict[str, float] = {}
    den: dict[str, float] = {}
    for dz2022, edges in by_dz2022.items():
        total = sum(weight for _dz2011, weight in edges)
        if total <= 0:
            continue
        plot = plots[dz2022]
        homes = float(plot["homes"])
        for dz2011, weight in edges:
            share = weight / total
            num_low[dz2011] = num_low.get(dz2011, 0.0) + share * homes * float(plot["low_parcel_coverage"])
            num_other[dz2011] = num_other.get(dz2011, 0.0) + share * homes * float(plot["other_land_share"])
            den[dz2011] = den.get(dz2011, 0.0) + share * homes
    out: dict[str, dict] = {}
    for dz2011, denominator in den.items():
        if denominator <= 0:
            continue
        out[dz2011] = {
            "low_parcel_coverage": num_low[dz2011] / denominator,
            "other_land_share": num_other[dz2011] / denominator,
        }
    if by_dz2022 and not out:
        raise HedonicRowError("crosswalk did not place plot-split controls on DZ2011")
    return out


def _weighted_areas(plot_path: Path, crosswalk_path: Path) -> dict[str, dict]:
    """Move DZ2022 plot columns onto DZ2011 by the frozen ratio of apportioned sums."""
    central = load_a_z_m2(plot_path, crosswalk_path, plot_ha_col="house_plot_ha")
    r20 = load_a_z_m2(plot_path, crosswalk_path, plot_ha_col="house_plot_ha_r20")
    r40 = load_a_z_m2(plot_path, crosswalk_path, plot_ha_col="house_plot_ha_r40")
    flags = _apportioned_plot_flags(plot_path, crosswalk_path)
    areas: dict[str, dict] = {}
    for zone, metres in central.items():
        if zone not in r20 or zone not in r40 or zone not in flags:
            continue
        areas[zone] = {
            "a_m2": metres,
            "a_r20": r20[zone],
            "a_r40": r40[zone],
            "low_parcel_coverage": flags[zone]["low_parcel_coverage"],
            "other_land_share": flags[zone]["other_land_share"],
        }
    if not areas:
        raise HedonicRowError("plot split produced no DZ2011 areas")
    return areas


def _load_merge(path: Path) -> dict[str, dict]:
    raw = _csv_maps(path, "dz2011", ("cell_final", "ur6", "itl3", "ca2019"))
    return {
        zone: {"cell": row["cell_final"], "ur6": row["ur6"], "itl3": row["itl3"], "ca2019": row["ca2019"]}
        for zone, row in raw.items()
    }


def _load_epc(path: Path) -> dict[str, dict]:
    fields = tuple(
        source for source, _target in BUILT_FORM_SOURCES
    ) + ("pt_flat_share", "pt_maisonette_share", "coverage_share", "share_lodged_last_10y")
    for sources in AGE_BAND_SOURCES.values():
        fields = fields + sources
    return _csv_maps(path, "code", fields)


def _load_sold_tfa(path: Path) -> dict[tuple[str, int], dict]:
    """Keep fit and holdout years. A 2024 row is skipped and its cells are not used."""
    out: dict[tuple[str, int], dict] = {}
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        header = next(reader, None)
        if not header:
            raise HedonicRowError(f"{path.name} is empty")
        index = {name: position for position, name in enumerate(header)}
        for needed in ("zone", "year", "sold_tfa_mean"):
            if needed not in index:
                raise HedonicRowError(f"{path.name} missing {needed}")
        year_i = index["year"]
        zone_i = index["zone"]
        floor_i = index["sold_tfa_mean"]
        imputed_i = index.get("f_imputed")
        for record in reader:
            if year_i >= len(record) or not str(record[year_i]).strip():
                continue
            year = int(record[year_i])
            if year >= 2024 or year not in KEPT_YEARS:
                continue
            zone = str(record[zone_i]).strip()
            imputed = 0
            if imputed_i is not None and imputed_i < len(record) and str(record[imputed_i]).strip():
                imputed = int(float(record[imputed_i]))
            out[(zone, year)] = {"f_m2": float(record[floor_i]), "f_imputed": imputed}
    return out


def _load_bedrooms(path: Path) -> dict[str, dict]:
    return _csv_maps(path, "zone", ("share_1", "share_3", "share_4plus"))


def _load_access(path: Path) -> dict[str, dict]:
    return _csv_maps(path, "zone", ("log_job_access",))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    for name in PINNED_SHA256:
        parser.add_argument(f"--{name.replace('_', '-')}", type=Path, default=None, dest=name)
    args = parser.parse_args(argv)
    paths = {name: getattr(args, name) for name in PINNED_SHA256}
    try:
        assert_pinned(paths)
        sales = read_house_sales(paths["house_sales"])
        rows = build_v14_hedonic_rows(
            sales=sales,
            areas=_weighted_areas(paths["plot_split_csv"], paths["crosswalk"]),
            epc=_load_epc(paths["epc_rollup"]),
            merge=_load_merge(paths["merge_map"]),
            sold_tfa=_load_sold_tfa(paths["sold_tfa"]),
            bedrooms=_load_bedrooms(paths["bedrooms"]),
            access=_load_access(paths["job_access"]),
        )
    except (HedonicRowError, OSError, ValueError, KeyError) as exc:
        sys.stderr.write(str(exc) + "\n")
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
    sys.stdout.write(f"wrote {args.out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
