# Frontend alignment — what3words-style public shell (draft)

**Status:** Docs only. Draft PR until Laurie explicitly marks ready. **Do not merge.**  
**Branch:** `cursor/frontend-alignment-doc-b31e`  
**Baseline:** `main` after SVDLS `#8` + AGR publication mount `#11` (`026432f`) and charter `docs/CHARTER.md`.  
**Direction (Laurie approved):** **what3words-style** — full-screen map, one big search (postcode / place / coordinates), click anywhere → clean place card. Simple and friendly for non-experts.

**Charter vision:** a free, public, open land map of Annual Ground Rent (land alone) plus who holds land, with honest evidence and visible gaps.

**Keep internal / unpublished:** [PR #6](https://github.com/LJMoffat81/scot-land/pull/6) (AGR → Wealth Engine rewrite) and [PR #9](https://github.com/LJMoffat81/scot-land/pull/9) (tax scenarios). No public modelled plot-level AGR £ and no public tax-scenario UI until yield calibration.

---

## Publication geometry rule (must not be broken)

From `docs/wealth_api.md` / `backend/georgist/publication_rules.py`:

- Modelled or proxy land value / rent is published **only on Data Zone (zone) geometry** (or coarser council grain where declared) — never attached to parcel, plot, UPRN or building on a public route.
- Plain shapes (e.g. RoS INSPIRE parcel outlines with **no** value) are fine.
- Site-level public figures only where the **source** is itself public at site level (SVDLS, HLS, business rates) and the figure is **measured**, not modelled.
- Plot / W3W cell residual AGR £ lives on `/internal/agr/...` (auth + flag) after `#11`.

Every public route declares a `LayerRule` in `PUBLIC_ROUTE_RULES`. Undeclared public routes stop the core app or skip the optional router.

---

## How the browser reaches the API

| Browser path | Upstream |
|---|---|
| `/backend/{path}` | FastAPI `/{path}` (local / same-origin proxy) |
| `/api/{name}` | FastAPI `/api/{name}` |
| `/api/parcels/tiles/{z}/{x}/{y}` | `/layers/parcels/tiles/...` |
| `/api/context/{layer}/tiles/...` | `/layers/context/{layer}/tiles/...` |

Capability probe: `GET /health` → `routers["api.agr_routes"].loaded` / `api.platform_routes`.

---

## 1. Backend audit (start: `GET /layers/catalog`)

`GET /layers/catalog` returns `platform_catalog()` (`backend/layers/platform.py`). Same layer list feeds gap thinking via `GET /platform/gaps`.

### Catalog layers (source of truth for “what the product claims”)

| Catalog `id` | Catalog status | Endpoint / access | Licence / source (catalog) | Reality after `#8` / `#11` |
|---|---|---|---|---|
| `agr_value` | **live** | *(none on public plot grain)* | — | **Drift.** Plot residual AGR is `/internal/agr/square` only. Public Wealth is zone-level `/georgist/wealth`. Catalog still says “W3W cells and notional plots”. |
| `boundaries` | live | `/layers/parcels` (+ tiles) | OGL / INSPIRE (Crown); ros.gov.uk/open-data | Live shapes; 503 when PostGIS unload; tiles via WMS proxy |
| `cell_grid` | **live** | *(none public)* | — | **Drift.** Grid is `/internal/layers/w3w-grid`. UI still calls public `/layers/w3w-grid` → 404 |
| `vdl` | live | `/layers/open/vdl` **(bbox required)** | OGL-3.0; SVDLS register | Live after `#8`; honest 503 when source down |
| `public_crown` | live | `/layers/open/public-land` **(bbox)** | SG 2024 five-body map | Live; not LA land; not a title |
| `la_holdings` | gap | Spatial Hub link only | Not open for portal | Correct gap |
| `planning` | linked | `/api/registers.json` + ePlanning | Official pages | Links, no national WMS |
| `council_assets` | linked | Spatial Hub URLs | Login-gated | Not mirrored |
| `common_good` | linked | `/api/common-good.json` | Council pages; Fife OS INSPIRE EUL linked only | **Link-only** — no national open map overlay |
| `fife_land_map` | linked | ArcGIS hub URL | Council hub | Not national |
| `sasine_private` | gap | — | Incomplete / paid | Correct gap — show honestly |

### Catalog tools (also drift-prone)

| Tool id | Catalog status | Public reality |
|---|---|---|
| `scenarios` | live | **Drift.** Tax / LVT scenarios → HOLD `#9` `/internal` only |
| `api` | live | Partial — many public routes; residual `/square` gone public |
| `downloads` | partial | `/downloads` + `/api/*.json` live when platform mounts |
| `scotlis` | live | Links only (correct) |
| `filters` | partial | Not a first-class w3w UI yet |

### Other live / declared public endpoints (not every row is a map layer)

| Endpoint | Publication | Role |
|---|---|---|
| `/health` | exempt | Liveness + router flags |
| `/layers/catalog` | zone / none | Catalog above |
| `/layers/councils` | zone / **modelled** | Council multi-metric choropleth (includes research AGR fields at **council** grain) |
| `/boundaries/councils`, `/boundaries/glasgow-ward-18` | none | Boundary shapes |
| `/layers/context/{id}` (+ tiles) | none | Sea / Energy / Place / Use overlays (`frontend/lib/contextLayers.ts`) |
| `/layers/context/urban-rural/class` | none | Class label at point |
| `/layers/context/seabed/at` | none | Crown Estate lease note at point |
| `/layers/context/data-zones/at` | none | Data Zone code / name / vintage |
| `/geocode/postcode` | none | Postcode → lat/lng only |
| `/postcode/{postcode}` | none | Centroid only (AGR £ on `/internal/agr/postcode/...`) |
| `/place`, `/address` | none | Search → location only |
| `/signoff`, `/config`, `/sales/status` | none | Meta |
| `/georgist/wealth` | zone / modelled | Wealth Inspector payload (Data Zone) |
| `/layers/georgist/surface-rent` | zone / modelled | DZ surface JSON (no map paint yet) |
| `/layers/georgist/resource-rent`, `/eco-rent` | site / measured | Empty/503 until real rows |
| `/layers/parcels`, `/at`, tiles | parcel / none | Cadastral shapes |
| `/layers/open/vdl`, `/public-land` | site / none | Viewport overlays |
| `/platform/place` | site / none | Ownership / vacant / gap card JSON |
| `/platform/gaps` | zone / none | Live vs gap lists |
| `/api/catalog.json`, `public-land.json`, `vdl.json`, `vdl-councils.json`, `roll.json`, `roll.csv`, `place.json`, `registers.json`, `common-good.json` | none | Open downloads / tables |
| `/downloads` | none | Download index |

### Internal only (never public nav / place card £)

| Endpoint | Role |
|---|---|
| `/internal/agr/square`, `/internal/agr/postcode/...` | Plot residual AGR £ (`publication_status=blocked`) |
| `/internal/layers/w3w-grid` | Cell grid with rents |
| `/internal/agr/layers/councils-agr`, `/internal/agr/fiscal/summary` | AGR choropleth / fiscal |
| `/internal/agr/assessment/report`, `/internal/agr/validation/*` | Reports / QA |
| `/internal/georgist/*` | Wealth diagnostics / mocks |
| `#9` `/internal/georgist/tax-scenario*` | Tax capture maths |

---

## 2. Single matrix — backend capability → UI today → w3w target

| Capability | Backend | UI today | w3w target (public) |
|---|---|---|---|
| Full-screen map shell | — | `ScotlandMap` (busy: metrics, scenarios, dual panels) | **Home:** map edge-to-edge; brand light; one search |
| Search postcode | `/geocode/postcode` or `/postcode/{pc}` | Split: geocode fallback vs `/place` when AGR up | **One search box** → fly to point → open place card |
| Search place / address | `/place`, `/address` | Used when `agr` loaded | Same search box (location only) |
| Search coordinates | client parse | Partial / URL params | Accepted in the same search |
| Click → place | mixed `/square` + Wealth | Still calls **public `/square`** (404 after `#11`) + WealthInspector + AgrBreakdown | **Clean place card** from `/platform/place` + DZ Wealth (zone £ only) + parcel outline; no plot AGR £ |
| Data Zone lookup | `/layers/context/data-zones/at` | Wealth click path | Place card context line |
| Zone Wealth / Surface Rent | `/georgist/wealth`, `/layers/georgist/surface-rent` | Inspector panel; surface layer **unpainted** | Place card primary £ (research estimate); optional DZ choropleth toggle later |
| Council choropleth | `/layers/councils` | Drawn when AGR up | Layers panel toggle; label research estimate; **not** plot AGR |
| ROS parcels | `/layers/parcels` + tiles | On by default at zoom | Layers panel toggle + source/licence |
| Public / Crown land | `/layers/open/public-land?bbox` | Viewport fetch | Layers panel toggle + source/licence |
| Vacant / derelict | `/layers/open/vdl?bbox` | Viewport fetch | Layers panel toggle + source/licence |
| Common Good | `/api/common-good.json` | Downloads / open-api lists only | Layers panel: **linked** row (open registers), honest “no national map” |
| Context overlays (sea, energy, …) | `/layers/context/{id}` + tiles | Toggles when AGR up | Layers panel groups; each with attribution |
| Urban-rural / seabed at point | context `.../class`, `seabed/at` | Click side-effects | Place card footnotes |
| Coverage gaps | `/platform/gaps`, catalog gaps | **CoveragePanel orphaned** | Dedicated gaps entry + panel |
| National snapshot stats | `/api/public-land.json`, `/api/vdl.json` | **NationalStats orphaned** | Optional secondary strip — not in first viewport |
| Open downloads | `/downloads`, `/api/*` | `/downloads` page | “Layers & sources” / downloads |
| Public API docs | `/open-api` | Still lists **`/square`**, `/assessment/report` | Rewrite to mounted public routes only |
| About / method | `/methodology` | Static; ownership copy stale | About under w3w chrome |
| Catalog API | `/layers/catalog` | Not driving UI | **Drive layers panel** (live toggleable; linked/gap honest) |
| Plot AGR / W3W grid / tax scenarios | `/internal/...` | Map still probes public `/square`, `/layers/w3w-grid` | **Hidden** from public UI (#6/#9 internal) |

**Rule for the layers panel:** every catalog layer with `status: live` must be toggleable, with **source + licence** visible. `linked` → open official link, say not on the map. `gap` → say unavailable and why. Never invent geometry.

---

## 3. Mismatch / drift list (capture)

| Item | Problem |
|---|---|
| `layout.tsx` title `SCOT-LAND MEGA BUILD 2026` | Stale codename in browser tab |
| Catalog `agr_value` / `cell_grid` = live | Public plot AGR + W3W grid moved to `/internal` (`#11`) |
| Catalog tool `scenarios` = live | Tax scenarios HOLD `#9` internal |
| `ScotlandMap` → `GET /square` | Public route removed; should not drive public place card |
| `ScotlandMap` → `GET /layers/w3w-grid` | Now `/internal/layers/w3w-grid` only |
| `/open-api` lists `/square` + `/assessment/report` | Stale; assessment is internal |
| `/downloads` links council AGR GeoJSON OK; copy may oversell plot rents | Align wording with council-grain / zone Wealth |
| `CoveragePanel`, `NationalStats` | Built, **not imported** |
| `fetchSurfaceRentLayer` | Exported, unused — no DZ choropleth UI |
| `MethodologyContent` “We never show who owns land…” | Contradicts charter (who holds land + honest gaps) |
| Surface Rent vs residual AGR | Risk of conflation — keep distinct labels |
| HOLD `#6` / `#9` | Must stay off public nav and public £ UX |

---

## 4. Proposed public structure — w3w shell

Five public jobs, one chrome:

| Piece | Job | Notes |
|---|---|---|
| **Home / map** | Full-bleed map; Scot-LAND present; **one** search (postcode / place / coordinates) | No hero clutter; no scenario calculators; no MEGA BUILD |
| **Place card** | Click or search → clean card: place name/postcode, who-holds flags (`/platform/place`), zone Wealth / surface views when publishable, parcel outline if any, ScotLIS link, gap notes | **No** public modelled plot AGR £; **no** tax scenarios |
| **Layers & sources** | Simple panel driven by `/layers/catalog` (+ context allowlist): toggle live layers; show source + licence; linked/gap rows honest | VDL/public-land need bbox fetches; Common Good = links |
| **About / method** | Short, friendly; research estimate ≠ bill; Surface Rent ≠ residual AGR; Data Zone rule in plain English | Fix ownership sentence |
| **Coverage gaps** | Sasine, private names, LA holdings, Common Good spatial gap | First-class; wire `CoveragePanel` or slim twin |

**Internal (not in public shell):** `#6`, `#9`, `/internal/*`, validation packs, W3W rent grid, residual `/square`.

---

## 5. Phased build plan — small PRs only

Each phase = one PR on its own branch. Never merge from this doc PR. Do not touch `data/external`. Do not collide with unrelated urgent branches.

| Phase | PR | Outcome |
|---|---|---|
| **0 — this doc** | `#10` (draft) | Alignment contract + matrix + w3w direction |
| **1 — Shell + search** | New | Full-screen map chrome; one search (postcode/place/coordinates via `/geocode/postcode` + `/place`); fly-to; drop public `/square` from click path; metadata title fix |
| **2 — Layers panel** | New | Panel driven by `/layers/catalog` + context layers; every live layer toggleable with source/licence; linked/gap honest; bbox for VDL + public-land; Common Good link row |
| **3 — Place cards** | New | Clean card: `/platform/place` + DZ Wealth + parcel-at; gaps + ScotLIS; no plot AGR £; no tax UI |
| **4 — Cleanup + drift check** | New | Fix `/open-api` + `/downloads` + About copy; remove dead `/square`/`w3w-grid` public calls; wire or delete orphans (`CoveragePanel`/`NationalStats`); catalog status drift test (`agr_value`/`cell_grid`/`scenarios` must not claim public live plot rents); CI green |

**Later (gated):** public DZ surface choropleth polish; any unblocking of `#6`/`#9` only after Laurie + yield calibration.

---

## Acceptance checks (for later code PRs)

- [ ] Public map never attaches modelled rent to parcel/plot geometry.
- [ ] Place card works from search **or** map click with the same card.
- [ ] Every `live` catalog layer is toggleable with source + licence; unavailable states are honest.
- [ ] No public tax scenarios; no public plot AGR £ (`/square` / W3W rent grid).
- [ ] Surface Rent (la-calc) and residual AGR never presented as the same figure.
- [ ] Research estimate / not a bill labelling retained.
- [ ] Browser title is Scot-LAND, not MEGA BUILD.

---

## Appendix A — Frontend file map

```
frontend/app/page.tsx                 → map home
frontend/app/methodology/page.tsx     → about
frontend/app/downloads/page.tsx       → downloads
frontend/app/open-api/page.tsx        → API catalogue (stale)
frontend/components/ScotlandMap.tsx   → current client (to become w3w shell)
frontend/components/WealthInspector.tsx
frontend/components/AgrBreakdown.tsx  → residual AGR UI (retire from public path)
frontend/components/NationalStats.tsx     (orphan)
frontend/components/CoveragePanel.tsx     (orphan)
frontend/lib/api.ts / useWealthApi.ts / contextLayers.ts
backend/layers/platform.py            → /layers/catalog
backend/georgist/publication_rules.py → PUBLIC_ROUTE_RULES
backend/api/{main,wealth,cadastral,geocode,platform,agr,internal}_routes.py
```

## Appendix B — Context layers allowlist (`contextLayers.ts`)

Sea: `sea-12nm`, `marine-regions`, `scottish-zone`, `harbours`, `seabed-leases`.  
Energy: `oil-fields`, `platforms`, `pipelines`, `wind-leases`, `wind-plan`, `wave-tidal`, `renewables`.  
Place: `data-zones`, `settlements`, `urban-rural`, `flood`.  
Use: `woodland`.  

All are shapes/labels via `/layers/context/...` — no modelled land AGR on the tile.
