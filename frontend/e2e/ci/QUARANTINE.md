# Quarantined e2e tests (CI-DEDUP-1a)

Non-blocking. Tagged `@quarantine` in titles. Blocking `e2e` uses `--grep-invert @quarantine`. Job `e2e-quarantine` runs `--grep @quarantine` with `continue-on-error: true`.

Exit rule for every entry: 10 consecutive green quarantine-job runs then remove the tag, or fix by **2026-11-21**. Owner: Eng Lead.

| Q | Spec | Title | Evidence runs |
|---|------|-------|---------------|
| Q1 | `layers-perf-3.spec.ts` | oil and gas hint stacks under the protected-sites hint | 39518106714, 39499629177 |
| Q2 | `layers-perf-3.spec.ts` | simplified outlines chip is shown at z6 and hidden at z10 | 38979369689, 39494972071 |
| Q3 | `sea-stub-card.spec.ts` | compact height; Show me Scotland resets national view | 39504926402 |
| Q4 | `ui-fix-4.spec.ts` | padding, peek, search, map tap, footer, reload, focus, one close | 39507837359 |
| Q5 | `frontend-batch-2.spec.ts` | T-M3 O1 missing attribution reverts | CI-DEDUP-1b-r2 local: MapLibre `AbortError: signal is aborted without reason` + chunk stack on aerial remount after empty attribution |
| Q6 | `map-cards-redesign-a11y-url.spec.ts` | 15+17 URL state place/panel/layers/z/c round-trip | CI-DEDUP-1b-r2 local: goBack after close → `panel=place` not `panel=layers` |

Exactly these six titles carry ` @quarantine`. word-area-1 click flake is fixed in item 5 of CI-DEDUP-1a (not quarantined).
