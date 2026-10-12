# Frontend information architecture

Status: **proposed** — agree this before merging further map-panel UI.  
Scope: product IA only (no application code in the PR that introduced this file).  
Related: [PLATFORM.md](PLATFORM.md), [CHARTER.md](CHARTER.md), `GET /layers/catalog`, draft [FRONTEND_ALIGNMENT.md](https://github.com/LJMoffat81/scot-land/pull/10).

**Pause:** do not merge new map-panel / shell UI that adds more layer toggles, themes, or HUD chrome until this IA is agreed. **Continue:** backend loaders, PostGIS ingest, catalog entries, place APIs, and Data-section content.

---

## Problem

The map page is becoming a data dump: every live catalog layer wants a toggle, bbox GeoJSON, and legend space. That fights the charter (what3words-style full-screen map, one search, place cards) and will not scale as natural-capital P1–P3 lands.

This document fixes the **shape** of the product: what is on by default, what hides under themes, what belongs only in Downloads / Public API, and how place detail deepens without crowding the map.

---

## 1. Map page

### Job

One composition: full-bleed Scotland map, brand-level product name, **one search** (postcode / place / coordinates), and a thin layers control. AGR / scenario analysis stays the analytical centre; spatial layers are context around it — not a GIS workstation.

### Curated default (on first paint)

| Element | Role |
|---|---|
| **Search** | Primary entry — find a place; click map for the same place card |
| **Scot-LAND squares** (`cell_grid`) | Grid context at suitable zoom; public £ withheld until yield calibration |
| **Data Zone boundaries** (`data_zones`) | National statistical frame; outlines + open rollups; no plot AGR £ |

Nothing else is on by default. Cadastral parcels, ownership overlays, natural capital, planning, and designations start **off**.

### Themes (collapsed by default)

Layer toggles sit under five themes. Themes render **collapsed**; opening one shows optional overlays. Catalog `group` today (`value` / `spatial` / `ownership`) is an implementation detail — IA themes are the public taxonomy.

1. **Land & ownership** — parcels, public/Crown (when OGL-verified), VDL, Common Good, community ownership, crofting / grazings, LA holdings (gap honesty).
2. **Nature & designations** — SSSI / designations, woodland (NFI, Native Woodland), peatland, soils, LCA, flood (use-constraint overlays; never add rent).
3. **Energy & resources** — REPD onshore wind, hydropower sites, SEPA CAR (where map-eligible), BritPits index.
4. **Sea** — ScotWind / INTOG, CES aquaculture seabed, cables, foreshore / moorings, NSTA (non-commercial), ICES rectangles where drawn.
5. **Planning & housing** — LDP allocations, Housing Land Audit, NRS settlements / localities; planning applications stay linked (no national drawable WMS).

Linked / gap catalog rows appear as honest text or outbound links inside the theme — not as fake paint toggles.

### Visibility budget

- **At most ~5 layers painted at once** (default set counts toward this). Enabling a sixth prompts the user to turn one off, or auto-defers the oldest optional overlay.
- Default panel shows search + the two default layers + a “Layers” control that opens themes — not a flat checklist of every catalog id.
- Dev/preview routes (`/layers-panel`, `/place-card`) may list more for QA; they are not the public shell.

### Zoom-dependent loading

| Layer class | Typical min zoom | Load behaviour |
|---|---|---|
| Data Zones | ≥ 10 (national simplify below) | Simplified outlines at country view; richer attributes when zoomed |
| Scot-LAND squares | ≥ 12 | Viewport tiles / cells only |
| ROS INSPIRE parcels | ≥ 14 | Tiles + bbox; soft-fail transparent when unloaded |
| Site points (hydro, VDL points, community) | ≥ 6–8 | Cluster or thin at low zoom |
| Dense polygons (designations, peat, leases) | Theme-specific | Never full-nation client GeoJSON |

Honor catalog `minzoom`. Below minzoom: no fetch, no empty error toast.

### Geometry delivery

- **Prefer vector tiles or server-simplified geometry** (MVT / WMS tiles / PostGIS simplify-by-zoom).
- **Do not** ship raw national GeoJSON to the browser for paint.
- Bbox GeoJSON endpoints may remain for small viewports, downloads, and tests; the public map paint path must not depend on them for large extents.
- 503 when a layer is unloaded is honest; empty viewport when loaded is 200.

---

## 2. Place card → place page

### Place card (map HUD)

Short summary on click / search hit:

- Where: postcode, council, coordinates, Data Zone code/name when known  
- Hits: which **map-default / map-optional** layers intersect (hit / miss / linked / gap)  
- One-line honesty: research estimate / not a title / gaps visible  
- Primary action: **Open full place**  
- Secondary: ScotLIS / methodology links already on the card  

No choropleth legend, no layer management, no scenario calculator on the card.

### Full place page

Route target (name flexible): `/place?...` or `/place/[slug]`. Same catalog-driven facts, deeper:

- Layer-by-layer intersection detail and attribution  
- Open downloads for that geography where licensed  
- Scenario / AGR tools when publication rules allow (held until ECONOMIC_RULES)  
- Explicit “not on the public map” callouts for data-section-only layers  

Map shell stays light; depth lives here.

---

## 3. Data section (Downloads + Public API)

Treat **Downloads** and **Public API** as one **Data** section with two tabs or sibling pages sharing one nav entry (“Data”).

| Concern | Downloads | Public API |
|---|---|---|
| Audience | Bulk / offline users | Integrators |
| Content | Dataset list, licence, credit, vintage, bulk file or export URL | Same catalog ids → documented endpoints |
| Driver | `GET /layers/catalog` (+ downloads index) | Same catalog + OpenAPI-style page copy |

Every catalog layer (live, linked, gap, partial) appears in Data with:

- **Dataset** label and one-line description  
- **Licence** + `licence_url` + required credit string  
- **Vintage** / ingest stamp when known  
- **Access:** bulk download, bbox/API, or “linked only / gap”  
- **Map class:** map-default / map-optional / data-section-only (this doc)

Catalog remains the single product claim list. UI drift checks stay mandatory for live map toggles; Data pages must not invent layers missing from the catalog.

Existing routes `/downloads` and `/open-api` implement this section; rename or combine in a later UI PR after IA agreement.

---

## 4. Layer classification

Classes:

- **map-default** — on in the curated first paint (within the ~5 paint budget).  
- **map-optional** — theme toggle; off by default; zoom-gated paint.  
- **data-section-only** — catalog / downloads / API / place-page detail; not a public map paint toggle (may still be linked or gap text in a theme).

### Current catalog (`platform_catalog` on `main`)

| Id | Class | Reason |
|---|---|---|
| `cell_grid` | map-default | Scot-LAND squares are the product grid; public £ still withheld |
| `data_zones` | map-default | National statistical frame for search and wealth context |
| `agr_value` | data-section-only | Plot AGR £ not public until calibration; national rollups via Data/API |
| `boundaries` | map-optional | Cadastre is essential but dense — Land & ownership, zoom ≥ 14 |
| `vdl` | map-optional | Vacant/derelict context; optional ownership theme overlay |
| `public_crown` | map-optional | Public/Crown holdings when OGL-verified; hide if licence unverified (#38) |
| `hydro_sites` | map-optional | Energy & resources inventory; no £ rent |
| `sepa_car` | data-section-only | `publication_status=download_only`; register export, not a default paint layer |
| `la_holdings` | data-section-only | Spatial Hub not openly licensed — gap, not scraped |
| `planning` | data-section-only | Linked ePlanning pages; no national drawable WMS |
| `council_assets` | data-section-only | Login-gated Spatial Hub — link only |
| `common_good` | data-section-only | Linked registers today; no national open polygons on `main` |
| `fife_land_map` | data-section-only | Single-council hub; not a national map layer |
| `sasine_private` | data-section-only | Honest gap; names not invented |

### Queued / in-flight layers (build-out + open PRs)

Classify for when they merge; backend loaders may land before any map toggle.

| Layer / PR theme | Class | Reason |
|---|---|---|
| ScotWind / INTOG (#42) | map-optional | Sea theme; seabed options, no fees on layer |
| REPD onshore wind (#43) | map-optional | Energy theme; MW/status inventory, no £ |
| CES aquaculture seabed (#47) | map-optional | Sea theme; OGL Spatial Hub leases (biomass HOLD) |
| SEPA CAR MapServer ingest (#46) | data-section-only | Improves download/API geometry; paint still opt-in only if catalog marks map-eligible later |
| NatureScot SSSI / designations (#26) | map-optional | Nature theme; constraint overlay, never adds rent |
| SEPA flood maps (#25) | map-optional | Nature theme; use constraint from OGL download only |
| NFI + Native Woodland (#29) | map-optional | Nature theme; woodland inventory |
| LDP allocations (#30) | map-optional | Planning & housing theme |
| Housing Land Audit (#31) | map-optional | Planning & housing theme |
| NRS settlements / localities (#24) | map-optional | Planning & housing context outlines |
| Community ownership (#36) | map-optional | Land & ownership; OGL points |
| Crofting Register + common grazings (#34) | map-optional | Land & ownership; OGL lists/geometries only — never personal List of Individuals |
| Common Good GIS expand (#33) | map-optional | Land & ownership when national/open polygons exist; else stay data-section |
| Land Capability for Agriculture (#39) | map-optional | Nature / land-use capability; Hutton licence + credit |
| DZ HPI / SIMD / density (#35) | map-optional | Attributes on Data Zones — off-default choropleth, not a second boundary layer |
| REPD + CES leases (older #32) | map-optional | Superseded in part by P1 PRs; same Energy/Sea themes when retained |
| BritPits OGL index (P2) | map-optional | Energy & resources points index only (full BritPits paid — drop) |
| Peatland ACTION (P2) | map-optional | Nature theme |
| Carbon & Peatland 2016 (P2, non-commercial) | map-optional | Nature theme; tag `licence=non-commercial` |
| Hutton 250k soils (P2) | map-optional | Nature theme; Hutton licence |
| ICES landings 2024 (P2) | data-section-only | Rectangle statistics better as Data/API than map clutter; optional Sea later if needed |
| NSTA licences/fields (P3, non-commercial) | map-optional | Sea theme; non-commercial tag |
| CES cable leases (P3) | map-optional | Sea theme |
| CES foreshore / moorings (P3, TBC) | map-optional | Sea theme when licence clear; else data-section-only |
| Hide unverified Crown land (#38) | (policy) | Forces `public_crown` off map until OGL proven — Data may still explain the gap |
| AGR place pages / tax scenarios (#6, #9, #19) | data-section-only | Held until ECONOMIC_RULES; not map-panel UI |
| SVDLS / Common Good valuation rules (#16, #17) | data-section-only | Engine rules, not map toggles |
| BGS mineral resources / full BritPits / Who Owns Scotland | — | **Drop** — paid or unclear; never catalog as open map |

Search, scenario calculators, ScotLIS links, and filters are **tools**, not layers — they appear in shell / place page / Data docs, not as theme paint toggles.

---

## 5. Performance budget

Targets for the public map shell (not lab ingest jobs):

| Budget | Target |
|---|---|
| Layers painted | ≤ ~5 concurrent |
| Initial map interactive | ≤ 3 s on mid laptop / decent 4G after basemap |
| Geometry to browser | Vector tiles or zoom-simplified payloads; **no** national raw GeoJSON paint |
| Viewport fetch | Cancel in-flight on pan/zoom; debounce ~200–300 ms |
| Place card payload | Small JSON (identity + layer hit list + links); deep series on place page |
| Failure mode | 503 / empty / withheld copy — never hang the HUD |
| Theme panel | Collapsed cost ≈ zero network; fetch only enabled optional layers |

Backend may keep heavy extracts in PostGIS; the IA constraint is **what the browser paints and fetches**.

---

## 6. Page map

```
/                     Map shell — search, defaults, themes, place card HUD
/place (or /place/…)  Full place page — depth, downloads for that spot, held AGR tools
/downloads            Data section — bulk datasets, licence, vintage
/open-api             Data section — Public API docs (same catalog)
/methodology          About / method (not a layer browser)
/layers-panel         Dev/QA catalog panel (not primary nav)
/place-card           Dev/QA place card fixture (not primary nav)
```

Primary nav (public): **Map · Data · About**.  
Data = Downloads + Public API. Layers live on the map (curated + themes), not as a top-level mega-menu of datasets.

---

## Agreement checklist

- [ ] Curated default = Scot-LAND squares + Data Zones + search only  
- [ ] Five themes, collapsed by default; ≤ ~5 layers painted  
- [ ] Vector tiles / simplified geometry for paint  
- [ ] Place card short → full place page  
- [ ] Data section driven by catalog (licence, credit, vintage, bulk + API)  
- [ ] New map-panel UI PRs wait; loader/catalog PRs may continue  

When Laurie (or Grok Bot per charter) marks this agreed, implement in small frontend PRs that follow this file — do not silently expand the default paint set.
