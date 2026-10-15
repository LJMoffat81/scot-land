/**
 * Public “what the checks mean” lines for /developers/checks.
 * Ids must stay exactly LEDGER_CHECK_ORDER (enforced by test-check-meanings).
 */
export const CHECK_MEANINGS = {
  "C-hectare": "Each hectare is counted once.",
  "C-turbine":
    "Wind turbine sites are counted once and only where they stand.",
  "C-aqua": "Fish farm sites are counted once and only at sea.",
  "C-mineral": "Mineral sites are counted once.",
  "C-forest": "Woodland is counted once.",
  "C-planning":
    "Planning allocations change best use but add no value on their own.",
  "C-overlay": "Limits on use change best use and add no value.",
  "C-overlap": "Where layers overlap, the land is not counted twice.",
  "C-totals":
    "Totals are added up per label only, never across labels or price years.",
  "C-cap": "The yield used stays inside its agreed cap.",
} as const;

export type CheckMeaningId = keyof typeof CHECK_MEANINGS;

export function checkMeaning(id: CheckMeaningId): string {
  return CHECK_MEANINGS[id];
}
