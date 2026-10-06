# Processed data manifest (repo standard)

Adopted from Scot-LAND GIS, 2026-10-06 (draft). Every dataset folder under
`data/processed/<dataset>/` carries a `manifest.csv`. **Only files listed in a
manifest are loaded**; anything else in the folder (READMEs, QA JSON, stray
files) is ignored, and stray data files are logged as "not loaded".

Loader: `backend/etl/load_processed.py`

```bash
cd backend
python -m etl.load_processed --check          # validate every data/processed/*/manifest.csv, no DB
python -m etl.load_processed                  # validate, then load into PostGIS (DATABASE_URL)
python -m etl.load_processed --dataset gis    # one folder only
```

## Columns

| column | required | meaning | loader check |
|---|---|---|---|
| `file` | yes | Path relative to the dataset folder, `/`-separated; subfolders allowed (e.g. `alt/dz_brma_share_oa2022.csv`) | must exist inside the folder; no absolute paths or `..`; listed once |
| `owner` | yes | Owning agent/team (e.g. `gis`) | recorded |
| `source` | yes | Upstream sources and vintages, human readable | recorded (table comment + registry) |
| `licence` | yes | Licence, with restrictions (e.g. Royal Mail postcode terms) | must be non-empty |
| `attribution` | yes for `public_*` | The exact credit line a public view must show. **The API reads attribution only from this column** (`georgist/attribution.py`); READMEs are never scraped | non-empty for every `public_site`/`public_zone` file; a public endpoint whose dataset lacks it answers 503 `attribution_missing` |
| `publish_level` | yes | `public_site`, `public_zone` or `internal` (economic rules v0.4 section 2) | must be one of the three; `blocked` is a publication status, not a level |
| `zone_vintage` | yes | `;`-separated zone vintages present: `2011`, `2022` (the labels `DZ2011`/`DZ2022` are accepted here and normalised) | every row's `vintage` must be declared here |
| `key` | yes | Declared primary key, e.g. `(code, vintage)`, `(code, vintage, brma_id)` or, for a crosswalk, `(dz2011, dz2022)` | must be one of the key types below; every key column present and non-empty; the **full** key is unique (duplicates listed); becomes the table's PRIMARY KEY |
| `key_type` | no | `zone`, `crosswalk` or `vintage`. Optional: the key's leading columns already identify the type | when present, must agree with `key` |
| `geometry_level` | no | `zone` (default), `site`, `parcel`, `plot`, `uprn` or `building`: the geometry the file's rows describe | publication geometry rule (below); a key column such as `plot_id`, `parcel_id`, `uprn`, `toid` or `site_ref` must be declared with its level |
| `source_granularity` | no | `zone` (default) or `site`: the grain at which the upstream source itself is published | needed (`site`) for public site-level values |
| `site_source` | no | `svdls`, `hls` or `business_rates`: the site-public source behind site-level values | public site-level value columns need one of these |
| `source_year` | no | Reference year of the upstream source (e.g. BRES employment year for `dz_access.csv`). Empty is allowed | empty or a four-digit year; recorded in `processed.manifest_loads.source_year` and passed into API credits as `source_year` |
| `rows` | yes | Data rows (CSV lines excluding the header; GeoJSON features) | must equal the file's count |
| `sha256` | yes | SHA-256 of the file bytes, lower-case hex | must match; a mismatching file is not parsed |

### Key types

| key type | key starts with | checks |
|---|---|---|
| `zone` | `(code, vintage)` | every `code` is a data zone code in the NRS range for its `vintage` (DZ2011 S01006506–S01013481, DZ2022 S01013482–S01020873); every `vintage` is declared in `zone_vintage` |
| `crosswalk` | `(dz2011, dz2022)` | every `dz2011` is a valid 2011 code and every `dz2022` a valid 2022 code; `zone_vintage` must be `2011;2022`. Used by Data Zones' `dz_crosswalk_people` (one row per 2011→2022 pair; extra columns such as the people share are loaded as they are) |
| `vintage` | `(vintage, ...)` with no `code` | vintage-level tables such as Data Zones' `dwellings_by_year_coverage` |

**Vintage standard.** In data, `vintage` is the integer `2011` or `2022`, nothing else; text
such as `DZ2011` in a data row is rejected loudly. The API takes `?vintage=2011|2022` and
answers 422 `invalid_vintage` for anything else (including `DZ2011`). Code ranges live in
`georgist/dz_lookup.DZ_RANGES`; `backend/tests/etl/test_zone_rules_agree.py` keeps them equal to
GIS's `etl/gis/zone_rules.py` and Valuation's `surface_zones.CODE_RANGES`.

Any other key (e.g. `(vintage, code)`, `(dz2022, dz2011)`, `(code)`) is rejected.

Further checks:
CSV column names are lower_snake_case identifiers. **Extra columns are
tolerated** and loaded as they are (e.g. EPC `recent10_*`; mean floor area columns
are still to come), so GIS can add columns without a code change. Only the declared
key columns are required.

Any other manifest column is tolerated (logged, ignored) by the loader and by
`scripts/check_publishable.py`, so owners can add metadata columns without a code change.

## Failure behaviour

