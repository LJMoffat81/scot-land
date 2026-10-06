# Surface land rent: residual method spec (v0.1 draft)

Owner: Scot-LAND Valuation. Status: **DRAFT — not yet approved by Laurie.** Results are internal until they pass the plausibility and holdout checks and Laurie approves them; this public spec carries methods, parameters and sources only. Read-only against repo `LJMoffat81/scot-land` @ `efabcb8` (2026-10-05 22:07 BST).
Binding rules: Georgist bot rules 1-6 (relayed 2026-10-06), team yield lock (BRMA x UR6, relayed 2026-10-06). Where data conflicts with a rule it is flagged **[CONFLICT]**.

Surface rent is a **separate lens** from the AGR residual roll (`backend/agr/`). AGENTS.md says the UI must not conflate them. This spec does not change `valuer_roll` or the signed-off `agr.yaml` defaults. It adds a new `surface_rent:` config block and a new output table.

---

## 0. Inputs (confirmed 2026-10-06)

| Id | Dataset | Geography / vintage | Years | Licence | URL |
|----|---------|---------------------|-------|---------|-----|
| ROS | House Prices: Residential Properties Sales and Price (RoS via SG) | **2011 Data Zones** (also IZ2011, ward, council and others) | 2004-2023 | OGL v3 | https://statistics.gov.scot/data/residential-properties-sales-and-price ; CSV `https://api.data.gov.scot/resource/3d9a31a5-4b62-436a-a537-7d9bbeba1723/download` (sha256 `702c9ada…49cf2`, matching the repo pin) |
| NRS-CT | NRS dwelling estimates by 2022 DZ: total, dwellings/ha, CT bands A-H | **DZ2022** | Dec 2024, Dec 2025 | OGL | https://www.nrscotland.gov.uk/media/43tfx3zo/dwelling-estimates-by-2022-data-zones-24-25.xlsx |
| NRS-11 | NRS dwelling estimates by 2011 DZ: CT bands, plus **type (D/S/T/F/unknown) and rooms (1..7+, median)** | DZ2011 | 2005-2025; **type/rooms only 2006-2017** | OGL | https://www.nrscotland.gov.uk/media/fqword2k/dwellings-estimate-by-2011-data-zones.xlsx (landing page https://www.nrscotland.gov.uk/publications/small-area-statistics-on-households-and-dwellings-2025/) |
| UR | SGUR 2022 to DZ2022 lookup (UR2/3/6/8, based on population-weighted centroid) | DZ2022 (7,392 rows) | 2022 | OGL | https://www.gov.scot/publications/scottish-government-urban-rural-classification-2022/documents/scottish-government-urban-rural-classification-2022---data-zone-2022-lookup/ |
| EPC | Domestic EPCs, dataset to Q1 2026 (floor area, construction age band, property type, habitable rooms, UPRN) | address/UPRN | Q2 2016-Q1 2026 | OGL for non-address fields. Address fields fall under Royal Mail/OSG terms | https://statistics.gov.scot/data/domestic-energy-performance-certificates (GIS bot owns the rollup) |
| PRS | Private Sector Rent Statistics, Scotland, 2010-2025: average advertised rents by **18 BRMAs** x size (1-bed shared, 1-4 bed), years to end-September | BRMA | 2010-2025 | OGL (gov.scot official statistics) | https://www.gov.scot/publications/private-sector-rent-statistics-scotland-2010-to-2025/documents/ (open-data CSV: `.../documents/prs-rent-statistics-2025---private-rents-open-data/`) |
| HPI | Council HPI slice, already in repo `data/processed/council_hpi.csv` | council | monthly | OGL | (repo) |
| RBC | Rebuild cost. **No open per-m² table exists.** The BCIS models behind the ABI calculator are licensed (BCIS Rebuild Matrix / ProtX). The free calculator is for individual householders, not bulk use | n/a | Jan-2025 base; BCIS reports +3.8% y/y | **Proprietary** | https://www.bcis.co.uk/products/insurance/ ; https://www.bcis.co.uk/news/rebuild-cost-models-update-shows-uplift-in-reinstatement-costs/ ; free calculator https://abi.bcis.co.uk/ |

Profiled RoS CSV: long format `GeographyCode, GeographyName, GeographyType, DateCode, Measurement{Count,Mean,Median,Lower Quartile,Upper Quartile}, Units, Value`. Of 6,976 DZ2011 zones, 6,926 have a Count row in 2023, but only **6,246 have a Median row**, so about 730 (10.5%) are suppressed. A suppressed cell is an absent row, not a `*`. The worst year is 2009, with 5,572 medians.

**[CONFLICT] Data vintages are mixed.** Prices, SIMD 2020 and NRS type/rooms are on DZ2011. UR6 2022 and the current NRS CT bands are on DZ2022. Section 7 sets out the vintage decision.
**[CONFLICT] Rule 2's "NRS dwellings by type and rooms" is stale.** NRS has not published type or rooms since 2017, and never on DZ2022. Proposal: EPC (type, floor area, rooms, age) becomes the primary mix source. NRS 2017 type/rooms becomes the fallback and EPC-coverage check, and NRS-CT supplies dwelling counts and the band ranking signal.

---

## 1. Price to residual land value

For zone z, year t (DZ2011 native):

1. **Market value per dwelling.** `P_z,t` = RoS **mean** price (proposed). Mean is additive (mean P − mean DRC = mean L), which matters because DRC is a mix-weighted mean. The median is kept as a robustness column. The repo currently uses the median (`dz2011_prices.csv`); see Q4.
2. **Index to the valuation date** `T` (config `surface_rent.valuation_date`, default to match `valuation.valuation_date` = 2025-04-01): `P*_z,t = P_z,t × HPI_c(T) / mean_months(HPI_c, t)`. This is the same method as `scripts/data/build_council_prices.py`.
3. **Pool years** (section 3) to get `P̄_z` and `n_z`.
4. **Rebuild cost new per dwelling** for the zone's *sold-stock* mix k ∈ {detached, semi, terrace, flat-purpose-built, flat-conversion}:
   `RC_z = Σ_k w_z,k × A_z,k × c_k × f_region(c) × f_index(T)`
   - `w_z,k`: mix share. Source: EPC certificates in the zone (sale/let-triggered, so closer to the sold mix), shrunk toward the NRS-2017 stock mix when EPC coverage is below `epc_min_coverage`.
   - `A_z,k`: median EPC total floor area (m²) by type in the zone, falling back to IZ and then council.
   - `c_k`: £/m² by archetype from config. The current repo values (`house 1950`, `flat 1850`) are labelled `ASSUMPTION, unsourced` in `agr.yaml _meta`. They must be replaced by a sourced table (Q2).
   - `f_region`: reuse `valuer_roll.rebuild.region_factors`, or replace with BCIS location factors if licensed.
5. **Depreciation by EPC construction age band.** `DRC_z = Σ_k w_z,k × RC_z,k × r(age_z,k)`, where `r(a) = max(r_min, 1 − a / L_life)` and `a = T − midpoint(age band)`. Config defaults: `L_life = 100` years and `r_min = 0.30` (both labelled ASSUMPTION). A config `refurb_uplift` covers pre-1919 stone stock that remains habitable. Age bands are mapped to midpoints in config, never inline.
6. **Residual:** `L_raw_z = P̄_z − DRC_z`, then `L_z = max(0, L_raw_z)`. When `L_raw_z ≤ 0`, set `flag_residual_nonpositive = true`, **store `L_raw_z`**, and tag `zero_floor`. Nothing is hidden (rule 2). The existing AGR `max_site_share 0.85` ceiling is **not applied** to surface rent (see Q5).
7. **Tag:** `value_basis = 'proxy'` always (rule 2), never `'market'`.

## 2. Land value model (fills thin zones and smooths noise)

