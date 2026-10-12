# dz_access.csv — within-class access drivers per data zone (built 6 Oct 2026, box only)
**Purpose:** the pre-registered within-urban-rural-class access drivers for Valuation's gradient test (rules doc `23df6297`): (1) job accessibility from BRES employment with a fixed negative-exponential falloff, (2) road distance to the nearest Large Urban Area centre.
**Rows:** 14,368 (6,976 DZ2011 S01006506–S01013481 + 7,392 DZ2022 S01013482–S01020873). Every official code is present, and the codes match the SG boundary files exactly. **Key:** (code, vintage), with vintage as the integer 2011 or 2022. **Publish level:** public_zone.
**Pre-registration:** all parameters are in `scripts/access_config.json` (sha256 `0ff9055a…`). It was written before any value was computed and was not changed afterwards. No land values, prices or correlations were read or computed in this build.

## Sources and licences
| Source | Use | Licence / attribution |
|---|---|---|
| SG Data Zone Centroids 2011 (6,976) and 2022 (7,392), https://maps.gov.scot/ATOM/shapefiles/SG_DataZoneCent_2011.zip and …_2022.zip (catalogue https://spatialdata.gov.scot/geonetwork/srv/api/records/6755b5a3-5d99-4ca3-bd19-33d5454774ac) | origins (both vintages); 2011 set also locates employment | OGL v3. Copyright Scottish Government, contains OS data © Crown copyright and database right 2026 |
| ONS BRES open access, Nomis NM_189_1, **2023**, geography "2011 scottish datazones" (TYPE231), industry Total, employment status "Employment" (employees + working owners), count. https://www.nomisweb.co.uk/api/v01/dataset/NM_189_1.data.csv?geography=2092957701TYPE231&date=2023&industry=37748736&employment_status=4&measure=1&measures=20100 | E_j | OGL v3. Source: Office for National Statistics, BRES via Nomis |
| OS Open Roads, GeoPackage, version 2026-04, https://api.os.uk/downloads/v1/products/OpenRoads/downloads?area=GB&format=GeoPackage&redirect | road network | OS OpenData licence (OGL-compatible). Contains OS data © Crown copyright and database right 2026 |
| SG Data Zone boundaries 2011/2022 (already in raw/) | code-completeness check only | OGL v3, © Scottish Government |

Raw sha256 values are in `SOURCES_SHA256_dz_access.txt`.

## Method (as pre-registered)
- **Origins:** the SG population-weighted centroids (`origin_method = sg_popweighted_centroid` for all 14,368 rows; no fallback was needed). Each is snapped to the nearest OS Open Roads node. If that node is in a component with fewer than 10 nodes and a node of a larger component lies within 2 km, it snaps to that node instead. This never triggered. `origin_snap_m` is the snap distance (median 38 m, max 810 m) and is not added to d.
- **Network:** every road_link in the box (0, 520000)–(480000, 1240000), which covers Scotland plus northern England. Links are undirected, weighted by length in metres, with speed ignored: 663,660 links, 558,206 nodes and 307 components, of which the mainland component has 531,462 nodes. Open Roads has no ferries.
- **Employment:** BRES 2023 by 2011 data zone, placed at the 2011 population-weighted centroid. No workplace-weighted point is openly published. 2022 origins use the same 2011 employment points, with no crosswalk.
- **Job accessibility:** `job_access` = Σ_j E_j·exp(−d_ij/10 km) over pairs with d_ij ≤ 60 km. The own zone is included (d = 0). d is network km when both points are in the same network component; otherwise it is 1.3 × straight-line km. `log_job_access` = ln(job_access), positive for every zone.
- **Large urban centres:** Glasgow, Edinburgh, Aberdeen and Dundee (SG UR 2022 Large Urban Areas). The official open polygon source, Spatial Hub *Town Centres – Scotland*, needs a signed-in account (anonymous WFS returns 403). The centre points are therefore documented landmarks, recorded in the config: Glasgow George Square (259265, 665392), Edinburgh Waverley Bridge/Princes St (325832, 673869), Aberdeen Castlegate (394431, 806392) and Dundee City Square (340347, 730239). All four snap within 60 m to the mainland network. `road_km_nearest_luc` is the network km to the nearest of the four. Where an origin's component holds no centre, it is 1.3 × the straight line to the nearest centre (`distance_method = euclid_x1.3`).

