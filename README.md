# Scot-LAND

**Product brief:** [docs/PLATFORM.md](docs/PLATFORM.md)

That document is the guide for this repository. Implementation follows it. The brief is not edited down to the current build.

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

**Build standard:** [docs/PROFESSIONAL_STANDARD.md](docs/PROFESSIONAL_STANDARD.md) · **Data policy:** [docs/DATA_LICENSING.md](docs/DATA_LICENSING.md) (no portal scraping).

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

**Operational charge maths (valuer residual roll):**
HABU existing use → **MV − DRC** (Wightman residual) → Pickard economic site capital → **× 5% yield** → Sandilands scenarios.

| Layer | Thinker | Role |
|-------|---------|------|
| Classical | **Adam Smith** | Ground-rent as distinct, taxable revenue |
| Classical | **David Ricardo** | Differential / locational rent |
| Scottish OG | **William Ogilvie** | Equal natural right in land |
| Programme | **Henry George** | Full site-rent recovery |
| Public finance | **Mason Gaffney** | ATCOR / EBCOR |
| Cycles | **Fred Harrison** | Boom–bust; speculative land prices |
| Modern theory | **Joseph Stiglitz** | Public goods capitalise into land |
| Housing/land | **Laurie Macfarlane** | Housing crisis = land market |
| Community contribution | **Martin Adams (Unitism)** | Land rent shared; optional citizen dividend |
| Scotland macro | **Roger Sandilands** | Rent pool; income-tax shift |
| Valuation | **Andy Wightman** | Residual / HABU site capital |
| Charge base | **Duncan Pickard** | Economic rent after speculation |

Also see: Mill, Paine, **School of Cooperative Individualism** (Georgist source library), **Lars Doucet / CLE** (OpenAVMKit mass appraisal path), McEwen, Churchill 1909, Scottish Land Commission — [docs/methodology.md](docs/methodology.md) · [docs/valuation-roadmap.md](docs/valuation-roadmap.md).

**Integrity:** map residual £ figures are a research estimate (not a rates bill). The Sandilands national rent pool is a separate macro concept used for equal-share and income-tax scaling — map squares are not calibrated to sum to that pool. See methodology “Two rent concepts”.

**Product clarity:** the map default is a plain £/year estimate and short policy choices; valuer steps, integrity caveats, and full lineage live under **How calculated** / **About AGR** and [methodology](docs/methodology.md).

**What3Words:** every estimate snaps to a **3×3 m W3W-aligned cell**. Plot-scale £/year is the household headline; the cell line always shows the 9 m² square charge. With `W3W_API_KEY`, the API reverse-geocodes `///three.word.address` on every lookup.