- Target: `y_z = log(L_z + δ)` on zones with `n_z ≥ n_min` (pooled count, default 5) and `L_raw_z > 0`. Zero-floored zones enter a separate hurdle (logit of nonpositive) so that zeros are not dropped silently.
- One model per **UR6 class** (rule 4). UR8 is used for display only. Class adjacency for borrowing: 1↔2, 2↔3, 3↔4, 3↔5, 4↔6, 5↔6. A class with fewer than `class_min_zones` (default 150) training zones is fitted with the adjacent class's data, with class as a fixed effect. Tag `borrowed_class:<c>`.
- Form: hierarchical (partial pooling) linear model with random intercepts for council, and for IZ nested in council. This generalises the existing `shrinkage_k = 8` IZ shrinkage. Later option: gradient boosting with monotone constraints (OpenAVMKit path in `docs/valuation-roadmap.md`).
- **Allowed drivers (rule 4):** SIMD access domain travel times (drive and public transport to GP, retail, school, post office), bus accessibility, broadband, dwelling density (NRS dwellings/ha); negatives: near-derelict (VDL), resident-felt crime (housebreaking, vandalism, violence, from the SIMD crime domain). Crime is down-weighted or masked in town-centre and low-resident zones (residents < `crime_min_residents`; mask list from GIS). GIS flood, noise and air-quality overlays come in as zone address-share exposures.
- **Excluded (rule 5):** income, employment, deprivation ranks and composite SIMD. **[CONFLICT]** The repo's `surface_wealth.simd_income_rank` column must not feed the model. Harm from an identifiable polluter that the eco module charges to its source is entered as `net_of` and **not** as a driver (GIS bot to tag overlays `charged_to_source`).
- **CT band ranking signal:** the band distribution (share of A-C/D-E/F-H, mean band index) enters as a covariate. For suppressed zones it also gives a rank-consistency check: the predicted L rank within council vs the band rank. Rank inversions above `rank_tol` get the tag `ct_rank_conflict`.
- SIMD 2020 is DZ2011, so it can be joined natively if the model runs on DZ2011. A DZ2022 model needs the Data Zones crosswalk (section 7).

## 3. Suppressed / low-sales zones

Order of fallbacks. Each step writes a proxy tag:
1. `n_z,T-window ≥ 5` over the latest `pool_years` (default 3: 2021-2023), indexed and count-weighted → `observed_pooled_3y`.
2. Widen to `pool_years_max` (default 5: 2019-2023) → `observed_pooled_5y`.
3. Still thin, or suppressed in all years → **model prediction** `L̂_z` (section 2) with interval → `model_filled`. **Never copied from a neighbour** (rule 1). A thin observed value (5 ≤ n < 15) is blended with the model as `L = (n·L_obs + k·L̂)/(n + k)`, k = `shrinkage_k` → `shrunk_to_model`.
4. Zones with no dwellings → `no_residential`, so no surface rent (not zero).
Suppression is detected by an absent Median row, not by 0. This matches the existing `zone_prices.py` rule in history.

## 4. Yield (team lock: BRMA x UR6 table)

1. **Gross yield cell** for BRMA b, class c, year t:
   `g_b,c = 12 × R̄_b(mix_b,c) / P̄_b,c`
   - `R̄_b(mix)`: PRS mean advertised monthly rent by bedroom size, weighted by the bedroom mix of the b×c stock (EPC habitable rooms mapped to bedrooms via config, or NRS-2017 rooms). The rent year to end-September t is aligned to RoS calendar year t.
   - `P̄_b,c`: RoS indexed mean price over the DZs in b×c, weighted by dwelling count × `dz_brma_share`. The mix must be the **same** on both sides.
   - **[CONFLICT/limitation]** PRS is published by BRMA x size only, not by urban-rural class. Within a BRMA, rent therefore does not vary by class, so the class variation in g comes only from prices. This makes yields in cheap rural cells look too high. Mitigations: cap the ratio to the BRMA-wide yield at `[0.7, 1.4]` and flag. Ask SG/Rent Service Scotland whether the Market Evidence Database can be split by UR class.
2. **Gross yield to land yield** (config deductions, all labelled ASSUMPTION until sourced):
   `y_land = g × (1 − void) × (1 − opex) − dep_bldg × (DRC/P)`
   with defaults `void = 0.04`, `opex = 0.25` (management, repairs, insurance, compliance), and `dep_bldg = 1/L_life` applied to the building share. Q3 covers the alternative residual-income form `rent_L = R_net − (y_land + dep) × DRC`.
3. **Thin evidence:** a cell with fewer than `prs_min_records` (published sample counts) or fewer than `price_min_sales` falls back to the BRMA-wide value, then to `surface_rent.yield.fallback` (default 0.05). That default is consistent with `valuer_roll.yield_rate`, but the code still has `yield_rate` `as_of: unknown`. Tag `yield_fallback:<level>`.
4. **Zone yield** = Σ_b `dz_brma_share(z,b) × y_land(b, c_z)`. GIS supplies `dz_brma_share(code, vintage, brma_id, dwelling_share)`, with Σ_b = 1 per zone validated at load (tolerance 1e-6).
5. Never hard-coded (rule 3). Note: `backend/georgist/calibration.py` currently hard-codes `cap_rate = 0.05`, which must change.
6. Business land rent from SAA rateable values is a **later module** and is out of scope here.

## 5. Rent and apportionment

- `rent_dwelling_z = L_z × y_zone_z` (£/yr per average dwelling) and `rent_zone_z = rent_dwelling_z × dwellings_z`.
- Apportionment below the zone, and any crosswalk, is **by addresses/parcels** (rule 6): UPRN/address counts, or parcel shares weighted by dwellings. **Never by area.** **[CONFLICT]** The repo's `surface_wealth.rent_per_ha` and the AGR `area_elasticity 0.35` parcel scaling are area-based. Surface rent must not use them. The AGR lens may keep its own convention, pending Georgist ruling (Q5).

## 6. Holdout validation

Land value is unobserved, so validate the **implied price** `P̂ = L̂ + DRC` against the observed RoS price, and validate yields against held-out PRS cells.
- **H1 zone holdout:** 15% of zones with n ≥ 15, stratified by UR6 × council, masked and predicted by the model.
- **H2 suppression mimic:** zones with 5 ≤ n ≤ 9 are treated as suppressed and their model fill is compared with the observed value. This tests the real use case.
- **H3 spatial block:** hold out whole IZs (10%) to stop leakage through the IZ random effect.
- **H4 temporal:** fit on 2019-2022 indexed data and predict 2023.
- **H5 yield:** leave-one-BRMA-out on the g model, plus a check that each zone's yield lies within the PRS lower/upper quartile band.
- **Metrics (IAAO-style, per UR6 class and council):** median ratio P̂/P (target 0.95-1.05), COD (target ≤ 15 urban, ≤ 20 rural), PRD (0.98-1.03), PRB (±0.05), MdAPE, 80% interval coverage (target 75-85%), Spearman ρ of L̂ vs mean CT band within council, and the share of zones flagged nonpositive. Results go to `surface_rent_validation` with seed and config hash. Holdout zone lists are pinned in a file so they are reproducible.

## 7. Geography / vintage decision (proposal)

- **Compute on DZ2011**, native to RoS, SIMD 2020 and NRS-11. UR6 is assigned to DZ2011 by **dwelling/address-weighted majority** from the DZ2022 lookup through the Data Zones crosswalk. Ties or a share below 0.6 get the tag `ur6_mixed`. Alternative: use the 2020 UR in repo `dz2011_urban_rural_2020.csv`, but that file is UR8 2020, not UR6 2022.
- **Publish on both vintages.** DZ2022 figures come from the crosswalk using **address/dwelling weights for rent and value** (rule 6). The Data Zones bot's population-weighted crosswalk is used for **denominators only** (per-person figures). Each row records `crosswalk_method`.

## 8. Output table (PostGIS), `surface_rent_dz`

Follows repo conventions: zone code as text key, `updated_at`, provenance in the style of `sales_schema.SalesProvenance`, and the `_meta` labelling (`ASSUMPTION`, `as_of`, `source`).

```sql
CREATE TABLE surface_rent_dz (
  code                 TEXT NOT NULL,          -- S01… (renamed from zone_code, 12.4)
  vintage              TEXT NOT NULL,          -- 'DZ2011' | 'DZ2022' (renamed from zone_vintage, 12.4)
  valuation_date       DATE NOT NULL,
  ur6_class            SMALLINT, ur8_class SMALLINT,
  dwellings            INT,                    -- NRS
  sales_n_pooled       INT, evidence_years TEXT,  -- e.g. '2021-2023' (renamed from price_years, 12.4)
  price_mean_gbp       NUMERIC, price_median_gbp NUMERIC,
  rebuild_new_gbp      NUMERIC, remaining_factor NUMERIC, drc_gbp NUMERIC,
  land_value_raw_gbp   NUMERIC,                -- may be negative; never hidden
  land_value_gbp       NUMERIC,                -- max(0, raw) or model
  flag_residual_nonpositive BOOLEAN NOT NULL DEFAULT false,
  yield_gross          NUMERIC, yield_land NUMERIC, yield_source TEXT, brma_mix JSONB,
  rent_per_dwelling_gbp NUMERIC, rent_zone_gbp NUMERIC,
  lv_low_gbp NUMERIC, lv_high_gbp NUMERIC, rent_low_gbp NUMERIC, rent_high_gbp NUMERIC,
  value_basis          TEXT NOT NULL DEFAULT 'proxy' CHECK (value_basis IN ('proxy')),
  value_tier           TEXT NOT NULL,          -- 'observed_pooled'|'shrunk_to_model'|'model_filled'|'no_residential'
  uncertainty          TEXT NOT NULL,          -- 'low'|'medium'|'high' (from interval width)
  commons_class        TEXT NOT NULL,          -- Georgist vocabulary, e.g. 'surface_residential'
  net_of               TEXT[],                 -- e.g. {'eco:charged_to_source'}
  crosswalk_method     TEXT NOT NULL,          -- 'native'|'address_weighted_dz11_dz22'
  proxy_tags           TEXT[],                 -- pooled_5y, model_filled, borrowed_class:5, zero_floor, ct_rank_conflict, yield_fallback:brma, ur6_mixed, epc_low_coverage
  method               TEXT NOT NULL,          -- 'residual_drc_surface_v1'
  model_version TEXT, config_sha256 TEXT, source_sha256 JSONB,
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (code, vintage, valuation_date)
);
```
Also: `surface_yield_cell(brma_id, ur6_class, year, g_gross, y_land, prs_n, price_n, source_tier)` and `surface_rent_validation(run_id, holdout, stratum, metric, value, target, pass)`.

