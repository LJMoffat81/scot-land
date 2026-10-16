# Work queue

Plain-English queue for maintainers (Laurie and agents). Update on main after merges — not in feature PRs (avoids serial conflict churn). Dedicated QUEUE-only follow-up is OK when nothing else is ready to piggyback.

**Cap:** ≤5 open non-draft PRs; one PR per item ID. Right now: drafts [#163](https://github.com/LJMoffat81/scot-land/pull/163) and [#169](https://github.com/LJMoffat81/scot-land/pull/169) do not count. This QUEUE sync opens as the 1st non-draft. Hold #169 draft / do-not-merge for the release cap.

## In progress

| Item | Description | PR | Status |
|------|-------------|----|--------|
| MAP-CARDS-REDESIGN | Place card, Layers, legend redesign (+ ADDENDUM-1) | [#163](https://github.com/LJMoffat81/scot-land/pull/163) | Draft; tip `bab579d…`; CI green |
| GRID-BASE-1 | Open 3 m BNG grid base layer (no values) | [#169](https://github.com/LJMoffat81/scot-land/pull/169) | Draft; tip `339d20d…`; CI green; Scot-LAND PASS; hold draft / do-not-merge for release cap |

## Next up (in order)

| Item | Description | PR | Status |
|------|-------------|----|--------|
| UI-FIX-1 | Tap targets ≥44×44 and related map chrome fixes on MAP-CARDS layout | — | Frozen ready; waits on #163 merge; no PR yet |
| LAYERS-ADD-1 | Open context layers + licence-gated catalog | — | Can target main / opening now (not blocked on #169); no PR yet |
| LAYERS-ADD-2 | Open-data sweep layers (after LAYERS-ADD-1) | — | Frozen ready; still after LAYERS-ADD-1; no PR yet |
| GBP-LIVE-V1c | £ per m² follow-ups before any flag enable (flag still default OFF) | — | Can target main / opening now (not blocked on #169); flag OFF; no PR yet |

### Frozen backlog

| Item | Description | PR | Status |
|------|-------------|----|--------|
| SW-044_slim | Slim the map view (licences out of left panel, chip key once, etc.) | [#157](https://github.com/LJMoffat81/scot-land/pull/157) | Closed / superseded by MAP-CARDS-REDESIGN (#163) |
| Suggestion 44 | Deploy SHA / git commit surface; park with SW-037 if it needs `main.py` | — | Parked (HEALTH-TRIM / SW-037 already on main via #166; SHA surface still open) |
| UX-00 … UX-05 | Mobile hit areas, legend aria, Esc focus, landmarks, place-card hug, desktop search | [#130](https://github.com/LJMoffat81/scot-land/pull/130) … [#136](https://github.com/LJMoffat81/scot-land/pull/136) | UX train done — all merged (incl. UX-00 #130 and UX10-1 #134) |
| SW-031 / SW-032 | Scrub banned wording and public money figures from public surfaces | [#133](https://github.com/LJMoffat81/scot-land/pull/133) | Merged |
| SW-039 + idea 45 | “Why no outline?” becomes a proper tap target; answer opens inline | [#136](https://github.com/LJMoffat81/scot-land/pull/136) | Done (with UX-01 mobile hit areas) |

## Recently merged

Newest first.

| Item | Description | PR | Status |
|------|-------------|----|--------|
| UI-TWEAKS-1 | Layers panel height/position and related map chrome tweaks | [#168](https://github.com/LJMoffat81/scot-land/pull/168) | Merged on main (`ffaa9f32`) |
| LOGO-FIX-1 | Absolute OG/Twitter URLs + drop Noun credit | [#167](https://github.com/LJMoffat81/scot-land/pull/167) | Merged (`cc2406f`) |
| HEALTH-TRIM | Public `/health` is status + version only (SW-037) | [#166](https://github.com/LJMoffat81/scot-land/pull/166) | Merged on main (`78a0af2`); verified |
| LOGO-H2 | Zone-grid loch mark, favicons, tagline | [#161](https://github.com/LJMoffat81/scot-land/pull/161) | Merged (`fbe8d0a`) |
| DZ-HIERARCHY | Intermediate Zone / council on the place card; mobile More-about fold | [#156](https://github.com/LJMoffat81/scot-land/pull/156) | Merged (`80d1870`) |
| QUEUE sync | Refresh after #152–#155, #160–#164; next MAP-CARDS train | [#165](https://github.com/LJMoffat81/scot-land/pull/165) | Merged (`3129826`) |
| GBP-LIVE-V1b | Per-m² unit for £ behind the flag (flag still default OFF) | [#155](https://github.com/LJMoffat81/scot-land/pull/155) | Merged (`0bb4cae`) |
| V14-FIDELITY | Straight-line remaining, O-G1, check-4 fail | [#164](https://github.com/LJMoffat81/scot-land/pull/164) | Merged (`fe026b7`) |
| O-MM | Hedonic cell merge map (v1.4) | [#162](https://github.com/LJMoffat81/scot-land/pull/162) | Merged (`cb3370c`) |
| V13-METHODS | Methods v1.3 cost basis, depreciation, checks | [#152](https://github.com/LJMoffat81/scot-land/pull/152) | Merged (`5529e27`) |
| POST-SHARE-1 | OSGB map ref, Coming soon layers, API badge, page width | [#160](https://github.com/LJMoffat81/scot-land/pull/160) | Merged (`f536b9f`) |
| SW-034_data_mobile | Mobile `/data` sources as stacked cards (no horizontal scroll) | [#154](https://github.com/LJMoffat81/scot-land/pull/154) | Merged (`25d1a88`) |
| MAPREF-HIDE | Omit Map reference row on place card | [#159](https://github.com/LJMoffat81/scot-land/pull/159) | Merged (`bf40bfc`) |
| WORDING-BATCH-1 | Map/place-card/API wording + SHARE-FIX | [#158](https://github.com/LJMoffat81/scot-land/pull/158) | Merged (`217fa2a`) |
| QUEUE sync | Refresh after #144–#151; drop ROS INSPIRE e2e mock | [#153](https://github.com/LJMoffat81/scot-land/pull/153) | Merged (`754119d`) |
| UX10-2 | Built-up mask (`map_builtup_mask`, `dz2022_masked`) | [#151](https://github.com/LJMoffat81/scot-land/pull/151) | Merged (`0e539c5`) |
| SURFACE-COSTS-STRICT | Exact fixture match in CI (20-row equality always runs) | [#148](https://github.com/LJMoffat81/scot-land/pull/148) | Merged (`c162243`) |
| QUEUE sync | Sync after SURFACE-COSTS-ALL / PARCELS-OFF merges | [#146](https://github.com/LJMoffat81/scot-land/pull/146) | Merged (`96ba57a`) |
| SW-045 + SW-046 | Legend follows the active layer; legend clear of place card | [#150](https://github.com/LJMoffat81/scot-land/pull/150) | Merged (`205040b`) |
| GBP-LIVE-V1 | Public £ surface rent on place card / legend / How it works (flag default OFF) | [#144](https://github.com/LJMoffat81/scot-land/pull/144) | Merged (`0791bd5`) |
| FILL-MEASURED-ZERO | Keep floored measured zeros (blocks £ gate) | [#149](https://github.com/LJMoffat81/scot-land/pull/149) | Merged (`16f467f`) |
| PARCELS-OFF | Gate parcel API/UI behind `PARCELS_PUBLIC` (default false); HIGH | [#145](https://github.com/LJMoffat81/scot-land/pull/145) | Merged (`fc5e1f1`) |
| SURFACE-COSTS-ALL | Rebuild surface costs for every DZ2011 zone | [#147](https://github.com/LJMoffat81/scot-land/pull/147) | Merged (`d98b513`) |
| HOME-TUNNEL step 2 | Named tunnel, offline Worker, backups | [#142](https://github.com/LJMoffat81/scot-land/pull/142) | Merged (`b41d2c6`) |
| FILL-ORDER-V12 | Mainland borrow drops next-UR class (Methods v1.2) | [#143](https://github.com/LJMoffat81/scot-land/pull/143) | Merged (`5196eab`) |
| SW-036 v2 | Desktop layout (≥1024): place card left, Layers right, legend pill below the card | [#139](https://github.com/LJMoffat81/scot-land/pull/139) | Merged (`705f2d5`) |
| FILL-POOLED | Run DZ2011/DZ2022 empty-zone fill on pooled inputs (target 129) | [#141](https://github.com/LJMoffat81/scot-land/pull/141) | Merged (`5156b74`) |
| NEIGHBOURS-2022 | Council neighbours CSV at `data/reference/council_neighbours_2022.csv` (reason column + invariants) | [#140](https://github.com/LJMoffat81/scot-land/pull/140) | Merged (`d49651a`) |
| SW/UX e2e auto-discovery | Playwright CI auto-discovers specs under `e2e/ci/` | [#138](https://github.com/LJMoffat81/scot-land/pull/138) | Merged (`cec7e41`) |
| UX-01 | Mobile tap targets ≥44×44 | [#136](https://github.com/LJMoffat81/scot-land/pull/136) | Merged |
| UX10-1 | Place card skeleton + FP1 schema | [#134](https://github.com/LJMoffat81/scot-land/pull/134) | Merged |
| UX-04 | Unique landmarks and button accessible names | [#132](https://github.com/LJMoffat81/scot-land/pull/132) | Merged |
| UX-02 | Legend fold `aria-expanded` tracks body visibility | [#131](https://github.com/LJMoffat81/scot-land/pull/131) | Merged |
| UX-05 | “No place matched” card hugs content | [#129](https://github.com/LJMoffat81/scot-land/pull/129) | Merged |
| UX-03 | Esc returns focus to Layers / nav toggle | [#128](https://github.com/LJMoffat81/scot-land/pull/128) | Merged |
| SW-038 | Deploy swaps api/frontend only — never touch cloudflared | [#137](https://github.com/LJMoffat81/scot-land/pull/137) | Merged |
| SW-026 | Research banner clears open place card | [#123](https://github.com/LJMoffat81/scot-land/pull/123) | Merged |
