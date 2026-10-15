# Database migrations (Alembic)

The Wealth Engine and cadastral tables are versioned with **Alembic**.
Ad hoc `CREATE TABLE IF NOT EXISTS` / `ALTER TABLE ... IF NOT EXISTS` in the
loader path is replaced by migrations. Source DDL for the baseline still lives
in `backend/db/schema/*.sql` and is applied by the baseline revision.

## Fresh database

```bash
cd backend
export DATABASE_URL=postgresql://scotland:<password>@127.0.0.1:5432/scotland_wealth
# or PGHOST / PGDATABASE / PGUSER / PGPASSWORD
alembic upgrade head
python -m db.check_drift   # optional: assert live schema matches db/schema/*.sql
```

`python -m etl.migrate_to_postgis --schema-only` also runs `alembic upgrade head`,
then can load placeholder resource/eco GeoJSON when run without `--schema-only`.

## Existing database (already created by the old schema path)

If PostGIS already has the Wealth tables from an earlier
`migrate_to_postgis` / init-script run, **do not** re-run the baseline DDL.
Stamp the current revision instead:

```bash
cd backend
export DATABASE_URL=...
alembic stamp head
python -m db.check_drift
```

After stamping, future revisions (`alembic revision` + `upgrade`) apply normally.

## Adding a migration

1. Change or add SQL under `backend/db/schema/` when the change is structural
   baseline documentation, **and/or** add an Alembic revision under
   `backend/alembic/versions/` for the incremental change.
2. Prefer an Alembic revision with explicit `upgrade()` / `downgrade()` for
   anything that must run on an already-stamped database.
3. Run `alembic upgrade head` and `python -m db.check_drift` locally.
4. CI runs upgrade + drift check on a fresh PostGIS 17 service before pytest.

## CI

`.github/workflows/ci.yml` (Backend tests job):

1. Create PostGIS extension on the service container.
2. `alembic upgrade head`
3. `python -m db.check_drift`
4. Then the existing pytest / manifest checks.

## Notes

- Never commit credentials; Alembic reads `DATABASE_URL` or `PG*`.
- Never touch gitignored `data/external`.
- `inspire_parcels` (RoS INSPIRE ingest from PR #4) is part of the baseline
  (`005_inspire_parcels.sql`).
- Natural-capital hydro + SEPA CAR: `006_hydro_sepa_car.sql` + Alembic
  `20261012_0002` (`hydro_sites`, `sepa_car_licences`).
- SEPA CAR MapServer ingest shape: Alembic `20261012_0003` recreates
  `sepa_car_licences` for layers 194/195 (`python -m etl.ingest_sepa_car`).
- SEPA flood extents: `007_sepa_flood.sql` plus Alembic revision `20261012_0004`.
  Ingest: `python -m etl.ingest_sepa_flood --from-gdb --replace` (see
  `scripts/data/README-sepa.md`; vintage **2025-02-25** from SEPA v3.0 release notes).
- NatureScot SSSI / SPA / SAC / NNR tables are `008_naturescot_designations.sql`
  plus Alembic revision `20261012_0005`.
- Crofting Commission tables (`croft_parishes`, `croft_holdings`,
  `common_grazings`) are in `013_crofting.sql` plus Alembic revision
  `20261012_0010` (`down_revision` = `20261012_0005`). Numbering skips
  `009`/`0006`–`012`/`0009` (historical open-tip reservations). Load with
  `python -m etl.ingest_crofting --download` (raw CSVs under gitignored
  `data/external/crofting/`). OGL lists only — no boundaries; never ingest
  List of Individuals.
- Community ownership assets are in `014_community_ownership.sql` plus
  Alembic revision `20261012_0011` (`down_revision` = `20261012_0010`).
- `nrs_settlements` / `nrs_localities` (NRS Census 2022, OGL) are in
  `015_nrs_settlements_localities.sql` and Alembic revision `20261012_0012`
  (`down_revision` = `20261012_0011`). Ingest:
  `python -m etl.ingest_nrs_settlements --fetch` (see
  `scripts/data/README-nrs-settlements.md`).
- NFI + Native Woodland Survey tables are `016_woodland_layers.sql` plus
  Alembic revision `20261012_0013` (`down_revision` = `20261012_0012`).
  Ingest: `python -m etl.ingest_woodland_layers --layer nfi --from-wfs --replace`
  (and `--layer native_woodland`; see `scripts/data/README-woodland.md`).
- `repd_sites` and `crown_estate_leases` (DESNZ REPD + CES OGL offshore leases)
  are in `017_open_energy_leases.sql` plus Alembic revision `20261012_0014`
  (`down_revision` = `20261012_0013`).
  Ingest: `python -m etl.ingest_repd` / `python -m etl.ingest_crown_estate_leases`.
- `lca_agriculture` (James Hutton LCA 1:250k) is in `018_lca_agriculture.sql` plus Alembic revision `20261012_0015` (`down_revision` = `20261012_0014`). Hutton Open Data Licence (not OGL). Ingest: `python -m etl.ingest_lca` (see `scripts/data/README-lca.md`). Ledger constraint — £0, not a rent.
- `ces_scotwind_intog` (CES Spatial Hub ScotWind Offers + INTOG Application Areas, OGL) is in `019_ces_scotwind_intog.sql` plus Alembic revision `20261012_0016` (`down_revision` = `20261012_0015`). Credit: Contains information from the Crown Estate Scotland licensed under the Open Government Licence v3.0. Polygons only; fees HOLD off-layer. Ingest: `python -m etl.ingest_scotwind_intog --from-api`. Ledger row 4 — no £ rent.
- `repd_onshore_wind` (DESNZ REPD Scotland onshore wind MW/status, natural-capital) is in `020_nc_repd_onshore_wind.sql` plus Alembic revision `20261012_0017` (`down_revision` = `20261012_0016`). Numbered past main ScotWind `019`/`0016`. Load with `python -m etl.ingest_repd_onshore_wind` (OGL quarterly CSV; never commit under `data/external`). Ledger row 3 — no £ rent.
- `surface_rent_rollup` (internal DZ2022 → IZ → Council → Scotland surface-rent sums) is in `023_surface_rent_rollup.sql` plus Alembic revision `20261013_0020` (`down_revision` = `20261012_0019`). `publish_level` is constrained to `internal`. Build path: `georgist.surface_dz2022` + `georgist.surface_rollup`; serve only `/internal/georgist/surface-rent-rollup`.
- `datazones.dz2011_dz2022_uprn_weights` (OS Open UPRN address-point crosswalk) is in `004_datazones.sql` / `024_dz2011_dz2022_uprn_weights.sql` plus Alembic revision `20261013_0021` (`down_revision` = `20261013_0020`). Surface conversion stamps `crosswalk_method=address_uprn`; min-share filter default ON in `georgist.surface_dz2022`.
- `map_builtup_mask` and `dz2022_masked` (UX10-2 built-up display mask; DZ2022 only) are in `025_map_builtup_mask.sql` plus Alembic revision `20261015_0022` (`down_revision` = `20261013_0021`). Display only — no rent. Ingest: `python -m etl.ingest_builtup_mask` from `BUILTUP_MASK_DIR` or `data/external/builtup/` (gitignored GeoJSON; see `scripts/data/README-builtup-mask.md`).
