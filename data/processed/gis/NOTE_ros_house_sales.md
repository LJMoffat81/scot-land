# Note: RoS "House Prices – Residential Properties Sales and Price" (data.gov.scot)

Checked 6 Oct 2026 against `/workspace/ros/house_sales.csv` (sha256 702c9ada…49cf2) and the dataset page https://data.gov.scot/dataset/house_prices___residential_properties_sales_and_price. Publisher: Registers of Scotland. Licence: OGL. Reference period 2004–2023. Last updated 9 Sep 2026.

## Findings
- **Zone geography is DZ2011 only.** `GeographyType` values are 2011 Data Zones, 2011 Intermediate Zones, Electoral Wards, Scottish Parliamentary Constituencies, Council Areas, Health Board Areas, Scottish Island Regions and Country. There are no 2022 Data Zones.
- **Measures:** Count, Lower Quartile, Median, Mean and Upper Quartile, for 2004–2023.
- **Codes present:** 6,970 of the 6,976 DZ2011 codes. All codes present are valid DZ2011.
- **Small zones:** values are suppressed where there are fewer than 5 sales. 6,246 zones have a 2023 median. 6,926 zones have a 2023 Count row, so 44 zones present in the file have no 2023 row at all.

## The 6 DZ2011 codes never present (any year, any measure)
**S01007788, S01010206, S01010226, S01010462, S01010493, S01011598**

| code | name | 2011 households (boundary file) | dwellings 2025 (Data Zones dwellings_total, Sep 2025) |
|---|---|---|---|
| S01007788 | Whitfield - 07 (Dundee) | 268 | 279 |
| S01010206 | Petershill - 04 (Glasgow) | 255 | 0 |
| S01010226 | Sighthill - 02 (Glasgow) | 394 | 0 |
| S01010462 | Knightswood Park East - 03 (Glasgow) | 437 | 396 |
| S01010493 | Drumchapel North - 03 (Glasgow) | 308 | 312 |
| S01011598 | Cliftonville - 01 (North Lanarkshire) | 544 | 378 |

Two of the six (Petershill-04 and Sighthill-02) now hold 0 dwellings; they are cleared regeneration sites. The other four are probably estates with almost no market-value sales in 2004–2023, which is my inference and not confirmed with RoS. Recommendation for Data Zones: flag these as "absent from source", not as zero sales.

Note that Sighthill-03 (S01010227) *is* in the RoS file but has 0 dwellings in 2025 and no Census 2022 households. It is one of the 3 DZ2011 area-share fallbacks in dz_brma_share.

(6 Oct 2026: dwellings column switched from the NRS assessor count, Dec 2025, to the team denominator, Scot-LAND Data Zones `dwellings_by_year` dwellings_total for count_year 2025. Only Whitfield-07 changes, 280 → 279.)
