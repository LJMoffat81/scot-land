# Data licensing policy

## Allowed

| Class | Examples | Use in product |
|-------|----------|----------------|
| Open Government Licence / free open data | UK HPI bulk CSVs, many ONS/boundary products, postcodes.io | Yes — cite source |
| Registers of Scotland open products | Whatever ROS publishes under open terms | Yes — cite + link |
| Licensed research/commercial extracts | ROS bulk sales, paid boundary packs | Yes — store under `data/licensed/`, **never commit secrets or full paid dumps to public git without permission** |
| What3Words API | Nonprofit/commercial key under their ToS | Yes — key in env only |

## Forbidden

| Class | Examples | Reason |
|-------|----------|--------|
| Website scraping | Zoopla, Rightmove, ESPC, OnTheMarket, etc. | ToS, legal risk, poor provenance |
| Grey-market scraped dumps | “Property data” torrents / unofficial CSVs of portal history | Same + unknown accuracy |
| Redistributing paid data publicly | Putting licensed ROS extracts in a public repo | Licence breach |
| Paid ownership datasets | Who Owns Scotland | Paid — **do not introduce** |

## Laurie GIS licence rules

Prefer **Open Government Licence v3.0** for open map / PostGIS layers. Every catalog entry in `data/config/sources.yaml` must carry a `licence_url` pointing at the exact licence text (for OGL: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

| Topic | Rule |
|-------|------|
| Land Capability for Agriculture | **Do build** — James Hutton Open Data Licence is accepted. Catalog must record licence + attribution / share-alike terms (**not** labelled as OGL) |
| Who Owns Scotland | **Out** — paid |
| SEPA flood | Ingest the **OGL download** from https://www2.sepa.org.uk/flooddata only — never the viewer, web services, or MapServer |
| Crofting | OGL **lists only** (parishes / holdings / grazings); **no boundaries**; never ingest the personal List of Individuals |
| Crown Estate leases | **Offshore only** |
| Community ownership | **Points** from the 2024 gov.scot publication only |
| SSSI / Native Woodland | Catalog must record the exact OGL `licence_url` |

## Portal data (Zoopla, Rightmove, …)

- **Scraping is not used and will not be built.**  
- If a **written licence** and official API/feed exist, evaluate under SLRG legal/commercial review.  
- Until then, treat portals as **out of scope** for pipeline inputs.

## Provenance fields (required on every sales row)

Every transaction record in this project must carry:

- `source_system` (e.g. `ros`, `fixture_synthetic`, `licensed_partner`)  
- `licence` (e.g. `OGL-3.0`, `ROS-research-2026`, `synthetic-test-only`)  
- `retrieved_at` (ISO date)  
- `source_record_id` when available  

Synthetic fixtures must set `licence: synthetic-test-only` and must never be presented as real market evidence in the public UI.

## Git rules

- `data/licensed/` — gitignored  
- `data/cache/` — gitignored  
- `data/fixtures/` — only synthetic or explicitly redistributable samples  
- API keys only in environment variables  

## Attribution

Public methodology and README must list active data sources. See `data/config/sources.yaml`.

### Open spatial layers (map)

| Layer | Source | Licence note |
|-------|--------|----------------|
| Cadastral parcels | Registers of Scotland INSPIRE Index Polygons | OGL-3.0 — cite RoS; raw extracts stay in `data/external/`; CI uses a synthetic fixture only |
| Public land | Scottish Government Public and Crown Estate Land 2024 | unverified/not open — dashboard only; hidden from the public map until an OGL source is confirmed |
| Settlements / localities | NRS Census 2022 (`CEN2022:Settlement2022`, `CEN2022:Locality2022`) | OGL-3.0 — cite NRS; contains OS data © Crown copyright |
| Vacant & derelict | SVDLS site register + Spatial Hub VDL polygons | OGL-3.0 — cite Scottish Government and Improvement Service / local planning authorities; survey sites, not a title |
| Hydropower sites | SEPA Hydropower Sites (ATOM shapefile) | OGL-3.0 — cite SEPA; CAR hydropower abstractions; value_tier=proxy; no £ rent |
| SEPA CAR licences | SEPA Open/SEPA_Reference MapServer 194/195 → PostGIS | OGL-3.0 — cite SEPA (confirmed on Environmental data); ingest-time MapServer load; **never proxied to clients**; value_tier=market; no £ rent |
| Flood extent | SEPA Flood Maps v3.0 (river / coastal medium likelihood) | OGL-3.0 — © SEPA 2025; cite SEPA attribution statements; indicative hazard, not a quote |
| Housing land audit | Spatial Hub Housing Land Supply – Scotland (HLA amalgamation) | OGL-3.0 — cite Improvement Service / local planning authorities; audit sites, not a title. PostGIS ingest from local extract; anonymous Spatial Hub WFS is gated; national SG ArcGIS republish is PSGA/Digimap (not used) |
| LDP allocations | Spatial Hub Local Development Plans pack + authority OGL FeatureServers → PostGIS | OGL-3.0 — cite Improvement Service / planning authorities; fragmented national coverage (Edinburgh missing); planning extents, not a title; ledger nested row 1a |
| SSSI | NatureScot Sites of Special Scientific Interest | OGL-3.0 — https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ — cite NatureScot; Constraint (£0); raw extracts stay in `data/external/` |
| NatureScot designations | NatureScot SPA, SAC, NNR | OGL-3.0 — https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ — cite NatureScot; Constraint (£0); raw extracts stay in `data/external/` |
| Community ownership | SG Community Ownership in Scotland 2024 Dataset | OGL v3.0 — cite Scottish Government; map points are postcode centroids, not title polygons; ownership-context (no public £ rent) |
| National Forest Inventory | Forestry Commission NFI Woodland Scotland (NatureScot OGC) | OGL v3.0 — https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ — © Forestry Commission; contains OS data © Crown copyright; ledger row 1 land-use overlay, not a rent |
| Native Woodland Survey | Scottish Forestry NWSS (NatureScot OGC) | OGL v3.0 — https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/ — © Scottish Forestry / Forestry Commission; ledger row 1 land-use overlay, not a title |
| REPD renewables | DESNZ Renewable Energy Planning Database quarterly CSV | OGL-3.0 — Scotland planning-site points via PostGIS ingest; not lease polygons; ledger row 3 (onshore wind + hydro resource); no £ rent |
| Crown Estate Scotland offshore leases | CES Spatial Hub FeatureServers (offshore wind, wave, tidal, CCS) | OGL-3.0 — offshore lease polygons only; aquaculture is a separate layer; not a title sheet; ledger row 4 (seabed & foreshore); no £ rent |
| Common Good | Statutory LA registers + Highland/Fife indicative FeatureServer metadata | Linked only. No national open spatial layer. Highland licence **unconfirmed** (not OGL) — link-only, not ingested. Fife under OS Public Sector End User Licence - INSPIRE — not redistributed here. Ownership-context (who/outline); no £ rent. |
| Crofting Register / common grazings | Crofting Commission open-data CSVs (Parishes, Holdings, Grazings) | OGL-3.0 — load into PostGIS for valuation joins. Individuals CSV not ingested (personal data). RoS Crofting Register map extents are linked, not redrawn. Spatial Hub Decrofted Areas is Restricted — not used |

### Accepted non-OGL open licence

| Product | Licence | Catalog requirement |
|---------|---------|---------------------|
| Land Capability for Agriculture (Hutton LCA 1:250k) | James Hutton Institute Open Data Licence | `licence` + `licence_url` + attribution / share-alike terms — **do not** label as OGL |

### Won’t build (paid)

| Product | Reason |
|---------|--------|
| Who Owns Scotland | Paid ownership product |

Missing open registers (local-authority holdings, national Common Good spatial file, Sasine, national OGL croft/grazing polygons) are catalogued as gaps — never invented.
Full REPD / CES extracts are not committed; load with `python -m etl.ingest_repd` and `python -m etl.ingest_crown_estate_leases`.
