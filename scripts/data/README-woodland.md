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

## Load into PostGIS

Raw national extracts stay under `data/external/woodland/` (gitignored).

```bash
cd backend
export DATABASE_URL=postgresql://...
alembic upgrade head

# Smoke / CI-sized fixture (committed under data/fixtures/gis/)
python -m etl.ingest_woodland_layers --layer nfi --fixture --replace
python -m etl.ingest_woodland_layers --layer native_woodland --fixture --replace

# Full local extract (download via WFS or Forestry Commission open data, then):
python -m etl.ingest_woodland_layers --layer nfi \
  --input ../data/external/woodland/nfi_woodland.geojson --replace
python -m etl.ingest_woodland_layers --layer native_woodland \
  --input ../data/external/woodland/native_woodland.geojson --replace
```

Empty tables → API **503** (honest gap). Never invent woodland polygons.

## Attribution (public UI)

- NFI: © Forestry Commission copyright. Contains Ordnance Survey data © Crown copyright and database right 2026. Open Government Licence v3.0.
- NWSS: Native Woodland Survey of Scotland. © Scottish Forestry / Forestry Commission. Open Government Licence v3.0.
