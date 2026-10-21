"""Load manifest-listed processed datasets into PostGIS. Rejects loudly; never guesses.

Repo standard (adopted from Scot-LAND GIS): every dataset folder under
data/processed/<dataset>/ carries a manifest.csv; ONLY files listed there are
loaded. See docs/processed_data_manifest.md for the column contract.

Per listed file, before anything is written:
  * the file exists inside the dataset folder (no '..', no absolute paths);
  * SHA-256 of the bytes equals `sha256`;
  * data-row count equals `rows`;
  * `licence` is non-empty and `publish_level` is public_site|public_zone|internal;
  * `attribution` (manifest column) is the credit text public views must show; it is
    REQUIRED (non-empty) for every public_site / public_zone file. Public API metadata
    reads it from the manifest (georgist.attribution);
  * `key` is declared and is one of three KEY TYPES (optional manifest column
    `key_type` must agree when present):
      - zone       key starts with (code, vintage); every (code, vintage) is a real
                   data zone code in its vintage's NRS range, and the vintage is one
                   of those declared in `zone_vintage`;
      - crosswalk  key starts with (dz2011, dz2022) (e.g. Data Zones'
                   dz_crosswalk_people); every dz2011 is a valid 2011 code, every
                   dz2022 a valid 2022 code, and zone_vintage declares both vintages;
      - vintage    key starts with (vintage) and has no code (per-vintage metadata,
                   e.g. Data Zones' dwellings_by_year_coverage (vintage, count_year)).
    Any other key is rejected. Every key column exists and is non-empty, and the
    FULL declared key is unique (duplicates are listed).
  * VINTAGE STANDARD (Data Zones owns zone identity): every value in a `vintage`
    column is the integer 2011 or 2022. Text such as 'DZ2011' is REJECTED with the
    offending values listed, never mapped: a silent no-match join is the failure this
    prevents. (The manifest's own `zone_vintage` declaration is metadata and may be
    written 2011;2022 or DZ2011;DZ2022; it is normalised to integers.)
Extra columns are tolerated (loaded as-is); key columns are required.

Publication geometry rule (georgist.publication_rules): optional manifest columns
`geometry_level` (zone|site|parcel|plot|uprn|building, default zone),
`source_granularity` (zone|site, default zone) and `site_source` (svdls|hls|business_rates).
A public file on parcel/plot/UPRN/building geometry may not carry value or rent columns;
a public site-level file with values needs source_granularity site and a site-public
site_source; a (code, vintage)-keyed file is zone geometry. Internal files are exempt
(they load only into processed_internal and are never served).

Datasets whose owner publishes a typed schema (TYPED_SCHEMAS: datazones -> the
vendored backend/db/schema/004_datazones.sql) load into `<schema>.<file stem>` by
COPYing the verified file bytes; the CSV header must equal the table's columns in
order, so owner/consumer drift fails loudly.

If ANY file in ANY manifest fails, nothing is loaded and the command exits 1
with every problem listed. Valid runs replace each target table in one
transaction and record provenance in processed.manifest_loads.

    python -m etl.load_processed                 # all data/processed/*/manifest.csv
    python -m etl.load_processed --dataset gis   # one folder
    python -m etl.load_processed --check         # validate only, no DB needed

Other CSV files load into schema `processed`, table `<dataset>_<path with / -> _>`
(e.g. processed.gis_alt_dz_brma_share_oa2022). dz2011_/dz2022_boundaries.geojson
load into the public `dz_boundaries` table used by the zone lookup.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from georgist.dz_lookup import BOUNDARY_FILES, VINTAGES, vintage_for_code  # noqa: E402
from georgist.publication_rules import check_manifest_entry  # noqa: E402
from georgist.wealth_schema import PUBLIC_LEVELS, PUBLISH_LEVELS  # noqa: E402
from paths import PROCESSED_DIR  # noqa: E402

logger = logging.getLogger("etl.load_processed")

MANIFEST_COLUMNS = ("file", "owner", "source", "licence", "publish_level", "zone_vintage", "key", "rows", "sha256")
# Optional columns the loader reads; any other column is tolerated and ignored (logged).
OPTIONAL_MANIFEST_COLUMNS = ("attribution", "key_type", "geometry_level", "source_granularity", "site_source",
                             "source_year")
ZONE_VINTAGES = VINTAGES  # (2011, 2022): integers only
KEY_PREFIX = ("code", "vintage")
CROSSWALK_PREFIX = ("dz2011", "dz2022")
VINTAGE_PREFIX = ("vintage",)
KEY_TYPES = {"zone": KEY_PREFIX, "crosswalk": CROSSWALK_PREFIX, "vintage": VINTAGE_PREFIX}
# Datasets whose owner's typed schema is vendored under backend/db/schema/ (dataset -> PG schema).
TYPED_SCHEMAS = {"datazones": "datazones"}
# Text columns where '' means "none" and must not become NULL (owner README: COPY with
# FORCE_NOT_NULL). Data Zones `flags` is a ';'-separated string, '' = no flags.
FORCE_NOT_NULL_COLUMNS = ("flags",)
# Within a typed dataset, parent tables load first (foreign keys reference them).
TYPED_LOAD_FIRST = {"datazones": ("zone_spine",)}
# Manifest-listed files deliberately NOT loaded yet (owner correcting them). Skipped with a
# warning, never validated or loaded; the file need not be present. Add an entry to hold one.
HELD_FILES: dict[tuple[str, str], str] = {
    # Scotland clip extent (SCOTLAND-CLIP-1a): shapes only, not a DZ boundary table.
    # Validated by spatial.scotland_clip / pin P4; never loaded into PostGIS.
    ("gis", "scotland_extent.27700.geojson"): (
        "Scotland extent for pipeline clip; not a zone boundary GeoJSON"
    ),
}
# publish_level=internal files (e.g. GIS's dz_detached_plot_bands.csv) are never in the public
# repo. They are skipped unless --include-internal, and then load into INTERNAL_SCHEMA, which
# no public endpoint reads.
INTERNAL_SCHEMA = "processed_internal"
_MANIFEST_VINTAGE = {"2011": 2011, "2022": 2022, "DZ2011": 2011, "DZ2022": 2022}
IDENT_RE = re.compile(r"^[a-z_][a-z0-9_]{0,62}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
SUPPORTED = (".csv", ".geojson")
BOUNDARY_TARGETS = {name: vintage for vintage, name in BOUNDARY_FILES.items()}


class ManifestError(RuntimeError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__(f"{len(problems)} manifest problem(s):\n  - " + "\n  - ".join(problems))


@dataclass
class Entry:
    dataset: str
    root: Path
    file: str
    owner: str
    source: str
    licence: str
    publish_level: str
    zone_vintages: tuple[int, ...]
    attribution: str
    key: tuple[str, ...]
    key_type: str
    rows: int
    sha256: str
    problems: list[str] = field(default_factory=list)
    frame: Any = None  # pandas DataFrame (CSV) or list of boundary tuples (GeoJSON)
    # Publication geometry rule (optional manifest columns; default zone/zone).
    geometry_level: str = "zone"
    source_granularity: str = "zone"
    site_source: str = ""
    source_year: int | None = None  # optional manifest column; metadata only (empty allowed)

    @property
    def path(self) -> Path:
        return self.root / self.file

    @property
    def label(self) -> str:
        return f"{self.dataset}/{self.file}"

    @property
    def typed_schema(self) -> str | None:
        return TYPED_SCHEMAS.get(self.dataset) if self.path.suffix.lower() == ".csv" else None

    @property
    def table(self) -> str:
        if PurePosixPath(self.file).name in BOUNDARY_TARGETS:
            return "dz_boundaries"
        stem = str(PurePosixPath(self.file).with_suffix("")).replace("/", "_").lower()
        return stem if self.typed_schema else f"{self.dataset}_{stem}"

    @property
    def schema(self) -> str:
        if self.table == "dz_boundaries":
            return "public"
        if self.publish_level == "internal":
            return INTERNAL_SCHEMA
        return self.typed_schema or "processed"

    @property
    def qualified_table(self) -> str:
        return f"{self.schema}.{self.table}"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_key(raw: str) -> tuple[str, ...]:
    """'(code, vintage, brma_id)' -> ('code', 'vintage', 'brma_id')."""
    inner = (raw or "").strip()
    if inner.startswith("(") and inner.endswith(")"):
        inner = inner[1:-1]
    return tuple(p.strip().lower() for p in inner.split(",") if p.strip())


# --------------------------------------------------------------------------- manifest


def read_manifest(manifest: Path, include_internal: bool = False) -> list[Entry]:
    dataset = manifest.parent.name
    problems: list[str] = []
    text = manifest.read_text(encoding="utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    header = tuple(h.strip() for h in (reader.fieldnames or ()))
    missing = [c for c in MANIFEST_COLUMNS if c not in header]
    if missing:
        raise ManifestError([f"{manifest}: manifest lacks required column(s) {missing}"])
    unknown = [c for c in header if c and c not in MANIFEST_COLUMNS + OPTIONAL_MANIFEST_COLUMNS]
    if unknown:  # tolerated: owners may add columns without a code change
        logger.info("%s: extra manifest column(s) %s ignored", manifest, unknown)
    entries: list[Entry] = []
    seen: set[str] = set()
    for i, raw in enumerate(reader, start=2):
        row = {k.strip(): (v or "").strip() for k, v in raw.items() if k}
        where = f"{dataset}/manifest.csv line {i}"
        f = row["file"]
        p = PurePosixPath(f)
        if not f or p.is_absolute() or ".." in p.parts or "\\" in f:
            problems.append(f"{where}: bad file path {f!r}")
            continue
        if f in seen:
            problems.append(f"{where}: {f} listed twice")
            continue
        seen.add(f)
        if (dataset, f) in HELD_FILES:
            logger.warning("%s/%s: HELD, not validated or loaded: %s", dataset, f, HELD_FILES[(dataset, f)])
            continue
        if row["publish_level"] == "internal" and not include_internal:
            logger.info("%s/%s: internal, not validated or loaded (use --include-internal for the internal "
                        "schema %s)", dataset, f, INTERNAL_SCHEMA)
            SKIPPED_INTERNAL.add((dataset, f))
            continue
        try:
            n_rows = int(row["rows"])
        except ValueError:
            n_rows = -1
        declared_vintages = [v.strip() for v in row["zone_vintage"].split(";") if v.strip()]
        e = Entry(
            dataset=dataset, root=manifest.parent, file=f, owner=row["owner"], source=row["source"],
            licence=row["licence"], publish_level=row["publish_level"],
            attribution=row.get("attribution", ""),
            zone_vintages=tuple(_MANIFEST_VINTAGE[v] for v in declared_vintages if v in _MANIFEST_VINTAGE),
            key=parse_key(row["key"]), key_type="", rows=n_rows, sha256=row["sha256"].lower(),
            geometry_level=(row.get("geometry_level") or "zone").lower(),
            source_granularity=(row.get("source_granularity") or "zone").lower(),
            site_source=(row.get("site_source") or "").lower(),
        )
        raw_year = row.get("source_year", "")
        if raw_year:
            if re.fullmatch(r"\d{4}", raw_year) and 1900 <= int(raw_year) <= 2100:
                e.source_year = int(raw_year)
            else:
                e.problems.append(f"source_year {raw_year!r} must be empty or a four-digit year")
        inferred = next((t for t, prefix in KEY_TYPES.items() if e.key[:len(prefix)] == prefix), None)
        if inferred == "vintage" and "code" in e.key:
            inferred = None  # zone keys start (code, vintage); (vintage, code) is not a key type
        declared = row.get("key_type", "").strip().lower()
        if declared and declared not in KEY_TYPES:
            e.problems.append(f"key_type {declared!r} not in {sorted(KEY_TYPES)}")
        elif declared and declared != inferred:
            e.problems.append(f"key_type {declared!r} but key {row['key']!r} starts with {e.key[:2]}; "
                              f"{declared} keys start with {KEY_TYPES[declared]}")
        e.key_type = inferred or ""
        if n_rows < 0:
            e.problems.append(f"rows {row['rows']!r} is not a non-negative integer")
        if not e.licence:
            e.problems.append("licence is empty")
        if e.publish_level not in PUBLISH_LEVELS:
            e.problems.append(f"publish_level {e.publish_level!r} not in {PUBLISH_LEVELS}")
        elif e.publish_level in PUBLIC_LEVELS and not e.attribution:
            e.problems.append(f"attribution is required for {e.publish_level} files (manifest column "
                              "`attribution`, the credit text public views must show)")
        if not declared_vintages or any(v not in _MANIFEST_VINTAGE for v in declared_vintages):
            e.problems.append(f"zone_vintage {row['zone_vintage']!r} must be ';'-separated vintages 2011, 2022")
        if inferred is None:
            e.problems.append(f"key {row['key']!r} must start with (code, vintage), (dz2011, dz2022) "
                              "for a crosswalk, or (vintage) without code for per-vintage metadata")
        elif inferred == "crosswalk" and set(e.zone_vintages) != set(ZONE_VINTAGES):
            e.problems.append("crosswalk files must declare zone_vintage 2011;2022")
        if len(set(e.key)) != len(e.key) or any(not IDENT_RE.match(k) for k in e.key):
            e.problems.append(f"key {row['key']!r} has repeated or invalid column names")
        if not SHA_RE.match(e.sha256):
            e.problems.append("sha256 is not a 64-char hex digest")
        if p.suffix.lower() not in SUPPORTED:
            e.problems.append(f"unsupported file type {p.suffix!r} (supported: {SUPPORTED})")
        entries.append(e)
    if problems:
        raise ManifestError(problems)
    return entries


def discover(root: Path, dataset: str | None = None) -> list[Path]:
    pattern = f"{dataset}/manifest.csv" if dataset else "*/manifest.csv"
    return sorted(root.glob(pattern))


# --------------------------------------------------------------------------- file checks


def _integer_vintages(e: Entry, values) -> list[int] | None:
    """Every value must be exactly 2011 or 2022. Text labels ('DZ2011') are listed and rejected."""
    text = values.astype("string").str.strip()
    bad = sorted(set(text[~text.isin(["2011", "2022"])].dropna().tolist()))
    if bad:
        labels = [b for b in bad if b.upper().startswith("DZ")]
        e.problems.append(
            f"vintage must be the integer 2011 or 2022; found {len(bad)} other value(s) {bad[:5]}"
            + (" (text labels like 'DZ2011' are rejected, not mapped: Data Zones vintage standard)" if labels else "")
        )
        return None
    return [int(v) for v in text]


def _check_vintage_keys(e: Entry, vintages: list[int]) -> None:
    undeclared = sorted(set(vintages) - set(e.zone_vintages))
    if undeclared:
        e.problems.append(f"vintage values {undeclared} not declared in zone_vintage {e.zone_vintages}")


def _check_zone_keys(e: Entry, codes, vintages: list[int]) -> None:
    bad, wrong_vintage = [], set()
    for code, vin in zip(codes, vintages):
        if vin not in e.zone_vintages:
            wrong_vintage.add(vin)
        elif vintage_for_code(code) != vin:
            bad.append(f"{code}/{vin}")
    if wrong_vintage:
        e.problems.append(f"vintage values {sorted(map(str, wrong_vintage))} not declared in zone_vintage {e.zone_vintages}")
    if bad:
        e.problems.append(f"{len(bad)} code(s) not valid for their vintage, e.g. {bad[:5]}")


def _check_crosswalk_keys(e: Entry, dz2011, dz2022) -> None:
    for col, values, vintage in (("dz2011", dz2011, 2011), ("dz2022", dz2022, 2022)):
        bad = sorted({str(v) for v in values if vintage_for_code(str(v).strip()) != vintage})
        if bad:
            e.problems.append(f"{len(bad)} {col} value(s) are not valid {vintage} codes, e.g. {bad[:5]}")


def _check_csv(e: Entry) -> None:
    import pandas as pd

    df = pd.read_csv(e.path, dtype={k: "string" for k in (*e.key, "vintage")}, keep_default_na=True,
                     low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    if e.typed_schema:
        # The owner's typed schema uses unquoted identifiers, which PostgreSQL folds to lower case;
        # its CSV header is matched the same way (logged so the owner can tidy it).
        mixed = [c for c in df.columns if c != c.lower()]
        if mixed:
            logger.warning("%s: header has mixed-case column(s) %s; matched case-folded to the owner's schema",
                           e.label, mixed)
        df.columns = [c.lower() for c in df.columns]
    bad_cols = [c for c in df.columns if not IDENT_RE.match(c)]
    if bad_cols:
        e.problems.append(f"column names must be lower_snake_case identifiers: {bad_cols}")
    if len(set(df.columns)) != len(df.columns):
        e.problems.append("duplicate column names")
    if len(df) != e.rows:
        e.problems.append(f"row count {len(df)} != manifest rows {e.rows}")
    missing = [k for k in e.key if k not in df.columns]
    if missing:
        e.problems.append(f"declared key column(s) {missing} not in file")
        return
    nulls = {k: int(df[k].isna().sum() + (df[k].str.strip() == "").sum()) for k in e.key}
    nulls = {k: n for k, n in nulls.items() if n}
    if nulls:
        e.problems.append(f"empty key values: {nulls}")
        return
    dupes = df[df.duplicated(list(e.key), keep=False)]
    if len(dupes):
        sample = dupes[list(e.key)].drop_duplicates().head(5).to_dict("records")
        e.problems.append(f"{len(dupes)} rows duplicate the declared key {e.key}, e.g. {sample}")
    vintages = None
    if "vintage" in df.columns:
        vintages = _integer_vintages(e, df["vintage"])
        if vintages is None:
            return
        df["vintage"] = pd.array(vintages, dtype="Int16")
    if e.key_type == "crosswalk":
        _check_crosswalk_keys(e, df["dz2011"], df["dz2022"])
    elif e.key_type == "vintage":
        _check_vintage_keys(e, vintages)
    else:
        _check_zone_keys(e, df["code"], vintages)
    e.frame = df


def _check_geojson(e: Entry) -> None:
    import json

    name = PurePosixPath(e.file).name
    if name not in BOUNDARY_TARGETS:
        e.problems.append(f"GeoJSON is only loaded for {sorted(BOUNDARY_TARGETS)}; got {name}")
        return
    vintage = BOUNDARY_TARGETS[name]
    if e.zone_vintages != (vintage,):
        e.problems.append(f"{name} must declare zone_vintage {vintage}")
    if e.key != KEY_PREFIX:
        e.problems.append("boundary files must be keyed (code, vintage)")
        return
    n_features = len(json.loads(e.path.read_text(encoding="utf-8")).get("features", []))
    if n_features != e.rows:
        e.problems.append(f"feature count {n_features} != manifest rows {e.rows}")
    from georgist.dz_lookup import read_boundary_file

    rows = read_boundary_file(e.path, vintage)  # refuses (and logs) bad codes
    if len(rows) != n_features:
        e.problems.append(f"{n_features - len(rows)} feature(s) lack a valid {vintage} code")
    codes = [c for c, _, _ in rows]
    if len(set(codes)) != len(codes):
        e.problems.append("duplicate (code, vintage) in boundary file")
    e.frame = rows


def check_entry(e: Entry) -> Entry:
    if e.problems:
        return e
    if not e.path.is_file():
        e.problems.append("file listed in manifest but missing")
        return e
    actual = sha256_file(e.path)
    if actual != e.sha256:
        e.problems.append(f"sha256 mismatch: manifest {e.sha256[:12]}..., file {actual[:12]}...")
        return e  # do not parse a file whose bytes are not the ones described
    try:
        (_check_geojson if e.path.suffix.lower() == ".geojson" else _check_csv)(e)
    except Exception as exc:  # malformed file: reject, with the parser's reason
        e.problems.append(f"could not read: {type(exc).__name__}: {exc}")
    return e


SKIPPED_INTERNAL: set[tuple[str, str]] = set()


def validate(root: Path = PROCESSED_DIR, dataset: str | None = None, include_internal: bool = False) -> list[Entry]:
    """Every manifest-listed file, validated. Raises ManifestError listing ALL problems."""
    manifests = discover(root, dataset)
    if not manifests:
        raise ManifestError([f"no */manifest.csv under {root}" + (f" for dataset {dataset!r}" if dataset else "")])
    entries: list[Entry] = []
    problems: list[str] = []
    for m in manifests:
        try:
            entries += read_manifest(m, include_internal)
        except ManifestError as exc:
            problems += exc.problems
    for e in entries:
        check_entry(e)
        if not e.problems:  # publication geometry rule: no values on sub-zone geometry
            columns = list(getattr(e.frame, "columns", []))
            e.problems += check_manifest_entry(
                geometry_level=e.geometry_level, source_granularity=e.source_granularity,
                site_source=e.site_source, publish_level=e.publish_level, key=e.key, columns=columns)
        problems += [f"{e.label}: {p}" for p in e.problems]
    tables = [e.table for e in entries if e.table != "dz_boundaries"]
    clash = sorted({t for t in tables if tables.count(t) > 1})
    if clash:
        problems.append(f"files map to the same table name: {clash}")
    if problems:
        raise ManifestError(problems)
    for m in manifests:  # not an error, but say so: unlisted files are never loaded
        listed = ({e.file for e in entries if e.root == m.parent} | {"manifest.csv"}
                  | {f for d, f in HELD_FILES if d == m.parent.name}
                  | {f for d, f in SKIPPED_INTERNAL if d == m.parent.name})
        unlisted = sorted(str(p.relative_to(m.parent)) for p in m.parent.rglob("*")
                          if p.is_file() and p.suffix.lower() in SUPPORTED and str(p.relative_to(m.parent)) not in listed)
        if unlisted:
            logger.warning("%s: %d data file(s) not in manifest, NOT loaded: %s", m.parent.name, len(unlisted), unlisted)
    return entries


# --------------------------------------------------------------------------- load

REGISTRY_SQL = """
CREATE SCHEMA IF NOT EXISTS processed;
CREATE TABLE IF NOT EXISTS processed.manifest_loads (
  dataset        TEXT NOT NULL,
  file           TEXT NOT NULL,
  table_name     TEXT NOT NULL,
  owner          TEXT,
  source         TEXT,
  licence        TEXT NOT NULL,
  attribution    TEXT,
  publish_level  TEXT NOT NULL CHECK (publish_level IN ('public_site', 'public_zone', 'internal')),
  zone_vintage   SMALLINT[] NOT NULL,
  key_type       TEXT NOT NULL CHECK (key_type IN ('zone', 'crosswalk', 'vintage')),
  key_columns    TEXT[] NOT NULL,
  rows           INTEGER NOT NULL,
  sha256         TEXT NOT NULL,
  loaded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (dataset, file)
);
-- Registries created by earlier drafts: key_type column, the 'vintage' key type, integer vintages.
ALTER TABLE processed.manifest_loads ADD COLUMN IF NOT EXISTS key_type TEXT;
ALTER TABLE processed.manifest_loads ADD COLUMN IF NOT EXISTS attribution TEXT;
ALTER TABLE processed.manifest_loads ADD COLUMN IF NOT EXISTS source_year SMALLINT;
ALTER TABLE processed.manifest_loads DROP CONSTRAINT IF EXISTS manifest_loads_key_type_check;
ALTER TABLE processed.manifest_loads ADD CONSTRAINT manifest_loads_key_type_check
  CHECK (key_type IN ('zone', 'crosswalk', 'vintage'));
