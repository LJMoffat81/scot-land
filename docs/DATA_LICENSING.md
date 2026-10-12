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
| Vacant & derelict | SVDLS site register + Spatial Hub VDL polygons | OGL-3.0 — cite Scottish Government and Improvement Service / local planning authorities; survey sites, not a title |
| Hydropower sites | SEPA Hydropower Sites (ATOM shapefile) | OGL-3.0 — cite SEPA; CAR hydropower abstractions; value_tier=proxy; no £ rent |
| SEPA CAR licences | SEPA Open/SEPA_Reference MapServer 194/195 → PostGIS | OGL-3.0 — cite SEPA (confirmed on Environmental data); ingest-time MapServer load; **never proxied to clients**; value_tier=market; no £ rent |
| Housing land audit | Spatial Hub Housing Land Supply – Scotland (HLA amalgamation) | OGL-3.0 — cite Improvement Service / local planning authorities; audit sites, not a title. PostGIS ingest from local extract; anonymous Spatial Hub WFS is gated; national SG ArcGIS republish is PSGA/Digimap (not used) |
| LDP allocations | Spatial Hub Local Development Plans pack + authority OGL FeatureServers → PostGIS | OGL-3.0 — cite Improvement Service / planning authorities; fragmented national coverage (Edinburgh missing); planning extents, not a title; ledger nested row 1a |

| Common Good | Statutory LA registers + Fife indicative titles metadata | Linked only. No national open spatial layer. Fife under OS Public Sector End User Licence - INSPIRE — not redistributed here |

### Accepted non-OGL open licence

| Product | Licence | Catalog requirement |
|---------|---------|---------------------|
| Land Capability for Agriculture (Hutton LCA 1:250k) | James Hutton Institute Open Data Licence | `licence` + `licence_url` + attribution / share-alike terms — **do not** label as OGL |

### Won’t build (paid)

| Product | Reason |
|---------|--------|
| Who Owns Scotland | Paid ownership product |

Missing open registers (local-authority holdings, national Common Good spatial file, Sasine) are catalogued as gaps — never invented.
