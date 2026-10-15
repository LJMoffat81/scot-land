# Spec: DZ2022 empty-zone fill (one Cursor PR)

Status: ready to build. Signed off by Georgist 14 Oct 2026 (A, B, C and the bias test, with changes 1–3 below). Source notes: Valuation /workspace/scot-land-valuation/dz2022_fill/NOTES.md.
Everything stays publication_status=blocked, internal only, value_tier=proxy, tag model_fill_dz2022. No £ goes into any public route, page, JSON or GeoJSON. The publishability guard must pass unchanged; adding to it is fine.
Do not touch backend/api/main.py, AGENTS.md or the guard's existing rules. Pull the latest main first. Reuse one branch and delete it when the PR closes.

## Inputs
- 2011-zone rent table (zone_id, central, low, high, status). Its path is a setting; it is never committed. Tests use a small fixture.
- UPRN weights through the existing georgist/surface_dz2022.py loaders, with the default minimum-share rule (share under 1% AND fewer than 5 address points; 2,848 pairs dropped).
- The council for each zone from datazones.zone_spine.
- Urban-rural class: the Scottish Government 6-fold 2022 classification, from 'Urban Rural 6 Fold 2022 Lookup.csv' in the NRS Scottish Postcode Directory geography lookups (release 2026/2, OGL v3), joined onto the DZ2022 zones. The file path is a setting and tests use a fixture. Do not use the 8-fold version, which is for the map only.
- Neighbouring councils: commit data/reference/council_neighbours_2022.csv exactly as given in the appendix (60 pairs, all 32 councils; built by GIS by merging DZ2022 zones into councils using the NRS postcode index council, Crown copyright, OGL v3). Add a README with that provenance. The code must not work neighbours out at run time.
- Island rule (DECIDED, Georgist 14 Oct): Na h-Eileanan Siar (S12000013), Orkney (S12000023) and Shetland (S12000027) have no land neighbours, so they borrow from each other as one island group within the same urban-rural class, before any mainland borrowing.
- Final fallback (DECIDED, for every group, island or mainland): if a group still has fewer than 10 measured zones after its earlier steps, borrow from the same urban-rural class across all of Scotland. Zones filled this way get a band widened from that class's holdout errors and are labelled fully_estimated. Every zone is filled.
- Borrowing order for C (Methods v1.2). Mainland: own council and class, then a neighbouring council in the same class until class_min, then the same class Scotland-wide (no next urban-rural class). Islands: own council and class, then the island group in the same class, then the same class Scotland-wide. Record fill_step (which step filled the zone) on every C or B zone.

