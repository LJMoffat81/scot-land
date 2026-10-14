# Scot-LAND
**Annual Ground Rent assessment at the core of a free, public, open land information system for Scotland.**

Scot-LAND is a professional, SLRG-aligned platform that estimates **Annual Ground Rent** (the rental value of land alone, excluding buildings and improvements) for every location in Scotland. It transforms complex valuation logic into a free public resource for education, research, policy analysis, and journalism.

The platform is permanently free for everyone to view, explore, and download (where licenses allow), designed to help the public understand both **who holds land** and **what the land is worth** under Georgist principles.

**Live Site:** [https://www.scot-land.scot](https://www.scot-land.scot)

---

## 🌟 The Platform Ecosystem

The repository powers a multi-layered information system:

### 1. The AGR Engine (Valuation Core)
The analytical heart of the project. It provides residual site-value estimates and Annual Ground Rent calculations on a **3×3 m What3Words grid**, ensuring that land rent is treated as a location-based value.

### 2. The National Wealth Engine (Aggregation Core)
A spatial aggregation system that sums three distinct forms of economic rent to show the "Total Wealth" of a location:
- **Surface Rent**: Derived from the `la-calc` model using socio-economic proxies.
- **Resource Rent**: Spatial intersection of Oil, Wind, and Marine assets.
- **Ecological Rent**: Spatial intersection of Carbon, Peat, and Woodland assets.
- **Wealth Inspector**: A frontend tool that provides a transparent "Wealth Stack" breakdown for any selected point.

### 3. Open Land & Ownership Layers (Expanding)
Expanding the platform into a broader land information system by integrating:
- **Cadastral Data**: ROS INSPIRE registered extents.
- **Public Holdings**: Indicative local-authority, Crown, and public-body land registers.
- **Vacant & Derelict Land**: SVDLS and OGL survey sites.
- **Transparency**: Clear visibility of data gaps (e.g., Sasine land or private owner names) rather than hiding them.

---

## 🛠 Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | Next.js 16, MapLibre GL JS, Tailwind CSS |
| **Backend** | Python FastAPI, Pydantic |
| **Data/Spatial** | PostgreSQL + PostGIS (National Wealth Engine) |
| **Valuation** | SLRG-aligned residual method (Wightman $\rightarrow$ Pickard $\rightarrow$ Sandilands) |
| **Grid** | What3Words 3 m grid (via `W3W_API_KEY`) |

---

## 🚀 Quick Start

### 1. Backend Setup
The backend handles the valuation engine and the National Wealth Engine (via PostGIS).

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Database Requirement**: The National Wealth Engine requires a PostgreSQL database with the **PostGIS** extension installed. Ensure your connection strings are configured in your environment.

**Initial Data Build**:
```powershell
# Build baseline valuation data (HPI, Boundaries)
python -m etl.build_processed
python -m etl.build_boundaries
python -m etl.build_wards
```

**Run API**:
```powershell
uvicorn api.main:app --reload --app-dir .
```
- **API Base**: `http://127.0.0.1:8000` | **Docs**: `http://127.0.0.1:8000/docs`

### 2. Frontend Setup
```powershell
cd frontend
npm install
$env:NEXT_PUBLIC_API_URL="http://127.0.0.1:8000"
npm run dev
```
- **App**: `http://localhost:3000`

---

## 🌐 API Reference

### National Wealth Engine
| Endpoint | Method | Description |
|----------|---------|-------------|
| `/georgist/wealth` | `GET` | **Wealth Inspector**. Sums Surface, Resource, and Eco rents for a point. |
| `/layers/georgist/surface-rent` | `GET` | Surface rent layer based on `la-calc` (Data Zone proxies). |
| `/layers/georgist/resource-rent` | `GET` | GeoJSON of resource polygons. |
| `/layers/georgist/eco-rent` | `GET` | GeoJSON of ecological polygons. |
| `/sync/ros` | `POST` | Syncs the wealth engine with Registers of Scotland open data. |

### Core AGR & Spatial Tools
| Endpoint | Method | Description |
|----------|---------|-------------|
| `/square` | `GET` | AGR for a point / W3W cell. |
| `/assessment/report` | `GET` | Professional assessment pack (JSON/Markdown). |
| `/layers/w3w-grid` | `GET` | Viewport W3W cells with AGR. |
| `/layers/parcels/at` | `GET` | Cadastral parcel polygon under a point (ROS INSPIRE). |
| `/fiscal/summary` | `GET` | National fiscal dashboard (Tax basket vs AGR). |

---

## 📈 Professional Data Stance
Scot-LAND adheres to a strict professional standard to ensure all research is defensible and legal.
- **Allowed**: UK HPI, ROS open/licensed products, postcodes.io, documented rebuild tables.
- **Forbidden**: **No scraping** of property portals (Zoopla, Rightmove, ESPC, etc.).
- **Integrity**: Research estimates are **never** presented as official statutory tax bills or VOA valuations. Every estimate carries methodology notes and uncertainty indicators.

## 🏛 Intellectual Foundation
The platform implements the lineage of Georgist land value theory:
**Adam Smith** $\rightarrow$ **David Ricardo** $\rightarrow$ **Henry George** $\rightarrow$ **Mason Gaffney** $\rightarrow$ **Fred Harrison** $\rightarrow$ **Roger Sandilands** $\rightarrow$ **Andy Wightman** (Residual) $\rightarrow$ **Duncan Pickard** (Economic Rent).

## 🚢 Deployment & Hosting
The public site is hosted on a local machine and published via a Cloudflare Tunnel:
- **Public URL**: `https://www.scot-land.scot` / `https://scot-land.scot`
- **Environment**: Docker Compose (`docker-compose.home.yml`) serves the app on port 3000.
- **Safe deploy**: `scripts/ops/deploy-home.ps1` builds images first, health-checks a canary, then swaps; never stops `cloudflared`. See **`docs/HOME_DEPLOY.md`**.
- **Uptime**: free local probe every 5 minutes (`scripts/ops/uptime-check.ps1` / `.sh`) — no paid vendor.
- **Note**: Vercel and Railway were used for earlier split deploys and are not the current public host.
