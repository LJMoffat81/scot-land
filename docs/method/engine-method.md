> **Working design** (Scot-LAND, 4 Oct 2026). Copied unchanged from the team's working file `engine-method-first-principles-2026-10-04.md`.
> Where it mentions sign-off, pinned Glasgow and Wick figures or frozen files, those were the rules when it was written; they were lifted on 4 Oct 2026 while the engine is developed.

# Scot-LAND engine method from first principles
*Policy & Economics, 4 Oct 2026, revised the same day to add S11, S12 and the recommendations in §6. A method spec for Laurie, Engine, Data and QA. It is a proposal: nothing is posted and the repo is untouched.*

**Status.**
- No live figure, rate or factor changes, and there is no code.
- `agr.yaml`, `docs/ENGINE.md` and the LOG stay as they are.
- Glasgow G1 1BL (about £8,001) and Wick KW1 4AA (about £8.28) stay pinned.
- Nothing here is built until Laurie signs it off in her review session.

**Laurie's direction (4 Oct).** Design the engine as if every ideal dataset existed. The data decides how well each slot is filled. It never decides the shape of the formula.

**Files this one lines up with.**
- Input slots are Data's **S1–S12** and the policy slots, with API labels `ideal` or `stand-in:<name>`, from `engine-inputs-proposal-v2-2026-10-04.md` (v2). The table in §4 matches them one to one.
- Principles are cited as **P-xx** from `land-economics-principles-2026-10-04.md`.

**Sources and labels.** No new figure is added. Every number comes from `engine-method-review-2026-10-04.md` (cited as "review", with its numbered sources [n]), `engine-inputs-proposal-2026-10-04.md` ("v1"), v2, or `BACKLOG.md`. **ASSUMPTION** marks my own judgement. "Unknown" means unknown.

---

## 1. What is being valued

**Unit of valuation.** One land unit. That is either a Land Register title (its RoS title extent) or an unmapped Sasine area: land not yet on the Land Register, valued by area and land type, with no outline, title or owner shown. A council is **not** a unit. One rate per council is today's stand-in for the location slot (S9).

**Coverage (P-15, HARD RULE).** Every m² of Scotland's land is valued exactly once:
- Land Register titles plus the Sasine remainder, with no gaps and no overlaps;
- national and council totals add up from the units;
- foreshore and seabed are excluded unless Laurie decides otherwise (D11);
- the share of land still on the Sasine register is unknown (v1 §1.2).

**Shared interests (P-16, HARD RULE).** A croft tenancy under an estate title, a long lease, or any other shared interest: the land is valued **once, as if unencumbered**. Splitting that value between the interests is a later policy question (D12).

**Value measured: unimproved land value, or site value (P-01, P-02).** This is what the land unit would fetch if it were bare, with every building and improvement disregarded, taking its location, size, shape, access and planning status as they are. The engine reports it as an **annual site rental value**, never as a post-reform capital value (P-10). A full Annual Ground Rent pushes sale prices towards zero (review §1; [1]).

**Valuation date (P-17, HARD RULE).** All figures are valued as at one date, like the Assessors' tone date. Older evidence is indexed to that date. Every result states the date and the index used (series and month). The date itself is Laurie's to set (D13).

**What counts as an improvement (D2).** Buildings, structures and the timber crop are improvements. Site works such as drainage, levelling and services are Laurie's call. New Zealand excludes them from land value ([4], review §1). **ASSUMPTION:** we follow New Zealand until Laurie decides.

**Basis of value (D1; P-07, P-11, P-12).** The engine computes all three bases. Policy chooses which one is published.
- **(a) Current use.** No hope value. This is today's engine, and a derelict site pays almost nothing (review §3). Under this basis the figure follows the owner's choices, which weakens neutrality (P-07).
- **(b) Consented or allocated use** where a live consent or LDP allocation exists (S6), and current use elsewhere (review §3).
- **(c) Highest and best permissible use.** This gives the strongest incentive effect, but it is "labour intensive and costly" and "open to challenge" ([1]).
- **Hope value** is stored separately as `hope_difference` and never folded in silently (P-12). Whether any of it is charged is part of D1.

---

## 2. How a perfect valuer would do it