ALTER TABLE processed.manifest_loads ALTER COLUMN zone_vintage TYPE SMALLINT[]
  USING string_to_array(replace(array_to_string(zone_vintage, ','), 'DZ', ''), ',')::smallint[];
"""


def _pg_type(dtype, column: str = "") -> str:
    if column == "vintage":
        return "SMALLINT"
    if column in FORCE_NOT_NULL_COLUMNS:
        return "TEXT"  # ';'-separated flags: '' = no flags, never NULL
    kind = getattr(dtype, "kind", "O")
    return {"i": "BIGINT", "u": "BIGINT", "f": "DOUBLE PRECISION", "b": "BOOLEAN"}.get(kind, "TEXT")


def _load_csv(cur, e: Entry) -> None:
    from psycopg2 import sql

    df = e.frame
    cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(e.schema)))
    tbl = sql.Identifier(e.schema, e.table)
    cols = [sql.SQL("{} {}{}").format(sql.Identifier(c), sql.SQL(_pg_type(df[c].dtype, c)),
                                      sql.SQL(" NOT NULL") if c in e.key else sql.SQL(""))
            for c in df.columns]
    cur.execute(sql.SQL("DROP TABLE IF EXISTS {}").format(tbl))
    cur.execute(sql.SQL("CREATE TABLE {} ({}, PRIMARY KEY ({}))").format(
        tbl, sql.SQL(", ").join(cols), sql.SQL(", ").join(map(sql.Identifier, e.key))))
    cur.execute(sql.SQL("COMMENT ON TABLE {} IS %s").format(tbl),
                (f"{e.label} | licence: {e.licence} | attribution: {e.attribution} | publish_level: {e.publish_level} "
                 f"| sha256: {e.sha256}",))
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    buf.seek(0)
    keep = [c for c in df.columns if c in FORCE_NOT_NULL_COLUMNS]  # e.g. GIS dz_access `flags`: '' stays ''
    force = (sql.SQL(", FORCE_NOT_NULL ({})").format(sql.SQL(", ").join(map(sql.Identifier, keep)))
             if keep else sql.SQL(""))
    cur.copy_expert(sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, NULL ''{})").format(
        tbl, sql.SQL(", ").join(map(sql.Identifier, df.columns)), force).as_string(cur), buf)


def _typed_columns(cur, schema: str, table: str) -> list[str]:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s "
                "ORDER BY ordinal_position", (schema, table))
    return [r[0] for r in cur.fetchall()]


def _load_typed(cur, e: Entry) -> None:
    """COPY the verified file bytes into the owner's typed table (already truncated by load())."""
    from psycopg2 import sql

    data = e.path.read_bytes()
    if hashlib.sha256(data).hexdigest() != e.sha256:
        raise ManifestError([f"{e.label}: file changed after validation (sha256); nothing loaded"])
    header = next(csv.reader(io.StringIO(data.decode("utf-8-sig").split("\n", 1)[0])))
    header = [h.strip().lower() for h in header]  # unquoted identifiers fold to lower case (owner schema)
    table_cols = _typed_columns(cur, e.typed_schema, e.table)
    if not table_cols:
        raise ManifestError([f"{e.label}: no table {e.qualified_table} (owner schema not applied?); nothing loaded"])
    if header != table_cols:
        raise ManifestError([f"{e.label}: CSV columns {header} != {e.qualified_table} columns {table_cols} "
                             "(owner schema drift); nothing loaded"])
    tbl = sql.Identifier(e.typed_schema, e.table)
    keep = [c for c in header if c in FORCE_NOT_NULL_COLUMNS]
    force = (sql.SQL(", FORCE_NOT_NULL ({})").format(sql.SQL(", ").join(map(sql.Identifier, keep)))
             if keep else sql.SQL(""))
    cur.copy_expert(sql.SQL("COPY {} ({}) FROM STDIN WITH (FORMAT csv, HEADER true{})").format(
        tbl, sql.SQL(", ").join(map(sql.Identifier, header)), force).as_string(cur), io.BytesIO(data))
    cur.execute(sql.SQL("SELECT count(*) FROM {}").format(tbl))
    n = cur.fetchone()[0]
    if n != e.rows:
        raise ManifestError([f"{e.label}: {n} rows in {e.qualified_table} after COPY, manifest says {e.rows}"])
    cur.execute(sql.SQL("COMMENT ON TABLE {} IS %s").format(tbl),
                (f"{e.label} | licence: {e.licence} | attribution: {e.attribution} | publish_level: {e.publish_level} "
                 f"| sha256: {e.sha256}",))


