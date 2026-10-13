# NRS Census 2022 Settlements and Localities

National Records of Scotland publishes settlement and locality polygons under
the **Open Government Licence v3.0**.

## Catalogue

| Field | Value |
|-------|--------|
| Authority | National Records of Scotland |
| Products | `CEN2022:Settlement2022`, `CEN2022:Locality2022` |
| Licence | OGL-3.0 |
| Attribution | Contains National Records of Scotland data © Crown copyright and database right. Contains Ordnance Survey data © Crown copyright and database right. |
| MapServer | https://maps.gov.scot/server/rest/services/NRS/Census2022/MapServer |
| WFS | https://maps.gov.scot/server/services/NRS/Census2022/MapServer/WFSServer |
| Settlements layer | MapServer id **8** (503 polygons) |
| Localities layer | MapServer id **6** (656 polygons) |
| Committed registry | `data/config/sources.yaml` → `nrs_settlements_localities` |

## Load into PostGIS

```bash
cd backend
export DATABASE_URL=postgresql://user:pass@localhost:5432/scotland_wealth
alembic upgrade head
python -m etl.ingest_nrs_settlements --fetch --replace
```

Optional offline files (gitignored):

```bash
python -m etl.ingest_nrs_settlements \
  --settlements ../data/external/nrs/settlements_2022.geojson \
  --localities ../data/external/nrs/localities_2022.geojson \
  --replace
```

## API

| Endpoint | Behaviour |
|----------|-----------|
| `GET /layers/open/settlements?...` | BBox GeoJSON; **503** if `nrs_settlements` empty |
| `GET /layers/open/localities?...` | BBox GeoJSON; **503** if `nrs_localities` empty |
| `GET /layers/open/settlements/at?lat=&lng=` | Containing settlement (or not found) |
| `GET /layers/open/localities/at?lat=&lng=` | Containing locality (or not found) |

Map context rasters continue to proxy the live MapServer export for display when
a local ingest is absent. The bbox endpoints are the authoritative “loaded”
contract for Georgist / valuation spatial joins.

## Known gaps

- Settlements are places of **500+** people only  
- Localities are built-up place geography, not ownership or title  
- Small rural clusters below the threshold are not drawn  
- Population counts are Census 2022 figures, not a land rent  
