# NatureScot SSSI and designations ingest

NatureScot publishes protected-area boundaries under the **Open Government
Licence v3.0**. Scot-LAND loads them into PostGIS and serves viewport GeoJSON.

## Licence and attribution

| Field | Value |
|-------|--------|
| Authority | NatureScot |
| Licence | OGL-3.0 |
| Attribution | Contains NatureScot information licensed under the Open Government Licence v3.0 |
| Open Data Hub | https://opendata.nature.scot/ |
| WFS | https://ogc.nature.scot/geoserver/protectedareas/wfs |

Committed registry: `data/config/sources.yaml` → `naturescot_sssi` and
`naturescot_designations`.

## Layers

| Catalog id | Table | Product | Download |
|------------|-------|---------|----------|
| `sssi` | `naturescot_sssi` | Sites of Special Scientific Interest | https://gis-downloads.nature.scot/SSSI_SCOTLAND_GEOJSON_4326.zip |
| `naturescot_designations` | `naturescot_designations` | SPA, SAC, NNR | SPA / SAC / NNR GeoJSON zips on gis-downloads.nature.scot |

BBox APIs:

- `GET /layers/open/sssi` → **503** when PostGIS table empty
- `GET /layers/open/naturescot-designations` → **503** when PostGIS table empty

## Refresh steps

1. Download the OGL GeoJSON zips from NatureScot (or export a council subset).
   **Do not commit** the raw files.
2. Unpack under `data/external/naturescot/` (gitignored), e.g.:

```text
data/external/naturescot/
  sssi.geojson
  spa.geojson
  sac.geojson
  nnr.geojson
```

3. Load into PostGIS:

```bash
cd backend
export DATABASE_URL=postgresql://user:pass@localhost:5432/scotland_wealth
alembic upgrade head
python -m etl.ingest_naturescot --layer all --replace --vintage YYYY-MM-DD
```

4. Confirm the API:

```bash
curl -s "http://127.0.0.1:8000/layers/open/sssi?south=55.8&west=-4.3&north=55.9&east=-4.2" | head
curl -s "http://127.0.0.1:8000/layers/open/naturescot-designations?south=55.8&west=-4.3&north=55.9&east=-4.2" | head
```

- Loaded data → GeoJSON FeatureCollection  
- Missing / empty table → **HTTP 503** (never placeholder designations)

## Known gaps

- Indicative NatureScot boundaries — not a ScotLIS title sheet  
- SSSI is separate from the SPA / SAC / NNR designations overlay  
- Full national extracts are large — keep them in `data/external/` only  
