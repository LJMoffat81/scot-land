# SEPA Flood Maps — repeatable load

Medium-likelihood (1:200) **river** and **coastal** present-day extents from
SEPA Flood Maps **v3.0**. Constraint / context only — never a rent.

| Field | Value |
|-------|--------|
| Download (only) | https://www2.sepa.org.uk/flooddata/ |
| Product | River + Coastal Flood Maps v3.0 ESRI FileGDB zips |
| Atom zips (linked from flooddata) | `SEPA_River_Flood_Maps_v3_0.zip`, `SEPA_Coastal_Flood_Maps_v3_0.zip` |
| Licence | OGL v3.0 — © SEPA 2025 |
| Release notes | https://www.sepa.org.uk/media/htpldzvk/flood-map-version-3_0-release-notes.pdf |
| Vintage | **2025-02-25** (release-notes date — not a 2025-01-01 placeholder) |
| PostGIS | `sepa_flood` |
| API | `GET /layers/open/flood` → **503** when unloaded |

Do **not** ingest via MapServer, viewer, or other live web services.

## Steps (home PC / docker compose)

1. Create writable mounts (see `docker-compose.home.yml` / PR #57):
   `data/external/sepa/` → `../scot-land-downloads/sepa`.
2. Download from https://www2.sepa.org.uk/flooddata/ :
   - SEPA River Flood Maps v3.0 — ESRI Geodatabase
   - SEPA Coastal Flood Maps v3.0 — ESRI Geodatabase
3. Unzip both under `data/external/sepa/` so the FileGDBs are findable, e.g.
   `…/FRM_River_Flood_Hazard_Layers_v3_0.gdb` and
   `…/FRM_Coastal_Flood_Hazard_Layers_v3_0.gdb`.
4. Needs **GDAL `ogr2ogr`** on PATH (OpenFileGDB driver).
5. One command:

```bash
cd backend
export DATABASE_URL=postgresql://…
alembic upgrade head
python -m etl.ingest_sepa_flood --from-gdb --replace --check-counts
```

What the loader does:

- Exports `FRM_FH_RIVER_EXTENT_M` (layer_id **1**) and
  `FRM_FH_COASTAL_EXTENT_M` (layer_id **7**)
- Reprojects to EPSG:4326, promotes to MultiPolygon
- Simplifies **~2 m** in source metres (BNG)
- Keeps **polygon** parts from mixed geometries; drops lines/points
- Writes `data/external/sepa/flood_medium_river_coastal.geojson` then loads PostGIS
- Stamps vintage **2025-02-25** from the v3.0 release notes
- `--check-counts` accepts within ~0.1% of the #57 baseline:
  **47,093** river + **16** coastal

Or export only:

```bash
python -m etl.ingest_sepa_flood --from-gdb --export-only
```

Or load a pre-built GeoJSON:

```bash
python -m etl.ingest_sepa_flood \
  --input ../data/external/sepa/flood_medium_river_coastal.geojson \
  --replace --check-counts
```

## Mintlify row counts

After a successful load:

```bash
python scripts/data/regen_layer_guide_counts.py
```

updates `docs/mintlify/map-layer-guide.mdx` from PostGIS (and WFS hits for woodland).
