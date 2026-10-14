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

Every PR must self-check against this list **before asking for review**. CI enforces the same rules (see `backend/tests/test_no_ledger_word_in_public_json.py` and frontend site-watch scripts). Fail the PR if any item fails.

1. **Banned visitor words** — Fail on visible `ledger` or `natural capital` in public pages or visitor-facing JSON. Code samples on `/developers` are excluded.
2. **No £ figures** — Fail on any £ amount in public pages or public JSON (placeholders and unit labels only; never published money figures).
3. **Group names** — Value/rent group headings must be exactly **Land** / **Natural resource rents** / **Services of nature**. Fail on any other name for those buckets (e.g. “Natural capital”).
4. **Spatial grain** — Fail on anything finer than Data Zone for published modelled/proxy values (no plot / UPRN / parcel / building grain).
5. **Required wording / test follow-ups**
   - `backend/georgist/place_stack.py` outside note must say `outside the Scottish totals`.
   - Runtime public-JSON tests must also ban `natural capital` (extend `test_no_ledger_word_in_public_json.py`).

## Tests
```powershell
cd backend
.\.venv\Scripts\Activate.ps1
python -m pytest tests/ -q
```
