# SURFACE-COSTS-STRICT — fixture-only inputs

Resolved zone inputs for the 20 measured DZ2011 codes in
`../surface_costs_dz2011_sample.csv`. Lets CI recompute
`rebuild_new_gbp` / `remaining_factor` / `drc_*` **without**
`data/processed` (estate rows are post-`borrow_plot_bands`).

Regenerate from a machine with processed GIS + Data Zones:

```bash
cd backend
python - <<'PY'
# see tests/surface/test_surface_costs_dz2011.py::_write_inputs_hint
PY
```
