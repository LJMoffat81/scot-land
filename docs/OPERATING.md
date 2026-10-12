# Operating the professional tool

## Daily local loop

```powershell
# One-shot checks + demo roll
.\scripts\run_professional_local.ps1

# API
cd backend
.\.venv\Scripts\Activate.ps1
uvicorn api.main_platform:app --reload --app-dir .

# UI (other terminal)
cd frontend
npm run dev
```

## Core endpoints

| Endpoint | Use |
|----------|-----|
| `GET /square?lat=&lng=` | Live AGR for a W3W cell (`platform` place card attached) |
| `GET /layers/catalog` | Open-land layers with live / linked / gap status |
| `GET /layers/parcels?...` | RoS INSPIRE Index Polygons bbox (PostGIS; **503** if not loaded) |
| `GET /layers/parcels/tiles/{z}/{x}/{y}` | Live RoS INSPIRE WMS proxy (soft-fail tiles) |
| `GET /layers/parcels/at?lat=&lng=` | Parcel under a point (live WMS GetFeatureInfo) |
| `GET /layers/open/vdl` | Vacant and derelict land overlay (bbox) |
| `GET /layers/open/public-land` | Public / Crown Estate overlay (bbox, five bodies; **503** if upstream down) |
| `GET /platform/place` | Ownership / vacant / gap card |
| `GET /platform/gaps` | Visible register gaps |
| `GET /downloads` | Open layer and official source index |
| `GET /api/catalog.json` | Live / linked / gap register |
| `GET /api/roll.json?scenario=` | 32-council AGR roll with SVDLS vacant ha |
| `GET /api/public-land.json` | Hectares by the five published bodies |
| `GET /api/vdl.json` | SVDLS hectares by owner class |
| `GET /api/place.json?pc=` | Place card (vacant / public / parcel / gaps) |
| `GET /assessment/report?format=markdown\|json` | Downloadable assessment pack |
| `GET /validation/ward18-qa-pack` | Spatial + ratio + mini-roll for Ward 18 |
| `GET /validation/ratio-study` | Residual vs sales-comp ratios |
| `GET /sales/status` | Sales store status |
| `GET /layers/councils-agr` | National council AGR choropleth |
| `GET /layers/w3w-grid?...` | Viewport 3×3 m cells with AGR (max_cells) |

### Map layers (product)

| Layer | Coverage | When |
|-------|----------|------|
| **Cadastral parcels** | RoS INSPIRE Index Polygons | Top of Layers; on by default zoom ≥ 14; attribution + click popup |
| **Public land** | SG 2024 five bodies | Top of Layers; on by default zoom ≥ 8; owner-type legend; gaps flagged |
| Council AGR | All Scotland | Overview choropleth (Annual Ground Rent — not Surface Rent) |
| W3W grid | Current map view | Zoom ≥ 12; every cell up to cap (then sampled) |
| Vacant land | Viewport SVDLS sites | Toggle **Vacant and derelict**; zoom ≥ 8 |
| Coverage | Live vs linked/gap | Sidebar **Coverage** list; live rows toggle overlays |
| Vacant residual story | Council choropleth + overlay | `/?story=vacant_land` |
| Filters | Vacant / public overlays, rent band | `/?vacant=1&public=1&band=high` |
| Click | Any cell | Layer popup (parcel id / area / owner type) + residual place card |

Cadastre ingest: `python -m etl.ingest_inspire_parcels` — see `scripts/data/README-inspire.md`.

Full national 3 m precompute is intentionally not stored (~billions of cells).

## Batch mini-roll (CLI)

```powershell
cd backend
python -m etl.batch_assess --ward18 --samples 12 --out ../data/processed/roll_ward18.csv --format csv --include-sales
```

## When ROS data arrives

1. Save extract under `data/licensed/` with `LICENSE.txt`  
2. Convert if needed (`etl.convert_sales_csv`)  
3. `python -m etl.ingest_sales --path ../data/licensed/sales.jsonl --require-production`  
4. Re-run Ward 18 QA pack — aim for `production_ready` on comps  

## Rules

- No portal scraping  
- Research estimates only until licensed sales + sign-off  
- See `PROFESSIONAL_STANDARD.md` and `DATA_LICENSING.md`  