Validation runs over every manifest first. If **any** file fails, nothing is
loaded, every problem is printed, and the command exits 1. A valid run replaces
each target table inside one transaction, so a crash part-way leaves the
previous load intact.

## Where data lands

* CSV → `processed.<dataset>_<path with / as _>`, e.g. `processed.gis_dz_brma_share`,
  `processed.gis_alt_dz_brma_share_dwelling_bounds`. Column types are inferred
  (BIGINT / DOUBLE PRECISION / BOOLEAN / TEXT). The table comment carries the file, licence,
  publish_level and sha256.
* `dz2011_boundaries.geojson` / `dz2022_boundaries.geojson` (key `(code, vintage)`,
  single vintage) → `dz_boundaries` (EPSG:27700), used by
  `GET /layers/context/data-zones/at`. GeoJSON is RFC 7946 WGS84 unless it names
  EPSG:27700 in `crs`.
* **Typed owner schemas.** `datazones` loads into the owner's own typed tables
  (`backend/db/schema/004_datazones.sql`, vendored from Data Zones' `schema.sql` with only
  mechanical edits; `tests/etl/test_datazones_schema.py` fails on drift). The verified bytes
  are COPYed as they are, `zone_spine` first; the CSV header must equal the table's columns
  (compared case-folded, because the SIMD access file has mixed-case headers, which is logged).
  `flags` is COPYed with `FORCE_NOT_NULL`, so "no flags" stays `''`, never NULL.
* **Held files.** `HELD_FILES` in the loader lists manifest rows deliberately not validated or
  loaded while the owner corrects them (empty today). They are skipped with a warning.
* **Internal files.** Rows with `publish_level = internal` are never copied into this public
  repo (none today: GIS's `dz_detached_plot_bands.csv` became public_zone once RoS INSPIRE
  parcels were confirmed OGL v3). The loader skips them
  unless `--include-internal` is given (with `--root` pointing at the owner's folder), and then
  loads them into schema `processed_internal`, which no public endpoint reads.
* **Derived tables.** After `gis/dz_residential_land.csv` loads, the same transaction fills
  `dz_denominators` (display areas and the per-hectare confidence inputs).
* Provenance: `processed.manifest_loads` (dataset, file, table, owner, source,
  licence, attribution, publish_level, zone_vintage, key_type, key, rows, sha256, loaded_at).

`publish_level` is recorded, not enforced, at load time: nothing in `processed.*`
is served by the public API yet. Any endpoint that serves it must check the level.
The repo guard (`scripts/check_publishable.py`) takes each tracked file's publishability from
its manifest `publish_level` alone (no hard-coded file names), so a level change in the owner's
manifest is all it takes.

**Publication geometry rule at load time** (`georgist/publication_rules.check_manifest_entry`).
Modelled or proxy values and rents are zone-level only. A public file whose `geometry_level` is
`parcel`, `plot`, `uprn` or `building` may not carry value or rent columns (names containing
`rent`, `value`, `price`, `gbp`, `rv`, `valuation`, `rateable`); plain shapes and areas are fine.
A public `site` file with values needs `source_granularity = site` and a `site_source` that is
public at site level (SVDLS, HLS, published business rateable values). A `(code, vintage)` key
is zone geometry. Internal files are exempt: they load only into `processed_internal`, which no
public endpoint reads. Breaking the rule fails validation like any other problem.

New files need no code: a GIS file such as the planned `dz_access.csv` (keyed `(code, vintage)`)
is validated and loaded as soon as it is listed in GIS's manifest.

## Files in this repo

`data/processed/gis/` is a copy of GIS's `scotland-gis/data/processed/gis/`
(including `alt/`, and the SVDLS / HLS rollups `dz_svdls_rollup.csv`, `dz_hls_rollup.csv`).
`data/processed/datazones/` is a copy of Data Zones' staged folder; it is kept byte-exact
(`.gitattributes` `-text`: its `manifest.csv` has CRLF line ends). Re-copy a whole folder
together with its manifest. Never edit a file without updating its `rows`/`sha256`. Files
larger than 50 MB are not committed: add them to `.gitignore` and record them here. None are
that large today: the largest is `epc_dz_rollup.csv` at about 9.2 MB.

Owner build scripts live in `etl/datazones/` and `etl/gis/` (see `etl/README.md`); raw
downloads are never committed.

## What may be published (this repo is public)

`internal` files, `raw/` and `internal/` folders, Spatial Hub downloads, GeoPackage site
layers (e.g. GIS's `svdls_sites.gpkg`, `hls_sites.gpkg`), RoS INSPIRE-derived files and
anything with address, postcode or UPRN columns must never be tracked. `.gitignore` covers
them, and `scripts/check_publishable.py` enforces it (it reads every manifest and checks the
git index). Run it before committing, or install the hook once per clone:

```bash
git config core.hooksPath scripts/hooks      # or: ln -s ../../scripts/hooks/pre-commit .git/hooks/pre-commit
python3 scripts/check_publishable.py         # also run by CI
```

Note for owners: `dz_brma_share.csv` and the `alt/` rental-area tables use
`household_share` (household-weighted). Real dwelling-based shares are
`dwelling_share_lower` / `dwelling_share_upper` / `share_mid` (± `share_halfwidth`) in
`alt/*_dwelling_bounds.csv`.
