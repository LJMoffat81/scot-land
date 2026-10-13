# Frontend information architecture — Natural capital ledger

Status: **finalised for agreement** — Georgist accounting rules received 2026-10-13 (verbatim spec in project store `docs/georgist-ledger-accounting-rules.md`).  
Scope: product IA only (no application code).  
Related: [PLATFORM.md](PLATFORM.md), [CHARTER.md](CHARTER.md), [ECONOMIC_RULES.md](ECONOMIC_RULES.md), `GET /layers/catalog`.

**Pause:** do not merge new map-panel / layers-pop-out UI until this ledger IA is agreed and implemented deliberately.  
**Continue:** backend loaders, PostGIS ingest, catalog entries, place APIs, Data-section content.  
**Publication:** zone-level only, never plots; nothing published for blocked zones. Public £ still gated by ECONOMIC_RULES / calibration where those hold.

---

## Claim the UI must prove

The public front end is a **Natural capital ledger**, not a GIS layer browser. It proves:

1. **All natural capital is accounted for** — every rent class has a ledger row (or is explicitly excluded with why).  
2. **No double counting** — one surface rent per hectare; resource rows enter only as the **stated differences** in the accounting rules.  
3. **Constraints are not rent** — designations, flood, crofting, LCA: **no ledger row**, **£0**, change best permitted use only.  
4. **Tags** — market / proxy / shadow on every rent figure; headline totals = market+proxy; **shadow total separate, never summed** into the headline.  
5. **Sceptic-ready** — ranges not points; checks pass/fail with run hash; “not yet” never shown as £0.

Raw spatial datasets live in the **Data** section. The map’s primary panel is the ledger.

---

## 1. Map shell

| Element | Role |
|---|---|
| **Search** | Postcode / place / coordinates → place card |
| **Scot-LAND squares** | Grid context at suitable zoom; plot £ never published |
| **Data Zone boundaries** | Zone frame (publication grain) |
| **Natural capital ledger** | Primary HUD — rows, checks, sceptic fields |
| **Constraints toggles** | Paint only; £0; change best use |

Paint via vector tiles / zoom-simplified geometry — not national raw GeoJSON. Ownership/cadastre outlines are context (who/outline), not extra rent rows.

---

## 2. Ledger rows (authoritative)

Use these rows **exactly**. Status on each row: `counted` | `partial` | `not yet` | `excluded` (+ why).  
Per row (sceptic): source, licence, vintage, tag, % coverage, status, a **range** (not a point).  
**One toggle** per row paints where that rent applies. Toggle never invents a second rent line.  
**“not yet” never shown as £0.**

| # | Row | Tag / rule | UI notes |
|---|---|---|---|
| **1** | **Surface site rent** | market / proxy | Best permitted use; idle/derelict = best use minus remediation |
| **1a** | **Planning uplift** | (nested) | **NESTED in 1, never added** as a sibling total — indent under 1 |
| **2** | **Mineral rent** | proxy | Royalty/tonne, below ground; extraction only here (see C-mineral) |
| **3** | **Onshore wind + hydro resource rent** | proxy | Site rent **minus** footprint surface rent |
| **4** | **Seabed & foreshore** | market | CES offshore wind, cables, moorings, foreshore |
| **5** | **Aquaculture licence rent** | shadow | Total minus CES seabed paid |
| **6** | **Fisheries quota** | market if lease prices, else shadow | — |
| **7** | **Water scarcity** | shadow | ~0 |
| **8** | **Unpriced peat/soil carbon** | shadow | Only **unpriced** carbon; priced timber/credits stay in row 1 (C-forest) |
| **9** | **Oil & gas** | reported | **UK-reserved — OUTSIDE Scottish total** (and outside headline + shadow Scottish sums) |
| **10** | **Ecosystem services** | shadow | Later |

### Benchmarks (beside ledger, not inputs)

- Spectrum / airspace  
- Wightman  

Labelled **benchmark only, not inputs** — never fed into headline or shadow totals.

### Constraints (no rent row)

| Constraint | Rule |
|---|---|
| Designations (e.g. SSSI) | No row, £0, change best use only |
| Flood | No row, £0, change best use only |
| Crofting / common grazings | No row, £0, change best use only |
| Land Capability for Agriculture (LCA) | No row, £0, change best use only |

Shown as a **Constraints** group with applicability toggles only — no £ column, no market/proxy/shadow rent tag.

### Excluded list

Always visible (ledger footer or Data cross-link), with reasons — e.g. paid data (full BritPits, BGS, Who Owns Scotland), unclear licence, personal crofting lists, blocked zones. Oil & gas (row 9) is **reported but outside Scottish total**, not silently dropped.

---

## 3. Checks (shown pass/fail)

Every check shows **result** (pass/fail), **run hash**, and link/ref to a **pre-registered test log** that includes failures (e.g. UR6 class 2, yield at cap).

| Check | Meaning |
|---|---|
| **C-hectare** | One surface rent/ha; rows 2–8 only as stated differences |
| **C-turbine** | Turbine / wind footprint accounting (no double count with surface) |
| **C-aqua** | Aquaculture = licence rent minus CES seabed paid |
| **C-mineral** | Surface = current/after-use; extraction only in row 2 |
| **C-forest** | Timber + market carbon credits inside row 1; only unpriced carbon in row 8 |
| **C-planning** | Planning uplift nested in 1, never added |
| **C-overlay** | Constraints £0 |
| **C-overlap** | VDL vs housing land supply: **housing owns it** |
| **C-totals** | Headline = market+proxy; shadow total separate, never summed; oil & gas + benchmarks outside both |
| **C-cap** | Land rent ≤ gross rent; **0.494 now, pass** |

