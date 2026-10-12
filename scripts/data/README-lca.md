# Land Capability for Agriculture (LCA) ingest

James Hutton Institute publishes **Land Capability for Agriculture** at
1:250,000 as an open national download. Scot-LAND serves it as a context map
layer from a local PostGIS load.

## Licence and attribution

| Field | Value |
|-------|--------|
| Product | Land Capability for Agriculture 1:250,000 (`LCA_250K`) |
| Authority | The James Hutton Institute (maintenance funded by Scottish Government RESAS) |
| Licence | **James Hutton Institute Open Data Licence** — not pure OGL. Public-sector information in the product is licensed under **OGL v2.0** per the Hutton attribution clause. |
| Attribution | Land Capability for Agriculture 1:250,000 copyright and database right The James Hutton Institute. Used with the permission of The James Hutton Institute. All rights reserved. Any public sector information contained in these data is licensed under the Open Government Licence v.2.0. |
| Download | https://www.hutton.ac.uk/sites/default/files/files/soils/downloads/Hutton_LCA250K_OpenData.zip |
| Catalogue | https://spatialdata.gov.scot/geonetwork/srv/api/records/24c6df5a-6b04-43f8-839f-0d45cc2802e3 |
| Licence PDF | https://www.hutton.ac.uk/wp-content/uploads/2024/05/The-James-Hutton-Institute-Open-Data-Licence-download.pdf |

Committed registry: `data/config/sources.yaml` → `lca`.

**Do not commit** the shapefile or zip. `scripts/data/data_check.py` treats
Hutton / LCA geometry as a FAIL if tracked.

## Refresh steps

1. Download `Hutton_LCA250K_OpenData.zip` from the Hutton open-data URL above.
2. Unzip under `data/external/lca/` (gitignored), so you have
   `data/external/lca/LCA_250K.shp` (+ `.dbf`, `.shx`, `.prj`).
3. Load into PostGIS (reprojects British National Grid → WGS84):

```bash
cd backend
export DATABASE_URL=postgresql://user:pass@localhost:5432/scotland_wealth
python -m etl.ingest_lca \
  --input ../data/external/lca/LCA_250K.shp \
  --replace
```

4. Confirm the API:

```bash
curl -s "http://127.0.0.1:8000/layers/open/lca?south=55.8&west=-4.3&north=55.9&east=-4.2" | head
```

- Loaded data → GeoJSON FeatureCollection  
- Missing / empty table → **HTTP 503** (never placeholder polygons)

## Known limits

- National **1:250,000** scale — indicative land capability, not field boundaries  
- Separate **1:50,000** partial-cover product exists; not loaded here  
- Does not change parcel AGR or Surface Rent