def _load_order(e: Entry) -> int:
    return 0 if e.table in TYPED_LOAD_FIRST.get(e.dataset, ()) else 1


def _load_boundaries(cur, e: Entry) -> None:
    from shapely import wkb
    from shapely.geometry import MultiPolygon, Polygon

    vintage = BOUNDARY_TARGETS[PurePosixPath(e.file).name]
    cur.execute("DELETE FROM dz_boundaries WHERE vintage = %s", (vintage,))
    for code, name, geom in e.frame:
        if isinstance(geom, Polygon):
            geom = MultiPolygon([geom])
        cur.execute(
            "INSERT INTO dz_boundaries (code, vintage, name, geom, source_id, licence) "
            "VALUES (%s, %s, %s, ST_SetSRID(ST_GeomFromWKB(%s), 27700), %s, %s)",
            (code, vintage, name, wkb.dumps(geom), f"{e.label}@{e.sha256[:12]}", e.licence),
        )


def _derive_dz_denominators(cur, e: Entry) -> None:
    """GIS dz_residential_land -> dz_denominators (display areas + confidence inputs). Display only:
    residential area never enters surface money totals. 0 / blank areas become NULL (pending)."""
    from psycopg2 import sql

    src = sql.Identifier(e.schema, e.table)
    cur.execute(sql.SQL("""
        INSERT INTO dz_denominators (code, vintage, residential_land_ha, residential_land_source,
            settlement_area_ha, settlement_source, share_res_uprn_in_parcels, mask_too_big_parcel,
            res_uprn_exceeds_dwellings, residential_flags, source_id, licence, updated_at)
        SELECT code, vintage::smallint, NULLIF(residential_parcel_ha::numeric, 0), %s,
            NULLIF(settlement_ha::numeric, 0), %s, share_res_uprn_in_parcels::numeric,
            lower(NULLIF(mask_too_big_parcel::text, '')) = 'true',
            lower(NULLIF(res_uprn_exceeds_dwellings::text, '')) = 'true',
            method_flags::text, %s, %s, now()
        FROM {}
        ON CONFLICT (code, vintage) DO UPDATE SET
            residential_land_ha = EXCLUDED.residential_land_ha,
            residential_land_source = EXCLUDED.residential_land_source,
            settlement_area_ha = EXCLUDED.settlement_area_ha, settlement_source = EXCLUDED.settlement_source,
            share_res_uprn_in_parcels = EXCLUDED.share_res_uprn_in_parcels,
            mask_too_big_parcel = EXCLUDED.mask_too_big_parcel,
            res_uprn_exceeds_dwellings = EXCLUDED.res_uprn_exceeds_dwellings,
            residential_flags = EXCLUDED.residential_flags, source_id = EXCLUDED.source_id,
            licence = EXCLUDED.licence, updated_at = now()
    """).format(src), (f"{e.label}:residential_parcel_ha", f"{e.label}:settlement_ha", e.label, e.licence))


