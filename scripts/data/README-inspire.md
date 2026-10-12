# RoS INSPIRE cadastral ingest

Registers of Scotland publishes **INSPIRE Index Polygons** (cadastral parcel
extents) as open data. Scot-LAND **self-fetches** per-registration-county
shapefile zips and loads them into PostGIS.

## Licence and attribution

| Field | Value |
|-------|--------|
| Product | INSPIRE Index Polygons (`CP.CadastralParcel`) |
| Authority | Registers of Scotland |
| Licence | **OGL-3.0** (Open Government Licence v3.0) — cite RoS |
| Attribution | © Crown copyright. Reproduced with the permission of Registers of Scotland. Contains OS data © Crown copyright and database right. |
| Catalogue | https://www.ros.gov.uk/open-data |
| Download page (legacy) | https://ros.locationcentre.co.uk/inspire/ |
| Download service (current) | https://ros-inspire.themapcloud.com/ |
| Download API | `https://ros-inspire.themapcloud.com/maps/download/ros-cp.cadastralparcel/{CODE}` |
| Live view | WMS `https://ros-inspire.themapcloud.com/maps/wms` (layer `CP.CadastralParcel`) |

Committed registry: `data/config/sources.yaml` → `parcels`.
County codes: `backend/etl/inspire_counties.py` (33 registration counties).

Laurie's ruling (Oct 2026): RoS grants Index Polygons under OGL v3.

## One-command usage

From `backend/` with `DATABASE_URL` set. Downloads use a **temp directory** and
are deleted after load — **never** `data/external/`.

### Pilot — Edinburgh + Fife

Edinburgh titles sit in the RoS **Midlothian (MID)** registration county; Fife is **FFE**.

```bash
cd backend
export DATABASE_URL=postgresql://user:pass@localhost:5432/scotland_wealth
python -m etl.ingest_inspire_parcels --pilot --replace
```

### All 33 registration counties

```bash
cd backend
export DATABASE_URL=postgresql://user:pass@localhost:5432/scotland_wealth
python -m etl.ingest_inspire_parcels --all --replace
```

### CI synthetic fixture only

```bash
cd backend
export DATABASE_URL=postgresql://…
python -m etl.ingest_inspire_parcels --fixture --replace
```

Retries: each county download uses exponential backoff (default 5 attempts).

## Confirm the API

```bash
curl -s "http://127.0.0.1:8000/layers/parcels?south=55.8&west=-4.3&north=55.9&east=-4.2" | head
```

- Loaded data in viewport → GeoJSON FeatureCollection (`meta.ok=true`)
- Loaded data, empty viewport → **HTTP 200** empty FeatureCollection
- Missing / empty table → **HTTP 503** (never placeholder parcels)

Map **tiles** still proxy the live RoS WMS; the bbox endpoint is the
authoritative “data loaded” contract for the Georgist / valuation stack.

## Known gaps

- Sasine titles without Land Register polygons
- Private owner names are not in the open INSPIRE product
- Index polygons are registered extents, not a ScotLIS title sheet
- RoS publishes **33 registration counties**, not the 32 modern local authorities
- Edinburgh (City) → Midlothian (`MID`) in the RoS county list