## 9. Config sketch (new block in `data/config/agr.yaml` or `surface_rent.yaml`)

```yaml
surface_rent:
  method: residual_drc_surface_v1
  valuation_date: "2025-04-01"
  price_measure: mean            # Q4
  pool_years: 3
  pool_years_max: 5
  n_min: 5
  shrinkage_k: 8
  class_min_zones: 150
  ur6_adjacency: {1:[2],2:[1,3],3:[2,4,5],4:[3,6],5:[3,6],6:[4,5]}
  rebuild:
    source: TBD                  # Q2; per-archetype £/m², labelled ASSUMPTION until sourced
    gbp_per_m2: {detached: null, semi: null, terrace: null, flat_pb: null, flat_conv: null}
  depreciation: {life_years: 100, remaining_min: 0.30, age_band_midpoints: {}}
  yield:
    table: brma_x_ur6
    deductions: {void: 0.04, opex: 0.25, building_dep: "1/life_years"}
    cell_ratio_cap: [0.7, 1.4]
    prs_min_records: 30
    price_min_sales: 30
    fallback: 0.05
  crime: {min_residents: 300, mask_town_centres: true}
```

## 10. Open questions

**Lead engineer / Laurie**
1. **Repo is broken at HEAD.** `api/main.py` and `agr/engine.py` import modules deleted in `4aa9219` (2026-10-05 20:52 BST): `agr/valuation.py`, `agr/zone_prices.py`, `agr/wide_range.py`, `validation/*`, `etl/convert_sales_csv.py`, `etl/ingest_sales.py`, all of `backend/tests/` and `.github/workflows/ci.yml`. `georgist/surface_rent.py` and `surface_harvester.py` are imported but were never committed. Restore from `c6adad0`, or rebuild?
2. **Rebuild cost source:** license BCIS (Rebuild Matrix), or accept a labelled open approximation? BCIS bulk use needs a licence, and the free ABI calculator is not for bulk use.
3. **Yield form:** a yield applied to L (team lock), or residual income (net rent − return and depreciation on DRC)? Also confirm the void and opex defaults.
4. **Price measure:** mean (additive with DRC) or median (current repo, robust)?
5. **Interaction with the AGR lens:** Pickard 0.70 despeculation, the 85% ceiling and area elasticity exist in `valuer_roll`. Confirm none apply to surface rent.

**Georgist bot:** the `commons_class` vocabulary; whether the CT band covariate may also enter the fit (not only ranking); the crime masking threshold; whether EPC may replace stale NRS type/rooms (rule 2 wording).
**GIS bot:** EPC rollup per DZ2011 and DZ2022 (type share, median floor area by type, age-band distribution, rooms, coverage ratio); `dz_brma_share`; overlay exposures as address shares with a `charged_to_source` flag; town-centre mask.
**Data Zones bot:** an **address/dwelling-weighted** DZ2011↔DZ2022 crosswalk in addition to the population-weighted one (rule 6 forbids area and population weights for rent); the SIMD 2020 to DZ2022 method.

---

## 11. Changes from v0.1 made while drafting code (branch `valuation/surface-rent-v1`)

- Config lives in its own file `data/config/surface.yaml` (block `surface_rent:`), not in `agr.yaml`. Rebuild £/m² is `status: PENDING_SOURCE` with null values. `rebuild_rates()` raises `PendingSourceError` until every type and a `source` are set. Research runs must pass rates explicitly.
- Dwelling types are fixed to `detached, semi_detached, terraced, flat_purpose_built, flat_conversion`. EPC age-band labels in config are placeholders to check against the SEPCR publication note.
- Depreciation stores band **midpoint years** rather than a fixed remaining-factor table, so changing the valuation date re-ages the stock.
- The class cap is applied only to evidence-based cells. Fallback cells (BRMA-wide or config) are not capped. A zone whose blended yield is ≤ 0 is tagged `yield_nonpositive` and rent is floored at 0.
- The output row adds `price_measure` and `config_status` columns. `brma_mix` is the GIS share map.
- Harvester facts from the real files: the RoS grid has 6,970 DZ2011 codes (6 codes never appear in any year), and 724 are suppressed in 2023. The SGUR DZ2022 CSV is cp1252, not UTF-8. UR6 class sizes (DZ2022): 1=2910, 2=2362, 3=738, **4=156**, 5=885, 6=341, so class 4 (Remote Small Towns) will be below `class_min_zones=150` once restricted to zones with sales and will borrow.

---

## 12. v0.3: open rebuild estimate and alignment with ECONOMIC_RULES.md v0.1 (2026-10-06)

**Rebuild £/m² (status OPEN_ESTIMATE, price base Apr-2025 = valuation date, uplift 1.0).** Full derivation and sources are in `data/config/surface.yaml` (`rebuild:`).
- Base: BCIS UK median £/m² rows as quoted by Aberdeenshire Council (Apr 2025). For each type, low = min row, central = mean of rows, high = max row.
- Then multiply by a Scotland location factor (0.86 / 0.93 / 1.00) and by on-costs for fees, externals and demolition (1.05 / 1.15 / 1.25, ASSUMPTION).

| type | low | central | high |
|---|---|---|---|
| detached | 1319 | 2058 | 3122 |
| semi_detached | 1338 | 1771 | 2398 |
| terraced | 1314 | 1672 | 2131 |
| flat_purpose_built | 1504 | 1936 | 2545 |
| flat_conversion | 1504 | 1936 | 2962 |
| other | 1314 | 1880 | 3122 |

Cross-check: SHN DVfM 2022/23 gives £2,145/m² for affordable new build. Rolled forward with SSHTPI (about −3% to 2025), that is about £2,080/m², inside every band.

The band is carried through every row: `drc_low/high`, `land_value_low/high` (low rebuild gives high land), and `uncertainty_low/high` on `measured_rent`.

**Illustrative real-price run.** RoS 2023 DZ2011 medians, NRS 2023 dwellings, one "other" archetype (97 m², remaining factor 0.55). Results are internal (public-repo rule): figures are kept in the internal notes and output directory, not in tracked files.

The internal run indicated rebuild cost is likely to dominate the error, and the holdout tests should check this early (BCIS trigger, rules 6.2).

**Schema now follows the rules doc.** Output columns:
- Residual and rent: `raw_residual`, `negative_residual`, `land_value(_low/_high)`, `measured_rent(_per_dwelling)`, `uncertainty_low/high`.
- Breakdowns, never totalled: `infra_share`, `planning_uplift` (blank and flagged until the farm proxy exists).
- Policy: `policy_despec_factor` / `policy_rent` (urban 0.70), never inside `measured_rent`.
- Tiers and publication: `value_tier = proxy`, `quality` (derived / modelled / placeholder), `fill_method`, `publish_level`.
- Provenance: `commons_class = surface`, `net_of` ∈ {extractive, eco_externality}, `use_basis`, `crosswalk_method` ∈ {none, pop_hhres_2022, address_uprn, value_weighted, footprint_area}. Surface may only use none, address_uprn or value_weighted. Also `source_id`, `licence`, `price_year`.

Totals: only `measured_rent` can be summed, per value tier. Blocked zones and placeholders are excluded.

**Rule 4.2 ceiling:** `observed_total_value = MEAN price × dwellings`, on the same vintage, otherwise an error. Ceiling rent = that total × gross yield. A breach (the low end of the module sum exceeds the ceiling) sets `publish_level = blocked`.