The order of preference is sales comparison first, then cross-checks ([5], review §2).

**2.1 Location comes first (P-03, P-04).** Location drives almost all of a land unit's value.
- **Today** it is captured only indirectly: a council-average house price minus the building (the residual). That gives one location per council (S9 stand-in `stand-in:uk-hpi-la`).
- **Ideal (slot S11):** a fine-grained location value surface at data zone, postcode or finer, built in three steps:
  1. derive the land value at each sale from land-only sales (S1), or by hedonic or land-share separation on full sales (S2) (P-05);
  2. smooth it spatially;
  3. fit it at the land-unit level.
- **Access and amenity measures** (jobs, transport, services, views; S11 thin-sales fill) are used **only to interpolate where sales are thin**, and **never as an extra weight on top of sales**, which would count location twice (P-04).
- **Rural location** comes from land capability (S7), access and remoteness (S9) (P-21).
- **QA test:** the figure moves with location inside a council, not only at council borders (P-03).

**2.2 Separating land from buildings using real sales (S1, S2; P-05).**
- **Land-only and bare-plot sales (S1).** This is the most direct evidence, using IAAO's residential vacant land class ([6]). Improvements are adjusted out, or the sale is excluded.
- **Hedonic or land-share model on full sales (S2).** Price = land component (location × size × planning status) + building component (type, floor area, age, condition). This follows Rosen (1974) and Davis & Palumbo (2008) under P-05, and the primary model in v1 §1.3.
- **Residual** (price − depreciated rebuild cost, from S3) is a labelled cross-check only (`stand-in:residual-from-price`). It magnifies cost errors where price and rebuild cost are close (review §2). The 15–85% clamp hides that error rather than measuring it.
- **Note.** The VOA land value estimates apply to England only and are **not** a Scottish stand-in (v2 S1).

**2.3 Building value to subtract (S3).** Floor area, age, condition, rebuild cost per m² and depreciation.
- The 0.55 depreciation factor is unsourced (`stand-in:factor-0.55-unsourced`).
- **Condition has no stand-in** (`stand-in:none`, so the condition term is neutral).
- A sourced depreciation schedule: source unknown (v2 S3).

**2.4 Non-domestic land (S10).** Start from the rents on the Assessors' roll and take off a return on the depreciated building. The RICS-style reference for this is unknown (v1 §1.5).

**2.5 Plot extent and the plot-size curve (S4, S5; P-13, P-14).**
- Value per m² falls as plot size grows. In US sales the elasticity is about −0.6 ([7], review §4).
- The ideal engine fits the curve from S1 sales with S4 extents.
- Above a normal plot, the remainder is valued at its own use (the stance-plus-remainder rule, review §4).
- **Exception:** plottage, where land being assembled carries a premium (P-14). It applies only with evidence or an allocation, and only if Laurie chooses it (D10).
- Tenements are valued once on the steading and apportioned for display only (review §4).

**2.6 Planning status (S6).** Live consent, LDP allocation, or neither. This drives bases (b) and (c) and `hope_difference`.
- The vacant and derelict land survey gives the flags. The 2025 survey found 8,591 ha, 81% of it derelict ([12], review §3).
- The licence for the Spatial Hub LDP data is **unverified** (Open vs Restricted), and Edinburgh's LDP is missing (v2 S6).
- Planning portals are never scraped.

**2.7 Rural land by type and capability (S7, S8; P-21).**
- Split each land unit by LCA class (seven classes, four of them subdivided [8]), forestry capability, woodland, hill and sporting land.
- Value each part from sales for that land type (S8) and from farm rents, which are direct rent evidence: £42/ha average, £143 outside the LFA and £28 inside it, in 2020 ([9], review §5).
- For forestry, land value is the bare planting-land price, because stocked prices include the timber (v1 §1.9).

