# Scot-LAND

This is the product brief. Build toward it. Do not shrink it to match the current codebase.

**Annual Ground Rent assessment at the core of a free, public, open land information system for Scotland.**

Scot-LAND began as a professional, SLRG-aligned tool that estimates **Annual Ground Rent** (the rental value of land alone, excluding buildings and improvements) for every location in Scotland. It remains the analytical heart of the project.

We are now expanding it into a broader **open land information platform** — a single free public resource that brings together:

- Modelled land values and AGR / Land Value Tax scenario tools (the original core)
- Free cadastral and spatial data from Registers of Scotland
- Public, Crown and local-authority land holdings
- Vacant and derelict land
- Clear ownership and value layers side-by-side
- Full transparency about data sources, methodology, currency and gaps

The platform is permanently free for everyone to view, explore and download (where licences allow). It is built for public education, research, policy analysis, journalism, community groups and anyone who wants to understand both **who holds land** and **what the land is worth** under Georgist principles.

### Core principles

- **AGR first** — the residual valuation engine (Wightman → Pickard → Sandilands scenarios) remains the methodological foundation.
- **Open and free** — only data that can be legally published for free public use is included in the open layers.
- **Transparent** — every estimate carries methodology notes, uncertainty indicators and source attribution. Research estimates are never presented as official valuations or tax bills.
- **Honest about limits** — private owner names and Sasine land remain incomplete or paid; the platform makes these gaps visible rather than hiding them.
- **Professional standards** — no portal scraping, strict licensing compliance, provenance tracking, and clear separation of open versus licensed data.

### What the platform provides

**Value & AGR layer (existing core)**
- Residual site-value estimates and Annual Ground Rent calculations
- 3×3 m Scot-LAND squares grid and parcel-level views
- Policy scenarios (full AGR, tax-replacement, revenue-neutral options, equal-share illustrations)
- Full public methodology and integrity caveats

**National Wealth Engine (current core)**
- Aggregated land wealth stacks: Surface, Resource, and Ecological rents
- Wealth Inspector: Point-scale breakdown of total economic rent
- `la-calc` surface rent aggregation based on socio-economic proxies
- PostGIS-powered spatial intersection of resource and eco-wealth polygons

**Spatial & ownership layers (expanding)**
- ROS INSPIRE cadastral parcels (registered extents)
- Indicative local-authority land ownership and asset registers
- Community Asset Transfer and Common Good registers
- Vacant & Derelict Land Survey sites
- Aggregated public-body and Crown Estate holdings
- Planning and land-use context where openly available

**Tools & access**
- Interactive map with toggleable layers
- Search and filtering by location, value band, public/private status, vacant land, etc.
- LVT / AGR scenario calculators
- Open downloads of freely licensed layers
- Public API for the open data
- Clear links to ScotLIS for users who need official title sheets

### Intellectual foundation

The valuation core continues the lineage already documented in this repository: Adam Smith and David Ricardo on ground rent, William Ogilvie’s equal natural right, Henry George, Mason Gaffney, Fred Harrison, Joseph Stiglitz, Laurie Macfarlane, Martin Adams (Unitism), Roger Sandilands, Andy Wightman’s residual method, and Duncan Pickard’s economic rent approach, among others.

The broader platform simply makes the spatial and ownership context of that rent visible and usable by the public.

### Status and direction

The current codebase already delivers a working AGR engine, map interface, council-level estimates, ROS INSPIRE integration, validation workflows and professional documentation.

Next development prioritises:

1. Surfacing the free cadastral and public-land layers more prominently — **in progress**: RoS INSPIRE Index Polygons (WMS tiles + PostGIS bbox with 503 when unloaded) and SG 2024 public-land overlay sit at the top of the map layer control, on by default at suitable zoom, with attribution, legend, and click popup. Known gaps (Sasine, private names, LA holdings outside the five bodies) stay visible. Refresh: `scripts/data/README-inspire.md` and `data/config/sources.yaml`.
2. Vacant & derelict land — **in progress**: SVDLS site-level overlay (OGL) in Ownership and cadastre with site-type legend, attribution/credits, click popup, and **503** when the upstream FeatureServer is down. Geometry precedence: Spatial Hub survey > RoS title outline > point (each site tagged `geometry_source`). Local-authority holdings remain a flagged gap.
3. Common Good — **linked registers**: verified council register / metadata links via `/api/common-good.json`; no national open spatial layer. Fife indicative titles (OS INSPIRE EUL) are linked, not mirrored.
4. Crofting Register + common grazings — **OGL lists only / spatial gap**: Crofting Commission Parishes, Holdings and Grazings CSVs (OGL-3.0) load into PostGIS via `python -m etl.ingest_crofting`; catalog layers `crofting_register` and `common_grazings` as ledger **constraints** (£0, no rent row; no LayersPanel toggle; no boundary polygons; never List of Individuals). RoS Crofting Register map holds definitive extents but is not an OGL redistributable polygon feed — gap stays visible. Spatial Hub Decrofted Areas is Restricted (rejected).
5. Improving national statistics and data-gap indicators
6. Keeping the AGR calculation engine and scenario tools as the analytical centre

The project remains aligned with SLRG principles and is intended as a permanent free public resource.

### Licence & contribution

- Build standard: [PROFESSIONAL_STANDARD.md](PROFESSIONAL_STANDARD.md)
- Data policy: [DATA_LICENSING.md](DATA_LICENSING.md)
- Data acquisition: [DATA_ACQUISITION.md](DATA_ACQUISITION.md)
- Valuation method: [methodology.md](methodology.md)

Only data that can be legally published for free public use belongs in the open layers. Contributions should follow the professional standard and data-licensing rules. Research estimates are never official valuations or tax bills.