# Post-load steps: (dataset, file) -> function(cur, entry), run in the same transaction.
DERIVED = {("gis", "dz_residential_land.csv"): _derive_dz_denominators}


def load(conn, entries: list[Entry]) -> dict[str, int]:
    """All entries in ONE transaction: either everything loads or nothing does."""
    loaded: dict[str, int] = {}
    try:
        with conn.cursor() as cur:
            cur.execute(REGISTRY_SQL)
            from psycopg2 import sql

            typed = [e for e in entries if e.typed_schema]
            if typed:  # one TRUNCATE per run so foreign keys between the owner's tables hold
                cur.execute(sql.SQL("TRUNCATE {}").format(sql.SQL(", ").join(
                    sql.Identifier(e.typed_schema, e.table) for e in typed)))
            for e in sorted(entries, key=_load_order):
                if e.table == "dz_boundaries":
                    _load_boundaries(cur, e)
                elif e.typed_schema:
                    _load_typed(cur, e)
                else:
                    _load_csv(cur, e)
                derive = DERIVED.get((e.dataset, e.file))
                if derive:
                    derive(cur, e)
                cur.execute(
                    "INSERT INTO processed.manifest_loads (dataset, file, table_name, owner, source, licence, "
                    "attribution, publish_level, zone_vintage, key_type, key_columns, rows, sha256, source_year) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (dataset, file) DO UPDATE SET table_name = EXCLUDED.table_name, "
                    "owner = EXCLUDED.owner, source = EXCLUDED.source, licence = EXCLUDED.licence, "
                    "attribution = EXCLUDED.attribution, "
                    "publish_level = EXCLUDED.publish_level, zone_vintage = EXCLUDED.zone_vintage, "
                    "key_type = EXCLUDED.key_type, "
                    "key_columns = EXCLUDED.key_columns, rows = EXCLUDED.rows, sha256 = EXCLUDED.sha256, "
                    "source_year = EXCLUDED.source_year, loaded_at = now()",
                    (e.dataset, e.file, e.qualified_table, e.owner, e.source, e.licence, e.attribution or None,
                     e.publish_level,
                     list(e.zone_vintages), e.key_type, list(e.key), e.rows, e.sha256, e.source_year),
                )
                loaded[e.label] = e.rows
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return loaded


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=PROCESSED_DIR)
    ap.add_argument("--dataset", help="only data/processed/<dataset>/manifest.csv")
    ap.add_argument("--check", action="store_true", help="validate only; no database")
    ap.add_argument("--include-internal", action="store_true",
                    help=f"also validate/load publish_level=internal files (into schema {INTERNAL_SCHEMA}; "
                    "point --root at the owner's folder, internal files are never in the repo)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    try:
        entries = validate(args.root, args.dataset, args.include_internal)
    except ManifestError as exc:
        logger.error("REJECTED, nothing loaded. %s", exc)
        return 1
    for e in entries:
        logger.info("OK %s: %d rows, %s key %s, %s, licence %r -> %s", e.label, e.rows, e.key_type, e.key,
                    e.publish_level,
                    e.licence, e.qualified_table)
    if args.check:
        return 0
    from etl.migrate_to_postgis import apply_schema
    from georgist import db

    conn = db.connect()
    try:
        apply_schema(conn)
        loaded = load(conn, entries)
    finally:
        conn.close()
    logger.info("Loaded %d file(s), %d rows", len(loaded), sum(loaded.values()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
