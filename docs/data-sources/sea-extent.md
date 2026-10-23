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

Boundary-Line MLW land crosses SI Sch 1 Pt II s1 east of ~3.35°W. After the
25 m simplify, the build adds 150 m water disks at undensified s1 vertices 1
and 2 (`difference` land) so those sea vertices stay ≤ 150 m from the extent
edge. Pinned in-land vertices 3 and 4 (C1b) stay inside OS land; land is never
cut.

## Hatton / optional shelf

`scotland_ext_shelf_optional.27700.geojson` holds UK continental shelf beyond
the UK EEZ next to the Scottish zone (Hatton face and Faroe shelf strips).
Seabed rights only; not Scottish waters; outside the default clip. It is not
loaded into `ref.extent` and is not in `CLIP_ZONES`.

## Build

Offline only (`python -m etl.build_scotland_extent`). Never in CI. Outputs:

- `data/processed/gis/scotland_extent.27700.geojson` (3 zones)
- `data/processed/gis/scotland_ext_shelf_optional.27700.geojson`
