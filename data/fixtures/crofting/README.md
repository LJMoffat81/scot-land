# Crofting fixtures (tests only)

Small redistributable slices of Crofting Commission Register of Crofts open
data (OGL-3.0) for CI and local smoke tests.

| File | Role |
|------|------|
| `parishes.csv` | Parish lookup |
| `holdings.csv` | Croft holdings (Register of Crofts tabular) |
| `grazings.csv` | Common grazings list with extent (ha) |

Load into PostGIS:

```bash
cd backend
python -m etl.ingest_crofting --from-fixtures
```

Production / research loads use `--download` into gitignored
`data/external/crofting/`. Do **not** commit Individuals CSV (personal data).
