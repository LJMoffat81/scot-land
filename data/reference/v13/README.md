# v1.3 method inputs (no £)

Commit when available (sha256 must match `surface.yaml` `v13.*`):

| File | sha256 | Notes |
|------|--------|-------|
| `dz2022_bedroom_bands.csv` | `6d15b887…` | Census 2022 UV408/MV406; no £ — may commit |
| `dz2022_plot_split_v13.csv` | `09e2082d…` | Settlement2022 plot split; no £ — may commit |
| `v13_holdout_zones.txt` | `19ac927b…` | 680-zone info-only list |

**Never commit:** `dz2022_other_land_lca.csv` (farmland/LCA rates). Set env `V13_OTHER_LAND_LCA_PATH` on the scoring host; CI skips with a clear message.
