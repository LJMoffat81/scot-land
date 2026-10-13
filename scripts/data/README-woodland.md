# Woodland layers — NFI and Native Woodland Survey

Open land-use overlays for the public map. **Not a rent** and **not a title**.

| Layer | Catalogue | Licence | PostGIS table | API |
|-------|-----------|---------|---------------|-----|
| National Forest Inventory Woodland Scotland | [data.gov.uk NFI Scotland 2025](https://www.data.gov.uk/dataset/c50cddf4-cdf0-42fb-8ac1-eae0cb6ef5ad/national-forest-inventory-scotland-2025) | OGL v3.0 — © Forestry Commission; contains OS data © Crown copyright | `nfi_woodland` | `GET /layers/open/nfi` |
| Native Woodland Survey of Scotland | [data.gov.uk NWSS](https://www.data.gov.uk/dataset/da3f8548-a130-4a0d-8ddd-45019adcf1f3/native-woodland-survey-of-scotland-nwss) | OGL v3.0 — © Scottish Forestry / Forestry Commission | `native_woodland` | `GET /layers/open/native-woodland` |

OGC host (NatureScot Scottish Forestry workspace):

- WFS/WMS: `https://ogc.nature.scot/geoserver/scottishforestry/ows`
- Type names: `scottishforestry:National_Forest_Inventory_Woodland_Scotland`, `scottishforestry:Native_Woodland_Survey_of_Scotland`

Registry: `data/config/sources.yaml` → `nfi` and `native_woodland`.

## Load into PostGIS (repeatable)

Raw national extracts stay under `data/external/woodland/` (gitignored). Prefer the
writable download mount from `docker-compose.home.yml` (PR #57).

### One command — WFS conversion in the loader

Pages NatureScot WFS GeoJSON, keeps **polygon** parts from mixed geometries,
loads PostGIS. Optional `--save-fetch` writes the extract under `data/external/woodland/`.

```bash
cd backend
export DATABASE_URL=postgresql://...
alembic upgrade head

python -m etl.ingest_woodland_layers --layer nfi --from-wfs --replace --check-counts
python -m etl.ingest_woodland_layers --layer native_woodland --from-wfs --replace --check-counts
```

`--check-counts` accepts within ~0.1% of the #57 / WFS baseline:

| Layer | Expected rows |
|-------|---------------|
| NFI | 207,640 |
| Native Woodland Survey | 95,814 |

### Fixture / local GeoJSON

```bash
# Smoke / CI-sized fixture (committed under data/fixtures/gis/)
python -m etl.ingest_woodland_layers --layer nfi --fixture --replace
python -m etl.ingest_woodland_layers --layer native_woodland --fixture --replace

# Pre-saved extract
python -m etl.ingest_woodland_layers --layer nfi \
  --input ../data/external/woodland/nfi_woodland.geojson --replace
python -m etl.ingest_woodland_layers --layer native_woodland \
  --input ../data/external/woodland/native_woodland.geojson --replace
```

Empty tables → API **503** (honest gap). Never invent woodland polygons.

## Mintlify row counts

```bash
python scripts/data/regen_layer_guide_counts.py
```

## Attribution (public UI)

- NFI: © Forestry Commission copyright. Contains Ordnance Survey data © Crown copyright and database right 2026. Open Government Licence v3.0.
- NWSS: Native Woodland Survey of Scotland. © Scottish Forestry / Forestry Commission. Open Government Licence v3.0.
