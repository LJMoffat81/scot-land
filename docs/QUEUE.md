# Work queue

Plain-English queue for maintainers (Laurie and agents). Update this file in each PR you open, or when queue order changes — piggyback on a real change; never open a PR just for `QUEUE.md`.

**Cap:** ≤5 open non-draft PRs; one PR per item ID. Right now: 0 open non-draft; [#139](https://github.com/LJMoffat81/scot-land/pull/139) (SW-036 v2) and [#140](https://github.com/LJMoffat81/scot-land/pull/140) (NEIGHBOURS-2022) are draft.

## In progress

| Item | Description | PR | Status |
|------|-------------|----|--------|
| NEIGHBOURS-2022 | Council neighbours CSV at `data/reference/council_neighbours_2022.csv` (reason column + invariants test; one-way `a < b`) | [#140](https://github.com/LJMoffat81/scot-land/pull/140) | Draft — path sealed to `data/reference/` |
| SW-036 v2 | Desktop layout (≥1024): place card left, Layers right, legend pill below the card | [#139](https://github.com/LJMoffat81/scot-land/pull/139) | Draft |

## Next up (in order)

| Item | Description | PR | Status |
|------|-------------|----|--------|
| FILL-POOLED | DZ2011/DZ2022 empty-zone fill on pooled inputs (reads neighbours CSV) | — | Parallel backend track; after NEIGHBOURS-2022 merges; one PR only |
| SW-045 | Legend follows the active layer (HIGH — Laurie-flagged); diagnose first | — | After SW-036; no PR yet; one PR only |
| SW-044 | Slim the map view (licences out of left panel, chip key once, etc.) | — | After SW-045; no PR yet; one PR only |

### Frozen backlog

| Item | Description | PR | Status |
|------|-------------|----|--------|
| SW-033 / SW-034 + ideas 37 / 38 / 40 / 41 / 44 | Polish batch: developers/api titles + scroll, mobile `/data` cards, place-card IZ title, catalogue notes, related small fixes | — | Frozen; open only when cap allows; after the Next-up train |
| SW-039 + idea 45 | “Why no outline?” becomes a proper tap target; answer opens inline | — | Frozen; after polish batch (or when scheduled) |
| Suggestion 44 | Deploy SHA / git commit surface; park with SW-037 if it needs `main.py` | — | Parked with SW-037 (next `main.py` change) |
| UX-00 … UX-05 | Mobile hit areas, legend aria, Esc focus, landmarks, place-card hug, desktop search | [#130](https://github.com/LJMoffat81/scot-land/pull/130) … [#136](https://github.com/LJMoffat81/scot-land/pull/136) | UX train done — all merged (incl. UX-00 #130 and UX10-1 #134) |
| SW-031 / SW-032 | Scrub banned wording and public money figures from public surfaces | [#133](https://github.com/LJMoffat81/scot-land/pull/133) | Merged |

## Recently merged

Newest first.

| Item | Description | PR | Status |
|------|-------------|----|--------|
| SW/UX e2e auto-discovery | Playwright CI auto-discovers specs under `e2e/ci/` | [#138](https://github.com/LJMoffat81/scot-land/pull/138) | Merged |
| UX-01 | Mobile tap targets ≥44×44 | [#136](https://github.com/LJMoffat81/scot-land/pull/136) | Merged |
| UX10-1 | Place card skeleton + FP1 schema | [#134](https://github.com/LJMoffat81/scot-land/pull/134) | Merged |
| UX-04 | Unique landmarks and button accessible names | [#132](https://github.com/LJMoffat81/scot-land/pull/132) | Merged |
| UX-02 | Legend fold `aria-expanded` tracks body visibility | [#131](https://github.com/LJMoffat81/scot-land/pull/131) | Merged |
| UX-05 | “No place matched” card hugs content | [#129](https://github.com/LJMoffat81/scot-land/pull/129) | Merged |
| UX-03 | Esc returns focus to Layers / nav toggle | [#128](https://github.com/LJMoffat81/scot-land/pull/128) | Merged |
| SW-038 | Deploy swaps api/frontend only — never touch cloudflared | [#137](https://github.com/LJMoffat81/scot-land/pull/137) | Merged |
| SW-026 | Research banner clears open place card | [#123](https://github.com/LJMoffat81/scot-land/pull/123) | Merged |
