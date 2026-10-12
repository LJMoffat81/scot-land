# Data acquisition plan — professional path

## Goal

Supply **completed residential (then all-tenure) sales** for Scotland so the AGR engine can move from aggregate HPI residual to **sales-informed residual / mass appraisal** (OpenAVMKit pilot).

## Primary source: Registers of Scotland

| Need | Action |
|------|--------|
| Residential sales for pilot | Contact ROS re research / open / commercial extract for **Glasgow City** or **Ward 18 area** |
| Fields | Price, completion/settlement date, property type, postcode or coordinates, title/UPRN if available, new-build flag if available |
| Cadastre | Live INSPIRE WMS tiles + local PostGIS ingest of Index Polygons (`python -m etl.ingest_inspire_parcels`); see `scripts/data/README-inspire.md` |
| Licence | Record in `data/licensed/LICENSE.txt` (local only) |

**Do not** substitute England & Wales Price Paid as “Scotland sales.”

## Secondary sources (aggregates — already in use)

| Source | Role |
|--------|------|
| UK House Price Index | Council-level average prices → current residual MV |
| postcodes.io | Geocoding |
| Boundaries.scot / open LAD geojson | Council / ward polygons |

## Explicitly out of scope

- Scraping Zoopla, Rightmove, ESPC, or similar  
- Purchasing scraped datasets of unknown provenance  

## If commercial portal data is ever considered

1. Written licence covering research + public education map  
2. Field dictionary + refresh schedule  
3. Store under `data/licensed/` only  
4. Independent QA against ROS sample  
5. SLRG sign-off before production use  

## Pilot acceptance criteria (Ward 18)

- [ ] ≥ N arms-length sales in window (e.g. 24–36 months) with usable locations  
- [ ] Load into `SalesStore` with full provenance  
- [ ] Residual vs sales-based land value comparison report  
- [ ] Decision: keep residual-only, blend, or pilot OpenAVMKit layer  

## Contact checklist (SLRG / project lead)

- [ ] ROS research data enquiry submitted  
- [ ] Licence terms reviewed  
- [ ] Storage + retention policy agreed  
- [ ] Public attribution wording agreed  

## Cadastre (RoS INSPIRE Index Polygons)

| Field | Value |
|-------|--------|
| Product | INSPIRE Index Polygons (`CP.CadastralParcel`) |
| Licence | **OGL-3.0** — cite Registers of Scotland (Laurie's ruling Oct 2026) |
| Attribution | © Crown copyright. Reproduced with the permission of Registers of Scotland |
| Source / catalogue | https://www.ros.gov.uk/open-data |
| Download | https://ros.locationcentre.co.uk/inspire/ |
| Live WMS | `https://ros-inspire.themapcloud.com/maps/wms` |
| BBox API | `GET /layers/parcels` → **503** when PostGIS table empty; empty viewport is **200** when loaded |
| ETL | `python -m etl.ingest_inspire_parcels` (PostGIS); CI: `--fixture` |
| CI fixture | `backend/tests/fixtures/cadastral_index_polygons.geojson` (`synthetic-test-only`) |
| Raw storage | `data/external/inspire/` (gitignored — never commit) |
| Refresh | [scripts/data/README-inspire.md](../scripts/data/README-inspire.md) |

### Known gaps

- Sasine titles without Land Register polygons  
- Private owner names are not in the open product  
- Index polygons are registered extents, not a ScotLIS title sheet  

## Public land (SG 2024 overlay)

| Field | Value |
|-------|--------|
| Source | Scottish Public and Crown Estate Land 2024 FeatureServer |
| Licence | OGL-3.0 |
| Source URL | https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897 |
| Bodies | Forestry and Land Scotland, NatureScot, Scottish Crown Estate, Scottish Water, Crofting Agricultural Holdings |
| BBox API | `GET /layers/open/public-land` → **503** when upstream unavailable |
| Gaps | Local-authority land, Common Good, and bodies outside the five are not shown — never guessed |

Registry: `data/config/sources.yaml` → `parcels` and `public_land`.

## Common Good (linked registers; no national open map)

| Field | Value |
|-------|--------|
| Status | Linked — not a live national overlay |
| Config | `data/config/common_good.yaml` |
| API | `GET /api/common-good.json` |
| Spatial | No national open polygon layer. Fife publishes indicative Common Good Titles (OS INSPIRE EUL) — metadata linked only; FeatureServer TLS was expired when checked 2026-10-12 and is **not** proxied |
| Gaps | Most councils publish PDF/XLSX registers; Spatial Hub assets need login; on-point Common Good is never invented |

Do not scrape Spatial Hub. Do not commit raw downloads under `data/external`.

## Vacant and derelict land (SVDLS)

| Field | Value |
|-------|--------|
| Product | Scottish Vacant and Derelict Land Survey — site-level as published |
| Licence | OGL v3.0 |
| Attribution | © Scottish Government; contains Improvement Service / local planning authority data under OGL |
| Site register | https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/ |
| Spatial Hub | https://data.spatialhub.scot/dataset/vacant_and_derelict_land-is |
| BBox API | `GET /layers/open/vdl` → **503** when upstream unavailable |
| Site types | Vacant Land; Vacant Land and Buildings; Derelict |
| Geometry precedence | **Spatial Hub survey > RoS title outline > point** — each site tagged `geometry_source` (`backend/layers/svdls_geometry.py`) |
| Live open overlay | Spatial Hub survey polygons only (`geometry_source=spatialhub_survey`) |
| Gaps | Owner class is a survey field (not title); Spatial Hub vintage may lag the SG register; RoS title outlines stay internal until OS/RoS end-user terms cleared |

Registry: `data/config/sources.yaml` → `vdl`. Zone-level rollups used by the Wealth Engine live under `data/processed/gis/` (see `README_svdls_hls.md`); the public map layer uses the live OGL FeatureServer, not gitignored `data/external`. GIS will review licences / CRS / zone alignment before merge of the map-layer PR.

## Local layout after acquisition

```text
data/licensed/
  LICENSE.txt                 # terms summary + contact
  ros_glasgow_sales_2024.parquet   # example — not in git
  provenance.json             # source, date, row count, hash

data/external/inspire/        # gitignored — RoS Index Polygons extract
  index_polygons.geojson
  index_polygons.geojson.ingest.json   # local vintage stamp
```

Load via:

```powershell
cd backend
# CSV from ROS/partner → JSONL
python -m etl.convert_sales_csv --input ../data/licensed/raw.csv --output ../data/licensed/sales.jsonl `
  --source ros --licence ROS-research `
  --map price=Price,date=Date,postcode=Postcode,lat=Lat,lng=Lng,floor_area=FloorArea

# Validate (must be production-eligible)
python -m etl.ingest_sales --path ../data/licensed/sales.jsonl --require-production
```

Enquiry template: [ROS_ENQUIRY.md](ROS_ENQUIRY.md).
