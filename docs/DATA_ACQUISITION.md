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
- **Who Owns Scotland** (paid)  
- SEPA Flood Maps via viewer / MapServer / other web services — use the OGL download at https://www2.sepa.org.uk/flooddata only  
- Crofting Register **boundaries** or the personal **List of Individuals** — OGL lists (parishes / holdings / grazings) only  
- Crown Estate Scotland **onshore** lease themes — offshore lease themes only  
- Community ownership geometries other than **points** from the 2024 gov.scot publication  

Land Capability for Agriculture (Hutton) **is in scope** under the James Hutton Open Data Licence — catalog licence + attribution / share-alike; never label it as OGL.  


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
| Download page | https://ros.locationcentre.co.uk/inspire/ (legacy) |
| Download API | `https://ros-inspire.themapcloud.com/maps/download/ros-cp.cadastralparcel/{CODE}` |
| Live WMS | `https://ros-inspire.themapcloud.com/maps/wms` |
| BBox API | `GET /layers/parcels` → **503** when PostGIS table empty; empty viewport is **200** when loaded |
| ETL pilot | `python -m etl.ingest_inspire_parcels --pilot --replace` (Edinburgh/MID + Fife) |
| ETL all | `python -m etl.ingest_inspire_parcels --all --replace` (33 registration counties) |
| ETL CI | `python -m etl.ingest_inspire_parcels --fixture --replace` |
| CI fixture | `backend/tests/fixtures/cadastral_index_polygons.geojson` (`synthetic-test-only`) |
| Temp downloads | Self-fetch uses temp dirs only — **never** `data/external/` |
| Refresh | [scripts/data/README-inspire.md](../scripts/data/README-inspire.md) |

### Known gaps

- Sasine titles without Land Register polygons  
- Private owner names are not in the open product  
- Index polygons are registered extents, not a ScotLIS title sheet  

## Public land (SG 2024 overlay)

| Field | Value |
|-------|--------|
| Source | Scottish Public and Crown Estate Land 2024 FeatureServer (behind official dashboard) |
| Licence | unverified/not open — dashboard only; do **not** present as OGL-3.0 |
| Public map | **Hidden** until a verified OGL-licensed source is found |
| Source URL | https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897 |
| Bodies | Forestry and Land Scotland, NatureScot, Scottish Crown Estate, Scottish Water, Crofting Agricultural Holdings |
| BBox API | `GET /layers/open/public-land` exists for internal/research use; not toggled on the public map |
| Gaps | Local-authority land, Common Good, and bodies outside the five are not shown — never guessed |

Registry: `data/config/sources.yaml` → `parcels` and `public_land`.

## Hydropower sites + SEPA CAR (natural capital; no £)

| Field | Value |
|-------|--------|
| Hydro source | SEPA Hydropower Sites ATOM → WGS84 shapefile |
| Hydro licence | OGL-3.0 — https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ |
| Hydro source URL | https://www.data.gov.uk/dataset/5750f8e5-d51b-4e75-a8d6-403a0d1ded81/hydropower_sites |
| Hydro ingest | `python -m etl.ingest_hydro_sites` → PostGIS `hydro_sites` |
| Hydro API | `GET /layers/open/hydro` → **503** until ingested |
| Hydro tags | `commons_class=extractive`, `value_tier=proxy`, `publication_status=ok` |
| CAR source | Open/SEPA_Reference MapServer layers 194 (simple) + 195 (registration) |
| CAR licence | OGL-3.0 — confirmed on https://www.sepa.org.uk/environment/environmental-data/ |
| CAR licence URL | https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ |
| CAR ingest (one command) | `python -m etl.ingest_sepa_car` → PostGIS `sepa_car_licences` |
| CAR API | `GET /layers/open/sepa-car` → **503** until ingested; **PostGIS only** (never proxies MapServer) |
| CAR tags | `commons_class=extractive`, `value_tier=market`, `publication_status=ok` |
| Gaps | No £ rent on either overlay; separate from surface rent; hydro ≠ full CAR register |

Registry: `data/config/sources.yaml` → `hydro_sites` and `sepa_car`. Do not commit raw downloads under `data/external`.

## Common Good (linked registers; no national open map)

| Field | Value |
|-------|--------|
| Status | Linked — not a live national overlay |
| Config | `data/config/common_good.yaml` |
| API | `GET /api/common-good.json` |
| Spatial | No national open polygon layer. Fife publishes indicative Common Good Titles (OS INSPIRE EUL) — metadata linked only; FeatureServer TLS was expired when checked 2026-10-12 and is **not** proxied |
| Gaps | Most councils publish PDF/XLSX registers; Spatial Hub assets need login; on-point Common Good is never invented |

Do not scrape Spatial Hub. Do not commit raw downloads under `data/external`.

## Local Development Plan allocations (LDP)

