# Routing lookups (open data only)

Placement lookups for the rent ledger, made by Scot-LAND Valuation & Data on 4 Oct 2026. They hold record IDs, public site names and our bucket labels only. They contain no holder names, no coordinates and no outlines. They move no figure: no engine code reads them yet.

| File | Built from | Licence | Attribution |
|---|---|---|---|
| `repd_revised_lookup.csv` (194 rows: Revised REPD records and their successor) | DESNZ Renewable Energy Planning Database, July 2026 (Q2), published 3 Aug 2026, https://www.gov.uk/government/publications/renewable-energy-planning-database-quarterly-extract | OGL v3.0 (GOV.UK: "All content is available under the Open Government Licence v3.0, except where otherwise stated") | Contains public sector information licensed under the Open Government Licence v3.0. |
| `ces_placements.csv` (912 features from 14 layers, incl. 45 from the Mountain Bike Trails layer) | Crown Estate Scotland Spatial Hub feature layers, retrieved 4 Oct 2026 (most layers last modified 18 Aug 2026) | OGL v3.0: every one of the 14 layers has its own hub item stating "The data sets are available under the Open Government Licence" (Mountain Bike Trails: item bba81258664042c5a8b259ac127cc6df, https://www.arcgis.com/home/item.html?id=bba81258664042c5a8b259ac127cc6df, read 4 Oct 2026) | Contains public sector information, licensed under the Open Government Licence v3.0, from Crown Estate Scotland |

Left out on purpose:
- SEPA authorisation placements. SEPA's environmental-data page lists authorisations under OGL, but SEPA's general data terms grant non-commercial use only, and most records are household sewage registrations whose numbers link to named holders on the public register (OGL excludes personal data). They wait until SEPA confirms the terms.
- The 2 CES `Mountain_Bike_Hub` points (layer 0 of the same Mountain Bike Trails service, so the same OGL item covers them): a hub and an "Emergency Info" point, which are not placements. Both would be outside the ledger anyway.
- The REPD and CES source extracts themselves.

Open Government Licence v3.0: https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/

Rebuild (Python 3.8+, standard library only, Windows-friendly), from any empty folder:
- `python build_repd_revised_lookup.py <out_dir>`: downloads the pinned REPD Q2 2026 CSV, checks sha256 84c1b5f9…695035, writes `repd_revised_lookup.csv`, prints sha256 2dd6657b…dee266.
- `python build_ces_placements.py <out_dir>`: queries the 14 CES layers (attributes only, no tenant names, no geometry), checks a sha256 of the fetched records against the 4 Oct 2026 pin 788dc5eb…e2d81a, writes `ces_placements.csv`, prints sha256 735d56d3…c08c2. CES updates layers monthly, so a later run may stop at the source check; `--accept-new` builds from the current layers.
- sha256 of the files: `repd_revised_lookup.csv` 2dd6657bf1ca7450a4e00ba151bb86327d3d92546303914a49956dcb66dee266; `ces_placements.csv` 735d56d3bda533fdfbd14cc5e12e8921bb93241720372d0e2af64d0a94dc08c2.
