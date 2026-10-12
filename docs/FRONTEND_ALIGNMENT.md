# Frontend alignment — public site vs API (draft)

**Status:** Step 1 inventory and plan only — **docs, not code**.  
**Branch:** `cursor/frontend-alignment-doc-b31e`  
**Baseline:** `main` @ Common Good merge (`#7` / `29f49eb`) and charter `docs/CHARTER.md`.  
**Charter vision:** a free, public, open land map of Annual Ground Rent (land alone) plus who holds land, with honest evidence and visible gaps.

This note inventories what the Next.js app and FastAPI surface today, where they disagree, and a small-PR path toward a clear public site. It does **not** authorise merging HOLD work ([PR #6](https://github.com/LJMoffat81/scot-land/pull/6) AGR → Wealth Engine rewrite; [PR #9](https://github.com/LJMoffat81/scot-land/pull/9) tax scenarios) onto the public map.

---

## Publication geometry rule (must not be broken)

From `docs/wealth_api.md` / `backend/georgist/publication_rules.py`:

- Modelled or proxy land value / rent is published **only on Data Zone (zone) geometry** — never attached to parcel, plot, UPRN or building on a public route.
- Plain shapes (e.g. RoS INSPIRE parcel outlines with **no** value) are fine.
- Site-level public figures only where the **source** is itself public at site level (SVDLS, HLS, business rates) and the figure is **measured**, not modelled.
- Spreading zone rents to plots stays on `/internal` (auth + flag).

Every public route must declare a `LayerRule` in `PUBLIC_ROUTE_RULES`. Undeclared public routes stop the core app; optional routers with undeclared routes are **skipped** at boot (`/health.routers.*.loaded = false`).

---

## (a) Frontend inventory — pages, components, API calls

Proxy pattern: browser calls same-origin `/backend/...` (local) or `NEXT_PUBLIC_API_URL` (deployed). Next also proxies `/api/{name}` → FastAPI `/api/{name}`, `/api/parcels/tiles/...` → `/layers/parcels/tiles/...`, and `/api/context/{layer}/tiles/...` → `/layers/context/{layer}/tiles/...`.

### App routes (pages)

| Page | File | Role | API calls |
|---|---|---|---|
| `/` (home / map) | `frontend/app/page.tsx` → `ScotlandMap` | Primary public surface | See ScotlandMap below |
| `/methodology` | `frontend/app/methodology/page.tsx` → `MethodologyContent` | About / method copy | None (static) |
| `/downloads` | `frontend/app/downloads/page.tsx` | Open downloads index | `GET /downloads`, `GET /health`; hard links to `/api/*.json`, `/api/*.csv`, and `GET /layers/councils?scenario=full_agr` |
| `/open-api` | `frontend/app/open-api/page.tsx` | Public API catalogue copy | SSR `GET /health` (commit stamp); documents many routes (see mismatches) |

### Next.js API proxies (not product pages)

| Path | Upstream |
|---|---|
| `app/api/[name]/route.ts` | `{API}/api/{name}` |
| `app/api/parcels/tiles/[z]/[x]/[y]/route.ts` | `{API}/layers/parcels/tiles/{z}/{x}/{y}` |
| `app/api/context/[layer]/tiles/.../route.ts` | `{API}/layers/context/{layer}/tiles/{z}/{x}/{y}` |
| `app/backend/[...path]/route.ts` | `{API}/{path}` |

### Components

| Component | Used by | API calls / behaviour |
|---|---|---|
| **ScotlandMap** | Home | Capability probe `GET /health` (`fetchCapabilities`). **Wealth path (always):** click → `useWealthApi.lookupWealthAt` → `GET /layers/context/data-zones/at` then `GET /georgist/wealth`; also `GET /layers/parcels/at`. **When `agr` router loaded:** `GET /square`, `GET /place`, `GET /postcode/{pc}`, `GET /layers/councils`, `GET /layers/w3w-grid`, context `GET /layers/context/{id}`, `GET /layers/context/urban-rural/class`, `GET /layers/context/seabed/at`. **When `platform` loaded:** `GET /layers/open/vdl`, `GET /layers/open/public-land`. **Tiles (browser):** `/api/parcels/tiles/...`, `/api/context/{layer}/tiles/...`. **Fallback search:** `GET /geocode/postcode` when AGR absent. |
| **WealthInspector** | ScotlandMap | No fetch — renders Wealth Engine payload from parent |
| **AgrBreakdown** | ScotlandMap | `GET /health` for engine stamp line; renders `/square` (or related) AGR payload from parent |
| **MethodologyContent** | `/methodology` | None |
| **NationalStats** | *orphaned — not imported* | Would call `GET /api/public-land.json`, `GET /api/vdl.json`, `GET /platform/gaps` |
| **CoveragePanel** | *orphaned — not imported* | Presentational only (expects parent-fed coverage lists) |

### Lib helpers

| Module | Role |
|---|---|
| `lib/api.ts` | Base URL, `apiFetch` / `apiJson`, `pingApi`, `fetchCapabilities` (`/health` → `agr` / `platform` loaded flags) |
| `lib/useWealthApi.ts` | Public Wealth clients: data-zones/at, `/georgist/wealth`, `/layers/georgist/surface-rent` (**fetcher exported; no UI caller yet**) |
| `lib/contextLayers.ts` | Allowlisted context layer ids/labels (Sea / Energy / Place / Use) — tiles need AGR context routes |
| `lib/exportUrl.ts` | Cache-bust CSV download links with live commit |

---

## (b) Public backend routes and publication declarations

Source of truth: `backend/georgist/publication_rules.py` → `PUBLIC_ROUTE_RULES`, enforced in `api/main.py` via `check_router`.

Exempt (no declaration): `/health`, OpenAPI/docs paths.  
Internal prefix `/internal/*` is never public (auth + `ENABLE_INTERNAL_ENDPOINTS`).

### Declared and intended public (mounted when their router loads)

| Route | geometry | source | value_basis | Note |
|---|---|---|---|---|
| `/georgist/wealth` | zone | zone | modelled | Data Zone Wealth stack |
| `/layers/georgist/surface-rent` | zone | zone | modelled | DZ surface choropleth JSON |
| `/layers/georgist/resource-rent` | site | site | measured | Site-public sources only |
| `/layers/georgist/eco-rent` | site | site | measured | Site-public sources only |
| `/layers/context/data-zones/at` | zone | zone | none | Code / name / vintage |
| `/geocode/postcode` | site | site | none | Centroid only |
| `/layers/parcels` (+ `/at`, tiles) | parcel | zone | none | Plain RoS shapes |
| `/layers/open/vdl` | site | site | none | SVDLS polygons, no rent |
| `/layers/open/public-land` | site | site | none | Public/Crown overlay, no rent |
| `/platform/place` | site | site | none | Ownership / vacant / gap card |
| `/platform/gaps` | zone | zone | none | Gap catalogue |
| `/api/catalog.json` | zone | zone | none | Catalogue |
| `/api/public-land.json` | zone | zone | none | Download meta |
| `/api/vdl.json` | zone | zone | none | Download meta |
| `/api/vdl-councils.json` | zone | zone | none | Download meta |
| `/api/roll.json` / `/api/roll.csv` | zone | zone | none | Open stats roll |
| `/api/place.json` | site | site | none | Place card download |
| `/api/registers.json` | zone | zone | none | Register links |
| `/api/common-good.json` | zone | zone | none | Common Good links + gaps |
| `/downloads` | zone | zone | none | Download index |

Core wealth + cadastral + geocode always attempt to mount. Platform router is optional (mounts when imports + declarations succeed — Common Good `#7` completed its declarations).

### Legacy AGR router (`api/agr_routes.py`) — all paths undeclared on `main`

On current `main`, **every** AGR path lacks a `PUBLIC_ROUTE_RULES` entry, so the optional AGR router is **skipped at boot** (`routers["api.agr_routes"].loaded = false`). Frontend already gates many calls on that flag.

Undeclared AGR paths (blocked from mounting until declarations land on a dedicated PR — do not conflate with HOLD #6/#9 product decisions):

| Path | Typical role |
|---|---|
| `/signoff`, `/config`, `/sales/status`, `/layers/catalog` | Meta |
| `/boundaries/councils`, `/boundaries/glasgow-ward-18` | Shapes |
| `/layers/councils`, `/layers/councils-agr`, `/fiscal/summary` | Modelled residual / fiscal research |
| `/layers/w3w-grid` | Cell grid |
| `/layers/context/{layer_id}`, `.../tiles/...`, `/urban-rural/class`, `/seabed/at` | Context layers |
| `/square`, `/postcode/{postcode}` | Click / postcode residual AGR |
| `/place`, `/address` | Search (location) |
| `/validation/*`, `/assessment/report` | QA / reports |

**HOLD ([PR #6](https://github.com/LJMoffat81/scot-land/pull/6)):** rewrites place pages toward Wealth Engine figures and keeps rent-bearing AGR **internal** until yield calibration. Treat as **internal / unpublished** for public-site planning.  
**HOLD ([PR #9](https://github.com/LJMoffat81/scot-land/pull/9)):** tax scenario maths on `/internal/georgist/tax-scenario*` only — **no public UI**.

### Internal-only (never public UI)

| Route | Role |
|---|---|
| `/internal/georgist/wealth` | Placeholders + diagnostics with numbers |
| `/internal/georgist/surface-rent/{zone}` | Full surface row |
| `/internal/layers/georgist/resource-rent` | Mock resource features |
| `/internal/layers/georgist/eco-rent` | Mock eco features |
| *(PR #9)* `/internal/georgist/tax-scenario*` | Capture-rate scenarios, always `publication_status=blocked` |
| *(PR #6)* `/internal/agr/*` | Unpublished AGR / Wealth place tooling |

---

## (c) Mismatch table

### Frontend calls with no / blocked public route (today on `main`)

| Frontend call | Why it fails / is gated | Severity |
|---|---|---|
| `/square`, `/place`, `/postcode/{pc}` | AGR router skipped (undeclared) | High for residual AGR UX; Wealth path still works |
| `/layers/councils`, `/layers/w3w-grid` | AGR skipped | High — map choropleth / cell grid |
| `/layers/context/*` (+ Next tile proxy) | AGR skipped | High — Sea/Energy/Place/Use overlays |
| `/layers/context/urban-rural/class`, `/seabed/at` | AGR skipped | Medium — click labels |
| Downloads / Open API links to `/layers/councils`, `/square`, `/assessment/report` | Documented but AGR skipped; pages do not capability-gate | High — broken public docs |
| `/api/place.json` rent copy on downloads | Platform may mount; roll/place figures subject to HOLD #6 policy (no public rents before calibration) | Medium — honesty |

### Public / declared routes with little or no UI

| Route | Gap |
|---|---|
| `/layers/georgist/surface-rent` | Hook exists; **no map layer** paints it |
| `/layers/georgist/resource-rent`, `/eco-rent` | Declared; empty/503 until real measured rows; UI correctly avoids mocks |
| `/platform/place`, `/platform/gaps` | Declared; **NationalStats / CoveragePanel orphaned** — gaps not first-class on map |
| `/api/common-good.json` | On downloads/open-api lists; no map layer (honest: links only, no national geometry) |
| `/api/catalog.json`, `/api/registers.json` | Downloads only |
| `/geocode/postcode` | Used as fallback when AGR absent — good |

### Orphan / stale UI and copy

| Item | Issue | Charter fit |
|---|---|---|
| `layout.tsx` metadata `title: "SCOT-LAND MEGA BUILD 2026"` | Stale internal codename in browser tab | Fail — public brand should be Scot-LAND |
| `MethodologyContent`: “We never show who owns land…” | Contradicts charter / PLATFORM ownership layers | Fail — rewrite toward “who holds land” + honest private/Sasine gaps |
| `NationalStats`, `CoveragePanel` | Built but unused | Missed coverage / snapshot UX |
| Open API advertises residual `/square` & `/assessment/report` as public | Routes not mounted on `main` | Stale docs |
| About page still describes council home-plot residual method as the click story | Live click path is increasingly Wealth Engine / Data Zone | Stale method story |
| Surface Rent vs AGR labels | Risk of conflating la-calc Surface Rent with residual AGR | Must stay distinct in UI |

### Parallel work — do not interfere

| Work | Status | This plan |
|---|---|---|
| AGR publication declarations / live map fix | Urgent separate thread | Inventory only; no code on that branch |
| [SVDLS #8](https://github.com/LJMoffat81/scot-land/pull/8) | Open; rebase settling | Consume when merged; no competing VDL edits here |
| [PR #6](https://github.com/LJMoffat81/scot-land/pull/6) / [PR #9](https://github.com/LJMoffat81/scot-land/pull/9) | HOLD / internal until yield calibration | Keep **internal**; public site must not depend on merging them |

---

## (d) Proposed simple public site structure

Keep five public destinations. Depth under tabs/panels; public £/year first; research-estimate labelling always.

| Destination | URL (proposal) | Job | Data Zone rule |
|---|---|---|---|
| **Home / map** | `/` | Free open map: zone-level Surface / Wealth figures when publishable; parcel + public-land + VDL **shapes**; search by postcode | Modelled rents only as **Data Zone** (or coarser council) layers — never on parcel fill |
| **Place card** | Panel on map (+ optional `/place?…` later) | One location: zone Wealth / surface views, ownership & vacant flags from platform, gap flags, ScotLIS link | Card may show zone figures + plain parcel outline; no modelled £ on the parcel polygon |
| **Layers & sources** | Map control + `/downloads` | Toggle layers; attribution; open JSON/CSV | Context tiles are shapes/labels only |
| **About / method** | `/methodology` (rename nav to About) | Charter-aligned story: AGR + who holds land; Surface Rent ≠ residual AGR; not a tax bill | Explain zone publication rule in plain English |
| **Coverage gaps** | Dedicated panel (wire `CoveragePanel` / `/platform/gaps`) | Sasine, private names, LA holdings outside five bodies, Common Good spatial gap | Gaps are first-class product |

**Explicitly internal (not in public nav):** Wealth Engine rewrite place pages ([#6](https://github.com/LJMoffat81/scot-land/pull/6)), tax scenario tools ([#9](https://github.com/LJMoffat81/scot-land/pull/9)), `/internal/*`, validation packs, W3W cell residual diagnostics.

**Nav sketch:** Map · Layers & downloads · About · Gaps (Gaps can start as a map panel before a route).

---

## (e) Phased build plan — small PRs

Each phase is one focused PR. No merges assumed here. Do not touch `data/external`. Avoid colliding with urgent AGR-declaration and SVDLS #8 branches.

| Phase | PR scope | Depends on | Notes |
|---|---|---|---|
| **0 — this PR** | `docs/FRONTEND_ALIGNMENT.md` only | — | Alignment contract |
| **1 — Copy hygiene** | Replace `SCOT-LAND MEGA BUILD 2026`; fix About ownership sentence; Surface Rent ≠ AGR glossary line | Phase 0 | Docs/UI strings only |
| **2 — Public docs honesty** | `/open-api` + `/downloads` list only routes that mount on `main` (or capability-gate); drop/relabel residual `/square` until declared+mounted | Phase 1; coordinate with AGR declaration PR | No new backend |
| **3 — Wire coverage UI** | Mount `CoveragePanel` + `NationalStats` (or slim equivalents) on map using `/platform/gaps` + open JSON | Platform router mounted | Honest gaps |
| **4 — Zone surface layer** | Paint `/layers/georgist/surface-rent` as Data Zone choropleth; attribution; withheld counts | PostGIS surface rows publishable | Respect blocked/internal rows |
| **5 — Context layers mount** | After AGR **non-rent** context routes are declared+mounted (separate urgent PR), restore Sea/Energy/Place/Use tiles | AGR declaration PR (non-HOLD) | Still no modelled rent on parcels |
| **6 — Place card v1** | Public card from Wealth + `/platform/place` + parcel outline; no tax scenarios | Phases 3–4 | Keep #6/#9 internal |
| **7 — SVDLS promote** | Consume [#8](https://github.com/LJMoffat81/scot-land/pull/8) when ready; map + downloads already partially wired | #8 merge | Site shapes, no modelled rent |
| **8 — Open API polish** | Stable public catalogue matching mounted routes; version stamp | Phases 2–5 | After tax scenarios stay internal |
| **Later (gated)** | Public tax scenarios / AGR residual revival | Laurie + yield calibration; #6/#9 leave HOLD | Out of public v1 path until unblocked |

---

## Acceptance for later frontend work

- Public map never attaches modelled rent to parcel/plot geometry.
- Research estimate / not a bill labelling retained.
- Surface Rent (la-calc) and residual AGR never presented as the same figure.
- Gaps (Sasine, private names, missing registers) remain visible.
- Internal HOLD PRs (#6, #9) stay off the public nav and public routes.

---

## Appendix — file map (quick)

```
frontend/app/page.tsx                 → map
frontend/app/methodology/page.tsx     → about
frontend/app/downloads/page.tsx       → downloads
frontend/app/open-api/page.tsx        → API catalogue
frontend/components/ScotlandMap.tsx   → main client
frontend/components/WealthInspector.tsx
frontend/components/AgrBreakdown.tsx
frontend/components/NationalStats.tsx     (orphan)
frontend/components/CoveragePanel.tsx     (orphan)
frontend/lib/api.ts / useWealthApi.ts / contextLayers.ts
backend/georgist/publication_rules.py → PUBLIC_ROUTE_RULES
backend/api/{main,wealth,cadastral,geocode,platform,agr,internal}_routes.py
```
