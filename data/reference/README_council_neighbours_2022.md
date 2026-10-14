# council_neighbours_2022.csv

Committed neighbouring-council lookup for the DZ2022 empty-zone fill (method C borrowing).

## Provenance

- **File:** `council_neighbours_2022.csv` (60 undirected pairs; all 32 mainland-touching councils appear).
- **Builder:** Scot-LAND GIS — dissolve DZ2022 zones into councils using the NRS Scottish Postcode Directory council assignment, then keep edges that touch within 1 m (`method = dz2022_dissolve_touch_1m`).
- **Copyright:** Crown copyright; licensed under the **Open Government Licence v3.0**.
- **Island councils** Na h-Eileanan Siar (`S12000013`), Orkney (`S12000023`) and Shetland (`S12000027`) have **no land neighbours** in this file. The fill engine treats them as one island group (Georgist decision, 14 Oct 2026) and does **not** invent land borders at run time.

## Rules for consumers

- Load this file; **do not** compute neighbours from geometries at run time.
- Columns: `council_a`, `council_b`, `method`.
