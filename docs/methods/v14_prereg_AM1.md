# v1.4 prereg amendment AM-1: check 3 removed from the 2023 holdout gate
Date: 17 Oct 2026. Amends v1.4 prereg e1ab6d0a. Frozen BEFORE any 2023 holdout data is opened (no holdout run has scored; no lock exists).
Ruling: Project Lead D1/(A), 17 Oct 2026.

## Reason
O-P1 v2 (ee379ad6, Auditor-signed rule text) needs C_council at a 280 m2 reference plot per council. The only provenance-chosen source (9f150950, commuted-sums FINAL_CHECK_TABLE.csv; pin note 6a7988b7) covers 4 bodies (Angus, Perth & Kinross, Moray, Cairngorms NPA), is per plot not per 280 m2, and has no fixed area aggregation. Check 3 therefore cannot reach the O-P1 floor (>=1,000 DZ2011 zones) and would be NOT_RUN, a gating fail, making both_fail_publish_neither certain. No check 3 outcome or 2023 price was viewed in deciding this.

## Change
1. Check 3 is NOT a gating check for the 2023 holdout. The holdout publish decision uses the remaining gating checks exactly as in e1ab6d0a, unchanged (thresholds, order, estimators).
2. Check 3 is still computed/reported as a non-gating diagnostic: status NOT_RUN, reason "C_council: national source not pinned (AM-1)".
3. The holdout result is labelled in the run note, report and public methods page as "passed/failed on gating checks excluding check 3 (AM-1)", never as a full v1.4 pass.
4. Before any £ switch-on or 2024 run: a national C_council source is pinned on provenance, O-P1 check 3 is built and passes as a gating check. Tracked as AM-1-FOLLOWUP (next week). AM-1-FOLLOWUP check 3 is scored as a gating check in the score-once 2024 run, not by re-scoring the 2023 holdout. The 2023 lock and result are never re-run or revised. The national C_council source is chosen on provenance only (publisher, date, coverage, 280 m2 basis), with alternatives listed in its pin note. No candidate is compared on check 3 or holdout outcomes. Auditor accepts the pin before the 2024 manifest freezes.
5. Code: GATING_MARKS is made year-aware by spec AM1-GATE-1 (check 3 non-gating for 2023 only, gating for 2024); its merged sha enters the frozen set before the lock is written.
6. Nothing else in e1ab6d0a changes.

## Sign-off (required before the run)
- Methods Auditor/Statistician (ff0d3261): ____
- Project Lead: ruled (A), 17 Oct 2026