**2.8 From capital value to annual rent.** Use **rent evidence directly** where it exists: farm rents and the roll (S10). Elsewhere, use **one evidenced rent-to-land-value ratio, with a range**, fitted where both rents and values are observed. It is not a flat 5% (review §1).
- **Slot ownership (agreed with Data).** The market-evidenced yield is a valuation input. Only a *discount* on top of it (de-speculation, today's 0.70/0.20) is policy (D3).
- **ASSUMPTION:** one national ratio is enough until the evidence shows it varies by land type.

**2.9 Every result carries:**
- low, central and high values and a confidence level;
- the basis used, the valuation date and the index used;
- engine version, config hash and data vintages;
- a `provenance` label for each slot (§5.2) (P-17, P-19).

---

## 3. Valuation layer and policy layer (P-18)

| Layer | Contains | Never contains |
|---|---|---|
| **Valuation** | Site rental value per land unit under bases (a), (b) and (c); `hope_difference`; range; confidence; valuation date; slot provenance | Reliefs, discounts, capture share, transition |
| **Policy** | `policy:basis_of_value` (D1); any discount on top of the evidenced yield (D3), today `policy:urban_factor` (0.70) and `policy:farmland_factor` (0.20) as visible de-speculation, if kept; `policy:plot_size_rule` until S5 is fitted; capture share (P-06); reliefs; exemptions; deferral (Denmark lets over-65s defer [1]); transition (P-22); remote credits; how to split between shared interests (D12) | Any change to valuation numbers |
| **Display** | Wording, units and labels, all read from provenance | Any number the two layers didn't produce |

Each layer is versioned separately ([3] lesson 3). **QA invariant:** changing only the policy config leaves the valuation hash and values unchanged.

---

## 4. Input slots, one to one with Data's v2 (S1–S12)

Ideal sources, stand-ins and labels are as in v2. Licence and cost notes come from v1 §4 and v2's BLOCKED-ON-LAURIE table. Figures are cited, not copied beyond that.

| Slot | Input | Ideal source | Today's stand-in (v2 label) | Gap | Licence or cost |
|---|---|---|---|---|---|
| **S1** | Land-only sales (bare land and plots) | RoS All Sales data, filtered to land-only, plot and site sales | None at parcel level. The residual is inferred (`stand-in:residual-from-price`). VOA estimates are England only, so not a stand-in | Every land figure is indirect, and errors compound | £933 + VAT/month. Publication terms unverified (NWP) |
| **S2** | Full residential and non-domestic sales | RoS Market Value Residential Sales; All Sales (commercial) | RoS HPS by council, data-zone sales, UK HPI (`stand-in:ros-hps-la` / `sg-dz-sales` / `uk-hpi`). Non-domestic: none | No hedonic fit and no hold-out test | £675 + VAT/month residential. Terms unverified. Individual prices never published |
| **S3** | Building value to subtract (floor area, age, **condition**, rebuild £/m², depreciation) | Measured area; build year; surveyor condition; BCIS rates; a sourced depreciation schedule | EPC floor area or SHCS mean or 97 m²; EPC age band; **condition: `stand-in:none`**; `agr.yaml` rebuild constants; **0.55 unsourced** (`stand-in:factor-0.55-unsourced`) | 0.55 is the top driver of uncertainty (80% swing, backlog P0-2) | BCIS: no public price, publication barred without permission. EPC address fields need an OSG licence |
| **S4** | Plot extent and title outlines | RoS title extents linked to UPRN | Modelled plot area (`stand-in:modelled-plot-area`). INSPIRE only as a candidate (`stand-in:ros-inspire-indicative`). No county files | Tenement land per address overstated by about +44% to +76% (v2 S4) | INSPIRE OGL3 vs the OS EUL conflict: RoS confirmation in writing needed. No title plans or numbers |
| **S5** | Plot-size curve evidence | S1 sales paired with S4 extents | None (`stand-in:policy-plot-size-rule`) | Curve shape assumed | Depends on S1 and S4 |
| **S6** | Planning status and allocations | National consent and allocation register (polygons) | Spatial Hub LDP (**licence unverified**; no Edinburgh), SVDLS 2024 (`stand-in:spatialhub-ldp` / `svdls-2024` / `none`) | Bases (b) and (c) and hope value can't be computed reliably | Spatial Hub cost and licence unknown. No portal scraping |
| **S7** | Rural land type and capability | Field-level land use plus LCA 1:50k everywhere | Hutton LCA 250k/50k, LCF, NFI 2024, NatureScot HLCM (`stand-in:hutton-lca250k` etc.) | One blended farm value live (`valuation.py:238`) | Hutton free, commercial use allowed, attribution and equivalent terms required. IACS-type data unknown |
| **S8** | Farmland, forestry and sporting land sales | RoS All Sales, filtered to rural | SLC 2025, forestry market report, agent reports, 2009 config (`stand-in:slc-2025` / `fmr-2025` / `agent-reports` / `wightman-2009-config`) | **Per-hectare averages** not tied to LCA. Hill and forestry config far below market evidence | Agent reports cite-only. SLC and Tilhill terms unverified |
| **S9** | Regional and locational factors | Location coefficients from S2 at data-zone level or finer | UK HPI and HPS by council, data-zone stats, SG UR 2022 (`stand-in:uk-hpi-la` / `sg-dz-sales` / `sg-ur2022`) | **One rate per council**: within-council gradients flattened | Follows S2 |
| **S10** | Valuation roll (non-domestic) | Assessors' roll with NAV/RV, use and floor area, by UPRN | 2009 config land-use values (`stand-in:wightman-2009-config`) | High street and retail park valued the same | About £100 per area (Grampian). Re-use needs consent |
| **S11** | Location value (measured once; access used only to fill gaps) | Location coefficients from RoS transaction sales (S1, S2, S8) minus S3, at data zone or finer | Data-zone sales 2004–2023 (OGL, fewer than 5 sales suppressed) minus S3 stand-ins (`stand-in:sg-dz-sales-2023`). Thin-sales fill: SIMD access minutes, SG UR 2022 remoteness as pooling strata, OS Open Roads | Latest year 2023, needs indexing (D13). 2011 vs 2022 data zones; the lookup is unverified. No control for house-type mix. Residential only | Stand-in OGL. Ideal = RoS sales (BLOCKED-ON-LAURIE 1–2). One provenance label per parcel; never added on top of sales (P-04) |
| **S12** | Sasine remainder by land type and capability | Not needed once registration is complete | Scotland's land area minus title extents (S4), valued through S7, S8 and S11 | Share still unregistered: unknown. Depends on the S4 licence route | Follows S4, S7 and S8. No outlines, titles or owners. Full v2 wording for S12: not yet in the v2 file at 12:20 BST, so the label is unknown |
| *policy* | Discount on the yield (`policy:urban_factor`, `policy:farmland_factor`), `policy:basis_of_value`, `policy:plot_size_rule` | Laurie's decisions. The yield itself is a valuation input (§2.8) | **Flat 5%** × **0.70** / **0.20**. Together, 0.70 and 5% charge 3.5% of residual urban land value (review §1) | 0.70 and 0.20 stand in for land/building separation and de-speculation | n/a |

**Now slots:** the location surface and access gap-fill are **S11**, and the Sasine remainder is **S12**.

**Artefacts shaped by data that must be replaced (stand-ins, not design):**
1. **One rate per council** → S11 location surface (P-03).
2. **Flat 5% yield** → an evidenced rent-to-value ratio, or direct rents (§2.8).
3. **0.70 and 0.20 factors** used in place of land/building separation → S1, S2, S3, S8 and S10 evidence. Any discount that remains becomes a visible policy setting (D3).
4. **Per-hectare rural averages** → S7 and S8 by capability and land type (P-21).
5. Also: the single 280 m² plot and area × one rate (→ S5 curve, P-13); the 0.55 factor and the 15–85% clamp (→ S3 and S1/S2, with ranges and not a clamp).

---

## 5. Validation

**5.1 Hold-out test against real sales: needs the paid RoS data (S2, plus S1 for land).**
- Hold out a random 20% of sales by data zone and time (v1 §1.3, review §7).
- Predict each price and report the median ratio, COD, PRD and PRB by council, price decile and location (P-20).
- IAAO targets: median ratio 0.90–1.10; PRD 0.98–1.03; COD 5–15 residential (up to 20 rural) and 5–20/25 for vacant land ([6]). Which to adopt is D6.
- QA's rule: swapping a stand-in for the ideal source must improve the hold-out statistics. If it doesn't, the formula is wrong.
- Blocked on D5.

**5.2 Until then (v2, held-out section).**
- Only aggregate checks: the engine's implied averages against RoS HPS council medians and data-zone sales stats (held-out years or regions), and rural £/ha against SLC regional medians.
- Physical checks: EPC floor area against SHCS, the tenement sample, LCA areas against census areas.
- **No per-plot accuracy claim** on the site, in the API or in comms until 5.1 runs (P-20 HARD RULE). The range is only the scenario band (v1 §3).

**5.3 Provenance labels on every figure (QA's ask; v2 design rule).** Every API value carries `provenance: "ideal"` or `"stand-in:<name>"` for each slot used, with source, vintage and licence. The display layer reads the labels, so no wording can claim full data where a stand-in was used. QA checks this automatically. Comms' methodology page uses the same labels.

**5.4 HARD RULE invariants for QA** (from the principles):
- value ≥ 0 (P-01);
- building-only changes don't move the value on the ideal path (P-02);
- location moves the value inside a council (P-03);
- amenity layer has no effect in sales-rich cells (P-04);
- owner improvements and occupancy never change the value (P-07);
- full coverage with no overlaps, and totals add up (P-15);
- each land unit is valued once (P-16);
- one valuation date per release (P-17);
- changing policy leaves valuation unchanged (P-18);
- deterministic, with stamps (P-19).

**5.5 Frozen anchors.** G1 1BL and KW1 4AA stay pinned. A new figure is compared only after Laurie has signed it off. No test uses an unsigned figure (backlog, ruling at 11:38).

---

## 6. Open decisions for Laurie

Each decision has a recommendation, the reason for it, and what happens if you choose otherwise. None of them changes a live figure. Any change to a figure is shown to you before and after, and needs your sign-off before it ships.

**D1 Basis of value.** Should vacant and allocated land be valued at its consented or allocated use, with current use elsewhere?
- **Recommendation:** Yes. Use basis (b), and don't charge hope value.
- **Why:** A pure current-use basis follows the owner's own choices and lets derelict land pay almost nothing (P-07, P-11). Full highest-and-best use is costly and open to challenge, and hope value stays visible as its own field (P-12).
- **If you choose otherwise:** Current use only means vacant and derelict land stays near zero and the land-banking incentive is lost. Full highest-and-best use means a costlier, more contestable valuation that S6 data can't yet support.
- **Note:** (b) can't be filled reliably until S6 is (the Spatial Hub licence is unverified and Edinburgh is missing), so until then those results carry `stand-in:none`.

**D2 Site works.** Should drainage, levelling and servicing count as improvements, and so be excluded?
- **Recommendation:** Yes, as New Zealand does.
- **Why:** Site value leaves out what the owner has put in, and taxing it would penalise investment (P-02, P-07).
- **If you choose otherwise:** Owners who service or drain their land pay more for their own investment, and S3 needs a site-works term with no source.

**D3 Discount on the yield.** Should any discount be applied on top of the market-evidenced yield?
- **Recommendation:** No. Publish the full evidenced rent. If you want a prudence margin, make it a visible policy setting that is off by default.
- **Why:** The 0.70 and 0.20 factors were stand-ins for separating land from buildings, not evidence (P-05). How much rent to collect is a separate policy choice that must not be hidden in the valuation (P-06, P-18).
- **If you choose otherwise:** Every figure carries a discount nobody has evidenced, and it must be labelled as policy on the site.

**D4 Size rule.** Should value per m² follow a fitted plot-size curve, with stance plus remainder for large parcels?
- **Recommendation:** Yes. Until S5 is fitted, label the rule `stand-in:policy-plot-size-rule`.
- **Why:** Value per m² falls as plots grow, and plottage is the named exception (P-13, P-14).
- **If you choose otherwise:** Linear area × rate keeps overcharging large parcels: DG1 2BD shows £70,942 at the flat rate (backlog P1-1).

**D5 Paid and permission-only data.** Should you pursue enquiries about terms, starting with RoS sales data?
- **Recommendation:** Yes, it's your call, and nothing has been bought or requested. Suggested order:
  1. the RoS Market Value Residential Sales terms, including whether model outputs may be published;
  2. RoS written confirmation of the INSPIRE licence (free);
  3. the Spatial Hub LDP licence status.
  BCIS and the Assessors' roll can wait.
- **Why:** Location (S11), separating land from buildings, and any claim of accuracy all depend on real sales (P-03, P-05, P-20).
- **If you choose otherwise:** The engine stays on labelled stand-ins and can never claim per-plot accuracy.

**D6 Publishing accuracy.** Should ranges be shown now, with COD and PRD only once the hold-out test runs?
- **Recommendation:** Yes. Use the IAAO targets in §5.1 as the pass marks.
- **Why:** Accuracy must be measured, not assumed, and nothing per-plot is claimed before the hold-out test (P-20).
- **If you choose otherwise:** Point figures alone imply a precision the engine doesn't have.

**D7 Policy scope at launch.** Should the site show the gross site rent only, with no reliefs, deferral or transition modelled yet?
- **Recommendation:** Yes. Add these later, in the policy layer, each with its own sign-off.
- **Why:** Reliefs and transition are value judgements and belong in a separate layer from the valuation (P-18, P-22).
- **If you choose otherwise:** Each relief becomes a political choice baked into the first public figures, and readers can't tell the valuation from the policy.

**D8 Sign-off of this spec.** Should this spec be approved as the design target?
- **Recommendation:** Yes. It changes no figure. Engine writes specs against S1–S12, Data fills the slots and QA adopts §5.4.
- **Why:** An agreed design keeps the slots, the labels and the tests consistent (P-18, P-19).
- **If you choose otherwise:** Each bot keeps working from today's data-shaped engine, and the stand-ins harden into the design.

**D9 Negative or contaminated land.** Should a negative raw value be shown as £0 with a flag?
- **Recommendation:** Yes.
- **Why:** Site rent at the margin is about zero, and the published figure is never negative (P-01).
- **If you choose otherwise:** A negative figure reads as a payment to the owner, which no policy has agreed.

**D10 Plottage premium.** Should an assembly premium apply only where there is evidence of assembly, from an S1 sale or an S6 allocation?
- **Recommendation:** Yes. Otherwise, no premium.
- **Why:** The premium is real where land is being assembled (P-14), but Scottish evidence is unknown, and a blanket premium would tax size, not use (P-07).
- **If you choose otherwise:** Large titles are charged a premium with no Scottish evidence behind it, or assembled sites are undervalued.

**D11 Foreshore and seabed.** Should they stay excluded?
- **Recommendation:** Yes.
- **Why:** Coverage is defined as land, valued exactly once (P-15).
- **If you choose otherwise:** They need their own source and method, both unknown today, and national totals would no longer be land-only.

**D12 Shared interests.** Should land with a croft tenancy, a long lease or another shared interest be valued once, as if unencumbered, with the split between interests deferred?
- **Recommendation:** Yes.
- **Why:** Valuing land once keeps coverage exact and avoids double counting (P-15, P-16).
- **If you choose otherwise:** Splitting now needs tenancy and lease data we don't have, and risks valuing the same land twice.

**D13 Valuation date and index.** Should every figure in a release share one valuation date that you set, with older evidence indexed to it?
- **Recommendation:** Yes. Use the RoS House Price Statistics (by council and house type, OGL) as the index for urban evidence, and name the series and month on each result.
- **Why:** One date makes figures comparable, and naming the index makes them reproducible (P-17, P-19).
- **If you choose otherwise:** With no common date, figures can't be compared and the 2023 data-zone values (S11) sit at a different date from the rest. Using the UK HPI as the index instead is acceptable if it's named on each result.

---

**References for valuation practice:** Data's reference pack in `/workspace/scot-land/refs/` contains Gloudemans & Almy, *Fundamentals of Mass Appraisal* (IAAO, 2011); the IAAO *Standard on Mass Appraisal of Real Property* and *Standard on Ratio Studies*; McCluskey & Franzsen, *Land Value Taxation: An Applied Analysis* (Ashgate, 2005); and Dye & England (eds), *Land Value Taxation: Theory, Evidence, and Practice* (Lincoln Institute, 2009). Bibliographic details are as in Data's pack. I haven't re-checked them in this file.
