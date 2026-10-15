# O-MM hedonic merge map — reproduce notes

**Valuation note (prereg DRAFT hash):** the Project store `v14_prereg_DRAFT.md` currently hashes to `f8117fd074589756fe060c673080c733d6bfc12f66cd2646f5c61c6f67fe06f0`. The frozen prefix cited in review is `04b0afb1…`. **Valuation must settle which is correct before freeze; this PR does not invent which.**

**Seed source:** `seeds.hedonic_cluster_bootstrap` from `--freeze-json` (default `/workspace/scotland-rules/v14_prereg_freeze.json`). Seed field is authoritative; freeze-file sha256 is not hard-coded in code. Tests use `backend/tests/fixtures/hedonic/v14_prereg_freeze_seed_only.json` (fixture only — not the pinned production freeze).

## Production merge-map sha256

`581b0aa1647c5af7ce5b9617e35fcfa73982bc8712a42eb63242243ee6a95947` (6,188 zones)

## Pinned inputs (path + sha256)

| Role | Path | sha256 | Notes |
|------|------|--------|-------|
| Sale **counts** only | `data/processed/methods_code_1/pr1/ros_dz2011_sales_n_2019_2023.csv` | `37fe46da5e647b29a966bd70713de21ae8514b95dfbe1e95b43a62e060eeeb50` | Columns: `code,year,sales_n,suppressed` only. |
| Urban–rural | `scotland-rules/ur6/dz2011_urban_rural_6fold_2020.csv` | `1f32a81532912334e3cd071e2f12f523e66068d14c73e5db4ae51add239b1a92` | **DZ2011 URC 2020** (freeze `inputs.ur6_dz2011`). |
| Plot split | Project store `omm-inputs/dz2022_plot_split_v13.csv` | `09e2082d801b15203794974aea802cc7e5c5c403761365b69bd4b695d7a0638c` | |
| UPRN weights | Project store `omm-inputs/dz2011_dz2022_uprn_weights.csv` | `7690bcbebf9968ca9b02cf898832aa9be8fca56f3eb9af70b20e25b5d23e13e4` | |
| SPD 2026/2 | `data/external/raw/spd_postcodeindex_cut_26_2_csv.zip` | `4e93069ddb9c39c211cafdc56eeb16c4b0ed4872c9a95c20e23ec73c3b499057` | |

## Exact CLI (reproduce)

```bash
cd backend
PYTHONPATH=. python3 scripts/build_hedonic_merge_map.py \
  --freeze-json /workspace/scotland-rules/v14_prereg_freeze.json \
  --counts /workspace/data/processed/methods_code_1/pr1/ros_dz2011_sales_n_2019_2023.csv \
  --ur /workspace/scotland-rules/ur6/dz2011_urban_rural_6fold_2020.csv \
  --plot-split /cursor/stores/self/omm-inputs/dz2022_plot_split_v13.csv \
  --uprn-weights /cursor/stores/self/omm-inputs/dz2011_dz2022_uprn_weights.csv \
  --spd-zip /workspace/data/external/raw/spd_postcodeindex_cut_26_2_csv.zip \
  --out /workspace/data/external/hedonic/merge_map_v14.csv
```

Stdout is the merge-map sha256. Output is gitignored under `data/external/`.