**Rule 12 checks** (`surface_holdout.py`): `two_route_check`, `gradient_check` (UR6 partial order plus access bins), `national_share_check` (range [0.49, 0.73] ± 0.10, sources in config), and `rebuild_sensitivity`.

### Conflicts and gaps against ECONOMIC_RULES.md (for the Georgist bot or the lead)
1. **6.1 median vs additivity.** The spine is now median by default (complies), but median price − mix-mean DRC is not additive. The 4.2 ceiling and the national share use the mean.
2. **1 capital value "derived only, V = R/(r−g)".** We derive capital land value from prices first, then rent = L × land_yield. Proposal: treat `land_yield` as ≡ r − g, or add explicit r and g.
3. **4.2 "observed economic rent evidence" is undefined.** Implemented as mean × count × gross yield. Other modules must be crosswalked to DZ2011 for the check.
4. **12.1 two routes is tautological.** PRS rent is only published per BRMA, and the land yield comes from the same cell, so the rent route reduces algebraically to P − DRC (shown in a test). It needs zone-level rent evidence, or should be downgraded.
5. **12.3 range not stated in the rules.** I propose [0.49, 0.73] ± 0.10. The UK ONS-derived 0.73 is an upper reference for Scotland.
6. **6.6 CT bands "by 2022 zone".** NRS also publishes CT bands on DZ2011 up to 2025, so they can be used natively on the DZ2011 spine. Suggest amending the wording.
7. **publish_level enum** {public, zone_total_only, internal, blocked} and the mapping from fill method are assumptions until GIS confirms.
8. **No `native` value in the crosswalk enum.** Native-vintage rows use `none`.
9. **6.3:** only strictly negative residuals are flagged. A residual of exactly 0 is not flagged.

### 12.1 Aligned to ECONOMIC_RULES.md v0.3 (2026-10-06)

The v0.3 rules supersede items 1, 2, 4, 6 and 7 in the conflict list above. What changed in the code:

- **Mean for anything that adds up (6.1).** `price.measure = mean`. A row refuses a median-pooled price.
  - Zone total land value = (mean P − mean DRC) × dwellings (`land_value_zone_total`).
  - `measured_rent` = zone total × land yield. `measured_rent_per_dwelling` = `measured_rent` / dwellings.
  - Pooling the mean across years is exact (Σ n·mean / Σ n). It now requires an HPI `index_factor` and a stated `index_to_year`; mixing price years without indexing raises.
- **Median is display only.** It is shown as `typical_sale_gbp`, with `mean_median_ratio` alongside.
  - `price_skew_flag` (tag `price_skew_small_sample`) fires when pooled sales are below `skew_flag.small_sales_n_below` (default 15, equal to `n_full`) and mean ÷ median ≥ `skew_flag.mean_median_ratio_min` (default 1.40).
  - Why 1.40: in RoS DZ2011 zone-years 2019–2023, the 95th percentile of mean ÷ median is 1.381 for zones with 5–9 sales and 1.389 for 10–14 sales. So the flag catches roughly the top 1 in 20 small zones.
- **Rebuild mix for the same homes.** `choose_rebuild_mix()` uses the mix of homes that sold (EPCs lodged for marketed sales in the price window) when there are at least `rebuild_mix.min_sold_records` (5, ASSUMPTION). Otherwise it uses the whole stock. `rebuild_mix_basis` (sold | all_stock) is stamped on every row, and all_stock is also tagged.
- **Land yield is r − g (rule 1).**
  - Config holds one figure, `yield.land_yield` (0.05, ASSUMPTION), which is also the thin-cell fallback.
  - `configured_land_yield()` refuses `r`, `g`, `discount_rate` or `growth_rate` in the yield config.
  - r and g may appear only under `scenarios`. `scenario_r_g()` and `capital_value(..., scenario=)` assert r − g == land_yield. V = R / land_yield, derived only.
- **Two-route check (12.1).** A pair counts only when its rent evidence is `saa_rateable_value`, or `brma_held_out` for a BRMA not in `calibration_brmas`. Same-cell PRS pairs are dropped and counted in `n_dropped_not_independent`. With nothing countable, `status = not_applicable` and `pass = None`. The shared rebuild assumption is still recorded.
- **Negative residuals by class (12.2).** New `negative_by_class_check`: it fails if more than 10% of zones (ASSUMPTION) in UR6 classes 1–2 are negative. Weak-market classes are reported but not failed.
- **Dwellings by year and vintage (rules 2 / 4.2).**
  - Rows take a `DwellingCount(count, year, vintage)` from `dwellings_for()`, which is an exact `(code, vintage, year)` lookup. A missing year gives `count=None` with the tag `dwellings_missing_year`, and is never filled from the nearest year.
  - `build_output_row` and `observed_total_value` raise `YearMismatchError` unless `price_year == dwelling_year`, and `VintageMismatchError` unless the vintages match.
  - A missing-year row gets `quality = placeholder` and `publish_level = internal`, has no rent and is left out of totals.
- **Rebuild price year (rule 2).** `rebuild.uplift.factor_by_price_year` holds only 2025: 1.0. Asking for the band at any other `price_year` raises `PendingSourceError`, so prices and rebuild cost can't be subtracted across price years. A real run must index RoS prices to 2025 and use 2025 dwelling counts, or add a sourced ONS OPI factor for the price year.
- **publish_level (rules 2 v0.3).** Exact enum: `public_site | public_zone | internal`. Every surface residential figure is `public_zone`; `no_residential` is `internal`. A reconciliation breach sets `internal` with the tag `reconciliation_breach` and is excluded from totals; `blocked` is no longer a level.
- **Illustrative re-run with means** (RoS 2023 means, NRS 2023 dwellings, one 97 m² archetype, remaining factor 0.55, rebuild at the 2025 base). Results are internal (public-repo rule): figures are kept in the internal notes and output directory, not in tracked files.

**Still open:**
- (a) Rule 2 says "code carries only what is listed here", but rows also carry diagnostic and provenance columns (`raw_residual`, `drc_*`, `typical_sale_gbp`, `price_skew_flag`, `rebuild_mix_basis`, `dwelling_year`, `proxy_tags`, ...). Should these be allowed as diagnostics, or moved to a side table?
- (b) Rule 1 vs 6.4: config holds one `land_yield`, but 6.4 calibrates yields per BRMA × UR6 cell. I read "one config number" as the fallback and the scenario anchor, with cell yields as calibration outputs (each one still r − g).
- (c) Independent rent evidence (SAA rateable values for residential, or held-out BRMAs) doesn't exist yet, so for residential v1 the two-route check will report `not_applicable`.
- (d) 12.2 threshold (10% negative in classes 1–2) and `min_sold_records` are assumptions.
- (e) Price year: RoS ends in 2023 and the rebuild base is 2025. Either an HPI index to 2025 (RoS/UK HPI Scotland series) plus 2025 dwelling counts from Data Zones, or a sourced OPI factor back to 2023.
- (f) The EPC "marketed sale" transaction-type filter for the sold mix needs checking against the SEPCR fields before ingest.

### 12.2 Price-year alignment and rules v0.4 (2026-10-06)

**Index (decided by the lead).** RoS 2023 DZ2011 mean prices are moved forward to the rebuild price base with the free UK House Price Index. Moving rebuild back to the price year is never done (rules 2, v0.4).

- **File:** UK HPI full file, July 2026 release (data to Jul 2026), OGL v3. Publishers: HM Land Registry, Registers of Scotland, ONS.
  - CSV: https://publicdata.landregistry.gov.uk/market-trend-data/house-price-index-data/UK-HPI-full-file-2026-07.csv (sha256 `654a5419…6607`, downloaded 2026-10-06)
  - Landing page: https://www.gov.uk/government/statistical-data-sets/uk-house-price-index-data-downloads-july-2026
- **Geography:** Scotland council areas (S12). All 32 codes match the council codes in the NRS DZ2011 file. Not data zone.
- **Series:** the non-seasonally adjusted `Index` (Jan 2023 = 100), by property type (`DetachedIndex`, `SemiDetachedIndex`, `TerracedIndex`, `FlatIndex`). The all-dwellings `Index` is the fallback.
- **Factor:** index in April 2025 (the single month that matches the rebuild price base, Apr-2025) ÷ mean of the 12 monthly values in 2023 (RoS prices are calendar-year).
- **By type:** value-weighted (Laspeyres), f = Σ s_t·P_t·f_t / Σ s_t·P_t.
  - s_t = the zone's type mix (NRS 2017 DZ2011 type counts until the EPC sold mix lands).
  - P_t = the council's UK HPI average price by type in 2023.
  - If a zone has no mix, the all-dwellings index is used.
