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
  Ingest: `python -m etl.ingest_woodland_layers` (see
  `scripts/data/README-woodland.md`).
- `repd_sites` and `crown_estate_leases` (DESNZ REPD + CES OGL offshore leases)
  are in `017_open_energy_leases.sql` plus Alembic revision `20261012_0014`
  (`down_revision` = `20261012_0013`).
  Ingest: `python -m etl.ingest_repd` / `python -m etl.ingest_crown_estate_leases`.
- `lca_agriculture` (James Hutton LCA 1:250k) is in `018_lca_agriculture.sql` plus Alembic revision `20261012_0015` (`down_revision` = `20261012_0014`). Hutton Open Data Licence (not OGL). Ingest: `python -m etl.ingest_lca` (see `scripts/data/README-lca.md`). Ledger constraint — £0, not a rent.
- `ces_scotwind_intog` (CES Spatial Hub ScotWind Offers + INTOG Application Areas, OGL) is in `019_ces_scotwind_intog.sql` plus Alembic revision `20261012_0016` (`down_revision` = `20261012_0015`). Credit: Contains information from the Crown Estate Scotland licensed under the Open Government Licence v3.0. Polygons only; fees HOLD off-layer. Ingest: `python -m etl.ingest_scotwind_intog --from-api`. Ledger row 4 — no £ rent.
