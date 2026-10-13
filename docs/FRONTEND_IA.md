# Frontend information architecture — Natural capital ledger

Status: **draft** — Laurie feedback on [#49](https://github.com/LJMoffat81/scot-land/pull/49).  
Scope: product IA only (no application code).  
Related: [PLATFORM.md](PLATFORM.md), [CHARTER.md](CHARTER.md), [ECONOMIC_RULES.md](ECONOMIC_RULES.md), `GET /layers/catalog`.

**Do not finalise** this IA until Laurie forwards the **Georgist accounting rules**. This file is a working draft so loaders and catalog work can continue against a clear product shape.

**Pause:** do not merge new map-panel / layers-pop-out UI until the ledger IA (and accounting rules) are agreed.  
**Continue:** backend loaders, PostGIS ingest, catalog entries, place APIs, Data-section content.

---

## Claim the UI must prove

Scot-LAND’s public front end is not a GIS layer browser. It is a **Natural capital ledger** that proves, for Scotland and for one place:

1. **All natural capital is accounted for** — every rent class has a ledger row (counted, partial, not yet, or excluded with why).  
2. **No double counting** — **one rent per hectare per use**; a hectare does not pay twice for the same use.  
3. **Three stacks stay separate:** **surface** land rent, **resource** rent, and **eco** rent (eco later).  
4. **Overlays change best permitted use; they never add value.** Designations, flood, crofting, LCA, etc. constrain which use wins — they are not rent lines.  
5. Every figure carries a tag: **market** (observed), **proxy** (modelled), or **shadow** (no market price).

Raw spatial datasets (parcels, registers, downloads) live in the **Data** section. The map’s primary panel is the ledger, not a checklist of GeoJSON layers.

---

## 1. Map shell

### Job

Full-bleed Scotland map, brand-level product name, **one search** (postcode / place / coordinates), place card on click, and a **Natural capital ledger** panel. AGR / scenario tools remain the analytical centre once publication rules allow.

### Curated map default (paint)

| Element | Role |
|---|---|
| **Search** | Find a place; same contract as map click → place card |
| **Scot-LAND squares** (`cell_grid`) | Grid context at suitable zoom; public £ withheld until yield calibration |
| **Data Zone boundaries** (`data_zones`) | Statistical frame; no plot AGR £ on the map |

Ownership outlines, resource geometries, and constraint polygons paint only when the matching **ledger row toggle** (or Constraints toggle) is on — and only where that rent or constraint applies. Prefer vector tiles / zoom-simplified geometry; never national raw GeoJSON for paint.

### What replaced the layers pop-out

Earlier drafts organised the UI as five GIS **themes** (Land & ownership, Nature, Energy, Sea, Planning). That shape invites every catalog layer onto the map and does not prove the Georgist claim.

**Replacement:** one **Natural capital ledger** panel (below). Themes are gone from the product IA. Catalog `group` fields remain an implementation detail for Data / API.

---

## 2. Natural capital ledger panel

The ledger is the primary HUD control beside the map. It answers: *what natural capital have we counted, and can two lines charge the same hectare for the same use?*

### Accounting rules (UI must enforce)

| Rule | UI consequence |
|---|---|
| One rent per hectare per use | Place view shows a **per-hectare stack**; mutually exclusive uses for the same hectare are not summed as if both fully apply |
| Surface / resource / eco separate | Ledger sections (or clear section headers); never one blended “total natural capital £” that hides double count |
| Overlays never add value | **Constraints** group is visually distinct — no £ column, no rent tag |
| Tags market / proxy / shadow | Every counted or partial row shows exactly one tag |
| Honest coverage | Status is always one of: **counted** · **partial** · **not yet** · **excluded** (+ why) |

Exact stacking arithmetic, Pickard factors, carbon price, and publication of £ figures wait on Laurie’s **Georgist accounting rules** (forthcoming). Until then: structure and status language only; no public tax bill UX.

### Ledger rows

Each row has:

- **Label** (rent class)  
- **Status:** `counted` | `partial` | `not yet` | `excluded` (+ short why)  
- **Tag:** `market` | `proxy` | `shadow` (omit only when `excluded` or `not yet` with no estimate)  
- **One toggle:** paints where this rent class applies on the map (off by default except as noted for shell defaults). Toggle does **not** invent a second rent line.

| # | Ledger row | Stack | Status (draft) | Tag (draft) | Notes |
|---|---|---|---|---|---|
| 1 | **Surface land** | surface | partial | proxy | AGR / Data Zone surface rent; plot £ withheld until calibration |
| 2 | **Wind — onshore** | resource | not yet → partial when REPD lands | proxy | REPD inventory; no £ rent on overlay |
| 3 | **Wind — offshore** | resource | not yet → partial when ScotWind/INTOG lands | market or proxy | Seabed options; fees as config constant, not a second layer sum |
| 4 | **Sea / aquaculture** | resource | not yet → partial when CES seabed lands | proxy | Biomass HOLD until licence clear |
| 5 | **Hydro / water** | resource | partial | proxy | SEPA hydropower sites live; full CAR download-only → Data |
| 6 | **Minerals** | resource | partial / excluded | proxy | BritPits **OGL index only**; full BritPits / BGS **excluded** (paid) |
| 7 | **Forestry** | resource | not yet | proxy | NFI / woodland when loaded; inventory ≠ automatic rent |
| 8 | **Peat / carbon** | resource | not yet | shadow or proxy | Peatland ACTION / Carbon & Peatland; carbon £ waits on Laurie |
| 9 | **Fisheries** | resource | not yet | proxy | ICES landings → prefer Data until map value is clear |
| 10 | **Oil & gas** | resource | not yet | proxy | NSTA non-commercial; Scottish-waters share rules TBD |
| 11 | **Foreshore / cables** | resource | not yet | proxy | CES cables / foreshore / moorings when licence clear |
| 12 | **Eco** | eco | not yet | shadow | Later module — biodiversity / ecosystem services |

Statuses above are **draft** from current catalog + queued PRs. Re-tag when Georgist accounting rules arrive.

### Constraints group (not rent)

Separate block under the ledger — **changes best use, adds no value**:

| Constraint | Role |
|---|---|
| Designations (e.g. SSSI) | Restricts permitted use |
| Flood maps | Use / risk constraint (OGL download ingest only) |
| Crofting / common grazings | Tenure / use constraint (no personal List of Individuals) |
| Land Capability for Agriculture (LCA) | Capability constraint (Hutton licence + credit) |

Each constraint: status (available / linked / gap / excluded+why), **no** market/proxy/shadow rent tag, **one** map toggle for where it applies. Never a £ column.

### Ownership & cadastre (context, not ledger rent)

Title/context layers (ROS INSPIRE parcels, public/Crown when OGL-verified, VDL, Common Good, community ownership, LA holdings gap, Sasine gap) are **not** extra rent rows. They answer *who holds / what outline* and may appear:

- as secondary toggles under Surface land or place view, or  
- as Data-section / place-page facts only  

They must not add a parallel £ line that double-counts surface rent.

---

## 3. Place view — per-hectare stack

### Place card (map HUD)

Short proof, not a layer dump:

- Where (postcode, council, Data Zone)  
- **Stack summary:** which ledger rows apply here (hit / miss / not yet / excluded)  
- Dominant or permitted **best use** after constraints (when rules exist)  
- Action: **Open full place**

### Full place page

Per-hectare (or per-parcel / per-square) **stack** that proves once-per-use:

```
Surface land     ……  £/ha  [proxy]     counted|partial|…
Wind onshore     ……  —                 not applicable here
Hydro / water    ……  £/ha  [proxy]     partial
…
Constraints      ……  SSSI → best use limited to …
Total by stack   ……  surface Σ | resource Σ | eco Σ   (never one naive double-count sum)
```

Rules for combining rows wait on Georgist accounting. Until then show **status + tag + presence**, and withhold published £ where ECONOMIC_RULES / calibration block.

---

## 4. Data section (raw data)

**Downloads** + **Public API** = one **Data** section (sibling pages or tabs; nav: Map · Data · About).

Raw datasets, licences, credits, vintages, bulk files, and API endpoints live here — driven by `GET /layers/catalog` (and downloads index). The ledger cites Data for “what geometry backs this row”; Data does not replace the ledger.

Every catalog entry lists: dataset, licence + `licence_url` + credit, vintage, access path, and **ledger role** (`rent-row` | `constraint` | `ownership-context` | `data-only`).

---

## 5. Layer → ledger role (current + queued)

Class keys for implementers (replacing map-default / theme-optional as the primary taxonomy):

- **ledger-default-paint** — on map first paint (shell only).  
- **ledger-row** — rent line in the Natural capital ledger (toggle paints applicability).  
- **constraint** — Constraints group.  
- **ownership-context** — who/outline; not a rent.  
- **data-only** — catalog / downloads / API; no ledger rent toggle.

### Current catalog (`main`)

| Id | Role | Ledger / note |
|---|---|---|
| `cell_grid` | ledger-default-paint | Surface grid context; £ withheld |
| `data_zones` | ledger-default-paint | Frame for surface partials |
| `agr_value` | ledger-row (surface) / data-only £ | Surface land; public plot £ blocked |
| `boundaries` | ownership-context | Cadastre outlines |
| `vdl` | ownership-context | Vacant/derelict survey — use context, not extra rent |
| `public_crown` | ownership-context | Hide if OGL unverified (#38) |
| `hydro_sites` | ledger-row | Hydro / water (partial, proxy) |
| `sepa_car` | data-only | download_only register export |
| `la_holdings` | data-only | gap — not open |
| `planning` | data-only | linked ePlanning |
| `council_assets` | data-only | login-gated |
| `common_good` | ownership-context / data-only | linked registers on `main` |
| `fife_land_map` | data-only | single-council hub |
| `sasine_private` | data-only | honest gap |

### Queued / in-flight

| Layer / PR | Role | Ledger row |
|---|---|---|
| REPD onshore wind (#43) | ledger-row | Wind — onshore |
| ScotWind / INTOG (#42) | ledger-row | Wind — offshore |
| CES aquaculture (#47) | ledger-row | Sea / aquaculture |
| SEPA CAR MapServer (#46) | data-only → may feed hydro/water | Hydro / water (geometry), not a second rent |
| NFI + Native Woodland (#29) | ledger-row | Forestry |
| Peatland ACTION / Carbon & Peatland (P2) | ledger-row | Peat / carbon |
| BritPits OGL index (P2) | ledger-row | Minerals (index only) |
| ICES landings (P2) | data-only (default) | Fisheries |
| NSTA (P3) | ledger-row | Oil & gas |
| CES cables / foreshore (P3) | ledger-row | Foreshore / cables |
| SSSI / designations (#26) | constraint | Designations |
| SEPA flood (#25) | constraint | Flood |
| Crofting / grazings (#34) | constraint | Crofting |
| LCA Hutton (#39) | constraint | LCA |
| LDP / HLA / NRS (#30 #31 #24) | data-only or ownership-context | Planning context — not rent rows |
| Community ownership (#36) | ownership-context | — |
| Common Good GIS (#33) | ownership-context | when open polygons exist |
| DZ HPI/SIMD/density (#35) | data-only / surface attributes | Supports surface proxy — not a new rent |
| AGR/tax holds (#6 #9 #19) | data-only until rules | Surface / scenarios |
| BGS / full BritPits / Who Owns Scotland | excluded | paid / unclear |

---

## 6. Performance budget

| Budget | Target |
|---|---|
| Ledger toggles painted | Few concurrent geometries; prefer one rent-class paint at a time plus defaults |
| Geometry | Vector tiles / zoom-simplified; no national raw GeoJSON paint |
| Place card | Small JSON: identity + ledger hit list + constraint flags |
| Place page stack | Server-assembled per-hectare breakdown; not client-side layer sum |
| Failure | 503 / empty / excluded+why — never hang the HUD |

---

## 7. Page map

```
/                     Map + search + ledger panel + place card HUD
/place (or /place/…)  Full place — per-hectare stack proving once-per-use
/downloads            Data — raw datasets, licence, vintage, bulk
/open-api             Data — Public API (same catalog)
/methodology          About / method
/layers-panel         Dev/QA only (not the public ledger)
/place-card           Dev/QA only
```

Primary nav: **Map · Data · About**.

---

## Open — wait for Georgist accounting rules

Laurie is forwarding **Georgist accounting rules**. Until those land, treat as open:

- [ ] Final status/tag per ledger row  
- [ ] Exact per-hectare stacking / mutual exclusion algebra  
- [ ] When eco rows appear and how shadow rent is shown  
- [ ] Which ownership-context toggles sit under Surface vs Data-only  
- [ ] Public £ publication vs status-only ledger  

**Draft now; do not merge UI that pretends the rules are settled.** Backend loaders and catalog may continue.

---

## Agreement checklist (when rules arrive)

- [ ] Ledger replaces layers-pop-out / theme checklist  
- [ ] Claim visible: all natural capital rows present; no double count  
- [ ] One rent per hectare per use; surface / resource / eco separate  
- [ ] Constraints change best use, never add value  
- [ ] Tags market / proxy / shadow on every rent figure  
- [ ] Place view shows per-hectare stack  
- [ ] Raw data stays in Data section  
- [ ] Accounting rules doc linked and statuses refreshed  
