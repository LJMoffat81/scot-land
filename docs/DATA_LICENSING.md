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
| Cadastral parcels | Registers of Scotland INSPIRE Index Polygons | OGL / INSPIRE (Crown) — cite RoS; raw extracts stay in `data/external/` |
| Public land | Scottish Government Public and Crown Estate Land 2024 | OGL-3.0 — cite Scottish Government; five bodies; indicative overlay, not a title |
| Vacant & derelict | SVDLS site register + Spatial Hub VDL polygons | OGL-3.0 — cite Scottish Government and Improvement Service / local planning authorities; survey sites, not a title |
| Land capability (agriculture) | James Hutton Institute LCA 1:250k open download | **James Hutton Open Data Licence** (not pure OGL). Public-sector information under OGL v2.0 per Hutton attribution. Raw stays in `data/external/lca/` |
| Common Good | Statutory LA registers + Fife indicative titles metadata | Linked only. No national open spatial layer. Fife under OS Public Sector End User Licence - INSPIRE — not redistributed here |

Missing open registers (local-authority holdings, national Common Good spatial file, Sasine) are catalogued as gaps — never invented.