---

## 4. Place view — per-hectare stack

### Place card (HUD)

Short: zone identity, which ledger rows apply, constraint flags, link to full place. No plot-level £.

### Full place page

**Per-hectare stack** that visibly adds to the totals:

- Rows **1–8** (as applicable) stack so the reader can see the sum.  
- **Nested** rows (planning uplift **1a**) drawn **indented** under their parent — never as a peer that gets added twice.  
- **Shadow** rows (**5** when shadow, **6** when shadow, **7**, **8**, **10**) drawn in a **separate shadow stack**; never summed into the market+proxy headline.  
- Row **9** (oil & gas) and benchmarks shown **beside**, labelled outside Scottish total / not inputs.  
- Constraints listed as use changers, £0.

Grain: **zone-level only, never plots.** Nothing published for blocked zones.

---

## 5. Data section (raw data)

**Downloads** + **Public API** = **Data** (nav: Map · Data · About).

Catalog-driven: dataset, licence + `licence_url` + credit, vintage, % coverage where known, bulk download / API path. Ledger rows cite Data for source/licence/vintage; Data does not replace the ledger.

Map catalog layers → role: `ledger-row` | `constraint` | `ownership-context` | `data-only` | `benchmark` | `excluded`.

---

## 6. Sceptic needs (UI must satisfy)

From the accounting rules — non-negotiable:

1. **Per row:** source, licence, vintage, tag, % coverage, status, a **range** not a point.  
2. **“not yet” never shown as £0.**  
3. **Place view** stacks visibly add to total; nested rows indented; shadow rows drawn separately.  
4. **Excluded list** with reasons.  
5. **Every check** with result + **run hash** + **pre-registered test log** including failures (UR6 class 2, yield at cap).  
6. **Benchmarks** beside but labelled not inputs.  
7. **Nothing published for blocked zones.**  
8. **Zone-level only, never plots.**

---

## 7. Layer → ledger mapping (implementers)

| Catalog / queue | Role | Ledger |
|---|---|---|
| `data_zones`, DZ metrics | ledger frame / surface inputs | Row 1 (zone grain) |
| `cell_grid`, `agr_value` | internal / withheld at plot | Supports row 1 engine; **not** public plot £ |
| `boundaries`, `public_crown`, `vdl`, Common Good, community ownership | ownership-context | Who/outline; C-overlap: housing owns VDL vs HLS conflict |
| LDP / HLA / planning uplift data | nested under surface | Row **1a** (nested) |
| BritPits OGL index | ledger-row | Row 2 (index only; full BritPits excluded) |
| REPD onshore wind, hydro sites | ledger-row | Row 3 |
| ScotWind/INTOG, CES cables/foreshore/moorings | ledger-row | Row 4 |
| CES aquaculture seabed + licence economics | ledger-row | Row 5 (shadow) |
| ICES / fisheries quota | ledger-row or data-only until priced | Row 6 |
| SEPA CAR / water | data-only / ~0 scarcity | Row 7 (~0 shadow) |
| Peatland / Carbon & Peatland unpriced | ledger-row | Row 8 |
| NSTA oil & gas | reported outside total | Row 9 |
| Eco module (later) | ledger-row | Row 10 |
| SSSI, flood, crofting, LCA | constraint | No row, £0 |
| `sepa_car` download_only, linked registers, gaps | data-only | Feed sceptic source fields |
| Spectrum/airspace, Wightman | benchmark | Not inputs |
| BGS, full BritPits, Who Owns Scotland | excluded | Paid / unclear |

---

## 8. Performance budget

| Budget | Target |
|---|---|
| Geometry paint | Vector tiles / zoom-simplified; no national raw GeoJSON |
| Ledger toggles | Few concurrent paints; defaults + selected rows |
| Place stack | Server-assembled zone stack; client does not sum layers into rent |
| Checks panel | Cached pass/fail + run hash; log linked, not recomputed on every pan |

---

## 9. Page map

```
/                     Map + search + Natural capital ledger + place card
/place (or /place/…)  Per-ha stack (nested indent + shadow separate) + checks
/downloads            Data — raw datasets, licence, vintage, bulk
/open-api             Data — Public API (same catalog)
/methodology          About / method + link to accounting rules
/layers-panel         Dev/QA only — not the public ledger
/place-card           Dev/QA only
```

Primary nav: **Map · Data · About**.

---

## Agreement checklist

- [x] Accounting rules received (ROWS, CHECKS, SCEPTIC NEEDS)  
- [ ] Ledger UI replaces layers-pop-out  
- [ ] Rows 1–10 (+ 1a nested) exactly as specified  
- [ ] Constraints = no rent row, £0  
- [ ] Place view: visible stack, nested indent, shadow separate  
- [ ] Checks pass/fail + run hash + pre-registered log  
- [ ] Sceptic fields per row; not yet ≠ £0; zone-only; blocked zones silent  
- [ ] Raw data in Data section  