## Classification of 2022 zones (from address-point mass coming from empty 2011 zones)
- Not affected (empty share 0): pass through unchanged.
- A, empty share at most 50%: scale up from the measured part (rent per address point of the measured parts times the zone's total address points). Label partly_estimated, and widen the range by the empty share.
- B, empty share over 50%: model the empty part with method C and blend by address-point share. Label partly_estimated, or fully_estimated if under 5% is measured.
- C, fully empty: a council-by-urban-rural model on log land rent per dwelling, fitted on measured 2011 zones. When a group has fewer than 10 training zones, borrow from a neighbouring council in the same class (from the lookup), then Scotland-wide same class, and tag the zone borrowed_class with what was borrowed. Report low/central/high as P10/P50/P90 from the group's residual spread. Label fully_estimated.
- D, zero-dwelling source zones (3): rent 0 with label not_applicable under v0.7 rules. This is NOT an error and NOT a gap to fill. The #71 raise-an-error rule stays only for rent landing on a 2022 zone with no address points.

Every filled zone carries an estimate_label and a range. A council or Scotland roll-up is still refused if any zone lacks a label (existing rule).

## Holdout and bias test (pre-registered, run once)
- Before scoring, write the spec hash, script hash, input SHA-256s, seed, metrics and pass bands to run_log/dz2022_fill_runs.jsonl. The run guard refuses a second scored run unless an override reason is logged.
- Mask 20% of measured 2011 zones, stratified by council and urban-rural class and over-weighting the lowest pooled-sales decile. Use a fixed seed.
- Test C on the masked zones. Test A on synthetic partly empty zones made by masking parts and scaling up (Georgist change 2: A is bias-tested too).
- Metrics: median absolute log error; P10–P90 coverage (target 80% ±5); signed median log bias in the lowest-sales decile, which passes if its absolute value is under 0.10; council roll-ups within the stated range.
- If the test fails (decided in advance, Georgist change 3): widen the bands for the affected zone types using the holdout errors. Nothing is re-fitted, the borrowing rule is not switched and nothing is re-run. Record the widening in the run log. Labels and ranges stay.

## After the fill
- Rerun on the real output: the Scotland total is conserved from 2011 to 2022 (assert_scotland_total_conserved), and every 2022 zone has rent above 0 except not_applicable ones. That pass is the gate; figures stay blocked even then until Laurie approves the rules doc.

## Tests (CI, fixture data, exact money with no approx)
A small fixture covering each of the not-affected case, A, B (including the under-5% fully_estimated case), C (including borrowing from a neighbouring council, never another UR class), D and the label refusal. Also cover the run guard refusing a second scored run, the fail path widening bands without re-fitting, and the guard showing no £ leaks.

## Reconciled facts
- 723 suppressed, 4 not in the price file (S01007788, S01010462, S01010493, S01011598, all filled under C), and 3 zero-dwelling (including S01010206 and S01010226; all D, not_applicable).

## Appendix: council_neighbours_2022.csv
```
council_a,council_b,method
S12000005,S12000047,dz2022_dissolve_touch_1m
S12000005,S12000030,dz2022_dissolve_touch_1m
S12000005,S12000048,dz2022_dissolve_touch_1m
S12000006,S12000028,dz2022_dissolve_touch_1m
S12000006,S12000008,dz2022_dissolve_touch_1m
S12000006,S12000026,dz2022_dissolve_touch_1m
S12000006,S12000029,dz2022_dissolve_touch_1m
S12000008,S12000028,dz2022_dissolve_touch_1m
S12000008,S12000021,dz2022_dissolve_touch_1m
S12000008,S12000011,dz2022_dissolve_touch_1m
S12000008,S12000029,dz2022_dissolve_touch_1m
S12000010,S12000026,dz2022_dissolve_touch_1m
S12000010,S12000019,dz2022_dissolve_touch_1m
S12000010,S12000036,dz2022_dissolve_touch_1m
S12000011,S12000021,dz2022_dissolve_touch_1m
S12000011,S12000038,dz2022_dissolve_touch_1m
S12000011,S12000049,dz2022_dissolve_touch_1m
S12000011,S12000029,dz2022_dissolve_touch_1m
S12000014,S12000050,dz2022_dissolve_touch_1m
S12000014,S12000040,dz2022_dissolve_touch_1m
S12000014,S12000030,dz2022_dissolve_touch_1m
S12000017,S12000035,dz2022_dissolve_touch_1m
S12000017,S12000048,dz2022_dissolve_touch_1m
S12000017,S12000034,dz2022_dissolve_touch_1m
S12000017,S12000020,dz2022_dissolve_touch_1m
S12000018,S12000021,dz2022_dissolve_touch_1m
S12000018,S12000038,dz2022_dissolve_touch_1m
S12000019,S12000026,dz2022_dissolve_touch_1m
S12000019,S12000036,dz2022_dissolve_touch_1m
S12000020,S12000034,dz2022_dissolve_touch_1m
S12000021,S12000028,dz2022_dissolve_touch_1m
S12000021,S12000038,dz2022_dissolve_touch_1m
S12000026,S12000029,dz2022_dissolve_touch_1m
S12000026,S12000040,dz2022_dissolve_touch_1m
S12000026,S12000036,dz2022_dissolve_touch_1m
S12000029,S12000049,dz2022_dissolve_touch_1m
S12000029,S12000050,dz2022_dissolve_touch_1m
S12000029,S12000040,dz2022_dissolve_touch_1m
S12000030,S12000050,dz2022_dissolve_touch_1m
S12000030,S12000045,dz2022_dissolve_touch_1m
S12000030,S12000039,dz2022_dissolve_touch_1m
S12000030,S12000035,dz2022_dissolve_touch_1m
S12000030,S12000048,dz2022_dissolve_touch_1m
S12000033,S12000034,dz2022_dissolve_touch_1m
S12000034,S12000048,dz2022_dissolve_touch_1m
S12000034,S12000041,dz2022_dissolve_touch_1m
S12000035,S12000039,dz2022_dissolve_touch_1m
S12000035,S12000048,dz2022_dissolve_touch_1m
S12000036,S12000040,dz2022_dissolve_touch_1m
S12000038,S12000049,dz2022_dissolve_touch_1m
S12000039,S12000049,dz2022_dissolve_touch_1m
S12000039,S12000045,dz2022_dissolve_touch_1m
S12000040,S12000050,dz2022_dissolve_touch_1m
S12000041,S12000042,dz2022_dissolve_touch_1m
S12000041,S12000048,dz2022_dissolve_touch_1m
S12000042,S12000048,dz2022_dissolve_touch_1m
S12000045,S12000049,dz2022_dissolve_touch_1m
S12000045,S12000050,dz2022_dissolve_touch_1m
S12000047,S12000048,dz2022_dissolve_touch_1m
S12000049,S12000050,dz2022_dissolve_touch_1m
```