- **Tags:** every indexed row carries `indexed_council_hpi`, because trends within a council can differ by zone. A factor with |ln f| > 0.15 is also tagged `index_factor_extreme`. Shetland, for example, is 1.25 from 2023 to Apr-2025.
- **Columns** (names superseded by 12.4: `price_year` → `evidence_year`, `price_base_year` → `price_year`)**:** raw RoS `price_gbp` and `price_year` (2023) are kept unchanged. New columns: `price_indexed_gbp`, `price_index_series`, `price_index_factor`, `price_base_year` (2025). The residual uses the indexed price.
- **Code:** `hpi_factor`, `index_price`, and `load_uk_hpi` / `council_hpi_points` in the harvester (a base year without all 12 months raises).

**Year checks.** The rebuild price base (2025) must equal `price_base_year`. Otherwise `YearMismatchError`.
- The raw `price_year` may differ from the base only through a recorded index; a row without a series is refused.
- Dwellings must be on the price vintage and, by default, `dwelling_year == price_base_year` (`dwellings.year_policy: strict`).
- `lag_allowed` (PENDING Georgist ruling): `dwelling_year` may be the latest published year up to `max_lag_years` before the base. Never a later year, and never extrapolated.
  - The row is flagged `dwelling_year_lag` (number of years).
  - Per-dwelling rent is at the 2025 price base; the zone total uses the latest published count.
