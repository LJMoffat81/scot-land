# RoS INSPIRE cadastral ingest

Registers of Scotland publishes **INSPIRE Index Polygons** (cadastral parcel
extents) as open data. Scot-LAND loads them into PostGIS and serves them as a
first-class map / API layer.

## Licence and attribution

| Field | Value |
|-------|--------|
| Product | INSPIRE Index Polygons (`CP.CadastralParcel`) |
| Authority | Registers of Scotland |
| Licence | **OGL-3.0** (Open Government Licence v3.0) — cite RoS |
| Attribution | © Crown copyright. Reproduced with the permission of Registers of Scotland. Contains OS data © Crown copyright and database right. |
| Catalogue | https://www.ros.gov.uk/open-data |
| Download | https://ros.locationcentre.co.uk/inspire/ |
| Live view | WMS `https://ros-inspire.themapcloud.com/maps/wms` (layer `CP.CadastralParcel`) |

Committed registry: `data/config/sources.yaml` → `parcels`.

Laurie's ruling (Oct 2026): RoS grants Index Polygons under OGL v3. The 2017 OS
INSPIRE end-user licence linked from RoS's dataset guide is an RoS error.

## Refresh steps (production extract)

1. Download the open Index Polygons extract from the RoS location-centre page
   (or export a council subset for a pilot). **Do not commit** the raw file.
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

- Loaded data in viewport → GeoJSON FeatureCollection (`meta.ok=true`)
- Loaded data, empty viewport → **HTTP 200** empty FeatureCollection (honest gap)
- Missing / empty table → **HTTP 503** (never placeholder parcels)

Map **tiles** still proxy the live RoS WMS for display when a local ingest is
absent; the bbox endpoint is the authoritative “data loaded” contract for the
Georgist / valuation stack.

## CI / local fixture (synthetic only)

National extracts are large and stay out of git. CI loads a tiny synthetic
fixture that must not be shown as real RoS titles:

```bash
cd backend
export DATABASE_URL=postgresql://…
python -m etl.ingest_inspire_parcels --fixture --replace
```

This sets `inspire_parcels_meta.load_scope=fixture`. Outside the fixture bbox
the API returns an empty FeatureCollection with `meta.fixture_scoped=true` and
an explicit gap note — not 503, and not invented parcels.

Fixture path: `backend/tests/fixtures/cadastral_index_polygons.geojson`.

## Known gaps

- Sasine titles without Land Register polygons
- Private owner names are not in the open INSPIRE product
- Index polygons are registered extents, not a ScotLIS title sheet
- Full national extracts are large — keep them in `data/external/` only
