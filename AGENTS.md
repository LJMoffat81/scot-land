# AGENTS.md — working on Scot-LAND

## Product
Build the **open land information platform** described in [docs/PLATFORM.md](docs/PLATFORM.md).

That brief is the destination. Do not rewrite it to match whatever happens to be shipped today. The AGR engine is the core; ownership, cadastral, public-land and vacant-land layers are in scope.

Annual Ground Rent remains first: residual site value on a What3Words 3×3 m grid, SLRG methodology, public education UI.

## Do
- Follow [docs/PLATFORM.md](docs/PLATFORM.md) when choosing what to build next
- Prefer residual valuer logic and documented config
- Use only open or licensed data (see `docs/DATA_LICENSING.md`)
- Keep map residual vs national rent pool distinct
- Make data gaps visible (Sasine, private names, missing public registers)
- Add tests for valuation and data schema changes
- Preserve clarity UI: public £/year first, depth under tabs
- Keep AGR / scenario tools as the analytical centre when adding spatial layers
- **Implement National Wealth aggregation using PostGIS spatial intersections**
- **Ensure `la-calc` calibration is verified against RoS market evidence**

## Do not
- Shrink the platform brief to the current map-only feature set
- Scrape property portals (Zoopla, Rightmove, ESPC, …)
- Commit API keys or full paid datasets
- Present synthetic fixtures as real ROS sales in the UI
- Silently change signed-off `agr.yaml` defaults without notes
- Present research estimates as official valuations or tax bills
- **Do not conflate "Surface Rent" (la-calc) with "AGR" (Residual) in the UI—they are different valuation lenses**

## Key paths
| Path | Role |
|------|------|
| `docs/PLATFORM.md` | Product brief — build toward this |
| `backend/agr/` | Assessment engine (Residual/Scenario) |
| `backend/backend/georgist/` | National Wealth Engine (Aggregation, la-calc, Calibration) |
| `backend/datasources/` | Data contracts and loaders |
| `data/config/` | Parameters and source registry |
| `docs/PROFESSIONAL_STANDARD.md` | Build standard |
| `docs/methodology.md` | Public methodology |

## Tests
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -q
```

## Cursor Cloud specific instructions

- Python 3.12 and Node 22 are already on the default image. Use `backend/.venv` and `frontend/node_modules` after install.
- `backend/georgist/` imports `psycopg2` and `pandas`. Those packages are not in `backend/requirements.txt`. The Cloud Agent install adds `psycopg2-binary`, `pandas`, and `pytest`.
- Local PostGIS follows `backend/docker-compose.yml`: database `scotland_wealth`, user `wealth_user`, password `wealth_password`, host `localhost`, port `5432`. The dev role is a superuser so schema setup can run `CREATE EXTENSION postgis`.
- API command: `cd backend && .venv/bin/uvicorn api.main:app --host 0.0.0.0 --port 8000`. UI command: `cd frontend && npm run dev -- --hostname 0.0.0.0 --port 3000`. In the browser the map calls same-origin `/backend`, which proxies to `http://127.0.0.1:8000`. `W3W_API_KEY` is optional for latitude/longitude assessment.
- `uvicorn api.main:app` currently exits while importing `backend/api/main.py`. `backend/agr/engine.py` imports `agr.valuation`, and that module is not in the tree (along with `agr.wide_range`, `agr.zone_prices`, `agr.sales_comps`, `agr.seabed`, `agr.settlement`, `georgist.surface_rent`, `georgist.surface_harvester`, `layers.vdl`, `layers.public_land`, `layers.registers`, `layers.open_stats`, `validation.glasgow_ward_18`, and `validation.ratio_study`). PostgreSQL, PostGIS, and the Next.js dev server still start. `backend/pytest.ini` sets `testpaths = tests`, and there is no `backend/tests` directory, so pytest exits 4.
