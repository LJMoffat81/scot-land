# Quarantined e2e tests (CI-DEDUP-1a)

Non-blocking. Tagged `@quarantine` in titles. Blocking `e2e` uses `--grep-invert @quarantine`. Job `e2e-quarantine` runs `--grep @quarantine` with `continue-on-error: true`.

Exit rule for every entry: 10 consecutive green quarantine-job runs then remove the tag, or fix by **2026-11-21**. Owner: Eng Lead.

| Q | Spec | Title | Evidence runs |
|---|------|-------|---------------|
| Q1 | `layers-perf-3.spec.ts` | oil and gas hint stacks under the protected-sites hint | 39518106714, 39499629177 |
| Q2 | `layers-perf-3.spec.ts` | simplified outlines chip is shown at z6 and hidden at z10 | 38979369689, 39494972071 |
| Q3 | `sea-stub-card.spec.ts` | compact height; Show me Scotland resets national view | 39504926402 |
| Q4 | `ui-fix-4.spec.ts` | padding, peek, search, map tap, footer, reload, focus, one close | 39507837359 |

Exactly these four titles carry ` @quarantine`. word-area-1 click flake is fixed in item 5 (not quarantined).
