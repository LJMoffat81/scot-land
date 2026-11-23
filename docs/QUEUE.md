# Work queue

Plain-English queue for maintainers (Laurie and agents). Update on main after merges — not in feature PRs (avoids serial conflict churn). Dedicated QUEUE-only follow-up is OK when nothing else is ready to piggyback. This file is also the sanctioned weekly docs sync path.

**Cap:** ≤5 open non-draft PRs; one PR per item ID. As of this sync (`main` @ `7b84ccc3`, tip of #324): **no open PRs** (draft or non-draft). This QUEUE sync opens as the 1st non-draft.

## In progress

None. GitHub shows no open PRs. Stale rows UI-FIX-4 / VDL-DZ-2 / LAYERS-ADD-2 were already merged (#183 / #182 / #184) and are listed under Recently merged.

## Next up (in order)

Nothing confirmed open or frozen on GitHub for this sync. Do not invent statuses here — add rows only when a frozen item or open PR exists.

### Frozen backlog (historical)

| Item | Description | PR | Status |
|------|-------------|----|--------|
| SW-044_slim | Slim the map view (licences out of left panel, chip key once, etc.) | [#157](https://github.com/LJMoffat81/scot-land/pull/157) | Closed / superseded by MAP-CARDS-REDESIGN (#163) |
| Suggestion 44 | Deploy SHA / git commit surface; park with SW-037 if it needs `main.py` | — | Parked (HEALTH-TRIM / SW-037 already on main via #166; SHA surface still open) |
| UX-00 … UX-05 | Mobile hit areas, legend aria, Esc focus, landmarks, place-card hug, desktop search | [#130](https://github.com/LJMoffat81/scot-land/pull/130) … [#136](https://github.com/LJMoffat81/scot-land/pull/136) | UX train done — all merged (incl. UX-00 #130 and UX10-1 #134) |
| SW-031 / SW-032 | Scrub banned wording and public money figures from public surfaces | [#133](https://github.com/LJMoffat81/scot-land/pull/133) | Merged |
| SW-039 + idea 45 | “Why no outline?” becomes a proper tap target; answer opens inline | [#136](https://github.com/LJMoffat81/scot-land/pull/136) | Done (with UX-01 mobile hit areas) |

## Recently merged

Newest first. Synced from GitHub through #324.

| Item | Description | PR | Status |
|------|-------------|----|--------|
| YET-WORDING-1 | Replace five locked visitor strings | [#324](https://github.com/LJMoffat81/scot-land/pull/324) | Merged (`7b84ccc3`) |
| UX-BATCH-2026-11-20 | Site card, card footer, story bar, search hint, nav 44 | [#323](https://github.com/LJMoffat81/scot-land/pull/323) | Merged (`370af2dd`) |
| SCHEDULE-DETECT-BASE-1 | Explicit `--no-changes` path for schedule/dispatch in Detect frontend changes | [#322](https://github.com/LJMoffat81/scot-land/pull/322) | Merged (`bc8359bb`) |
| CLEANUP-318 | WUX nits, exact-text pins, hls-open data-as-of date, G6 context guard | [#321](https://github.com/LJMoffat81/scot-land/pull/321) | Merged (`0cf7d179`) |
| M1-CLOSE-1 | Close G1–G3, G4 limit tests, re-tag hls-open/ldp-highland, context cap 6 | [#320](https://github.com/LJMoffat81/scot-land/pull/320) | Merged (`5d0c4457`) |
| PSGA-COPY-CLEANUP-1 | Reword legacy HLS and LDP display copy | [#319](https://github.com/LJMoffat81/scot-land/pull/319) | Merged (`2de80409`) |
| PLANNING-PUBLISH-1 PR-B | Housing land supply and Highland plan rows | [#318](https://github.com/LJMoffat81/scot-land/pull/318) | Merged (`0b366689`) |
| PLANNING-PUBLISH-1 PR-A | Publish allow-list for hls-open and ldp-highland | [#317](https://github.com/LJMoffat81/scot-land/pull/317) | Merged (`603fed8b`) |
| Map load / search focus | Show when the map or layers fail to load; fix search focus ring | [#316](https://github.com/LJMoffat81/scot-land/pull/316) | Merged (`09683099`) |
| EXTERNAL-UPTIME-1 | Hourly external health probe (`.github/workflows/uptime.yml`) | [#315](https://github.com/LJMoffat81/scot-land/pull/315) | Merged (`3e3b4968`) |
| LOOKUP-DEADLINES-1a | Per-request lookup deadlines and locked error line | [#314](https://github.com/LJMoffat81/scot-land/pull/314) | Merged (`d1947f7d`) |
| COMPOSE-LOGGING-3 | json-file log rotation on the home stack | [#313](https://github.com/LJMoffat81/scot-land/pull/313) | Merged (`10aa9e97`) |
| E2E-FLAKE-1 | Stabilise search blur, downloads hit targets, basemap toggle | [#310](https://github.com/LJMoffat81/scot-land/pull/310) | Merged (`4c13d936`) |
| M6 Carbon and land | Story view only (Q6 explainer) | [#309](https://github.com/LJMoffat81/scot-land/pull/309) | Merged (`2f51dbeb`) |
| M2 Idle land | Vacant and derelict land council story view | [#308](https://github.com/LJMoffat81/scot-land/pull/308) | Merged (`ad97cca0`) |
| M5 Who holds Scotland | Council community-ownership story view | [#307](https://github.com/LJMoffat81/scot-land/pull/307) | Merged (`0e114847`) |
| M4 story-view framework | Explainer rows on view presets | [#306](https://github.com/LJMoffat81/scot-land/pull/306) | Merged (`0a316936`) |
| DZ-HEATMAP PR-B | Estimate-status fill and key | [#305](https://github.com/LJMoffat81/scot-land/pull/305) | Merged (`59fa8ec5`) |
| LAYERS-ADD-2 | Open-data sweep and council sources | [#184](https://github.com/LJMoffat81/scot-land/pull/184) | Merged (`54c4ba98`) |
| UI-FIX-4 | Layers column, sheet, and card polish | [#183](https://github.com/LJMoffat81/scot-land/pull/183) | Merged (`052d6b3e`) |
| VDL-DZ-2 | Small-count suppression and drop site overlay | [#182](https://github.com/LJMoffat81/scot-land/pull/182) | Merged (`df350f9f`) |
| QUEUE sync | Sync after #177, #178, and #180 | [#181](https://github.com/LJMoffat81/scot-land/pull/181) | Merged (`1e9b302e`) |
| LAYERS-FIX-1 | Empty layer switches; live protected sites and oil fields | [#180](https://github.com/LJMoffat81/scot-land/pull/180) | Merged (`b633b4ba`; tip `30a52013`) |
| UI-FIX-3 | One close control and no empty place-card tail | [#178](https://github.com/LJMoffat81/scot-land/pull/178) | Merged (`2445c63`) |
| VDL-DZ-1 | Data Zone totals only on `/layers/open/vdl` (no site-level fields) | [#177](https://github.com/LJMoffat81/scot-land/pull/177) | Merged (`86f8e5c`) |
| LAYERS-ADD-1 | Open context layers + licence gates | [#172](https://github.com/LJMoffat81/scot-land/pull/172) | Merged on main (`1bdfdf6`) |
| UI-FIX-2 | Mobile place-card layout | [#176](https://github.com/LJMoffat81/scot-land/pull/176) | Merged (`f81dbee`) |
| UI-FIX-1 | Tap targets, SW-056, roadmap OG (+ ADDENDUM-1/2) | [#173](https://github.com/LJMoffat81/scot-land/pull/173) | Merged (`ef0d15e`) |
| HOTFIX-VIEW-1 | Fresh visitors frame Scotland | [#175](https://github.com/LJMoffat81/scot-land/pull/175) | Merged (`f02be56`) |
| GBP-LIVE-V1d | Zero and negative zero unavailable; range central; order check | [#174](https://github.com/LJMoffat81/scot-land/pull/174) | Merged (`0b99774`) |
| GRID-BASE-1 | Open 3 m BNG grid base layer (no values) | [#169](https://github.com/LJMoffat81/scot-land/pull/169) | Merged (`cd11f98`) |
| GBP-LIVE-V1c | Residential numerator, unit label, 3 significant figures (flag still default OFF) | [#171](https://github.com/LJMoffat81/scot-land/pull/171) | Merged (`02f2b14`) |
| MAP-CARDS-REDESIGN | Place card, Layers, legend redesign (+ ADDENDUM-1) | [#163](https://github.com/LJMoffat81/scot-land/pull/163) | Merged (`56d961c`) |
| QUEUE sync | Sync after #156/#161/#166–#168; tip #163/#169 | [#170](https://github.com/LJMoffat81/scot-land/pull/170) | Merged (`f294b78`) |
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
