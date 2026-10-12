# Operating the professional tool

## Mandatory post-deploy smoke

After every production or preview deploy, run the smoke scripts before calling
the release good. They must exit **non-zero** on any failure.

```powershell
# PowerShell (Windows / pwsh)
.\scripts\smoke.ps1 -BaseUrl https://YOUR-SITE
# or split front/API:
.\scripts\smoke.ps1 -SiteUrl https://YOUR-SITE -ApiUrl https://YOUR-API
```

```bash
# Bash (Linux / macOS / CI)
./scripts/smoke.sh https://YOUR-SITE
# or:
SITE_URL=https://YOUR-SITE API_URL=https://YOUR-API ./scripts/smoke.sh
```

Checks (pass/fail table printed to stdout):

| Check | Pass when |
|-------|-----------|
| Site `/` | HTTP **200** |
| `GET /health` | HTTP **200** and `git_commit` present |
| Each **live** catalog layer with a bbox `endpoint` | HTTP **200** with **>0** features, **or** HTTP **503** honest not-yet-loaded |

Do not treat empty **200** FeatureCollections as success. Linked/gap catalog
rows without drawable endpoints are skipped.

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
| `GET /square?lat=&lng=` | Live AGR for a Scot-LAND square (`platform` place card attached) |
| `GET /layers/catalog` | Open-land layers with live / linked / gap status |
| `GET /layers/parcels?...` | RoS INSPIRE Index Polygons bbox (PostGIS; **503** if table empty; empty viewport **200** when loaded; CI may use `--fixture`) |
| `GET /layers/parcels/tiles/{z}/{x}/{y}` | Live RoS INSPIRE WMS proxy (soft-fail tiles) |
| `GET /layers/parcels/at?lat=&lng=` | Parcel under a point (live WMS GetFeatureInfo) |
| `GET /layers/open/settlements?...` | NRS Census 2022 settlements bbox (PostGIS; **503** if not loaded) |
| `GET /layers/open/localities?...` | NRS Census 2022 localities bbox (PostGIS; **503** if not loaded) |
| `GET /layers/open/vdl` | SVDLS vacant/derelict sites (bbox; **503** if upstream down) |
| `GET /layers/open/public-land` | Public / Crown Estate overlay (**licence unverified/not open** — hidden from public map; **503** if upstream down) |
| `GET /layers/open/community-ownership` | SG Community Ownership 2024 points (PostGIS; **503** if unloaded; ownership-context, no £ rent) |
| `GET /platform/place` | Ownership / vacant / gap card |
| `GET /platform/gaps` | Visible register gaps |
| `GET /downloads` | Open layer and official source index |
| `GET /api/catalog.json` | Live / linked / gap register |
| `GET /api/roll.json?scenario=` | 32-council AGR roll with SVDLS vacant ha |
| `GET /api/public-land.json` | Hectares by the five published bodies (licence unverified/not open; not listed on open downloads) |
| `GET /api/vdl.json` | SVDLS hectares by owner class |
| `GET /api/place.json?pc=` | Place card (vacant / public / parcel / gaps) |
| `GET /api/common-good.json` | Verified Common Good register links + spatial gaps |
| `GET /api/crofting.json` | Crofting Commission OGL RoC + grazings; PostGIS load status; spatial gaps |
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
| Scot-LAND squares | Current map view | Zoom ≥ 12; every cell up to cap (then sampled) |
| **Vacant and derelict** | SVDLS site-level survey polygons | Ownership and cadastre; site-type legend + credits; zoom ≥ 8; click popup; each site tagged `geometry_source` (Spatial Hub survey > RoS title outline > point) |
| **Community ownership** | SG 2024 OGL asset points | Ownership and cadastre; asset-type legend + OGL credits; zoom ≥ 6; PostGIS postcode centroids (not titles); **503** when unloaded |
| Coverage | Live vs linked/gap | Sidebar **Coverage** list; live rows toggle overlays |
| Vacant residual story | Council choropleth + overlay | `/?story=vacant_land` |
| Filters | Vacant / public overlays, rent band | `/?vacant=1&public=1&band=high` |
| Click | Any cell | Layer popup (parcel id / area / owner type / SVDLS site) + residual place card |

Cadastre ingest (one command each): `--pilot` (Edinburgh/MID + Fife), `--all` (33 counties), or `--fixture` (CI). Self-fetch never writes `data/external/`. See `scripts/data/README-inspire.md`. Licence **OGL-3.0**.

Crofting / common grazings (OGL CSV → PostGIS): `python -m etl.ingest_crofting --download` (raw under `data/external/crofting/`, gitignored). Fixtures: `python -m etl.ingest_crofting --from-fixtures`.

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
