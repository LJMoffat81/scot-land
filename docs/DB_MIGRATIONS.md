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
