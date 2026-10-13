# Scottish Government Data Zone boundaries

Scottish Government publishes 2011 and 2022 Data Zone polygons under the
**Open Government Licence v3.0**. Scot-LAND loads them into PostGIS as the
Georgist / valuation zone frame (`dz_boundaries`, EPSG:27700).

## Catalogue

| Field | Value |
|-------|--------|
| Authority | Scottish Government |
| Products | `DataZoneBdry2011`, `DataZoneBdry2022` |
| Licence | OGL-3.0 |
| Attribution | © Scottish Government, contains OS data © Crown copyright and database right |
| 2011 ATOM | https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2011.zip |
| 2022 ATOM | https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneBdry_2022.zip |
| Expected counts | **6,976** (2011), **7,392** (2022) |
| Target CRS | EPSG:27700 |
| Committed registry | `data/config/sources.yaml` → `data_zone_boundaries` |

## Load into PostGIS

```bash
cd backend
export DATABASE_URL=postgresql://user:pass@localhost:5432/scotland_wealth
alembic upgrade head
python -m etl.ingest_dz_boundaries --fetch --replace
```

Self-fetch downloads to a temp directory only — **never** `data/external/`.
Each vintage records provenance in `dz_boundaries_meta` (URL, vintage, sha256,
row_count, licence). Wrong national counts or invalid codes fail the load.

CI / local smoke without the national zips:

```bash
python -m etl.ingest_dz_boundaries --fixture --replace
```

The fixture is synthetic (`backend/tests/fixtures/dz_boundaries_sample.geojson`)
and must never be labelled as real SG polygons. It covers Balfron so that
`GET /layers/context/data-zones/at?lat=56.0715&lon=-4.3375` returns `S01013010`.

## API

| Endpoint | Behaviour |
|----------|-----------|
| `GET /layers/open/data-zones?...` | BBox GeoJSON; **503** if `dz_boundaries` empty |
| `GET /layers/context/data-zones/at?lat=&lon=` | Containing zone(s) per loaded vintage |

No £ rent figures are stored or served by this ingest.
