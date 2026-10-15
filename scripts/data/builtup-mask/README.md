# UX-10 built-up display mask (DISPLAY ONLY — never changes any figure)
Built 2026-10-15, EPSG:27700, script build_builtup_mask.py (sha256 1b823a21e035175627d0345ad9fec721aeee7fa920b42cddb60af5cdf3084199).
Method: union(NRS Settlements) ∪ 50 m buffers of OS Open UPRN points outside settlements; 10 km tiles, quadtree dissolve, simplified 10 m (topology-preserving); then 2 m buffers unioned round the 553 UPRNs the simplification left outside. dz2022_masked(code, geom) = DZ2022 ∩ mask.
## Sources and licence
- NRS Settlements: Census 2022 Settlement2022 (503 polygons; maps.gov.scot WFS), OGL v3. Chosen source, replacing the mid-2020-based layer because it is newer.
- Data Zones 2022: Scottish Government, OGL v3.
- OS Open UPRN 2026-09: OS OpenData, OGL v3.
Attribution: "Contains NRS data © Crown copyright and database right 2026. Contains OS data © Crown copyright and database right 2026. Contains public sector information licensed under the Open Government Licence v3.0."
## Files (sha256)
- map_builtup_mask.gpkg 5f5120e77800ae11dfe63864e6f884b9b62fef91e1b083ca3560d8b4854a2240
- dz2022_masked.gpkg 1f1fde1c445db0fdf79b6e32e42517c1f7871f2d89766eb22f4cb429709b00bd
- map_builtup_mask.4326.geojson 15e8e80117552773b72ff0a04a56df19ec8987faf2a17bf8ae8358e3f5b62eea
- dz2022_masked.4326.geojson 49142a45e9f21a881a1e0d761e9c4931da570782c19dbc59debf89e75eae24c1
## QA (qa_builtup_mask.json) — 3/3 PASS
1. DZ2022 with UPRNs 7392/7392; masked rows 7392; missing 0 — PASS
2. Masked codes unique and all in DZ2022 — PASS
3. UPRNs inside mask 3,886,588/3,886,588 (100%); outside 0 — PASS
Mask area 405,530.9 ha = 5.206% of Scotland; 179,548 polygons.
