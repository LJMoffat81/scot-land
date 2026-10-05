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

2. **Launch the Infrastructure:**
   ```bash
   docker-compose up -d
   ```

3. **Migrate the Data:**
   ```bash
   cd backend
   pip install -r requirements.txt
   export PYTHONPATH=. && python3 etl/migrate_to_postgis.py
   ```

4. **Start the API:**
   ```bash
   uvicorn api.main:app --reload --port 8000
   ```

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

The **Surface Rent** is calculated as:
$$\text{Base Rent} \times (\text{Density Multiplier}) \times (\text{Economic Multiplier}) \times (\text{Access Multiplier})$$

This ensures that value is attributed to the *location* and the *community*, not the individual improvement on the land.

## 🤝 Collaboration & Data Sharing
This project is designed for synchronization with other land-reform initiatives. We adopt a **UPID (Unique Parcel ID)** standard to allow seamless data sharing with ownership datasets (such as the "Who Owns Scotland" project).

**License:** Open Government Licence v3.0 / MIT**
