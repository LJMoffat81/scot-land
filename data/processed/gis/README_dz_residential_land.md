# dz_residential_land.csv — residential land area per data zone (built 6 Oct 2026, box only)
**Purpose:** the denominator for the default map view, rent per hectare of residential land.
**Rows:** 14,368 (6,976 DZ2011 + 7,392 DZ2022). **Key:** (code, vintage). vintage is the integer 2011 or 2022. **Publish level:** public_zone. The file holds zone totals only; no parcel geometry or parcel IDs are in it.
**Scripts (run in order):** `build_dz_residential_stage1.py` → `build_dz_residential_stage2a.py <counties>` → `build_dz_residential_stage2b.py` → `build_dz_residential_final.py` → `apply_team_rules.py`. QA: `qa_dz_residential_land.json`.

## Columns
| column | meaning |
|---|---|
| zone_ha | Area of the zone polygon (SG data zone boundaries, EPSG:27700) |
| settlement_ha | **Stage 1, method `settlement_mask`.** Zone area inside the union of NRS Census 2022 Settlements (503 settlements, 193,202 ha). This is rough: it includes all urban land uses. |
| residential_parcel_ha | **Stage 2, method `parcel_residential_uprn`.** Area of the union of residential RoS INSPIRE parcels, clipped to the zone. Stacked or overlapping titles are counted once. |
| n_res_parcels | Kept residential parcels whose point-on-surface lies in the zone |
| n_res_uprn | Residential UPRNs located in the zone (point in polygon) |
| share_res_uprn_in_parcels | Share of those UPRNs that fall inside a kept residential parcel (coverage) |
| capped_parcels_n, capped_ha | Residential parcels removed by the size cap (assigned by point-on-surface; full parcel area) |
| method_flags | The method stamp, plus any of: `no_residential_parcel`, `low_parcel_coverage_lt0.5`, `area_from_parcels_centred_in_neighbour_zone`, `*_sliver_lt_0.01ha_zeroed` |
| dwellings_total_2025 | QA denominator: Scot-LAND Data Zones `dwellings_by_year.csv` dwellings_total, count_year 2025, same vintage (team rule) |
| official_dph_2025 | Official NRS dwellings per hectare (Dec 2025; assessor dwellings ÷ the whole zone's area), same vintage |
| dph_settlement, dph_parcel | dwellings_total_2025 ÷ settlement_ha or residential_parcel_ha (blank if the mask is 0) |
| mask_too_big_settlement, mask_too_big_parcel | True if our dph, rounded to 2 dp, is ≤ the official whole-zone dph. Blank if the mask is 0. |

## Method
**Stage 1:** `make_valid`, then dissolve the settlements, then intersect each zone with the union. Mask slivers under 0.01 ha are set to 0 and flagged (13 DZ2011 zones and 255 DZ2022 zones, nearly all from boundary misalignment).

**Stage 2:**
1. **Parcels:** RoS INSPIRE Cadastral Parcels, 33 registration-county files (ros-inspire.themapcloud.com, extract dated 25 Aug 2026). 1,573,146 parcels covering 6.81 M ha. These are Land Register titles only; Sasine (unregistered) land has no parcel.
2. **Residential points:** the Scottish domestic EPC open data carries `OSG_REFERENCE_NUMBER`, the One Scotland Gazetteer UPRN. I took the latest certificate per property and found 1,885,772 distinct UPRNs. 1,884,917 of them (99.95%) join to OS Open UPRN (Sept 2026 release) coordinates.
3. **Residential parcel:** a parcel is residential if it contains at least 1 such UPRN (point within the polygon). That gives 893,713 parcels.
4. **Size cap, chosen from the data:** residential parcel area has p90 0.15 ha, p95 0.56 ha, p98 4.1 ha and p99 17 ha. Single-UPRN parcels have p95 0.22 ha and p99 3.5 ha. A plain 2 ha cap would remove 25,956 parcels. But many of those are estate or multi-unit titles, and dropping them cuts UPRN coverage from 74.1% to 60.5%. The rule is therefore: **cap parcels over 2 ha unless they hold at least 1 residential UPRN per 1,000 m²** (that is, at least 10 certified homes per ha). Result: **20,749 parcels capped, 4,302,815 ha** (farms and estates; they held 296,018 UPRN-parcel hits). 5,207 large dense parcels (41,189 ha) are kept, and 872,964 parcels are kept in total.
5. **Zone assignment:** area is the intersection of each kept parcel with each zone, then a union per zone, so stacked flat and common-ground titles are not double-counted. The sum of the kept parcels' raw areas would be 103,266 ha; the union is 69,181 ha. Parcel counts use point-on-surface.

## QA (DZ2022 unless stated; the DZ2011 figures are nearly identical)
**National residential land**
- Parcel method: **69,181 ha**, 0.89% of Scotland.
- Settlement mask: 193,202 ha, 2.5%.
- Official comparators. No official Scottish "residential land" series exists.
  - ONS *UK natural capital: ecosystem accounts for urban areas* (Table 4, 2017): Scotland's built-up area is 176,000 ha, of which residential gardens are 44,100 ha (25%). Garden plus dwelling footprint is the urban residential plot, so our 69 k ha (urban plus rural) is the right order. It is a floor, given the coverage gaps below.
  - SG *Scotland's Fourth Land Use Strategy: evidence pack*: urban and suburban land cover is 233,000 ha (3.0%).
  - NRS: 91% of the population lives on 2.3% of the land, which agrees with our settlement mask.

**Dwellings per residential hectare** (2,757,323 dwellings)
- National: 39.9 (parcel) and 14.3 (settlement).
- Zone quantiles, parcel method: p5 13.3, p25 30.4, median 48.0, p75 89.7, p95 341, p99 1,030.
- Zone quantiles, settlement method: p5 4.9, median 18.4, p95 64.

**Sanity checks**
- Dense Glasgow tenement zones:
  - Hillhead-08 (S01017544): official 193 dph; parcel 432 dph (3.0 ha of 6.7 ha; coverage 0.92). Plausible.
  - City Centre South-01 (S01017423): official 426; parcel 10,913 (0.04 ha; coverage 0.34). This is not plausible; it is a coverage failure.
- Rural zones:
  - Lochaber East & North-07: 81,330 ha, official 0.00 dph, parcel 9.7 dph, no settlement.
  - Rothes & N Speyside-02: official 0.03, parcel 6.2.

**Coverage**
- 72.8% of residential UPRNs fall in a kept parcel (74.1% before the cap). Zone median 0.80; p5 0.34.
- 1,034 DZ2022 zones and 1,005 DZ2011 zones have coverage below 0.5 and are flagged. These are mostly city-centre tenements and Sasine-heavy areas, where `residential_parcel_ha` is too small and dph is too high.
- EPC UPRNs cover only 68% of dwellings (homes with no EPC are invisible), so parcels holding only uncertified homes are missed.
- Zones with no residential parcel: 2 in DZ2022 (S01014479, S01018629) and 1 in DZ2011 (S01008462).

**Official dph check (`mask_too_big`)**
The official figure comes from the NRS *Dwelling estimates by 2011/2022 Data Zone*, Dec 2025 sheet (published 30 Jul 2026), column "Dwellings per hectare". It is calculated over the whole zone. statistics.gov.scot `dwellings-hectare` republishes the same NRS series, but that site returned SSL EOF / HTTP 500 on 6 Oct 2026. Its index also lists only 2001/2011 data zones, up to 2023, so it has no DZ2022.

| | settlement mask | parcel method |
|---|---|---|
| DZ2022 flagged | **5,115** of 7,392 | **19** |
| DZ2011 flagged | **3,764** of 6,976 | **14** |
| zones with mask ≥ the NRS whole-zone area (pure area test, DZ2022) | 6,339 | 13 |

- **Settlement mask:** 6,387 DZ2022 zones lie at least 99% inside a settlement, so the mask equals the zone and our figure equals the official one, except for the numerator difference: council-tax dwellings_total against assessor counts (ratio p1 0.93, median 1.00, p99 1.09). Expected outcome: the settlement mask adds no information for urban zones. Worst DZ2022 cases are new-build or demolition zones where dwellings_total is far below the assessor count: S01017422 (ours 48.5 against official 82.7), S01014395 (4.2 against 6.6) and S01020586 (12.7 against 18.0). In DZ2011, the worst cases also come from the official figure using a different area base: S01012188 (Erskine E & Inchinnan-01) has a polygon of 319 ha, but the NRS area implied by its official dph is 33 ha. 285 DZ2011 zones and 249 DZ2022 zones have an NRS area base that differs from the polygon by more than 5%.
- **Parcel method:** all flags are zones where large estate or common-ground titles cover more than 96% of the zone (median 99.95%). Worst DZ2022 cases: S01016463 (ours 22.7 against 24.0), S01016466 (14.2 against 15.0), S01016534 (23.8 against 25.0), S01016533, S01016467 (a cluster in one estate) and S01015385 (75.5 against 78.5). Worst DZ2011 case: S01009354 (16.2 against 17.0). The ratios are 0.95–1.00, so the cause is the mask rather than a data error. These zones need a building or land-use mask, for example OS Open Zoomstack or OSM, to strip roads and open space.

## Licences
- **RoS INSPIRE Cadastral Parcels:** OGL v3, plus the OS INSPIRE end-user licence (© Crown copyright and database right 2026; © Registers of Scotland). Parcel geometry is used internally only. It is not redistributed: only zone-level area totals are published here. Please confirm the public_zone use of derived totals with the licence owner before any push.
- **OS Open UPRN:** OS OpenData licence (OGL-compatible). "Contains OS data © Crown copyright and database right 2026."
- **Domestic EPC:** OGL v3 (Scottish Government). OSG UPRN used for the join only; no address data is published.
- **NRS Census 2022 Settlements** (maps.gov.scot WFS `CEN2022:Settlement2022`): OGL. "Copyright NRS, contains OS data © Crown copyright and database right 2026."
- **NRS dwelling estimates:** OGL v3.
