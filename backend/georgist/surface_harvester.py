"""Load surface-rent inputs into tidy frames, each stamped with licence and vintage.

Sources (confirmed 2026-10-06; see surface_rent_spec.md section 0):
- RoS Residential Properties Sales and Price, long CSV, 2004-2023, DZ2011 (OGL v3)
- NRS dwelling estimates by data zone (DZ2011 2005-2025; DZ2022 2024-2025) (OGL)
- SG Urban Rural Classification 2022, DZ2022 lookup (OGL)
- UK House Price Index full file (HM Land Registry / RoS / ONS, OGL v3), monthly,
  Scotland council areas (S12), all dwellings and by property type

The loaders do no modelling. A suppressed RoS cell has no Median/Mean row.
The loaders keep it as NaN with `suppressed = True`, never 0.
Nothing here downloads; pass local paths (see georgist.surface_paths: env var or gitignored surface.local.yaml).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from georgist.surface_zones import validate_codes, vintage_int

ROS_URL = "https://api.data.gov.scot/resource/3d9a31a5-4b62-436a-a537-7d9bbeba1723/download"
ROS_SHA256 = "702c9ada0b26dad9904e97f00ea7aa3357e1bf449e724e83292b5265f0549cf2"
NRS_DZ2011_URL = "https://www.nrscotland.gov.uk/media/fqword2k/dwellings-estimate-by-2011-data-zones.xlsx"
NRS_DZ2022_URL = "https://www.nrscotland.gov.uk/media/43tfx3zo/dwelling-estimates-by-2022-data-zones-24-25.xlsx"
URC2020_DZ2011_URL = (
    "https://www.gov.scot/binaries/content/documents/govscot/publications/advice-and-guidance/2022/05/"
    "scottish-government-urban-rural-classification-2020/documents/"
    "scottish-government-urban-rural-classification-2020-data-zone-2011-lookup/"
    "scottish-government-urban-rural-classification-2020-data-zone-2011-lookup/govscot%3Adocument/"
    "scottish-government-urban-rural-classification-2020-data-zone-2011-lookup.csv"
)
URC2020_DZ2011_SHA256 = "0440de97902c393c2568780505901251dab9426f0781069fb9c6a3a383f04851"
UKHPI_URL = "https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/UK-HPI-full-file-2026-07.csv"
UKHPI_PAGE = "https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads-july-2026"
UKHPI_SHA256 = "654a541934ba7b393a741e23bc0c6fb668690f562feb8a7b4fff62d653fd6607"
URC_URL = (
    "https://www.gov.scot/publications/scottish-government-urban-rural-classification-2022/"
    "documents/scottish-government-urban-rural-classification-2022---data-zone-2022-lookup/"
)

GEOGRAPHY_VINTAGE = {
    "2011 Data Zones": 2011,
    "2011 Intermediate Zones": "IZ2011",
    "Council Areas": "CA2019",
}


@dataclass(frozen=True)
class SourceStamp:
    source_id: str
    url: str
    licence: str
    vintage: str
    sha256: str
    loaded_at: str
    synthetic: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _stamp(df: pd.DataFrame, stamp: SourceStamp) -> pd.DataFrame:
    df.attrs["provenance"] = stamp.to_dict()
    df["source_id"] = stamp.source_id
    df["licence"] = stamp.licence
    df["source_vintage"] = stamp.vintage  # provenance text; the data column is `vintage`
    return df


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- RoS

_MEASURES = {
    "Count": "sales_n",
    "Mean": "price_mean_gbp",
    "Median": "price_median_gbp",
    "Lower Quartile": "price_lq_gbp",
    "Upper Quartile": "price_uq_gbp",
}


def load_ros_sales(
    path: Path | str,
    *,
    geography_types: tuple[str, ...] = ("2011 Data Zones", "2011 Intermediate Zones", "Council Areas"),
    expected_sha256: str | None = ROS_SHA256,
    licence: str = "OGL-3.0",
    synthetic: bool = False,
) -> pd.DataFrame:
    """RoS long CSV -> one row per (code, year) with count, mean, median, quartiles.

    `suppressed` is True when a Count row exists but no Median row (RoS blanks n<5),
    or when the zone-year is absent entirely for a zone present in other years.
    """
    path = Path(path)
    digest = sha256_file(path)
    if expected_sha256 is not None and digest != expected_sha256:
        raise ValueError(f"RoS file sha256 {digest} does not match pinned {expected_sha256}")
    raw = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    need = {"GeographyCode", "GeographyType", "DateCode", "Measurement", "Value"}
    if not need <= set(raw.columns):
        raise ValueError(f"RoS CSV missing columns {need - set(raw.columns)}")
    raw = raw[raw["GeographyType"].isin(geography_types) & raw["Measurement"].isin(_MEASURES)]
    raw = raw.assign(
        year=pd.to_numeric(raw["DateCode"], errors="coerce").astype("Int64"),
        value=pd.to_numeric(raw["Value"].str.strip(), errors="coerce"),
        measure=raw["Measurement"].map(_MEASURES),
    )
    tidy = (
        raw.pivot_table(
            index=["GeographyCode", "GeographyType", "year"],
            columns="measure",
            values="value",
            aggfunc="first",
        )
        .reset_index()
        .rename(columns={"GeographyCode": "code", "GeographyType": "geography_type"})
    )
    tidy.columns.name = None
    for col in _MEASURES.values():
        if col not in tidy:
            tidy[col] = pd.NA
    # Complete the zone x year grid so an absent row is explicit, not silently dropped.
    years = sorted(tidy["year"].dropna().unique())
    zones = tidy[["code", "geography_type"]].drop_duplicates()
    grid = zones.merge(pd.DataFrame({"year": years}), how="cross")
    tidy = grid.merge(tidy, on=["code", "geography_type", "year"], how="left")
    tidy["suppressed"] = tidy["price_median_gbp"].isna()
    tidy["sales_n"] = tidy["sales_n"].astype("Int64")
    tidy["vintage"] = tidy["geography_type"].map(GEOGRAPHY_VINTAGE).fillna("other")
    tidy = tidy.sort_values(["geography_type", "code", "year"]).reset_index(drop=True)
    stamp = SourceStamp(
        source_id="ros_residential_sales_price",
        url=ROS_URL,
        licence=licence,
        vintage="DZ2011; years %s-%s" % (int(min(years)), int(max(years))) if years else "DZ2011",
        sha256=digest,
        loaded_at=_now(),
        synthetic=synthetic,
    )
    return _stamp(tidy, stamp)


# --------------------------------------------------------------------------- NRS

def _norm(col: object) -> str:
    text = re.sub(r"\s+", " ", str(col)).strip().lower()
    text = text.replace("council tax band: ", "ct_").replace("type of dwelling: ", "type_")
    text = text.replace("number of rooms in dwelling: ", "rooms_")
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


_NRS_RENAME = {
    "data_zone_code": "code",
    "data_zone_name": "zone_name",
    "council_area_code": "council_code",
    "council_area_name": "council_name",
    "total_number_of_dwellings": "dwellings",
    "dwellings_per_hectare": "dwellings_per_ha",  # density driver (rule 4), not a rent basis
    "type_semidetached": "type_semi_detached",
    "rooms_7": "rooms_7plus",
}


def _find_header(path: Path, sheet: str) -> int:
    probe = pd.read_excel(path, sheet_name=sheet, header=None, nrows=15)
    for i, row in probe.iterrows():
        if any(str(v).strip() == "Data Zone code" for v in row.values):
            return int(i)
    raise ValueError(f"no 'Data Zone code' header in sheet {sheet}")


def load_nrs_dwellings(
    path: Path | str,
    *,
    year: int,
    vintage: str,
    url: str | None = None,
    licence: str = "OGL-3.0",
    synthetic: bool = False,
) -> pd.DataFrame:
    """One NRS year sheet -> code, council, dwellings, CT A-H, and type/rooms when published."""
    vintage = vintage_int(vintage)
    path = Path(path)
    sheet = str(year)
    header = _find_header(path, sheet)
    df = pd.read_excel(path, sheet_name=sheet, header=header, dtype=str)
    df.columns = [_NRS_RENAME.get(_norm(c), _norm(c)) for c in df.columns]
    df = df[df["code"].astype(str).str.match(r"^S01\d{6}$", na=False)].copy()
    numeric = [c for c in df.columns if c not in ("code", "zone_name", "council_code", "council_name")]
    for c in numeric:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["has_type_rooms"] = any(c.startswith("type_") for c in df.columns)
    df["data_year"] = year
    df["vintage"] = vintage
    stamp = SourceStamp(
        source_id=f"nrs_dwellings_dz{vintage}",
        url=url or (NRS_DZ2011_URL if vintage == 2011 else NRS_DZ2022_URL),
        licence=licence,
        vintage=f"DZ{vintage}; year {year} sheet",
        sha256=sha256_file(path),
        loaded_at=_now(),
        synthetic=synthetic,
    )
    return _stamp(df.reset_index(drop=True), stamp)


# --------------------------------------------------------------------------- URC

def load_urban_rural_lookup(
    path: Path | str,
    *,
    licence: str = "OGL-3.0",
    synthetic: bool = False,
) -> pd.DataFrame:
    """SGUR 2022 DZ2022 lookup -> code, ur2..ur8 codes and names. UR8 is display only."""
    path = Path(path)
    try:
        df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    except UnicodeDecodeError:  # the published file is cp1252 (non-breaking spaces in names)
        df = pd.read_csv(path, dtype=str, encoding="cp1252")
    need = {"DZ22_Code", "UR6_Code", "UR8_Code"}
    if not need <= set(df.columns):
        raise ValueError(f"URC lookup missing {need - set(df.columns)}")
    out = pd.DataFrame({"code": df["DZ22_Code"].str.strip()})
    for n in (2, 3, 6, 8):
        if f"UR{n}_Code" in df:
            out[f"ur{n}_class"] = pd.to_numeric(df[f"UR{n}_Code"], errors="coerce").astype("Int64")
            out[f"ur{n}_name"] = df.get(f"UR{n}_Name")
    bad = out["ur6_class"].dropna()
    if not bad.between(1, 6).all():
        raise ValueError("UR6 codes outside 1-6")
    out["vintage"] = 2022
    validate_codes(out["code"], 2022)
    out["assignment"] = "population_weighted_centroid"
    stamp = SourceStamp(
        source_id="sg_urban_rural_2022_dz2022",
        url=URC_URL,
        licence=licence,
        vintage="SGUR2022 on DZ2022",
        sha256=sha256_file(path),
        loaded_at=_now(),
        synthetic=synthetic,
    )
    return _stamp(out, stamp)


# --------------------------------------------------------------------------- UK HPI

_HPI_TYPES = {"all": "", "detached": "Detached", "semi_detached": "SemiDetached", "terraced": "Terraced", "flat": "Flat"}


def load_uk_hpi(
    path: Path | str,
    *,
    expected_sha256: str | None = UKHPI_SHA256,
    url: str = UKHPI_URL,
    licence: str = "OGL-3.0",
    synthetic: bool = False,
) -> pd.DataFrame:
    """UK HPI full file -> Scotland council-area (S12) monthly rows.

    Columns: council_code, council_name, date, index_<type>, price_<type> for
    type in all/detached/semi_detached/terraced/flat. Index is the non-seasonally
    adjusted UK HPI (Jan 2023 = 100 in the current file); price is the average price.
    """
    path = Path(path)
    sha = sha256_file(path)
    if expected_sha256 is not None and sha != expected_sha256:
        raise ValueError(f"UK HPI file sha256 {sha} != pinned {expected_sha256}")
    raw = pd.read_csv(path, dtype={"AreaCode": str})
    raw = raw[raw["AreaCode"].str.match(r"^S12\d{6}$", na=False)].copy()
    out = pd.DataFrame({
        "council_code": raw["AreaCode"],
        "council_name": raw["RegionName"],
        "date": pd.to_datetime(raw["Date"], dayfirst=True),
    })
    for t, prefix in _HPI_TYPES.items():
        out[f"index_{t}"] = pd.to_numeric(raw[f"{prefix}Index" if prefix else "Index"], errors="coerce")
        out[f"price_{t}"] = pd.to_numeric(raw[f"{prefix}Price" if prefix else "AveragePrice"], errors="coerce")
    stamp = SourceStamp("uk_hpi_full_file", url, licence, f"UK HPI to {out['date'].max():%Y-%m}; S12 council areas", sha, _now(), synthetic)
    return _stamp(out.sort_values(["council_code", "date"]).reset_index(drop=True), stamp)


def council_hpi_points(hpi: pd.DataFrame, *, base_year: int, target_month: str) -> dict:
    """{council_code: CouncilHPI}: base = mean of the 12 monthly values in base_year
    (matches the RoS calendar-year price); target = the single month `target_month`
    (YYYY-MM, matches the rebuild price base). Missing months raise."""
    from georgist.surface_rent import CouncilHPI

    target = pd.Timestamp(f"{target_month}-01")
    out = {}
    for code, g in hpi.groupby("council_code"):
        base = g[g["date"].dt.year == base_year]
        tgt = g[g["date"] == target]
        if len(base) != 12 or len(tgt) != 1:
            raise ValueError(f"{code}: need 12 months of {base_year} and {target_month}")
        types = list(_HPI_TYPES)
        out[code] = CouncilHPI(
            council_code=code,
            base_period=str(base_year),
            target_period=target_month,
            base_index={t: float(base[f"index_{t}"].mean()) for t in types if base[f"index_{t}"].notna().all()},
            target_index={t: float(tgt[f"index_{t}"].iloc[0]) for t in types if tgt[f"index_{t}"].notna().all()},
            base_price={t: float(base[f"price_{t}"].mean()) for t in types if base[f"price_{t}"].notna().all()},
        )
    return out


# --------------------------------------------------------------------------- SGUR 2020 on DZ2011

def load_urban_rural_2020_dz2011(
    path: Path | str, *, expected_sha256: str | None = URC2020_DZ2011_SHA256, licence: str = "OGL-3.0", synthetic: bool = False,
) -> pd.DataFrame:
    """SGUR 2020 Data Zone 2011 lookup -> code, ur2/ur3/ur6/ur8_class on DZ2011 (matches the price vintage)."""
    path = Path(path)
    sha = sha256_file(path)
    if expected_sha256 is not None and sha != expected_sha256:
        raise ValueError(f"SGUR 2020 DZ2011 lookup sha256 {sha} != pinned {expected_sha256}")
    df = pd.read_csv(path, dtype=str, encoding="utf-8-sig")
    need = {"DataZone", "UR6FOLD"}
    if not need <= set(df.columns):
        raise ValueError(f"SGUR 2020 lookup missing {need - set(df.columns)}")
    out = pd.DataFrame({"code": df["DataZone"].str.strip()})
    if not out["code"].str.match(r"^S01\d{6}$").all() or not out["code"].is_unique:
        raise ValueError("SGUR 2020 lookup: zone codes must be unique DZ2011 S01 codes")
    for n in (2, 3, 6, 8):
        if f"UR{n}FOLD" in df:
            out[f"ur{n}_class"] = pd.to_numeric(df[f"UR{n}FOLD"], errors="raise").astype(int)
    if not out["ur6_class"].between(1, 6).all():
        raise ValueError("UR6 codes outside 1-6")
    out["vintage"] = 2011
    validate_codes(out["code"], 2011)
    stamp = SourceStamp("sg_urban_rural_2020_dz2011", URC2020_DZ2011_URL, licence, "SGUR2020 on DZ2011 (population-weighted centroids)",
                        sha, _now(), synthetic)
    return _stamp(out, stamp)


# --------------------------------------------------------------------------- GIS EPC rollup

FLAG_COLUMNS = ("flags", "dwellings_flag", "method_flags")


def read_flagged_csv(path) -> pd.DataFrame:
    """read_csv with flag columns read via converters=str, so empty cells are '' (never NaN or float)."""
    head = pd.read_csv(path, nrows=0).columns
    conv = {c: str for c in FLAG_COLUMNS if c in head}
    return pd.read_csv(path, dtype={c: str for c in ("code", "brma_id") if c in head}, converters=conv)


def load_gis_checked(path: Path | str, *, sha_prefix: str | None, publish_level: str | None = None) -> pd.DataFrame:
    """load_gis_output plus an expected sha256 prefix and, if given, the manifest publish_level."""
    path = Path(path)
    if sha_prefix and not sha256_file(path).startswith(sha_prefix):
        raise ValueError(f"{path.name} sha256 does not start {sha_prefix}")
    df = load_gis_output(path)
    if publish_level:
        man = pd.read_csv(path.parent / "manifest.csv", dtype=str).set_index("file")
        got = str(man.loc[path.name, "publish_level"]).strip().lower()
        if got != publish_level:
            raise ValueError(f"{path.name} publish_level {got!r} != {publish_level!r}")
    return df


ZONE_SPINE_SHA_PREFIX = "a11cf5b5"   # Data Zones staged zone_spine.csv checked 2026-10-06


def load_zone_spine(path: Path | str | None = None, *, expected_sha_prefix: str | None = ZONE_SPINE_SHA_PREFIX) -> pd.DataFrame | None:
    """Data Zones `zone_spine.csv`, verified against the Data Zones manifest (sha, rows, key) and, if given,
    the expected sha prefix. Flags read with converters={'flags': str}. Returns None when the file is
    missing (callers then use the tested zero-dwelling fallback codes)."""
    path = Path(path) if path else Path(DATAZONES_DIR) / "zone_spine.csv"
    if not path.exists():
        return None
    if expected_sha_prefix and not sha256_file(path).startswith(expected_sha_prefix):
        raise ValueError(f"zone_spine sha256 does not start {expected_sha_prefix}")
    return load_gis_output(path)


def load_gis_output(
    path: Path | str, *, manifest_path: Path | str | None = None, vintage: str | None = None, manifest_name: str | None = None,
) -> pd.DataFrame:
    """Load a GIS output file and verify it against GIS manifest.csv (sha256, rows, key, licence, vintages).

    `vintage` filters to one zone vintage AFTER verification (rules 2: never mix vintages).
    """
    path = Path(path)
    manifest_path = Path(manifest_path) if manifest_path else path.parent / "manifest.csv"
    man = pd.read_csv(manifest_path, dtype=str).set_index("file")
    name = manifest_name or path.name
    if name not in man.index:
        raise ValueError(f"{name} not in {manifest_path}")
    entry = man.loc[name]
    sha = sha256_file(path)
    if sha != entry["sha256"]:
        raise ValueError(f"{path.name} sha256 {sha} != manifest {entry['sha256']}")
    df = read_flagged_csv(path)
    if len(df) != int(entry["rows"]):
        raise ValueError(f"{path.name} has {len(df)} rows, manifest says {entry['rows']}")
    key = [k.strip() for k in str(entry["key"]).strip("()").split(",")]
    if key[:2] != ["code", "vintage"] or not set(key) <= set(df.columns) or df.duplicated(key).any():
        raise ValueError(f"GIS key {entry['key']} must start (code, vintage), exist and be unique")
    df["vintage"] = df["vintage"].map(vintage_int)  # 2011 | 2022 integers (Data Zones convention)
    if set(df["vintage"]) - {vintage_int(v) for v in str(entry["zone_vintage"]).split(";") if v.strip()}:
        raise ValueError("vintages in file not declared in manifest")
    for v in set(df["vintage"]):
        validate_codes(df.loc[df["vintage"] == v, "code"].astype(str), v)
    if df["code"].isna().any() or (df["code"].astype(str).str.lower() == "unknown").any():
        raise ValueError("GIS file has missing/'unknown' zone codes")
    df.attrs["provenance"] = {"source_id": f"gis_{path.stem}", "url": str(path), "licence": entry["licence"],
                              "vintage": entry["zone_vintage"], "sha256": sha, "rows": int(entry["rows"]),
                              "publish_level": entry["publish_level"], "source": entry["source"]}
    if vintage is not None:
        vintage = vintage_int(vintage)
        df = df[df["vintage"] == vintage].reset_index(drop=True)
        df.attrs["provenance"] = dict(df.attrs.get("provenance", {}), vintage_used=vintage)
    return df


# --------------------------------------------------------------------------- dwelling counts (pluggable)
# Rules 6.4 (v0.5): surface totals use TOTAL dwellings (council-tax list, incl.
# vacant and second homes), never households. Every loader returns the same
# frame: code, vintage, count_year, dwellings_total, occupied, vacant,
# second_homes, vacant_share, second_home_share, source_id (+ provenance attrs).

NRS_HH_DZ2011_URL = "https://www.nrscotland.gov.uk/publications/small-area-statistics-on-households-and-dwellings-2025/"
NRS_HH_DZ2011_SHA256 = "4061bbba01790a7e25dfb1598ad46d47116ae911a91b7a3e708a9c8ba1ba4fe6"  # = GIS raw/household-estimates-by-2011-data-zones.xlsx
DWELLING_FRAME = ("code", "vintage", "count_year", "dwellings_total", "occupied", "vacant", "second_homes",
                  "vacant_share", "second_home_share", "source_id")


def _finish_dwellings(df: pd.DataFrame, stamp: SourceStamp) -> pd.DataFrame:
    for c in ("occupied", "vacant", "second_homes"):
        if c not in df:
            df[c] = pd.NA
    tot = pd.to_numeric(df["dwellings_total"], errors="coerce")
    df["vacant_share"] = pd.to_numeric(df["vacant"], errors="coerce") / tot.where(tot > 0)
    df["second_home_share"] = pd.to_numeric(df["second_homes"], errors="coerce") / tot.where(tot > 0)
    df["source_id"] = stamp.source_id
    out = df[list(DWELLING_FRAME)].reset_index(drop=True)
    out.attrs["provenance"] = stamp.to_dict()
    return out


def _dw_nrs_dwelling_estimates(path, *, year: int, vintage, **kw) -> pd.DataFrame:
    """INTERIM: NRS 'Dwelling estimates by data zone'. Total dwellings on the council tax
    valuation list (cover sheet: includes second homes; vacant dwellings are on the list). No occupancy split."""
    df = load_nrs_dwellings(path, year=year, vintage=vintage, **kw)
    out = pd.DataFrame({"code": df["code"], "vintage": vintage_int(vintage), "count_year": year, "dwellings_total": df["dwellings"]})
    return _finish_dwellings(out, SourceStamp(**{**df.attrs["provenance"], "source_id": f"nrs_dwelling_estimates_dz{vintage_int(vintage)}"}))


def _dw_nrs_household_estimates(path, *, year: int, vintage: str, expected_sha256: str | None = NRS_HH_DZ2011_SHA256,
                                licence: str = "OGL-3.0", synthetic: bool = False) -> pd.DataFrame:
    """NRS 'Household estimates by data zone' (council-tax based, Sep-Aug year, 2014-2025):
    total dwellings, occupied, vacant, second homes."""
    path = Path(path)
    sha = sha256_file(path)
    if expected_sha256 is not None and sha != expected_sha256:
        raise ValueError(f"household estimates sha256 {sha} != pinned {expected_sha256}")
    header = _find_header(path, str(year))
    raw = pd.read_excel(path, sheet_name=str(year), header=header)
    cols: dict[str, object] = {}
    for c in raw.columns:  # counts come first; the later '(%)' columns normalise to the same names
        cols.setdefault(_norm(c), c)
    pick = lambda name: cols[name]  # noqa: E731
    out = pd.DataFrame({
        "code": raw[cols["data_zone_code"]].astype(str).str.strip(),
        "vintage": vintage_int(vintage), "count_year": year,
        "dwellings_total": pd.to_numeric(raw[pick("total_number_of_dwellings")], errors="coerce"),
        "occupied": pd.to_numeric(raw[pick("occupied_dwellings")], errors="coerce"),
        "vacant": pd.to_numeric(raw[pick("vacant_dwellings")], errors="coerce"),
        "second_homes": pd.to_numeric(raw[pick("second_homes")], errors="coerce"),
    })
    out = out[out["code"].str.match(r"^S01\d{6}$", na=False)]
    validate_codes(out["code"], vintage)
    stamp = SourceStamp(f"nrs_household_estimates_dz{vintage_int(vintage)}", NRS_HH_DZ2011_URL, licence,
                        f"DZ{vintage_int(vintage)}; {year} (Sep-Aug council tax year)", sha, _now(), synthetic)
    return _finish_dwellings(out, stamp)


from georgist.surface_paths import data_dir as _data_dir  # noqa: E402

DATAZONES_DIR = str(_data_dir("datazones"))  # env SCOT_LAND_DATAZONES_DIR, else surface.local.yaml, else repo default


def _dw_datazones_ct_table(path, *, year: int, vintage, licence: str | None = None, synthetic: bool = False,
                           manifest_path=None, verify_manifest: bool = True) -> pd.DataFrame:
    """Data Zones' canonical `dwellings_by_year` (council tax, September; DZ2011 2014-2025, DZ2022 2024-2025).

    Verified against Data Zones manifest.csv (sha256, rows, key (code, vintage, count_year),
    integer vintages, official code ranges) unless verify_manifest=False (synthetic tests).
    Uses `dwellings_total` (TOTAL dwellings incl. vacant and second homes) with
    occupied / vacant / second homes; `assessor_dwellings_dec` is reference only and
    never used. Rows are selected by count_year == price_year; a missing year gives
    no row (flagged downstream dwellings_missing_year), never another year. A file
    with households but no dwellings_total is refused.
    """
    path = Path(path)
    if verify_manifest:
        raw = load_gis_output(path, manifest_path=manifest_path)
        licence = licence or dict(raw.attrs.get("provenance", {})).get("licence", "OGL v3")
    else:
        raw = pd.read_csv(path, dtype={"code": str})
    if "count_year" not in raw.columns and "year" in raw.columns:
        raw = raw.rename(columns={"year": "count_year"})  # pre-rename CSVs; schema.sql column is count_year
    need = {"code", "vintage", "count_year", "dwellings_total"}
    if not need <= set(raw.columns):
        raise ValueError(f"Data Zones table missing {sorted(need - set(raw.columns))} (TOTAL dwellings, never households)")
    want = vintage_int(vintage)
    raw["vintage"] = raw["vintage"].map(vintage_int)
    raw = raw[(raw["vintage"] == want) & (raw["count_year"] == int(year))].copy()
    validate_codes(raw["code"], want)
    raw = raw.drop(columns=[c for c in ("assessor_dwellings_dec",) if c in raw.columns])  # reference only, never used
    stamp = SourceStamp("datazones_dwellings_by_year", str(path), licence or "pending",
                        f"DZ{want}; count_year {year} (council tax, September)", sha256_file(path), _now(), synthetic)
    return _finish_dwellings(raw, stamp)


DWELLING_SOURCES = {
    "nrs_dwelling_estimates": _dw_nrs_dwelling_estimates,      # interim totals
    "nrs_household_estimates": _dw_nrs_household_estimates,    # totals + vacant / second homes
    "datazones_ct_table": _dw_datazones_ct_table,              # canonical, when Data Zones delivers
}


def load_dwelling_counts(source: str, path, *, price_year: int, vintage: str, **kw) -> pd.DataFrame:
    """Pluggable dwelling-count loader (rules 6.4 v0.5: TOTAL dwellings, never households).

    Counts join on the row's price_year: the frame's count_year always equals
    `price_year`. Zones absent for that year are absent here and are flagged
    downstream; no other year is ever substituted.
    """
    if source not in DWELLING_SOURCES:
        raise ValueError(f"unknown dwelling source {source!r}; one of {sorted(DWELLING_SOURCES)}")
    out = DWELLING_SOURCES[source](path, year=int(price_year), vintage=vintage, **kw)
    if len(out) and set(out["count_year"].astype(int)) != {int(price_year)}:
        raise ValueError("dwelling count_year must equal price_year")
    return out