| Field | Value |
|-------|--------|
| Product | Local Development Plans — Scotland (Spatial Hub amalgamated pack) + authority OGL FeatureServers |
| Licence | OGL v3.0 |
| Spatial Hub | https://data.spatialhub.scot/dataset/local_development_plans-is |
| SpatialData.gov.scot metadata | https://spatialdata.gov.scot/geonetwork/srv/api/records/8e13ad58-41f2-4308-a3a8-5ffe8593e731 |
| Example OGL seed | Highland Council LDP Allocations FeatureServer (UK OGL v3.0) |
| PostGIS table | `ldp_allocations` |
| Ingest | `python -m etl.ingest_ldp_allocations --from-config` (or `--input` GeoJSON under `data/external/ldp/`) |
| BBox API | `GET /layers/open/ldp` → **503** when table empty / PostGIS down |
| Coverage meta | `GET /api/ldp.json` |
| Gaps | **Fragmented** national pack (per-authority ZIP or portal link). **City of Edinburgh unavailable**. Portal-only authorities not mirrored until an OGL download/FeatureServer is ingested. Planning extents, not a title — review with adopted LDP + NPF4 |

Registry: `data/config/sources.yaml` → `ldp_allocations`. Never commit raw Spatial Hub ZIPs under `data/external`.

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

## Housing land audit / supply (HLA)

| Field | Value |
|-------|--------|
| Product | Spatial Hub *Housing Land Supply – Scotland* (local-authority Housing Land Audit amalgamation) |
| Licence | OGL v3.0 (`uk-ogl`) |
| Attribution | © Improvement Service / Scottish Government; local planning authority HLA data under OGL |
| Spatial Hub | https://data.spatialhub.scot/dataset/housing_land_supply-is |
| Metadata | https://spatialdata.gov.scot/geonetwork/srv/api/records/911d7102-d5bc-4de9-bbfd-6e0abd429d01 |
| BBox API | `GET /layers/open/hla` → **503** when PostGIS has no `planning_sites` rows with `source='hla'` |
| PostGIS | `planning_sites` (`source='hla'`, EPSG:27700) via `python -m etl.ingest_hla_sites` |
| Raw dir | `data/external/spatialhub/hls/` (gitignored — never commit) |

**Honest access notes**

- Spatial Hub lists the open product under OGL, but anonymous WFS from this host returns **403** (same GeoServer gate as other Spatial Hub WFS endpoints).
- The national SG ArcGIS FeatureServer *Housing Land Supply (Scotland)* is **PSGA / Digimap restricted** — not used here.
- Glasgow City Region publishes an OGL FeatureServer extract — regional only; not used as a national substitute.
- Operators download the OGL open product from Spatial Hub, convert to WGS84 GeoJSON if needed, and ingest locally:

```powershell
cd backend
# After placing pub_hls.geojson under data/external/spatialhub/hls/
python -m etl.ingest_hla_sites --input ../data/external/spatialhub/hls/pub_hls.geojson --replace
```

Registry: `data/config/sources.yaml` → `hla`.

<<<<<<< HEAD
## SEPA Flood Maps (OGL)

| Field | Value |
|-------|--------|
| Product | SEPA Flood Maps v3.0 — medium-likelihood river + coastal (present day) |
| Licence | OGL v3.0 |
| Attribution | © SEPA 2025; see SEPA flood map attribution statements |
| Download | https://www2.sepa.org.uk/flooddata/ (**only** ingest source — never MapServer/viewer) |
| Licence URL | https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ |
| BBox API | `GET /layers/open/flood` (PostGIS when ingested; **503** when unloaded) |
| Ingest | `python -m etl.ingest_sepa_flood --input ../data/external/sepa/...geojson --replace` |

Registry: `data/config/sources.yaml` → `flood`. Raw geodatabases stay under gitignored `data/external/sepa/`.
=======
## NatureScot SSSI and designations (OGL-3.0)

| Field | Value |
|-------|--------|
| Products | SSSI; SPA; SAC; NNR |
| Licence | OGL-3.0 |
| Attribution | Contains NatureScot information licensed under the Open Government Licence v3.0 |
| Open Data Hub | https://opendata.nature.scot/ |
| SSSI page | https://opendata.nature.scot/maps/sites-of-special-scientific-interest |
| Downloads | `https://gis-downloads.nature.scot/{SSSI,SPA,SAC,NNR}_SCOTLAND_GEOJSON_4326.zip` |
| WFS | https://ogc.nature.scot/geoserver/protectedareas/wfs |
| BBox APIs | `GET /layers/open/sssi`, `GET /layers/open/naturescot-designations` → **503** when PostGIS unloaded |
| Ingest | `python -m etl.ingest_naturescot` |
| Raw storage | `data/external/naturescot/` (gitignored) |
| Gaps | Indicative boundaries (not a title); SSSI is a separate catalog layer from SPA/SAC/NNR |

Registry: `data/config/sources.yaml` → `naturescot_sssi` and `naturescot_designations`. Refresh: [scripts/data/README-naturescot.md](../scripts/data/README-naturescot.md).
>>>>>>> b0abba5 (Add NatureScot SSSI and designations layers (OGL-3.0))

## Local layout after acquisition

```text
data/licensed/
  LICENSE.txt                 # terms summary + contact
  ros_glasgow_sales_2024.parquet   # example — not in git
  provenance.json             # source, date, row count, hash

# Cadastre: prefer self-fetch (temp dir only — never required under data/external/)
#   python -m etl.ingest_inspire_parcels --pilot --replace
#   python -m etl.ingest_inspire_parcels --all --replace
```

Load sales via:

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
