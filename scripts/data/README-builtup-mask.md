# Built-up display mask (UX10-2)

Display-only layer for the map: **never changes any Annual Ground Rent or other
figure**. Colour banding clipped to this mask is UX10-3 (not this PR).

## Tables

| PostGIS table | Contents |
|---------------|----------|
| `map_builtup_mask` | National built-up extent (Polygon parts, EPSG:4326) |
| `dz2022_masked` | DZ2022 ∩ mask — one row per address zone (`code` PK) |

Acceptance (full national load): **7,392** masked DZ2022 codes, 1:1 with the
spine; **100%** UPRN coverage per `scripts/data/builtup-mask/qa_builtup_mask.json`.

## Visitor attribution

`NRS Settlements 2022 (OGL v3), contains OS data`

## Where the large files live

Do **not** commit the ~50–75 MB `.4326.geojson` / `.gpkg` blobs. Mount or copy
them at runtime:

| Path / env | Role |
|------------|------|
| `BUILTUP_MASK_DIR` | Preferred absolute directory containing the delivery files |
| `DATA_DIR/external/builtup/` | Default under the repo `data/` tree (gitignored) |
| Agent Store `mask-ux10-2/` | Build output + `SHA256SUMS` (verify before load) |

Required delivery filenames:

- `map_builtup_mask.4326.geojson` (API CRS)
- `dz2022_masked.4326.geojson`
- Optional: matching `.gpkg` (EPSG:27700 source), `qa_builtup_mask.json`, `SHA256SUMS`

Small committed copies of README / QA / build script live under
`scripts/data/builtup-mask/`.

## Load into PostGIS

```bash
cd backend
export DATABASE_URL=postgresql://user:pass@localhost:5432/scotland_wealth
alembic upgrade head

# Full national delivery (after mounting the Agent Store / artifact dir):
export BUILTUP_MASK_DIR=/path/to/mask-ux10-2
python -m etl.ingest_builtup_mask --replace --assert-full-qa

# CI / local smoke (tiny fixture):
python -m etl.ingest_builtup_mask --fixture --replace
```

Verify checksums before a full load:

```bash
cd "$BUILTUP_MASK_DIR" && sha256sum -c SHA256SUMS
```

## API

| Endpoint | Behaviour |
|----------|-----------|
| `GET /layers/open/builtup-mask?...` | BBox GeoJSON; **503** if unloaded |
| `GET /layers/open/dz2022-masked?...` | BBox GeoJSON for masked DZ2022; **503** if unloaded |
| `GET /layers/open/builtup-mask/tiles/{z}/{x}/{y}` | MVT (`map_builtup_mask`) |
| `GET /layers/open/dz2022-masked/tiles/{z}/{x}/{y}` | MVT (`dz2022_masked`) |

MapLibre uses the vector-tile endpoints; faint full Data Zone outlines remain
the clickable layer. No parcel polygons.

## Registry

`data/config/sources.yaml` → `map_builtup_mask`
