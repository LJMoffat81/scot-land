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
