# Owner build scripts (provenance)

Scripts the owning bots used to build `data/processed/<dataset>/`. They are kept for
provenance and re-runs; the engine never imports them, and they are not part of the
backend package (`backend/etl/` is the engine's own loader).

- `datazones/`: Scot-LAND Data Zones (`fetch.py` downloads and verifies, `build.py`,
  `stage.py`), plus the owner's `README.md`, `sources.md`, `schema.sql`, `SOURCES_SHA256.txt`
  and `requirements.txt`. They passed the owner's rebuild-from-scratch check (byte-for-byte).
  Paths come from `--root` / `--raw` / `--out` / `--dest` (or `DZ_ROOT`, `DZ_RAW`, `DZ_OUT`,
  `DZ_STAGE`); in this repo pass `--root` explicitly, because the default (the parent of the
  scripts folder) would be `etl/`.
- `gis/`: Scot-LAND GIS build scripts. `zone_rules.py` holds the shared vintage/code-range
  checks; `backend/tests/etl/test_zone_rules_agree.py` keeps our loader's ranges in step.
  Excluded on GIS's instruction: `apply_team_rules.py`, `update_manifest_gis.py`,
  `backup_pre_int_vintage/`.

Raw downloads (`raw/`, 736 MB for Data Zones, about 16 GB for GIS) are never committed
(`.gitignore`). The GIS scripts still contain the owner's absolute `/workspace/...` paths;
set them for your machine before re-running.
