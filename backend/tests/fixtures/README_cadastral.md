# Cadastral fixtures (CI only)

Synthetic Index Polygon–shaped GeoJSON for PostGIS loader and `/layers/parcels` tests.

| Field | Value |
|-------|--------|
| File | `cadastral_index_polygons.geojson` |
| Licence | `synthetic-test-only` |
| Scope | Glasgow-ish bbox only (two tiny polygons) |
| Real product | RoS INSPIRE Index Polygons (OGL-3.0) — see `data/config/sources.yaml` → `parcels` |

**Never** present these features as real RoS titles in the UI. National extracts stay under gitignored `data/external/inspire/`.

```bash
cd backend
export DATABASE_URL=postgresql://…
python -m etl.ingest_inspire_parcels --fixture --replace
```
