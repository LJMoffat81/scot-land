# Scot-LAND — Economic Rules for the Commons (DRAFT v0.7)

**Status:** DRAFT v0.7 for team review, 6 Oct 2026. Not yet approved by Laurie Moffat; open decisions are listed in section 15. Owner: Scot-LAND Georgist (economic rules).
**Companion:** GIS source tier table (Scot-LAND GIS). **Builds on:** `docs/methodology.md` and `docs/valuation-roadmap.md`. Section 14 lists where this draft changes them.

These rules say *what* we measure and *how values may combine*. Code that produces or sums a value must follow them. Where a rule cannot be met, the figure is flagged and left out of totals rather than guessed.

---

## 1. Core definitions

- **Economic rent (R):** the annual payment a site or natural resource can command because of where it is or what it holds, excluding any return to labour, buildings or other capital invested in it. Rent is the headline unit. Every module outputs £ per year.
- **Land vs improvements:** buildings, drainage, planting and other investment are improvements and are never part of rent. Location, natural endowment and publicly granted permission are not improvements.
- **Capital value:** derived only, as `V = R / (r − g)`. The calibrated **land yield is the observed `r − g`**, and config stores that single figure. Only the difference is observed in the market, so `r` and `g` are set separately only in scenario runs, where they must satisfy `r − g = land_yield`. Capital value is never an input to totals.
- **Commons class:** the single module that owns a given £ of rent (section 3).
- **Measured rent vs policy rent:** measured rent is our best estimate of what the market would pay. Policy adjustments (e.g. Pickard de-speculation factors, scenario capture rates) are applied afterwards, in a separate column (section 13).

## 2. Units and grain

