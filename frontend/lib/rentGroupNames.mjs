/**
 * Public value/rent group headings (AGENTS.md Pre-review checklist).
 * Single runtime export — imported by TS UI modules and the prereview test.
 */
export const RENT_GROUP_NAMES = Object.freeze([
  "Land",
  "Natural resource rents",
  "Services of nature",
]);

/** Keyed access for land / resources / nature buckets. */
export const RENT_GROUP_NAME = Object.freeze({
  land: RENT_GROUP_NAMES[0],
  resources: RENT_GROUP_NAMES[1],
  nature: RENT_GROUP_NAMES[2],
});
