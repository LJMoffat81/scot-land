# AGENTS.md — working on Scot-LAND

## Workflow

Grok Bot plans and writes PRDs; the Repo Outer Loop bot sends coding prompts to the Cursor Project `scot-land`. Cursor does all coding. No single writer. Pull the latest `main` first and never discard others' uncommitted work. Full rule: `C:\Projects\.cursor\rules\two-tool.mdc`.

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
| `backend/georgist/` | National Wealth Engine (Aggregation, la-calc, Calibration) |
| `backend/datasources/` | Data contracts and loaders |
| `data/config/` | Parameters and source registry |
| `docs/PROFESSIONAL_STANDARD.md` | Build standard |
| `docs/methodology.md` | Public methodology |

## Pre-review checklist

Every PR must self-check against this list **before asking for review**. Fail the PR if any item fails.

Tag each line: **CI** = covered by an automated check today; **hand** = reviewer confirms.

### Always (public surface)

| Check | Who |
|-------|-----|
| Fail on visible `ledger` or `natural capital` (code samples on `/developers` excluded) | **CI** |
| Fail on any £ figure in public pages or public JSON | **CI** |
| Fail on value/rent group names other than Land / Natural resource rents / Services of nature (`RENT_GROUP_NAMES`) | **CI** |
| Fail on anything finer than Data Zone for published modelled/proxy values | **CI** |
| `place_stack` outside note says `outside the Scottish totals` | **CI** |
| Runtime public JSON also bans `natural capital` | **CI** |

### Pass / fail (from prior PRs)

| Check | Who |
|-------|-----|
| Every layer has a label and licence credit, including the OS credit on parcels (#82) | **CI** |
| The holdout is pre-registered before scoring (#84) | **CI** |
| `class_min` comes from settings, default 10, never hard-coded (#84) | **CI** |
| Money tests are exact, with no approx, and order tests force each fill step, including the island to Scotland-wide fallthrough (#84) | **CI** |
| The PR is rebased on main and merges cleanly, especially `check_publishable.py` and its test (#87) | **hand** |
| Guard changes only add rules, never loosen one | **hand** |
| The banned visible words `ledger`, `natural capital` and `headline/shadow` are checked in the built HTML **and** the runtime JSON (#87) | **CI** |
| Never show `No data` when the code is known; show `name not loaded yet` (#87) | **CI** |
| Jargon is fixed at the source (`platform.py` and its developer notes), with a backend test that runs without `BACKEND_URL` (#87) | **CI** |
| `main.py` and `AGENTS.md` stay untouched unless an add-only change is approved | **hand** |
| SLRG wording: Annual Ground Rent comes before land value tax; “Why it matters” is used word for word; the chips are Market/Modelled/Estimate with API values unchanged; the constraint line reads `Constraint: changes best use, adds no value`; totals are per chip only | **CI** |
| e2e tests run at the stated widths and fail on console errors | **hand** |

## Tests
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -q
```
