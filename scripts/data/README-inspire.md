# RoS INSPIRE cadastral ingest

Registers of Scotland publishes **INSPIRE Index Polygons** (cadastral parcel
extents) as open data. Scot-LAND serves them as a first-class map layer.

## Licence and attribution

| Field | Value |
|-------|--------|
| Product | INSPIRE Index Polygons (`CP.CadastralParcel`) |
| Authority | Registers of Scotland |
| Licence | Open Government Licence / INSPIRE (Crown) |
| Attribution | © Crown copyright. Reproduced with the permission of Registers of Scotland. Contains OS data © Crown copyright and database right. |
| Source | https://www.ros.gov.uk/open-data |
| Live view | WMS `https://ros-inspire.themapcloud.com/maps/wms` (layer `CP.CadastralParcel`) |

Committed registry: `data/config/sources.yaml` → `parcels`.

## Refresh steps

1. Download the open Index Polygons extract from RoS open data (or export a
   council subset for a pilot). **Do not commit** the raw file.
2. Place GeoJSON under `data/external/inspire/` (gitignored), e.g.
   `data/external/inspire/index_polygons.geojson`.
3. Load into PostGIS:

```bash
cd backend
export DATABASE_URL=postgresql://user:pass@localhost:5432/scotland_wealth
python -m etl.ingest_inspire_parcels \
  --input ../data/external/inspire/index_polygons.geojson \
  --vintage YYYY-MM-DD \
  --replace
```

4. Confirm the API:

```bash
curl -s "http://127.0.0.1:8000/layers/parcels?south=55.8&west=-4.3&north=55.9&east=-4.2" | head
```

- Loaded data → GeoJSON FeatureCollection  
- Missing / empty table → **HTTP 503** (never placeholder parcels)

Map **tiles** still proxy the live RoS WMS for display when a local ingest is
absent; the bbox endpoint is the authoritative “data loaded” contract.

## Known gaps

- Sasine titles without Land Register polygons  
- Private owner names are not in the open INSPIRE product  
- Index polygons are registered extents, not a ScotLIS title sheet  
- Full national extracts are large — keep them in `data/external/` only