## Columns
`code, vintage, origin_method, origin_easting, origin_northing, origin_snap_m, network_component (mainland | island_<id>), job_access, log_job_access, job_access_method (network | network+euclid_x1.3), job_access_euclid_share (share of A_i from 1.3×straight-line pairs), km_nearest_emp_point (diagnostic: d to the nearest 2011 employment point with E>0), nearest_luc, road_km_nearest_luc, euclid_km_nearest_luc, distance_method (network | euclid_x1.3), flags`
Flags are separated by semicolons: `off_mainland_network`, `luc_distance_euclid_x1.3`, `job_access_partly_euclid_x1.3`, `nearest_emp_point_gt_5km`, `snap_gt_1km` (none), `snap_skipped_tiny_component` (none). Read them with `converters={"flags": str}` and `z["flags"]`.

## QA (full detail in qa_dz_access.json)
- **Coverage:** 6,976 / 6,976 and 7,392 / 7,392, with no nulls in job_access, log_job_access or road_km.
- **job_access, 2011 (min / p10 / p25 / median / p75 / p90 / max):** 243 / 6,817 / 29,745 / 83,855 / 199,881 / 280,513 / 431,917. **2022:** 26 / 6,952 / 30,357 / 85,509 / 199,819 / 280,187 / 431,297.
- **road_km_nearest_luc, 2011:** 0.12 / 4.1 / 8.4 / 23.2 / 41.3 / 107.6 / 530.6. **2022:** 0.12 / 4.1 / 8.4 / 22.4 / 40.9 / 103.9 / 531.4.
- **Top job_access:** the top 10 on both vintages are all central Glasgow (City Centre South/East/West, Laurieston). The top Edinburgh-nearest zones (Tollcross, Old Town/Princes St) are about 296k, rank about 1,150 of 14,368, behind about 1,100 zones in the denser Glasgow conurbation. Aberdeen's top zone (Rosemount) is about 125k and Dundee's (City Centre) about 71k.
- **Bottom job_access:** remote NW Sutherland, Wester Ross, Lewis, the Uists and the North Isles. Island zones are 1.8% of all rows but 14.6% of the bottom decile; median island job_access is 2,534 against 86,655 on the mainland.
- **City-centre road km (zones within 1.5 km straight line of the centre):** Edinburgh n = 137, median 1.66, max 2.59 km. Glasgow median 1.44, Aberdeen 1.44, Dundee 1.44.
- **Road/straight ratio, mainland, network rows:** median 1.20 at 2–5 km, 1.14 at 5–20 km, 1.12 at 20–50 km, 1.15 at 50–100 km and 1.24 at 100+ km. The overall median for rows over 5 km is 1.14 (p10–p90 about 1.07–1.35). This is slightly below the 1.2–1.5 rule of thumb, as expected for routes to a city on a dense trunk network.
- **Euclid fallbacks:** 255 rows (125 for 2011, 130 for 2022) use 1.3 × straight line for the LUC distance. These are zones on unbridged islands: Shetland, Orkney, the Western Isles, Arran, Bute, Islay/Jura, Mull, Cumbrae and others. 4,154 rows have at least one 1.3 × straight-line pair inside 60 km in job_access, mostly west-central-belt zones within reach of Bute, Arran and Cumbrae jobs. That share is above 1% for only 316 rows and above 10% for 90.
- **Vintage agreement (each 2022 origin against the nearest 2011 origin):** within 5 m (n = 3,117), the max |Δlog A| is 0.027 and the max |Δkm| is 0.46. Within 250 m (n = 6,547), the median |Δlog A| is 0. Across all 2022 zones, the correlation of log A is 0.9993 and of road km 0.99996.

## Known limitations
- **BRES** open-access small-area counts are rounded (every zone value here is a multiple of 5) and exclude farm agriculture (SIC 01000). The zone sum is 2,581,645; Scotland's 2023 BRES total including farm agriculture is 2,651,000. There is no suppression (no missing cells), but 193 zones are 0.
- **Residential points:** employment sits at residential population-weighted points, so city-centre jobs are a few hundred metres off their true workplaces. Within the 10 km falloff this matters little.
- **2022 zones with no nearby 2011 employment point:** because there is no crosswalk, a 2022 zone can sit far from any 2011 point carrying its area's jobs. These 32 zones are flagged `nearest_emp_point_gt_5km` (2022 only). The extreme case is S01017861, Ross and Cromarty South West – 03 (Applecross), at A = 26, against hundreds for its 2011 parent. Treat those 2022 values with care.
- **No ferries:** island-to-mainland distances are a 1.3 × straight-line proxy, not a sailing time.
- **Centre points** are landmarks, not official town-centre polygon centroids (see above).
- **Status:** experimental, not an official statistic.
