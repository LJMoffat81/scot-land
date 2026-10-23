# Scotland land and sea extent (SRC-A)

Illustrative Scotland land / inshore (0–12 nm) / offshore (12–200 nm) extent
used for clipping and the optional map outline. Not prejudicial to delimitation.
Not for navigation.

## Sources

| id | Publisher | Role | CRS | Licence |
|---|---|---|---|---|
| `ukho-mlb` | UK Hydrographic Office | Outer limits (TSL, EEZ, median, IoM, Art 4(b)(ii) TSL segment) | EPSG:4326 → 27700 via OSTN15 / Helmert | OGL v3 |
| `si-1999-1126` | legislation.gov.uk | Lateral limits (Sch 1 Pt I, Sch 1 Pt II s1+s2, Sch 2) | OSGB36 → EPSG:27700 (no OSTN15) | OGL v3 |
| `os-boundary-line` | Ordnance Survey | Land (`country_region` = Scotland, MLW) | EPSG:27700 | OGL v3 |
| `ostn15` | OS / PROJ | Grid shift for UKHO WGS 84 → OSGB36 inside coverage | — | OGL v3 |

Attribution:

- `Contains public sector information, licensed under the Open Government Licence v3.0, from UK Hydrographic Office.`
- `Contains OS data © Crown copyright and database right 2026.`

## Datum notes

- SI coordinates are already OSGB36. Densify along the Airy 1830 Mercator
  loxodrome (≤ 1,000 m segments); project to EPSG:27700 with no OSTN15 shift.
- UKHO WGS 84 vertices inside the OSTN15 grid use the explicit PROJ pipeline
  (`unitconvert → inv hgridshift → tmerc`). Outside the grid, EPSG:1314 Helmert
  is used and counted.

## Solway note

Boundary-Line MLW land crosses SI Sch 1 Pt II s1 east of ~3.35°W. The build
locally polygonizes the densified SI Sch 1 Pt II s1 line with the OS land
boundary (plus shortest connectors from undensified s1#1/#2 to the land
boundary so the graph closes), keeps Scottish-side water faces in the upper
s1 corridor, and merges them into `inshore_0_12nm` with `difference(land)`.
No invented disks. Pinned in-land vertices 3 and 4 (C1b) stay inside OS land;
land is never cut.

The AOI box and corridor buffer are configured in
`backend/layers/extent/scotland_extent_sources.yaml` under `solway`
(`aoi: [305000, 555000, 340000, 572000]`, `corridor_m: 700`) — not hard-coded
in the builder.

**Connector length vs `snap_m`:** the s1#1 / s1#2 → land-boundary connectors
are ~594 m and ~409 m. That is intentional and **not** a violation of
`snap_m: 150`. `SNAP_M` only caps endpoint snaps when noding the flood graph
(§3.4). The Solway connectors are a separate §3.7 step that closes the local
polygonize graph so Scottish-side faces exist; they are shortest-path links
to OS land, not snap fillers, and may exceed 150 m.

## Hatton / optional shelf

`scotland_ext_shelf_optional.27700.geojson` holds UK continental shelf beyond
the UK EEZ next to the Scottish zone (Hatton face and Faroe shelf strips).
Seabed rights only; not Scottish waters; outside the default clip. It is not
loaded into `ref.extent` and is not in `CLIP_ZONES`.

The Faroe shelf **zone** in that file is ~12,514 km² (the EEZ–continental-shelf
strip(s) next to the Scottish side). The dry-run figure of **8,028 km²
“removed”** is the intersection of that strip with the previous NMPi-based
`scotland_extent` offshore zone — only that overlap left the default clip.
The rest of the 12,514 km² was never inside the old extent, so it is optional
shelf without being a removal.

## Bookkeeping

- `.gitignore` lists `scot-land-data/` (offline UKHO / Boundary-Line / OSTN15
  inputs; not committed).
- `etl.load_processed.HELD_FILES` holds both `scotland_extent.27700.geojson`
  (loaded via `build_scotland_extent --load-only`) and
  `scotland_ext_shelf_optional.27700.geojson` (outside `CLIP_ZONES`).
- ARCH-1 `test_k2_catalog_credits` keeps an exact-match assert on
  `SCOTLAND_EXTENT_LAND_CREDIT` (OS Crown copyright 2026 string).

## Build

Offline only (`python -m etl.build_scotland_extent`). Never in CI. Outputs:

- `data/processed/gis/scotland_extent.27700.geojson` (3 zones)
- `data/processed/gis/scotland_ext_shelf_optional.27700.geojson`