Built for [SLRG](https://www.slrg.scot) as a standalone public education and advocacy tool.

### Direction

Next development prioritises:

1. Surfacing the free cadastral and public-land layers more prominently
2. Adding vacant & derelict land and local-authority holdings
3. Improving national statistics and data-gap indicators
4. Keeping the AGR calculation engine and scenario tools as the analytical centre

The project remains aligned with SLRG principles and is intended as a permanent free public resource.

### Licence & contribution

- Product brief: [docs/PLATFORM.md](docs/PLATFORM.md)
- Build standard: [docs/PROFESSIONAL_STANDARD.md](docs/PROFESSIONAL_STANDARD.md)
- Data policy: [docs/DATA_LICENSING.md](docs/DATA_LICENSING.md)
- Data acquisition: [docs/DATA_ACQUISITION.md](docs/DATA_ACQUISITION.md)
- Operating notes: [docs/OPERATING.md](docs/OPERATING.md)

Only data that can be legally published for free public use belongs in the open layers. Contributions should follow the professional standard and data-licensing rules. Research estimates are never official valuations or tax bills.

---

## Current codebase

The sections below are how to run and deploy what is in the repository now. They do not limit the brief above.

## Stack

| Layer | Technology |
|-------|------------|
| Frontend | Next.js 16, MapLibre GL JS |
| Backend | Python FastAPI + valuation service |
| Data layer | `backend/datasources/` (HPI residual + sales schema/store) |
| Config | `data/config/agr.yaml`, `sources.yaml` |
| Sales path | ROS / licensed extracts → `SalesStore` (fixtures for CI only) |
| Tiles | OpenStreetMap (free) |
| W3W | 3 m grid + optional API key |

## Professional data stance

- **Allowed:** UK HPI, ROS open/licensed products, postcodes.io, documented rebuild tables
- **Forbidden:** scraping Zoopla, Rightmove, ESPC, or grey-market scraped dumps
- **Next:** acquire ROS pilot sales for Ward 18 / Glasgow → optional OpenAVMKit comparison

See [docs/DATA_ACQUISITION.md](docs/DATA_ACQUISITION.md).

## Quick start

### Build valuation data (first run / monthly refresh)

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m etl.build_processed
```

Downloads UK HPI from HM Land Registry (free) and writes `data/processed/councils.json`.

```powershell
python -m etl.build_boundaries   # council polygons
python -m etl.build_wards        # Glasgow Ward 18 validation area
```

Optional: set `W3W_API_KEY` in `backend/.env` after SLRG nonprofit approval.

### Backend

```powershell
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn api.main:app --reload --app-dir .
```

API: http://127.0.0.1:8000  
Docs: http://127.0.0.1:8000/docs

| Endpoint | Purpose |
|----------|---------|
| `GET /square` | AGR for a point / W3W cell |
| `GET /assessment/report` | Professional JSON or markdown report (`format=markdown`) |
| `GET /validation/ratio-study` | Residual vs sales-comp ratios (Ward 18 samples) |
| `GET /validation/ward18-qa-pack` | Full Ward 18 QA: spatial + ratios + mini-roll |
| `GET /sales/status` | Sales pipeline status |
| `GET /layers/councils-agr` | Council choropleth (plot AGR £/year) |
| `GET /layers/w3w-grid?south&west&north&east` | Viewport W3W cells with AGR (capped) |
| `GET /layers/open/vdl?south&west&north&east` | Viewport vacant/derelict land (SVDLS, OGL) |
| `GET /layers/open/public-land?south&west&north&east` | Viewport public / Crown land (SG 2024, five bodies) |
| `GET /api/catalog.json` | Live / linked / gap register |
| `GET /api/roll.json` | 32-council AGR roll + SVDLS vacant ha |
| `GET /api/public-land.json` | Hectares by the five published bodies |
| `GET /api/vdl.json` | SVDLS hectares by owner class |
| `GET /api/registers.json` | Official planning / CAT / ScotLIS landing pages |
| `GET /api/place.json?pc=` | Place card (vacant / public / parcel / gaps) |
| `GET /downloads` | Index of open stats and official source links |

Ops: [docs/OPERATING.md](docs/OPERATING.md) · `.\scripts\run_professional_local.ps1`

### Professional workflow

```powershell
# Validate synthetic fixtures
python -m etl.ingest_sales --path ../data/fixtures/sales/ward18_synthetic.jsonl

# After ROS extract arrives (see docs/ROS_ENQUIRY.md)
python -m etl.convert_sales_csv --input ../data/licensed/raw.csv --output ../data/licensed/sales.jsonl ...
python -m etl.ingest_sales --path ../data/licensed/sales.jsonl --require-production
```

### Frontend

```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8000"
npm run dev
```

App: http://localhost:3000  
Open data: http://localhost:3000/downloads · http://localhost:3000/open-api

## Project structure

```
scotland-open-land/
├── frontend/          # Next.js + MapLibre map UI
├── backend/           # FastAPI AGR engine
├── data/config/       # agr.yaml (SLRG parameters)
├── docs/              # Brief, methodology and references
└── docker-compose.yml
```

## Legacy prototype

The original Streamlit prototype is preserved at git tag `legacy/streamlit-prototype`.

## Deploy

The public site is this PC. `docker compose -f docker-compose.home.yml` serves the app on port 3000. The Cloudflare Tunnel `scot-land` publishes `https://www.scot-land.scot` and `https://scot-land.scot` from that port. Mail for the domain is Proton and is separate from this app. The git folder stays `scotland-open-land`.

Vercel and Railway are an older split deploy. They are not the public host.

## Older split deploy (not the public site)

Free-tier friendly: **Vercel** (frontend) + **Railway** (API). No paid map or data APIs required. Do not point `scot-land.scot` at Vercel.

### 1. Railway — API

1. Create a project at [railway.app](https://railway.app) and connect this GitHub repo.
2. Railway reads `railway.toml` and builds `backend/Dockerfile` (includes `data/`).
3. Set environment variables:

| Variable | Value |
|----------|-------|
| `ALLOWED_ORIGINS` | Your Vercel URL, e.g. `https://scotland-agr-map.vercel.app` |
| `ALLOW_VERCEL_PREVIEWS` | `true` (allows `*.vercel.app` preview deploys) |
| `W3W_API_KEY` | Optional — after SLRG nonprofit approval |

4. Copy the public Railway URL (e.g. `https://scotland-agr-map-api.up.railway.app`).

Health check: `GET /health`

### 2. Vercel — frontend

1. Import the repo at [vercel.com](https://vercel.com).
2. Set **Root Directory** to `frontend`.
3. Set environment variable **before first deploy**:

| Variable | Value |
|----------|-------|
| `NEXT_PUBLIC_API_URL` | Your Railway API URL |

4. Deploy. `frontend/vercel.json` is included.

### 3. Custom domain

Do not point `scot-land.scot` at Vercel. That name is already served from this PC. A separate Vercel hostname, if one is still used, belongs in Railway `ALLOWED_ORIGINS`.

### Economist sign-off

Parameters live in `data/config/agr.yaml`. When the SLRG economist approves, update:

```yaml
economist_signoff:
  status: approved
  signed_by: "Name, credentials"
  signed_at: "2026-06-08"
```

Redeploy Railway. Status appears on `/signoff` and the methodology page.

### Docker (self-hosted alternative)

```powershell
docker compose up --build
```

App: http://localhost:3000 · API: http://localhost:8000