- Rent in £ per year, at a stated `price_year`: the year **the money is priced in** (e.g. 2025), not the year the evidence was observed. No summing across price years without indexing. The year of the underlying evidence (e.g. 2023 sales) goes in a separate `evidence_year` column. Dwelling and population counts join on `count_year = price_year` (a 2025-priced total uses the 2025 stock), on the same zone vintage. A missing count for that year is flagged, never filled from another year.
- Surface rent lives on **data zones** (2011 and 2022 vintages, keyed `(code, vintage)`, vintage stored as the integer 2011 or 2022 and each code checked against its vintage's official range) and stops at the coast. Offshore rent stays on marine geography.
- Every figure carries: `commons_class`, `value_tier`, `quality`, `uncertainty_low`, `uncertainty_high`, `net_of`, `use_basis`, `crosswalk_method`, `publish_level`, `source_id`, `licence`, `price_year`. These are **required**; a row missing any of them is rejected. Diagnostic columns (e.g. `raw_residual`, rebuild range, `typical_sale_gbp`, skew flag, `rebuild_mix_basis`) may sit on the row but are internal only and never served by the public API or map.
- `crosswalk_method` is one of: `none`, `pop_hhres_2022`, `address_uprn`, `value_weighted`, `footprint_area`.
- `publish_level` says how widely a figure may be shown, which the licence name alone does not: `public_site` (site-level public), `public_zone` (zone totals only, e.g. EPC and RoS outline derived figures), `internal` (e.g. council-owned derelict site records until cleared). RoS INSPIRE parcels are OGL v3 (Laurie's ruling, 6 Oct 2026). The public map and API refuse anything below its level.
- **Licence is not the only limit.** Modelled residential surface rent is a zone-level estimate and is published at zone level only. Parcel outlines may be shown as base geography, but no public layer attaches a modelled land value or rent to an individual home's parcel: that would be an unofficial valuation of a private property, at a precision the model does not have. Parcel-level spreading stays internal (for site layers and checks). Site-level public values are allowed only where the source itself is site-level and public (e.g. derelict and housing land sites, published non-domestic rateable values).
- `publication_status` is separate from `publish_level`: `ok` or `blocked` (e.g. a zone failing the section 4.2 ceiling). A block hides the figure without changing its licence level, so clearing the block restores it.
- **Placeholders and mocks are not served.** Any figure with `quality = placeholder` (including mock resource and eco values) is absent from the public API and map until real, not merely flagged. Developers can still see them on internal endpoints.
- **Price-year alignment.** Prices are indexed to the rebuild cost's price year using the UK House Price Index at council level (tagged proxy), never the other way round. Dwelling counts match the indexed year and vintage.
- **Same-vintage denominators.** Per-person, per-household and per-dwelling figures divide by counts on the same zone vintage as the numerator, never by counts moved across through a crosswalk.

## 3. Commons classes and scope

| Class | Definition | Scotland examples | Version | Usual tier |
|---|---|---|---|---|
| **Surface (location)** | Rent from position: access, amenity, agglomeration, permitted use | Residential, business, farm and forestry land; idle and allocated sites | v1 | market / proxy |
| **Extractive** | Rent from depletable or licensed natural resources, net of extraction cost | Crown Estate Scotland seabed and foreshore leases (incl. ScotWind), minerals and aggregates, water abstraction, fish quota | v1 (sources to be confirmed by GIS) | market where leases or royalties are observed, otherwise proxy |
| **Eco sinks and services** | Value of natural systems absorbing harm or providing services | Peatland and soil carbon, woodland carbon, flood regulation | v1, carbon only | shadow |
| **Infrastructure commons** | Rent created by public networks (transport, broadband, utilities) | Station catchments, broadband coverage | v2 | attribution only (section 4.3) |
| **Artificial privileges** | Rent from publicly granted rights that restrict entry | Planning permission uplift, licences, quotas not covered above | v2, but planning uplift is reported from v1 as attribution | attribution, or standalone where not capitalised into land |
| **Spectrum and orbits** | Rent from radio spectrum and orbital slots | Ofcom licences, ITU filings | v3 stub, labelled "reserved / devolution-contingent" | none in v1 |

## 4. Attribution rule (no double counting)

### 4.1 One £, one owner
Every £ of rent is assigned to exactly one commons class. If two modules could claim the same rent, the **more specific** one owns it, and the other is measured net of it:

1. Extractive rent on a parcel is owned by Extractive. Surface value on that parcel is recorded `net_of = extractive`.
2. A harm charged to an identifiable polluter in Eco is **not** also deducted from neighbours' surface rent. Surface rent there is recorded `net_of = eco_externality`. See section 10.
3. Rent that is already priced into land values stays in Surface. Infrastructure and planning permission are mostly in this category.

### 4.2 Reconciliation check
Before publication, the sum of standalone module rents on land in each data zone must not exceed that zone's **rent ceiling**, within the stated uncertainty band. A breach blocks publication of that zone and is logged.

`rent_ceiling = mean sale price × dwelling count × gross yield`
- **Mean**, not median: mean × count is the zone's total property value; the median understates it in exactly the high-value zones.
- Dwelling count and price on the **same vintage** (2011 until the price spine is moved to 2022 zones).
- **Gross** yield, because the ceiling is whole-property rent (land plus buildings). Land rent must sit below it.
- Zones without a published mean use the model-filled value and are flagged. Business, farm and offshore rents get their own ceilings when those modules land.

### 4.3 Attribution-only columns
Some quantities explain surface rent rather than add to it:
- `infra_share`: the part of surface rent explained by public infrastructure (from the land value model, section 6.6).
- `planning_uplift`: permitted-use value minus existing-use value (section 8).

These are **breakdowns**. The totals code must make it impossible to add them to surface rent. They are shown as "of which".

## 5. Value tiers

| Tier | Meaning | Examples |
|---|---|---|
| **market** | Directly observed rent or price for the thing being valued | Crown Estate lease income, land-only sale (if licensed) |
| **proxy** | Derived from market evidence by a stated method | Residual land value from house sales, farm rent by land class |
| **shadow** | Imputed value without a market for the thing itself | Peatland carbon at a policy carbon price |

Rules:
- Every value carries a tier and an uncertainty band.
- Tiers are totalled **separately**. No headline figure mixes market, proxy and shadow without showing each tier.
- The tier records the *valuation basis*. The existing quality tags (`live | derived | modelled | placeholder`) record *data state*. Both are kept. Placeholders never enter totals.

## 6. Surface rules (residential v1)

### 6.1 Price spine
RoS residential sales and price by 2011 data zone, 2004–2023, OGL (data.gov.scot). **Mean for anything that adds up, median for display.** Rent, totals and the ceiling use mean price minus mean depreciated rebuild cost for the same homes: means subtract and sum consistently, medians don't. Per-home figures are zone totals divided by the dwelling count. The median price is shown as the typical sale and used as a robustness flag: where mean ÷ median is unusually high in a small-sales zone, the zone is flagged as possibly skewed by a few sales. The rebuild mix should match the homes that sold where the data allows; where it uses the whole stock instead, that is flagged. EPCs are issued mainly on sale or letting, so the certificates from the last 10 years are the preferred proxy for the sold mix. Zones where EPC coverage goes above 100% (certificates surviving demolition) use the mix from recent certificates only, and are flagged. Zones with fewer than 5 sales are **missing**, never zero. Zones absent from the file are flagged separately. The spine moves to 2022 zones by address (section 11).

### 6.2 Residual land value
`land_value = price − depreciated rebuild cost`
- Housing mix and floor area come from the EPC rollup by zone, with a coverage share. The 2017 NRS type and rooms mix is used for checks and as a 2011-only fallback.
- **Depreciation** (signed off 6 Oct 2026): age-based from EPC age bands, 100-year life, remaining building value never below 0.30. Both are config values with a low–high band (life 80–120 years, floor 0.20–0.40) that feeds the uncertainty band together with the rebuild band, never as a fixed point. Zones with large old homes and strongly negative residuals are reviewed for a floor that is too high (obsolescence), not forced positive.
- Rebuild £/m² is a **required config value with no default**. v1 uses a stated open estimate with a wide band. A paid cost table is bought only if holdout tests show this assumption drives the error.
- **Procurement route** (v0.7): rebuild cost is the cost of replacing the building the way that type and era was typically built. Detached houses on estate-sized plots use a volume-builder estate-house rate, and the one-off (self-build or architect) rate applies to detached homes on larger plots. The split is made by plot evidence for **all** detached homes, whatever their age band (1960s–70s estates exist too, and the 1976–83 band need not be dropped); age is not the test. The rate is sourced like the others and stated in config. v1 source: Aberdeenshire Cost Index "Estate housing, 4 units or more", tagged `rate_basis = generic_estate` because it mixes built forms; it carries the same low–high band as the other rates. The non-estate share uses a one-off-only rate: v1 source is Aberdeenshire Cost Index 2025, Table 1, "One off detached houses, 3 units or less", cross-checked against other council guides, tagged `rate_basis = one_off_detached`. If a future source lacks one, the fallback is the general detached rate tagged `generic_detached`, with its high end widened because it understates one-off cost and so biases land value up on large plots. The change is justified by the evidence on what was built, never by how many negatives it removes. Holdout tests are re-run afterwards, and zones that stay negative (e.g. genuinely weak markets) are reported, not adjusted. Plot size (GIS's zone-level parcel-size band shares, `public_zone` under OGL v3, using the `all_ages_*` columns: under 0.05 ha estate rate, 0.05–0.1 ha half and half, over 0.1 ha one-off; zones with too few matched homes borrow the shares of their council × urban-rural class, flagged `plot_bands_borrowed`, never defaulting to all-estate or all-one-off) is used only to blend the estate and one-off rates by share, never as a hard cut and never as a land value driver. Check: large-plot zones must not show lower land value per residential hectare merely because they drew the higher rebuild rate.
- **Combining the bands** (v0.7): rebuild, building life and floor are judgement ranges applied to every zone at once, so they don't average out across zones. The published outer band is the **corner** combination (low land value = high rebuild, 120-year life, 0.40 floor; high = the opposite). Each parameter's one-at-a-time swing is also stored, so users can see which assumption drives the band. Plausibility checks (negative-zone share by class, national land share) are **pass/fail on the central case**. At the corners they are reported as stress results: a corner outside the plausible range narrows that parameter's range only if independent evidence supports it, and is never quietly tuned away.
- Tier: **proxy**.

### 6.3 Negative residuals
The raw residual is **stored as computed, including negatives**, in `raw_residual` (diagnostics only). The published value is `measured_rent`, floored at 0 and flagged `negative_residual = true`. Negatives are evidence, usually of a wrong rebuild cost or a weak market, and must stay visible in diagnostics.

### 6.4 Annualisation
`rent = land_value × land_yield`
- **Gross yield** is calibrated per Broad Rental Market Area × 6-class urban-rural, from Scottish Government private rent statistics against mix-matched RoS prices.
- **Land yield** = gross yield minus stated deductions for running costs, voids and building depreciation. It should come out lower than the gross yield.
- Zones straddling rental areas blend yields by dwelling share. Until open within-zone dwelling locations exist, use the midpoint of GIS's upper and lower limits (empty and second homes all on one side, then all on the other), and carry the spread into the uncertainty band.
- **Occupancy doesn't change rent.** Land under empty and second homes carries the same location rent as land under occupied homes, so surface totals count **all dwellings** (NRS council-tax dwelling estimates, `dwellings_total`, the single denominator; the assessors' December count is reference only), never households. Vacancy and second-home shares are reported alongside for policy analysis. Per-resident figures in high second-home areas (e.g. the Cairngorms) will look high, and are labelled as such. **Zones with zero dwellings** (e.g. cleared regeneration sites such as Sighthill) get no residential surface rent, flagged `zero_dwellings`, and are shown as not applicable rather than £0. Their land is valued through the vacant/derelict and housing land supply layers at best permitted use (sections 7 and 8), never left at zero. `zero_dwellings` (read from `zone_spine`) overrides any price, and the old sales in such zones are also excluded from model fitting and neighbour fill. Where `pop_dwellings_mismatch` is set, the per-resident view is suppressed for that zone.
- **Map denominators.** The default map shows surface rent **per hectare of residential land** (inside the rural mask's settlement and residential parcels): that is the land value surface itself. Rent **per dwelling** is the second view, showing what a typical home's site would carry. Per resident is optional and shown with the second-home share. Rent per hectare of whole-zone area is never shown for surface rent, because farmland and moor dilute it in rural zones. All denominators share the figure's zone vintage. Residential land area is a **display denominator only**: surface totals are per-dwelling values × dwellings and never depend on it. Where the parcel match is weak (`share_res_uprn_in_parcels` < 0.5, mostly tenements and Sasine land, so area is too small) or `mask_too_big_parcel` is set, the per-hectare view is shown as low-confidence and the per-dwelling view is preferred for that zone.
- A stated fallback yield applies where rental evidence is thin, and is flagged. It is also the anchor for scenario runs. Calibrated yields per rental area × urban-rural class are each an observed `r − g`.

### 6.5 Business land (later in v1)
Scottish Assessors' rateable value is already an estimate of annual rent. Business land rent = rateable value minus the building's share. No capitalisation step.

### 6.6 Land value model
Fit land value per zone separately within each **6-class urban-rural** class. The 8-class version is for display only. Thin classes borrow from the nearest class, never Scotland-wide.

Drivers allowed:
- **Positive:** SIMD access-to-services travel times, bus accessibility, broadband, dwelling density.
- **Negative:** proximity to derelict sites, resident-felt crime (housebreaking, vandalism, violence), flood risk, noise, air quality.
- **Ranking signal:** council tax band distribution by 2022 zone, for thin-sales zones.

The model fills missing zones and produces `infra_share`.

### 6.7 Excluded drivers
Income, employment and other deprivation outcomes are **not** drivers, because they partly result from low land values and would make the model circular. They are kept for distribution analysis only. Crime is handled with care in town centres and in zones with few residents, where per-resident rates mislead.

## 7. Use basis (which use the land is valued in)

| Land situation | Use basis | Notes |
|---|---|---|
| Occupied land | **Existing authorised use** | As in `methodology.md` |
| Vacant or derelict land (SVDLS) | **Best permitted use** | Zone land value adjusted for development potential, minus a stated remediation assumption by previous-use category |
| Allocated or consented but unbuilt (Housing Land Audit) | **Permitted use** | Zone land value per home × remaining capacity, discounted for deliverability, constraints and build timing |
| Land with no permission or allocation | **Existing use** | Speculative hope value is excluded from the levy base |

Rationale: valuing idle land at what it earns while empty would reward holding it idle. Permitted use is a public grant and is in scope. Unpermitted hope value is not.

Each site is valued once. Housing Land Audit and SVDLS sites are deduplicated by outline overlap before valuation.

Overlap and area rules (v0.7):
- **Derelict land that is also housing land:** the housing land layer owns the value, at permitted housing use minus the remediation assumption for the derelict site's previous-use category. The derelict layer values only its land outside housing land supply (the `excl_hls` hectares). The overlap is never valued in both.
- **Housing land area** is the ground covered (shapes unioned), never the sum of overlapping site hectares.
- **Capacity:** where remaining capacity (homes) is unavailable, the fallback is the zone's land value per residential hectare × site hectares, with the same deliverability discount, tagged proxy and flagged `capacity_missing`. Capacity × land value per home replaces it when the capacity fields are available. In zones with a weak parcel match or `mask_too_big_parcel`, the per-hectare figure is unreliable, so the fallback uses land value per home × the median homes per residential hectare of well-matched zones in the same council and urban-rural class, flagged. v1 ships on the per-hectare fallback; council housing land audit schedules (cities first) are an upgrade and a check, not a blocker.
- **Against surface rent:** any part of a derelict or housing land site that overlaps residential parcels already counted in surface rent (e.g. part-built phases) is valued once, in surface rent, and removed from the site layer. This uses true outlines only: every site whose `geom_provenance` is not a true outline (buffered or point-sized circles) is left out of that overlay and flagged.

## 8. Planning

- `planning_uplift = permitted-use value − existing-use value` for the same land.
- Existing-use value comes from the farm rent proxy (section 9) or the derelict figure. Until the farm proxy exists, `planning_uplift` is blank and flagged, never guessed.
- Planning uplift is an attribution column (section 4.3). It is never added to surface rent.
- Sources: Spatial Hub Housing Land Supply (full v1 layer), Planning Applications (dated event layer), Local Development Plans (context for permitted use, patchy coverage).
- Planning authority is looked up per zone, including the two national parks. Plan-making and deciding authority are recorded separately.

## 9. Rural land (farm and forestry)

- Per-hectare proxy = James Hutton Institute land capability class (agriculture and forestry) × Scottish Government farm survey rent per hectare by region and land quality.
- **Rural mask.** The farm proxy applies only to land outside settlements and residential parcels (NRS settlement boundaries, with RoS title outlines inside them), so farm rent never lands on ground already carrying residential surface rent.
- Tier: **proxy**. Crosswalked by the land's own footprint (area-weighted), after masking.
- Replaces the single 2009 land-use table in `methodology.md` once validated against it.
- Agricultural rent includes some return to the farmer's capital. The deduction must be stated.

## 10. Externalities

- Negative factors with no single source (crime, general disorder) stay as negative drivers in surface rent.
- Harm from an **identifiable source** (landfill, major road, polluting works) is valued in Eco as a charge on that source. Surface rent near it is recorded `net_of = eco_externality`, so the same harm is not counted both as lost neighbour rent and as a polluter charge.
- Public improvements that raise land values (safety, regeneration, transport) show up in `infra_share`. This is the evidence base for recovering that value through ground rent.

## 11. Crosswalk rule

Each rent is crosswalked by **whatever drives it**:
- **Surface:** by address or parcel (OS Open UPRN, RoS outlines), or value-weighted shares where addresses aren't available. **Never by area.**
- **Extractive and eco:** by the resource's own footprint, area-weighted.
- **People counts:** by population or address weights (`pop_hhres_2022`).

Order matters: the price spine uses 2011 zones only, so it goes through the address crosswalk before any 2022-zone work.

The method is stamped on every figure, from the fixed list in section 2.

## 12. Validation (required before any figure is published)

No open land-only sales series exists for Scotland, so the land share is tested indirectly:

1. **Two routes (limited).** Where rent and yield come from the same rental area × urban-rural cell, the rent route reduces to price minus rebuild, so it checks nothing. It counts only where rent evidence is independent of the yield calibration: below rental-area level (e.g. Assessors' rateable values for business land), or in rental areas held out of the yield calibration. Even then it shares the rebuild assumption.
2. **Location gradient.** Tested on **land value per residential hectare**, not land share: land share rises with plot size, so rural homes on big plots show high shares even where each hectare is worth less. Per hectare must fall from large urban through small towns to rural, and within each class must rise with the access drivers. A flat or reversed gradient means the rebuild or depreciation assumption is wrong. This is the strongest check. Land share is used only for the national plausibility check (3). The within-class test runs on **observed-sales zones only**: model-filled zones use the same travel-time drivers, so including them would make the test pass by construction. The gradient runs only on the parcel version of residential land, and reports pending on the settlement version. It excludes zones with `share_res_uprn_in_parcels` < 0.5, `mask_too_big_parcel`, `res_uprn_exceeds_dwellings` or `zero_dwellings`.
   - **Within-class access measure (v0.7).** Land rent follows access to jobs and centres, not to local services. SIMD's GP, shop and post office minutes barely vary inside towns, so they are a weak test there. The within-class test therefore uses a **job accessibility** measure as its primary driver for all classes: employment by data zone (BRES, open), weighted by a fixed distance decay stated in config before the run, with road distance to the nearest large urban centre as a secondary measure. The driver, decay and threshold (correlation ≥ +0.10 within class) are fixed before the run, and the run is done once. The SIMD-minutes result is still reported as run. A class that fails on the pre-set measure is reported as **failed**, not inconclusive, and its model-filled zones get wider uncertainty bands, set from that class's own holdout prediction errors (the 5th–95th percentile of holdout error, applied where wider than the existing band), never a fixed multiplier. Until the holdout run exists, bands stay unwidened and are tagged `fail_band_pending_holdout` (research / internal); a fixed multiplier remains rejected and is not published. **Implementation note (2026-10-12):** UR6 class 2 failed the pre-registered job-access gradient; `gradient_v07.on_class_fail.active_behaviour = holdout_error_band` applies that class's own holdout residuals via `surface_holdout.widen_failed_class_band`. Null Data Zone model fill (727 = suppressed ∪ absent − zero dwellings) is `georgist.surface_model` — Wealth Engine internal calibration, research estimates only.
   - Changing a test's measure or threshold after seeing its result is not allowed; a new measure is a new pre-set test, and both results are published. A setting counts as fixed in advance when it was set by rule in the team record before the scored input was opened; the commit time is supporting evidence, and any ordering gap is stated in the commit message.
   - **Negative residuals by class.** Widespread negative residuals in high-demand urban classes are implausible and count against that part of the rebuild band. Negatives in weak remote or post-industrial markets can be real.
   - If these checks are used to **narrow** the rebuild band, that narrowing is a calibration step: it is documented, and the checks are then re-run on held-out zones rather than counted as independent validation.
3. **Plausible total.** National residential land value as a share of total housing value must fall in a documented plausible range.
4. **Holdout.** Predict held-back zones' prices and report error by urban-rural class.
5. **Order of magnitude.** Totals are compared with ONS Scotland natural capital accounts and GERS where comparable, or the gap is explained.

Optional direct check: a one-off RoS custom extract of bare-land sales (from £300). Used as a check only, not to price zones, and subject to its licence on publication. Request (agreed 6 Oct 2026): a one-off bespoke report (quote may exceed £300), sales 2019–2025, all Scotland including cities, land classes L, A and F. Fields: title and parent title, price, date of entry, description, address, postcode, data zone if held, parcel-centre grid reference. Flags: no or partial money price, connected parties, garden ground where possible. No title numbers, no purchase. Plot area comes from RoS INSPIRE boundaries (method stamped). Excluded from the check: garden strips (small part-title sales off residential parents), non-market and connected-party sales, and burdened sales, which count as lower limits only. The extract does not block the build; it narrows uncertainty bands.

Comparison rule: a bare-land price includes whatever the buyer expects to be allowed to build, including hope value we exclude. Each sale is compared with our **permitted-use** value where the plot has an allocation or consent (section 7). Otherwise it is treated as an upper bound on existing-use value, never as a direct match. Plots with consent are flagged and checked against the Housing Land Audit before use.

## 13. Policy layers (kept separate from measured rent)

The Pickard de-speculation factors (urban × 0.70, farmland × 0.20), scenario capture rates and the Sandilands national rent pool are **policy and scenario choices**, not measurements. They are applied **after** measured rent, shown in their own columns, and never folded into `measured_rent`. The national pool remains separate from the sum of zone rents unless explicitly calibrated, as in `methodology.md`.

### 13.1 Ownership does not zero value

Public, Crown, local-authority and Common Good ownership **tags the owner** and does **not** set land value to zero. Residual / surface rent is assessed like any other land. Any tax exemption for those owners belongs only in **scenario tools** (`policy.yaml` `ownership_reliefs` on a charge scenario), never inside the valuation engine. See `backend/layers/ownership_value.py`.

## 14. Changes to existing docs (for Laurie's decision)

| `methodology.md` today | This draft | Effect |
|---|---|---|
| Fixed 5% yield | Calibrated land yield per rental area × urban-rural, with fallback | Yield becomes evidence-based |
| Floor at 0 inside the formula | Store raw negatives, publish floored with a flag | Diagnostics keep the evidence |
| HABU = existing use everywhere | Existing use for occupied land, permitted use for idle and allocated land, hope value still excluded | Idle land no longer rewarded |
| Rural = 2009 category table × HPI | Hutton land capability × SG farm rents | Rural rent varies by land quality and region |
| Pickard factors inside the economic rent step | Pickard factors as a separate policy column | Measured and policy rent no longer mixed |
| No commons classes beyond surface | Classes, attribution rule and tiers (sections 3–5) | Ready for the extractive and eco modules |

## 15. Open decisions

1. ~~Rebuild £/m² source~~ **Decided (Laurie, 6 Oct 2026):** free sources. Council cost guides are the base, with no BCIS licence.
2. Whether to buy the one-off RoS bare-land sales extract as a validation check. **Recommended**: the internal (unpublished) results show the national land share swinging widely across the combined rebuild, life and floor ranges, and the indirect checks can't settle that alone.
3. Whether the Pickard factors stay as defaults in the published policy view.
4. Carbon price for eco shadow values: which official series, and at what price year.
5. Remediation cost assumptions by previous-use category for derelict sites.
