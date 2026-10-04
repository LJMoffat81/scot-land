# Data sources

Every data source the engine or the map uses or plans to use, with its edition, licence and the attribution it requires.
Built from Data's inputs register (`model-inputs-table-2026-10-04.md` §4) and licence table (`engine-inputs-proposal-2026-10-04.md` §4), 4 Oct 2026.
"Unknown" means we could not verify it. Licence readings are the team's judgement, not legal advice.

Status: **live** = used on main now; **planned** = named in a queued job; **candidate** = under review; **blocked** = needs a paid licence or written permission.

## Open data

| Source | Publisher | Edition / date | Licence | Required attribution | Status |
|---|---|---|---|---|---|
| UK House Price Index (average prices, indices) | HM Land Registry, with RoS and ONS | period 2026-03 still supplies `scotland_hpi_index` for the farmland path (`data/config/sources.yaml`). The July 2026 full file indexes the 2023 council median to 1 April 2025 (`data/processed/council_hpi.csv`) | OGL v3.0 | "Contains HM Land Registry data © Crown copyright and database right [year]. This data is licensed under the Open Government Licence v3.0." (data.gov.uk UK HPI record) | live |
| RoS INSPIRE Cadastral Parcels (WMS `CP.CadastralParcel`) | Registers of Scotland | live at request | OGL v3.0 per the download page; the dataset spec v1.5 still points to the OS INSPIRE End User Licence. Written confirmation from RoS is outstanding | "© Crown copyright. Reproduced with the permission of Registers of Scotland." and "Contains OS data. © Crown copyright and database right (year)." (spec v1.5, Licensing/General). No RoS logos | live (display only; no RoS-derived file is committed) |
| Postcode lookup (postcodes.io, built on the ONS Postcode Directory) | ONS (data); postcodes.io (service) | live at request | OGL v3.0 (GB postcodes) | "Contains OS data © Crown copyright and database right [year]", "Contains Royal Mail data © Royal Mail copyright and database right [year]", "Source: Office for National Statistics licensed under the Open Government Licence v.3.0" (ONS Licences page, postcode products). That postcodes.io uses ONSPD is not re-checked: unknown | live |
| SG Urban Rural Classification 2022 | Scottish Government | published Dec 2024; zip last-modified 16 Dec 2024 | OGL v3.0 | "Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right (year)." (metadata inside the zip) | live (map layer); planned (engine, job E5) |
| Scottish Vacant and Derelict Land Survey | Scottish Government | unknown | OGL v3.0 | "Contains public sector information licensed under the Open Government Licence v3.0." | live (map layer) |
| Scottish Public and Crown Estate Land 2024 | Scottish Government | 2024 update | unknown (not checked by Data) | unknown | live (map layer) |
| Crown Estate Scotland Spatial Hub layers | Crown Estate Scotland | layers last modified 18 Aug 2026 (most) | OGL v3.0 | "Contains public sector information, licensed under the Open Government Licence v3.0, from Crown Estate Scotland" (hub item licence text) | live (map layers) |
| Renewable Energy Planning Database | DESNZ (managed by Barbour ABI) | July 2026 (Q2), published 3 Aug 2026 | OGL v3.0 (GOV.UK site licence) | "Contains public sector information licensed under the Open Government Licence v3.0." (OGL default; no specific statement found) | live (map layer) |
| National Forest Inventory Scotland 2024 | Forestry Commission | item updated 28 Aug 2026; layer `NFI_Scotland_IFT_Data_20250826` | OGL v3.0 | "© Forestry Commission copyright. Contains Ordnance Survey data © Crown copyright and database right 2025." (ArcGIS item licence text) | live (map layer); planned (job E10) |
| SEPA flood maps | SEPA | unknown | OGL v3.0 | "© SEPA [year]; this SEPA product is licenced under the Open Government Licence 3.0" (SEPA environmental data page); OS terms also apply to the flood map viewer | live (map layer) |
| Census 2022 settlements | National Records of Scotland | 2022 | OGL v3.0 (not re-checked) | "Contains National Records of Scotland data. Contains Ordnance Survey data © Crown copyright and database right." (as on the site) | live (map layer) |
| Marine layers (12 NM, Scottish zone, marine regions, harbours, sectoral plan) | Scottish Government (Marine Directorate), UKHO | unknown | OGL v3.0 (as on the site) | as shown on each layer on the site | live (map layers) |
| Oil fields, platforms, pipelines | North Sea Transition Authority | unknown | unknown (not checked by Data) | "Contains information provided by the North Sea Transition Authority and/or other third parties." (as on the site) | live (map layers) |
| Residential Properties Sales and Price (data-zone medians) | Registers of Scotland via statistics.gov.scot | 2004–2023; record updated 9 Sep 2026. Council 2023 median, indexed to 2025-04-01, is the town market value (`data/processed/dz2011_prices.csv`) | OGL v3.0 (dataset record) | "Contains public sector information licensed under the Open Government Licence v3.0." plus naming RoS as the source. RoS's own statement: unknown | live (job 034) |
| 2011 Data Zone lookup and population-weighted centroids | Scottish Government | lookup 16 Dec 2024; centroids 2011 | OGL v3.0 | "Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right (year)." (SG spatial data statement; not re-read for this file) | planned (job E6 build input) |
| Agricultural survey: results – December 2020 | Scottish Government | published 23 Mar 2021 | OGL v3.0 (gov.scot) | "Contains public sector information licensed under the Open Government Licence v3.0." | planned (job E7: £42/ha) |
| Less Favoured Areas 2020 | Scottish Government | revised 1 Dec 2020 | OGL v3.0 | Scottish Government and OS statement (exact text: unknown) | candidate (job E7b) |
| NatureScot / Space Intelligence Habitat and Land Cover Map 2022 | NatureScot | 2022 | OGL v3.0 | "Contains public sector information licensed under the Open Government Licence v3.0." | candidate |
| OS OpenData (Boundary-Line, Open UPRN, OpenMap Local, Code-Point Open) | Ordnance Survey | edition not chosen | OGL v3.0 | "Contains OS data © Crown copyright and database right (year)"; Code-Point Open adds Royal Mail and National Statistics lines | candidate |
| Council boundaries (`lad.json` mirror) | martinjc/UK-GeoJSON (GitHub) | 2013 vintage | unknown | unknown | live; to be replaced |
| Basemap tiles | OpenFreeMap (OpenMapTiles, OpenStreetMap data) | live | OpenStreetMap: ODbL | "OpenFreeMap © OpenMapTiles Data from OpenStreetMap" (OpenFreeMap TileJSON) | live |
| Satellite tiles | Esri World Imagery | live | Esri terms (not read by Data) | "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community" (service copyright text) | live |

