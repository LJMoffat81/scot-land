# dz_detached_plot_bands.csv — plot-size bands for detached houses per data zone (built 6 Oct 2026, box only)
**Publish level: public_zone.** The figures are zone aggregates derived from RoS INSPIRE parcels, which RoS grants under OGL v3. The 2017 OS INSPIRE end-user licence linked from RoS's dataset guide is an RoS error (project owner's ruling, Oct 2026). No parcel geometry is in this file.
**Rows:** 14,368 (6,976 for 2011 + 7,392 for 2022). **Key:** (code, vintage); vintage is the integer 2011 or 2022. Every zone appears; counts are 0 where there are no cases.
**Script:** `scripts/build_dz_detached_plot_bands.py`. It runs after `build_dz_residential_stage2a.py` and `build_dz_residential_pairs.py`. QA output is in `qa_dz_detached_plot_bands.json`.

## Universe and rules
- **Properties:** the latest domestic EPC per OSG UPRN (1,885,772 UPRNs). Kept where `BUILT_FORM` = Detached and `PROPERTY_TYPE` is House or Bungalow: 359,902 properties.
- **Cohorts:**
  - `post1980`: age bands 1984–1991, 1992–1998, 1999–2002, 2003–2007 and 2008 onwards, plus `SAP, new dwelling` certificates. Those carry no age band, but they are lodged on construction, from 2010 onwards. 39,771 of the 169,682 post1980 homes enter this way.
  - `pre1980`: before 1919 through 1965–1975 (144,226).
  - Excluded from both cohorts: the 1976–1983 band, because it straddles 1980 (24,483), and unknown age (21,511).
- **Parcel:** the smallest residential RoS INSPIRE parcel containing the UPRN point. Three cases are excluded and counted:
  - `n_excl_multi_address`: that parcel contains more than 1 residential (EPC) UPRN, for example a shared title.
  - `n_excl_capped`: the parcel is larger than 2 ha (a farm or estate title; the same cap as dz_residential_land).
  - `n_excl_unmatched`: there is no parcel, typically Sasine land that is not yet on the Land Register.
- **Bands:**
  - `share_lt005`: under 0.05 ha
  - `share_005_010`: 0.05 to 0.10 ha inclusive
  - `share_gt010`: over 0.10 ha, up to the 2 ha cap

  The three shares sum to 1 (maximum error 2e-16). `median_parcel_ha` is the median for matched homes. Shares and the median are blank where `n_*_matched` is below 5.
- **Zone:** UPRN point in polygon, using SG data zone boundaries 2011/2022 (EPSG:27700).

## Columns
code, vintage, then for each cohort c ∈ {post1980, pre1980}:
- `n_detached_c_matched`
- `c_share_lt005`, `c_share_005_010`, `c_share_gt010`
- `c_median_parcel_ha`
- `c_n_excl_multi_address`, `c_n_excl_capped`, `c_n_excl_unmatched`

## National summary (matched homes)
| cohort | n matched | <0.05 ha | 0.05–0.10 ha | >0.10 ha | median ha | p25 / p75 ha | matched rate | excluded: multi / capped / unmatched |
|---|---|---|---|---|---|---|---|---|
| post1980 | 145,573 | 0.586 | 0.251 | 0.163 | 0.044 | 0.032 / 0.072 | 85.9% | 12,527 / 2,421 / 9,038 |
| pre1980 | 106,614 | 0.241 | 0.428 | 0.332 | 0.073 | 0.051 / 0.122 | 74.0% | 9,526 / 5,317 / 22,605 |

Zones with shares (n ≥ 5): post1980 in 3,662 of the 2022 zones (3,387 of the 2011 zones); pre1980 in 3,599 (2022) and 3,523 (2011).

## Caveats
- "Multi-address" is detected only from EPC-certified UPRNs. A shared title whose other homes have no EPC looks single-address. The bias is towards larger plots in terraces and semis, but the universe here is detached homes, so the effect is small.
- RoS INSPIRE parcels are title extents. A title can include, or exclude, an access strip or a separately registered garden plot.
- The pre1980 cohort has a lower match rate: older homes are more often on unregistered Sasine land. Its matched set leans towards homes that have been sold since Land Register triggers came in.
- EPC built form and age band are assessor-recorded and are sometimes defaulted.

## Attribution
© Crown copyright. Reproduced with the permission of Registers of Scotland. Contains OS data © Crown copyright and database right 2026; OS Open UPRN under the OS OpenData licence; domestic EPC data © Scottish Government, OGL v3; data zone boundaries © Scottish Government, OGL v3.

## all_ages cohort (added Oct 6 2026, rules 3b273073)
`all_ages_*` columns cover every detached house or bungalow whatever its age band, including 1976–1983 and unknown age. Valuation splits estate and one-off rebuild rates by plot evidence for all detached homes using these columns. National: 290,695 matched (matched rate 0.808); shares 0.449 under 0.05 ha, 0.323 for 0.05–0.10 ha, 0.228 over 0.10 ha; median 0.054 ha. Shares filled for 4,716 zones (2011) and 5,031 (2022); blank where fewer than 5 match.
