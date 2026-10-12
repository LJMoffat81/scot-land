# 🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scot-LAND: The National Wealth Engine

**An open-source platform for quantifying the economic rent of Scotland's natural and community commons.**

## 🌍 The Vision
Scot-LAND is a professional-grade tool designed to visualize and quantify the "unearned increment" of land value. Based on Georgist economic principles, the platform identifies the wealth created not by the landowner, but by the community and nature.

Instead of traditional property valuations, Scot-LAND calculates **Annual Ground Rent** across three dimensions of the "Commons":

1.  **The Surface Commons:** Value created by population density, infrastructure, and urban accessibility (derived from SIMD and Census data).
2.  **The Resource Commons:** Value created by sub-surface minerals, oil, gas, and offshore wind (derived from NSTA and Marine Scotland data).
3.  **The Ecological Commons:** Value created by carbon sequestration in peatlands and biodiversity in ancient woodlands (derived from NatureScot data).

---

## ⚙️ The Architecture

The engine uses a high-performance spatial stack to provide real-time wealth aggregation:

### 🏗️ Backend (The Brain)
- **PostGIS Database:** A spatial PostgreSQL database that stores land-value polygons and la-calc metrics.
- **FastAPI Engine:** A high-speed API that performs spatial intersections (`ST_Intersects`) to sum the wealth layers.
- **la-calc Multipliers:** A calibrated valuation model that converts socio-economic proxies into estimated annual rents.
- **Auto-Sync:** A CKAN-based synchronization service that keeps la-calc data updated with the latest Registers of Scotland (RoS) open data.

### 🎨 Frontend (The Face)
- **Next.js 16 & MapLibre GL JS:** A modern, responsive geospatial interface.
- **Wealth Inspector:** A dedicated "Wealth Stack" UI that breaks down the la-calc rent for any point in Scotland.
- **Dynamic Heatmaps:** Visualizations of the "National Wealth" across different common-wealth layers.

---

## 🚀 Quick Start

### Prerequisites
- Docker & Docker Compose
- Python 3.12+
- Node.js & npm

### Installation
1. **Clone the repository:**
   ```bash
   git clone https://github.com/[your-username]/scot-land.git
   cd scot-land
   ```

2. **Launch the Infrastructure** (needs `POSTGRES_PASSWORD` in `.env`; see `backend/.env.example`):
   ```bash
   docker compose up -d db
   ```

3. **Apply the Wealth schema / load placeholder layers (internal only) and manifest data:**
   ```bash
   cd backend
   pip install -r requirements-dev.txt
   export DATABASE_URL=postgresql://scotland:<password>@127.0.0.1:5432/scotland_wealth
   alembic upgrade head                    # see docs/DB_MIGRATIONS.md
   python -m db.check_drift                # optional
   python -m etl.migrate_to_postgis --schema-only   # also runs alembic upgrade head
   python -m etl.load_processed            # manifest-listed data/processed/*/ files (checksummed)
   ```
   Mock resource/eco layers are only visible on `/internal/...` with
   `ENABLE_INTERNAL_ENDPOINTS=1` **and** a configured `INTERNAL_API_TOKEN`
   (Bearer or X-API-Key). Without the token the routes stay locked (403) —
   they never fall open.
4. **Start the API** (boots without a DB; `/health` reports `db.status`):
   ```bash
   uvicorn api.main:app --reload --port 8000
   ```

   See [`docs/wealth_api.md`](../docs/wealth_api.md) for endpoints, error codes and the `surface_rent_dz` / `planning_sites` schema.

5. **Start the Frontend:**
   ```bash
   cd ../frontend
   npm install
   npm run dev
   ```

---

## 📈 The la-calc Methodology
The la-calc engine avoids "guessing" prices. It uses a **weighted multi-factor model**:

$$\text{Total Rent} = \text{Surface Rent} + \text{Resource Rent} + \text{Eco Rent}$$

> **Superseded (draft economic rules, Oct 2026):** the API no longer returns one mixed total. Totals are reported per value tier (market / proxy / shadow), placeholder layers are excluded, and the surface method is the residual method in `docs/surface_rent_spec.md`, not the SIMD multipliers below.

The **Surface Rent** is calculated as:
$$\text{Base Rent} \times (\text{Density Multiplier}) \times (\text{Economic Multiplier}) \times (\text{Access Multiplier})$$

This ensures that value is attributed to the *location* and the *community*, not the individual improvement on the land.

## 🤝 Collaboration & Data Sharing
This project is designed for synchronization with other land-reform initiatives. We adopt a **UPID (Unique Parcel ID)** standard to allow seamless data sharing with ownership datasets (such as the "Who Owns Scotland" project).

**License:** Open Government Licence v3.0 / MIT**
