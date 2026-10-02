# Scot-LAND

This is the product brief. Build toward it. Do not shrink it to match the current codebase.

**Annual Ground Rent assessment at the core of a free, public, open land information system for Scotland.**

Scotland AGR Map began as a professional, SLRG-aligned tool that estimates **Annual Ground Rent** (the rental value of land alone, excluding buildings and improvements) for every location in Scotland. It remains the analytical heart of the project.

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
- 3×3 m What3Words grid and parcel-level views
- Policy scenarios (full AGR, tax-replacement, revenue-neutral options, equal-share illustrations)
- Full public methodology and integrity caveats

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

1. Surfacing the free cadastral and public-land layers more prominently
2. Adding vacant & derelict land and local-authority holdings
3. Improving national statistics and data-gap indicators
4. Keeping the AGR calculation engine and scenario tools as the analytical centre

The project remains aligned with SLRG principles and is intended as a permanent free public resource.

### Licence & contribution

- Build standard: [PROFESSIONAL_STANDARD.md](PROFESSIONAL_STANDARD.md)
- Data policy: [DATA_LICENSING.md](DATA_LICENSING.md)
- Data acquisition: [DATA_ACQUISITION.md](DATA_ACQUISITION.md)
- Valuation method: [methodology.md](methodology.md)

Only data that can be legally published for free public use belongs in the open layers. Contributions should follow the professional standard and data-licensing rules. Research estimates are never official valuations or tax bills.