- **Dwellings source:** NRS DZ2011 file, years 2005–2025 (https://www.nrscotland.gov.uk/media/fqword2k/dwellings-estimate-by-2011-data-zones.xlsx, sha256 `6fdf2951…df4e49`, the same file GIS holds). It already includes a 2025 sheet, so strict mode works with 2025 counts. It is tagged `dwellings_nrs_interim_pending_data_zones` and stamped `dwellings_source` until Data Zones supplies the canonical counts. The loader's vintage label no longer claims a reference month ("year N sheet").

**Rules v0.4.**
- **Required fields:** the 12 fields in `REQUIRED_FIELDS` must be present; a non-placeholder row with any of them empty is rejected (`RowRejectedError`).
- **Internal-only diagnostics:** `INTERNAL_ONLY_COLUMNS` (`raw_residual`, `drc_*`, `rebuild_new_gbp`, `remaining_factor`, `land_value_low/high`, `typical_sale_gbp`, `mean_median_ratio`, `price_skew_flag`, `rebuild_mix_basis`, `brma_mix`, `yield_source`, `fill_method`, `proxy_tags`) stay on the internal row. `public_view()` drops them.
- **`publication_status` (ok | blocked)** is separate from `publish_level`. A 4.2 ceiling breach sets `blocked` and leaves `publish_level` unchanged, so clearing the block restores the figure. Blocked rows are excluded from totals and from `public_view()`.
- **Placeholders** (e.g. a missing dwelling year) are never served by `public_view()` and never totalled.
- **EPC sold-mix proxy:** certificates from the last 10 years. Coverage above 100% means recent certificates only, flagged by `epc_coverage_tags()`.
- **Output files:** `georgist/surface_manifest.write_outputs()` writes `<stem>_internal.csv` (all columns, `internal`) and `<stem>_public.csv` (public view, `public_zone`). It also writes `manifest.csv` in the GIS format: file, owner, source, licence, publish_level, zone_vintage, key `(code, vintage)`, rows, sha256.

**Illustrative national run, aligned to 2025 (internal).** RoS 2023 DZ2011 mean prices for zones with at least 5 sales, indexed to Apr-2025 by type-weighted council UK HPI; NRS 2025 DZ2011 dwelling counts; one "other" archetype (97 m², remaining factor 0.55) at the 2025 band. Results are internal (public-repo rule): figures are kept in the internal notes and output directory, not in tracked files.

### 12.3 EPC rebuild inputs, SGUR 2020, rules v0.5 (2026-10-06)

**ILLUSTRATIVE.** Every row here is an internal diagnostic and is never served. Prices are RoS 2023 DZ2011 means indexed by council UK HPI to Apr-2025. Rebuild uses the OPEN_ESTIMATE band.

**EPC rollup (GIS).** `epc_dz_rollup.csv` has 83 columns and 14,368 rows covering both vintages, sha256 `38d086bc248aff1d4ee5825b6334d756d1c371390b94846b24a5282412879071`.
- Checked against the GIS `manifest.csv` with `surface_harvester.load_gis_output`, which verifies sha, row count, key `(code, vintage)` unique, declared vintages, and no missing or `unknown` codes.
- Filtered to DZ2011: 6,976 rows used, 7,392 DZ2022 rows ignored and never mixed. Joins are exact on code: NRS = SGUR = EPC (6,976).
- All six GIS manifest files re-verified (sha and rows OK).
- Licence: OGL v3. EPC postcode placement is Royal Mail **non-commercial research only**, so a licence check is needed before any commercial use.

**Rebuild per zone** (`surface_rent.zone_rebuild_inputs` / `zone_rebuild_band`).
- **All-certificate columns are primary.** `recent10_` is the sensitivity.
- Coverage > 1 means the stock denominator is stale. Those zones (82 of those priced) use recent10, tagged `epc_coverage_over_100_recent_only`.
- **Mix.** Type marginals map as follows:
  - house and bungalow are split into detached / semi / terraced by built-form shares, with unknown form dropped (tag `epc_mix_marginal_approx`);
  - flat and maisonette → `flat_purpose_built` (tag `epc_flats_as_purpose_built`);
  - park home and unknown → `other`.
  - Age bands are depreciated per band (life 100 years, floor 0.30). Type and age are treated as independent.
- **Floor area basis is MEAN.**
  - Detached / semi / terraced use `tfa_mean_house_m2`; flats use `tfa_mean_flat_m2`. Each is blank if fewer than 5 certificates.
  - Fallbacks run `tfa_mean_m2` → default 97 m² (tag `floor_area_default`).
  - Median is used only when the rollup has no mean columns (tag `floor_area_median_biased_low`).
  - Without EPC the fallback is NRS 2017 mix plus default area (`rebuild_mix_nrs2017_fallback`).
  - Every priced zone gets mean area with the house/flat split in the internal run.

**SGUR 2020 6-fold.** The DZ2011 lookup is at `https://www.gov.scot/binaries/content/documents/govscot/publications/advice-and-guidance/2022/05/scottish-government-urban-rural-classification-2020/documents/scottish-government-urban-rural-classification-2020-data-zone-2011-lookup/scottish-government-urban-rural-classification-2020-data-zone-2011-lookup/govscot%3Adocument/scottish-government-urban-rural-classification-2020-data-zone-2011-lookup.csv` (URL pinned in `surface_harvester.URC2020_DZ2011_URL`).
- sha256 `0440de97902c393c2568780505901251dab9426f0781069fb9c6a3a383f04851`, OGL v3.
- 6,976 unique S01 codes, UR6 values 1–6.

**Dwellings (rules v0.5 6.4).** Surface totals use NRS **total** dwellings, including vacant and second homes, and never households.
- **Interim file confirmed total dwellings.** The interim file (NRS dwelling estimates, council-tax valuation list, cover sheet "includes second homes") totals 2,763,896 for 2025.
- The household estimates (Sep 2025, sha `4061bbba…4fe6`) give 2,757,376 dwellings, 89,516 vacant, 20,876 second homes and 2,647,347 occupied.
  - Against the interim file: 50.5% of zones match exactly, with p99 absolute difference 52.
  - These estimates supply the `vacant_share` and `second_home_share` output columns, which are carried but don't change rent.
  - Their reference date (Sep) differs from the dwelling estimates (Dec).
- The loader is pluggable via `load_dwelling_counts(source, …)`:
  - `nrs_dwelling_estimates`;
  - `nrs_household_estimates`;
  - `datazones_ct_table`, a placeholder for Data Zones' canonical council-tax table (2014–2025, both vintages). Its schema is `code, vintage, year, dwellings_total[, occupied, vacant, second_homes]`. A households-only file raises.

**Yield blend.** Split zones use GIS `alt/dz_brma_share_dwelling_bounds.csv`:
- `share_mid` (sums to 1) gives the blend;
- `share_halfwidth` moves weight towards the low-yield and high-yield BRMA to give `y_low` and `y_high`, which widen the uncertainty band (tag `brma_share_bounds_in_band`).
- `household_share` is never treated as dwellings; missing bounds for a split zone raise.

**Map denominator.**
- Output `rent_per_res_ha = measured_rent / residential_land_ha`.
- `residential_land_ha` is a nullable input from GIS (`gis_residential_land`) or the rough fallback `settlement_area` (tag `res_land_settlement_area_rough`).
- Until it is supplied, `rent_per_res_ha` is null and tagged `pending_residential_land`.
- Any other source, such as whole-zone area, raises. Per-dwelling rent stays as the second output.

**Results.** Land share = Σ(price − DRC)·dw / Σ price·dw over priced zones, for EPC all-time, recent10 and the 97 m² archetype, with a decomposition (fixed remaining factor; zone mean without house/flat split; zone median area) and the 12.2 checks. Results are internal (public-repo rule): figures are kept in the internal notes and output directory, not in tracked files.

**Caveats.**
- The mix is reconstructed from marginals.
- Flats are all treated as purpose-built.
- Age-based depreciation (life 100 years, floor 0.30) is an assumption and moves results as much as floor area does.
- Rules 6.1 prefer recent10 for the sold mix, but the team set all-time as primary. Both are reported.

### 12.4 Rules v0.6: depreciation band, old-home review, per-hectare gradient, schema renames (2026-10-06)

**ILLUSTRATIVE.** Rows are internal diagnostics only.

**Depreciation band (rules 6.2 v0.6).** Config `surface_rent.depreciation`:
- `life_years: {low: 80, central: 100, high: 120}`;
- `remaining_min: {low: 0.20, central: 0.30, high: 0.40}`;
- `band_combination.rule: corner`.

The lead can mirror these keys in the engine settings.

**Combination rule: corner, not quadrature.**
- DRC per dwelling is monotone increasing in each of rebuild £/m², building life (slower write-down) and remaining-value floor. So the joint extremes of the input box are exact corners:
  - `drc_high_gbp` → `land_value_low` = **high rebuild × life 120 × floor 0.40**;
  - `drc_low_gbp` → `land_value_high` = **low rebuild × life 80 × floor 0.20**;
  - central = central × central × central.
- Quadrature (√Σ²) is not used:
  - it assumes the three errors are independent and random, with known spreads;
  - these are judgment ranges on systematic assumptions applied identically to every zone, so they don't average out in national totals;
  - quadrature would understate the band.
- The corner band is the honest envelope of the stated ranges. It is wide by construction.
- `surface_rent.band_corners` rejects any other pairing or rule.
- Tests:
  - the corners equal the max/min over the full 3×3×3 grid;
  - `land_value_low` pairs high rebuild with a long life and a high floor;
  - the band is wider than both the rebuild-only band and quadrature.
- The yield deduction for building depreciation uses the central life.
- Zones without an EPC age mix keep the fixed default remaining factor and get no depreciation band.

**Results** (EPC all-certificate, mean area, priced DZ2011 zones, Data Zones `dwellings_by_year` 2025, prices indexed to Apr-2025): national and per-UR6 land share and % zones / dwellings negative at each corner, the rebuild-only band and the recent10 sensitivity. Results are internal (public-repo rule): figures are kept in the internal notes and output directory, not in tracked files.

**Old large homes review (rules 6.2).** Method: zones negative at the high corner were compared with all priced zones on dwelling-weighted pre-1919 and post-1983 shares, mean floor area and median price; named examples were re-run across the life × floor grid at high and central rebuild. Qualitative finding (figures internal): the high-corner negatives are mainly young volume-built estates (1990s–2000s) drawing the high one-off detached rate, not old stock; lowering the floor would not fix them; life matters more than floor; some weak-market negatives can be real (rules 12.2). This motivated the procurement-route review in 12.5.

**Per-hectare gradient (rules 12.2 v0.6).** `surface_holdout.per_hectare_gradient_check`.
- **Between classes:** median observed land value per **residential** hectare must satisfy the `ur6_expected_order` pairs (1 ≥ 2 ≥ 3 ≥ {4, 5} ≥ 6).
- **Within each class:**
  - Spearman ρ of £/res-ha against the mean of the six drive-time minutes, and against the mean of the three public-transport minutes, must each be ≤ `access_rho_max` (−0.10, ASSUMPTION);
  - inputs are Data Zones `simd2020v2_access_indicators_dz2011` raw minutes;
  - SIMD ranks, scores and deciles are refused.
- **Observed zones only (Georgist ruling 2026-10-06):**
  - zones with fewer than 5 sales or `model_filled` are excluded and counted;
  - shrunk zones enter with their observed residual, not the blend;
  - `n_used_by_class` is recorded;
  - a class below `min_zones_per_class` (30) is `pending / insufficient_n`, and so are its pairs.
- **Residential land:**
  - runs only on GIS `dz_residential_land` (code, vintage, residential_land_ha, method) with `method = parcel_based`;
  - `settlement_area`, a missing file, or more than 5% of observed zones missing land or access returns `pending` with the reason.
- Land share is **not** used. It stays only in the national plausibility check, and the land-share ordering in `surface_illustrative` is a diagnostic only.
- Current status: `pending: residential_land_missing`.

**Schema renames for the lead's loader (2026-10-06).** These supersede the names used earlier in this spec.
- `zone_code` → `code` and `zone_vintage` → `vintage` in every output file. The manifest key `(code, vintage)` is now made of real columns, and writing a file without them raises.
  - The manifest's own `zone_vintage` column (GIS manifest format: which vintages a file covers) is unchanged.
  - Manifests gain a trailing `attribution` column.
- `price_year` = the year values are expressed in (2025, = rebuild price base), formerly `price_base_year`.
- `evidence_year` = the RoS sales year (2023), formerly `price_year`. `evidence_years` (window) was formerly `price_years`.
- `count_year` = the dwelling count year, formerly `dwelling_year`, and `count_year_lag` (formerly `dwelling_year_lag`).
- Dwelling counts join on `price_year`:
  - Data Zones `dwellings_by_year.count_year` is read, with `vintage` 2011/2022 normalised to DZ2011/DZ2022;
  - a missing count for that year leaves the row flagged `dwellings_missing_year` and is never filled from another year.
- `total_measured_rent` and `total_policy_rent` raise `YearMismatchError` on rows with differing `price_year`.
- **EPC licence and attribution:**
  - rows built from the EPC rollup must carry its licence text (`surface_manifest.epc_licence`), and `build_output_row` raises otherwise;
  - manifests for such files carry that licence plus the attribution "Contains Scottish Government EPC data licensed under the Open Government Licence v3.0. Contains NRS data © Crown copyright and database right 2026. Incorporates data from PAF® the copyright in which is owned by Royal Mail Group Limited. Contains OS data © Crown copyright and database right 2026."

**Data Zones canonical inputs, integer vintages (2026-10-06, same commit).**
- **Dwellings:**
  - source is Data Zones `dwellings_by_year` (`datazones` dir via `surface_paths`), verified against its manifest:
    - sha `b47605c6…c2b7`;
    - 98,496 rows;
    - key `(code, vintage, count_year)` unique;
    - integer vintages;
    - code ranges.
  - `dwellings_total` (council tax, September) is joined on `count_year == price_year` (2025). That gives 2,757,376 on 2011 zones (published NRS total).
  - Occupied, vacant and second-home shares are carried. `assessor_dwellings_dec` is dropped on load (reference only).
  - The interim NRS tag `dwellings_nrs_interim_pending_data_zones` is gone. The NRS loaders stay for checks only.
- **Vintage:**
  - stored as the integer 2011 or 2022 in every frame and output row (`surface_zones.vintage_int`), and `build_output_row` refuses strings;
  - codes are validated against the official ranges: S01006506–S01013481 (2011) and S01013482–S01020873 (2022). Mismatches raise.
  - Manifests keep the `zone_vintage` text label (`DZ2011;DZ2022`) as in the GIS and Data Zones manifests.
  - Synthetic test codes moved into range (S010134xx for 2011, S010208xx for 2022).
- **No-price zones:** DZ2011 has 6,976 zones = 6,246 priced (2023, ≥5 sales) + 724 suppressed (<5 sales) + 6 absent from the RoS file.
  - The 6 absent zones are Data Zones `zone_spine` flag `absent_from_ros_price_file`: S01007788, S01010206, S01010226, S01010462, S01010493, S01011598.
  - They are no-price zones: `resolve_land_value(absent_from_price_file=True)` gives `model_filled`, with land value None and tag `model_fill_pending` until the model exists. They are never zero.
- **Access indicators:** Data Zones `simd2020v2_access_indicators_dz2011` (sha `49428c29…b8ce`, 6,976 rows) is verified and wired into `per_hectare_gradient_check`, using the 6 drive and 3 PT minute columns only. All 6,976 zones parse.
  - The gradient is still `pending: residential_land_missing` because GIS `dz_residential_land` has not been posted.
- **GIS:** checksums were re-verified at about 01:45 BST and are unchanged (string vintages). The loaders accept the coming integer vintages and normalise both.

### 12.5 Rules v0.7: procurement-route estate rate, Georgist guard, swings, central-only checks, zero-dwelling zones, CI safety (2026-10-06)

DRAFT, not yet approved by Laurie. Results are internal until they pass the checks and Laurie approves them, so this section gives methods, parameters and sources only.

**Estate detached rate (rules 6.2 v0.7, procurement route).**
- Post-1980 detached homes on estates take a volume-builder estate rate. Pre-1980 and non-estate detached homes keep `rebuild.gbp_per_m2.detached`, which is unchanged.
- **Source:** [S1] Aberdeenshire Cost Index 2025 (V06.00, April 2025), page 1, Table 1, "Estate housing 4 units or more". These are UK median BCIS figures: single storey 1,718, two storey 1,461 and three storey 1,562 £/m². The 1.5-storey row is excluded because it is derived at +30%.
  - Cross-checks: West Lothian (BCIS Apr-2026), Midlothian Cost Index v14 (Apr-2026), and Highland, whose row reads "Estate housing (2-storey, incl. semi-detached)".
- **Gap, reported honestly:** no free council guide publishes a separate "estate housing – detached" row. The estate row is generic across built forms. The Georgist approved it on 2026-10-06 (rules sha256 prefix `933c3767`). Status `APPROVED_GENERIC_ESTATE`. Rows using it carry `rate_basis=generic_estate`, the rules-doc form that replaces the old tag `estate_rate_generic_estate_row`.
- The band uses the same factors as every other type (location 0.86/0.93/1.00, on-costs 1.05/1.15/1.25). That gives `detached_estate` = 1,319 / 1,690 / 2,148 £/m² (2025 base).
- **Source scope:** the source defines estate housing as schemes of 4 or more units, against one-off schemes of 3 or fewer. It states no plot size, so parcel size is our proxy for "on an estate".
- **Post-1980 EPC bands:** 1984-1991, 1992-1998, 1999-2002, 2003-2007 and 2008 onwards. The 1976-1983 band straddles 1980 and stays on the detached rate (conservative).
- **Open issue:** a one-off-only band from the one-off rows (2,383 / 2,498) would differ from the current blended `detached` band. Georgist to rule.

**Georgist guard: weighted blend, plot size never a driver.**
- Input: GIS estate fields on `dz_residential_land` (internal; built from RoS INSPIRE parcels and OS data). Per zone, the share of post-1980 detached homes in each parcel band (< 0.05 ha, 0.05–0.1 ha, > 0.1 ha), the median parcel size and the pre-1980 shares.
  - Fields are blank where a zone has fewer than 5 such homes; multi-address parcels are excluded.
- **Estate fraction** e = Σ wᵦ·shareᵦ / Σ shareᵦ, with w = 1 for < 0.05 ha, `band_weights.mid` (default 0.5) for 0.05–0.1 ha, and 0 for > 0.1 ha. There is no hard cut-off.
  - Mid-weight sensitivity at 0 and 1 (equivalent to hard cut-offs at 0.05 ha and 0.1 ha).
- Each detached × post-1980 component is split into a fraction e at `detached_estate` and 1 − e at `detached`.
- **Modes** (`estate.mode`):
  - `pending` (default until the GIS fields exist): all detached homes at `detached`, tagged `estate_share_pending`;
  - `gis_bands`: blank zones fall back to pending;
  - `epc_age_upper_bound`: SENSITIVITY only, with every post-1980 detached home at the estate rate, tagged `estate_upper_bound_epc_age_only`.
- Any row using the GIS estate input is forced to `publish_level internal` (tag `publish_internal_estate_input`) until GIS clears the OS terms.
- **Plot size selects the rebuild rate only.** `drivers.forbidden_substrings` now includes `parcel`, `plot`, `estate_share`, `post1980_det` and `pre1980_det`, and a test enforces this.
- **Holdout diagnostic** `surface_holdout.plot_size_rate_diagnostic` (internal, never a model pass/fail):
  - within each UR6 class, on observed zones only, it computes Spearman ρ of land value per residential hectare against median parcel size and against the share of dwellings drawing the one-off rate;
  - each ρ is computed on actual values and on a uniform-rate counterfactual, where every post-1980 detached home takes the national dwelling-weighted mean estate fraction;
  - it flags `big_plot_lower_due_to_rate` where ρ ≤ −0.10 on actual values but > −0.10 under the uniform rate;
  - it returns pending without residential land or the estate fields, and `insufficient_n` below 30 zones.

**One-at-a-time swings and central-only checks (rules 6.2 / 12 v0.7).**
- `surface_rent.one_at_a_time_drc` returns DRC at central and at each of rebuild, life and floor set to low or high with the others central. `surface_illustrative.swing_table` gives national and UR6 land share and % negative per swing.
- The per-row column `drc_swing_gbp` is internal-only.
- `surface_holdout.plausibility_checks` passes or fails on the **central** case only. The outer-band corners are reported as `stress_inside` or `stress_outside` and never fail.

**Zero-dwelling zones (rules v0.7).**
- Zones flagged `zero_dwellings` get no residential surface rent: `fill_method not_applicable`, land value and rent null (never 0), raw residual blank, quality placeholder.
- The flag overrides any RoS price.
- Codes come from Data Zones `zone_spine.flags` when the spine carries the token. Otherwise the tested fallback applies: S01010206, S01010226 and S01010227.
- `surface_rent.sample_for(purpose, …)` is the single choke point. These zones' sales never enter model fitting, yield calibration (`cell_price_evidence`), fill donors or holdout samples. The holdout splits, `run_holdout`, the gradient check, plausibility and the plot diagnostic all apply it.

**Per-resident figures.** `measured_rent_per_resident` is null wherever Data Zones sets `pop_dwellings_mismatch` (for example S01011598), tagged `per_resident_hidden_pop_dwellings_mismatch`. It is also null with no population.

**EPC over-count proxy.**
- Old certificates on demolished stock bias EPC floor area and age. `surface_rent.tag_epc_overcount` tags floor area and age as proxy (`epc_overcount_proxy`, `floor_area_proxy_epc_overcount`, `age_proxy_epc_overcount`) where certificates divided by 2025 homes exceed `epc_overcount.threshold` (1.25).
- The ratio used matches the certificate family actually used: `recent10_coverage_share` for recent10 inputs, otherwise `coverage_share`.
- GIS's `res_uprn_exceeds_dwellings` flag is preferred once it appears in the rollup.

**GIS rebuild (06 Oct 2026).** The six GIS files were re-verified against their manifest. The rollup column `dwellings_nrs_2025` is now `dwellings_total_2025`, with a new `dwellings_flag`, and the readers accept both names. `dz_residential_land` is not used until GIS posts a corrected checksum, so the gradient and plot diagnostics stay pending.

**CI safety.**
- Data locations come from `georgist.surface_paths`: the env var `SCOT_LAND_<NAME>_DIR`, then the gitignored `data/config/surface.local.yaml`, then repo-relative defaults under `data/external/`.
- Tests use synthetic fixtures. Tests that need local data skip when the path is missing.
- Never committed: `out/`, raw data, anything built from RoS parcels or the GIS estate or plot fields, addresses or postcodes.

**Follow-up (2026-10-06): `rate_basis` and Data Zones flags.**
- `rebuild.rate_basis` declares a basis for every rate, from `surface_rent.RATE_BASES`:
  - `bcis_median_type` for detached, semi-detached, terraced and purpose-built flats;
  - `bcis_median_type_override` for converted flats;
  - `bcis_median_all_rows` for other;
  - `generic_estate` for `detached_estate`.
- `rebuild_band` rejects a missing or invalid basis, and rejects `detached_estate` with any basis other than `generic_estate`. The estate rate uses the same band construction as the others.
- **Data Zones flags.** The `zero_dwellings` and `pop_dwellings_mismatch` flags are read from Data Zones `zone_spine.csv` via `surface_harvester.load_zone_spine`:
  - the file is verified against the Data Zones manifest and the expected sha256 prefix;
  - `flags` is read with `converters={'flags': str}`, so empty cells are `''`;
  - membership is tested with `split(';')`, joined on `(code, vintage)`, 2011 vintage.
- `surface_rent.zone_flag_sets`: a zone carrying both flags is treated as `zero_dwellings` only.
- The three hard-coded zero-dwelling codes are now only a tested fallback for a missing spine. With no spine, the mismatch set is empty.

### 12.6 GIS plot bands and residential land wired in; all-ages estate split; borrowing (2026-10-06, rules sha256 prefix 22c35eba)

DRAFT, not yet approved by Laurie. Results are internal (out/ JSON only) until they pass the checks and Laurie approves them.

**Inputs, verified against the GIS manifest and the expected sha256 prefixes (`surface_harvester.load_gis_checked`).**
- `dz_residential_land.csv` (`33207976`, public_zone, 14,368 rows, key (code, vintage)). The parcel method `residential_parcel_ha` is the per-hectare denominator.
- `dz_detached_plot_bands.csv` (`9bb56d3b`, **INTERNAL**: RoS INSPIRE + OS terms). The loader checks that the manifest publish_level is `internal`.

**Estate/one-off split by plot evidence for ALL detached homes (supersedes the post-1980 gating in 12.5).**
- `estate.mode: plot_bands` uses the `all_ages_*` shares: under 0.05 ha estate, 0.05–0.1 ha weight `band_weights.mid` (0.5; sensitivity 0 and 1), over 0.1 ha one-off.
- Every detached component is split, whatever its age band, including 1976–1983 and unknown age.
- The EPC-age-only variant (`epc_age_upper_bound`: all post-1980 detached at the estate rate, no plot evidence) is kept as a labelled sensitivity only.
- **Blank shares never default.** A zone with fewer than 5 matched homes borrows the dwelling-weighted all_ages shares of its council × UR6 cell, weighted by `n_detached_all_ages_matched`, flagged `plot_bands_borrowed`. If that cell has no filled zone, it borrows from the UR6 class nationally, flagged `plot_bands_borrowed_national` (`surface_rent.borrow_plot_bands`).
  - `with_estate(mode='plot_bands')` raises on an unborrowed blank row, so no zone falls back to an estate share of 0 or 1. Tests enforce this.
  - Borrowed rows carry no median parcel size.
- Rows using plot bands (filled or borrowed) are `publish_level internal` (`estate_share_gis` → `publish_internal_estate_input`).
- Plot size remains barred as a land-value driver. `drivers.forbidden_substrings` adds `all_ages_`, `post1980_`, `pre1980_` and the band-share suffixes.

**Per-hectare gradient on parcel residential land (rules 12.2 v0.6).**
- `surface_holdout.residential_land_rows_from_gis` excludes zones from the gradient, counted by reason and not treated as missing:
  - `share_res_uprn_in_parcels` < 0.5 (`weak_match`);
  - `mask_too_big_parcel`;
  - `res_uprn_exceeds_dwellings`;
  - `zero_dwellings` (GIS flag or Data Zones codes);
  - `no_residential_parcel`.
- A `keep` sensitivity retains weak-match zones.
- The gradient runs on observed zones with 5 or more sales. Pass/fail rules are unchanged (between-class order 1 → 6; within-class Spearman ρ against drive and PT minutes ≤ −0.10; minimum 30 zones per class).
- **Low-confidence tags on per-hectare outputs:** `build_output_row(residential_land_low_confidence=…)` adds `res_land_low_confidence_{weak_match|mask_too_big|uprn_exceeds}`.
- **Residential area never changes surface totals.** It is a denominator for `rent_per_res_ha` only. A test checks that measured rent, land value, uncertainty and `total_measured_rent` are identical with any area or none.

**Plot-size check (Georgist guard), live.**
- `plot_size_rate_diagnostic` runs within each UR6 class on observed zones with their own plot evidence (filled, not borrowed), after the same residential-land exclusions.
- It compares ρ(£/res-ha, median parcel size) and ρ(£/res-ha, one-off share) on actual values against a uniform-rate counterfactual (national dwelling-weighted mean estate fraction). It flags `big_plot_lower_due_to_rate` where the actual ρ ≤ −0.10 but the counterfactual ρ > −0.10.

**Runs (internal JSON in the out/ directory only):**
- central `plot_bands` (mid 0.5) with swings;
- mid-weight 0 and 1;
- the EPC-age-only sensitivity;
- the pending case for comparison;
- weak-match `keep` for the gradient.

### 12.7 Pre-registered job-access gradient (2026-10-06, rules sha256 prefix 23df6297)

DRAFT, not approved by Laurie. This section was committed **before** GIS's `dz_access.csv` existed. Nothing in it was chosen after seeing that file, and no result has been computed from it.

- **Primary within-class driver (decides pass or fail):** job accessibility from `dz_access.csv`, joined on (code, vintage 2011). For every UR6 class, the test passes if Spearman ρ between land value per residential hectare and job accessibility is **≥ +0.10** within that class.
- **Secondary measure (reported only):** road distance to the nearest large urban centre. The reported pass mark is ρ ≤ −0.10. It is shown next to the primary result and never decides pass or fail.
- **Sample (same rules as v0.6):**
  - observed zones with 5 or more sales only;
  - exclude `weak_match`, `mask_too_big_parcel`, `res_uprn_exceeds_dwellings` and `zero_dwellings`, plus zero-dwelling zones from the zone spine;
  - a class needs at least 30 zones, otherwise it is reported as `insufficient_n` and the overall result is pending.
- **Between-class test:** unchanged (UR6 expected order).
- **Expected GIS metadata (`gradient_v07.expected_metadata`), checked against the file's manifest on arrival:**
  - BRES 2011-DZ employment;
  - exponential falloff, 10 km scale, 60 km cutoff, own-zone jobs included;
  - OS Open Roads distances from official SG population-weighted centroids;
  - the 4 city centres (Aberdeen, Dundee, Edinburgh, Glasgow);
  - islands with no road link use straight-line distance × 1.3 and are flagged.

  A mismatch stops the run (`AccessMetadataMismatch`). Missing keys leave the result pending and unverified. Rank columns are refused.
- **Superseded driver:** the v0.6 SIMD drive-time result is still computed and published as it came out, labelled "superseded driver, reported".
- **A class that fails:**
  - it is reported as `failed`, not inconclusive;
  - its model-filled zones get wider bands: (central − low) and (high − central) are each multiplied by `gradient_v07.on_class_fail.model_filled_band_multiplier`, with the low end floored at 0. Observed zones are not widened.
  - The multiplier value is a **PLACEHOLDER awaiting Georgist sign-off** (`multiplier_status: PLACEHOLDER_GEORGIST_SIGNOFF`). Widened rows carry the tag `band_multiplier_placeholder`.
- **Run once:** before scoring, a scored run writes the dz_access sha256 and a hash of the `gradient_v07` config section to an internal run log (`{valuation_out_dir}/run_log/gradient_v07_runs.jsonl`, outside the repo). A second scored run on the same input is refused (`RepeatScoredRunError`) unless an explicit override with a written reason is given, and the override is logged too.
- **Tests:** synthetic fixtures only (`tests/surface/test_surface_gradient_v07.py`).

### 12.8 One-off detached rate for the non-estate share (2026-10-06, rules sha256 prefix 23df6297)

DRAFT, not approved by Laurie.

- **Source found:** a free published one-off row exists, so the generic-detached fallback was **not** needed. [S1] Aberdeenshire Cost Index 2025 (V06.00 April 2025), **page 1, Table 1, "One off detached houses 3 Units or less"**, UK BCIS median column:
  - single storey £2,383/m²;
  - 2 storey £2,498/m²;
  - the 1.5-storey row is excluded because Aberdeenshire derived it as +30%, not from BCIS.
  - File sha256 c7a1efab…aef3.
- **Cross-checks (not used in the numbers):**
  - [S3] Midlothian v14 one-off single and multi-storey rows;
  - [S2] West Lothian (BCIS Apr-2026) one-off rows;
  - [S4] Highland "One-off detached house".
- **New rate type `detached_one_off`, `rate_basis: one_off_detached`:** band built from those two rows with the same location and on-cost factors as every other type (min / mean / max × factors), giving £2,152 / £2,610 / £3,122 per m². Its high end equals the generic detached high end, because both take the highest one-off row as their maximum.
- **Where it applies:**
  - In `plot_bands` (main) and `epc_age_upper_bound` (sensitivity), the non-estate detached share (1 − e) now uses `detached_one_off` instead of the generic `detached` blend (estate + one-off rows). This is set by `estate.oneoff_rate_type`, and the component is tagged `oneoff_rate=detached_one_off`.
  - `pending` keeps the generic blend.
  - The estate share keeps `detached_estate` (generic_estate).
- **Expected direction:** rebuild cost for the non-estate share goes up, so land value on those zones goes down. This removes the downward bias in one-off rebuild cost (and the upward bias in land value on big plots) that the generic blend would have caused.
- **Data note:** GIS's manifest now marks `dz_detached_plot_bands.csv` as `public_zone`, following a project-owner licence ruling. The data sha is unchanged. The loader accepts `internal` or `public_zone` (`estate.accepted_publish_levels`), but outputs that use this input stay **internal** until Scot-LAND or Laurie lift `publish_level_inherited`.
- Figures are kept only in the internal output folder, never in this repo.