## Licensed or restricted: not used in public outputs

| Source | Licence position | Status |
|---|---|---|
| James Hutton Institute LCA 1:250k and LCF 1:250k | Hutton Open Data Licence: any purpose (cl. 1.1); derived data to be notified to soils@hutton.ac.uk (cl. 4.2); attribution cl. 4.5; no implied partnership (cl. 3.2). Notice not sent | not used on the site; **no Hutton-derived file may be committed** |
| RoS paid sales data (All Sales, Market Value Residential) | Sold under licence; terms unknown | blocked (spend decision) |
| ScotLIS | Private, domestic or internal use only (terms cl. 7) | manual checks only; never scraped |
| SAA valuation roll | Personal use only without consent | blocked |
| BCIS rebuild costs | Subscription; no public redistribution | blocked |
| UKCEH Land Cover Map | Non-commercial only; political use unknown | not used |
| Savills, Strutt & Parker, Tilhill, SLC market reports | Cite figures with a link only; no reproduction | cited in method notes only |
| BGS BritPits (full) | Paid BGS licence | blocked |
| Ofgem Renewable Electricity Register | Terms unknown (service down 4 Oct 2026) | not used |

## Rules
- Open Government Licence v3.0: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/. Where listing every statement on the map is impractical, the OGL allows a link to a page that has them all.
- Nothing here suggests that any publisher endorses Scot-LAND.
- Never commit Hutton- or Registers of Scotland-derived files, or anything whose licence is still being confirmed. The repo is public.
