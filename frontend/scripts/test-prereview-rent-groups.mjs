/**
 * Pre-review checklist — rent/value group names come from RENT_GROUP_NAMES only.
 * Asserts against the exported constant (not by scanning source for return "Land").
 * SW-021 (additive): ban Surface / Resource / Nature as visible group headings.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const repoRoot = join(frontendRoot, "..");

/** Banned as visible rent/value group headings only (additive — never loosen). */
const BANNED_GROUP_HEADINGS = Object.freeze(["Surface", "Resource", "Nature"]);

const { RENT_GROUP_NAMES, RENT_GROUP_NAME } = await import(
  pathToFileURL(join(frontendRoot, "lib/rentGroupNames.mjs")).href,
);
const { defaultAgrGroupRows } = await import(
  pathToFileURL(join(frontendRoot, "lib/rentGroupAgrRows.mjs")).href,
);
const { mapLayerGroupLabel } = await import(
  pathToFileURL(join(frontendRoot, "lib/mapLayerGroups.ts")).href,
);
const { dataSourceGroupLabel } = await import(
  pathToFileURL(join(frontendRoot, "lib/dataSourceGroups.ts")).href,
);
assert.deepEqual(
  [...RENT_GROUP_NAMES],
  ["Land", "Natural resource rents", "Services of nature"],
);
assert.equal(RENT_GROUP_NAME.land, RENT_GROUP_NAMES[0]);
assert.equal(RENT_GROUP_NAME.resources, RENT_GROUP_NAMES[1]);
assert.equal(RENT_GROUP_NAME.nature, RENT_GROUP_NAMES[2]);

assert.equal(mapLayerGroupLabel("land"), RENT_GROUP_NAME.land);
assert.equal(mapLayerGroupLabel("resources"), RENT_GROUP_NAME.resources);
assert.equal(mapLayerGroupLabel("nature"), RENT_GROUP_NAME.nature);

assert.equal(dataSourceGroupLabel("land"), RENT_GROUP_NAME.land);
assert.equal(dataSourceGroupLabel("resources"), RENT_GROUP_NAME.resources);
assert.equal(dataSourceGroupLabel("nature"), RENT_GROUP_NAME.nature);

const agrLabels = defaultAgrGroupRows().map((row) => row.label);
assert.deepEqual(agrLabels, [...RENT_GROUP_NAMES]);
for (const label of agrLabels) {
  assert.ok(
    RENT_GROUP_NAMES.includes(label),
    `unexpected rent group label: ${label}`,
  );
  assert.ok(
    !BANNED_GROUP_HEADINGS.includes(label),
    `banned group heading used as agr label: ${label}`,
  );
}

for (const bad of BANNED_GROUP_HEADINGS) {
  assert.notEqual(mapLayerGroupLabel("land"), bad);
  assert.notEqual(mapLayerGroupLabel("resources"), bad);
  assert.notEqual(mapLayerGroupLabel("nature"), bad);
  assert.notEqual(dataSourceGroupLabel("land"), bad);
  assert.notEqual(dataSourceGroupLabel("resources"), bad);
  assert.notEqual(dataSourceGroupLabel("nature"), bad);
}

// LayersPanel catalog groupLabel must use RENT_GROUP_NAME (source scan — no @/ import).
const layerCatalogSrc = readFileSync(
  join(frontendRoot, "lib/layerCatalog.ts"),
  "utf8",
);
assert.match(layerCatalogSrc, /RENT_GROUP_NAME/);
assert.match(
  layerCatalogSrc,
  /case "resources":\s*return RENT_GROUP_NAME\.resources/,
);
assert.match(
  layerCatalogSrc,
  /case "nature":\s*return RENT_GROUP_NAME\.nature/,
);
assert.doesNotMatch(layerCatalogSrc, /return "Resources"/);
assert.doesNotMatch(layerCatalogSrc, /return "Nature"/);
assert.doesNotMatch(layerCatalogSrc, /return "Surface"/);
assert.doesNotMatch(layerCatalogSrc, /return "Resource"/);

// Shared place card remaps legacy API labels by id (source contract — no @/ import).
const placeCardLibForRemap = readFileSync(
  join(frontendRoot, "lib/placeCard.ts"),
  "utf8",
);
assert.match(placeCardLibForRemap, /AGR_ROW_LABEL_BY_ID/);
assert.match(
  placeCardLibForRemap,
  /surface:\s*RENT_GROUP_NAME\.land/,
);
assert.match(
  placeCardLibForRemap,
  /resource:\s*RENT_GROUP_NAME\.resources/,
);
assert.match(
  placeCardLibForRemap,
  /nature:\s*RENT_GROUP_NAME\.nature/,
);
assert.match(
  placeCardLibForRemap,
  /AGR_ROW_LABEL_BY_ID\[row\.id\]\s*\?\?/,
);
assert.match(
  placeCardLibForRemap,
  /AGR_ROW_LABEL_BY_LEGACY\[row\.label\]\s*\?\?/,
);
assert.match(placeCardLibForRemap, /label:\s*approved,/);

// Platform place-card API source must emit approved headings (not Surface/Resource/Nature).
const platformSrc = readFileSync(
  join(repoRoot, "backend/layers/platform.py"),
  "utf8",
);
for (const bad of BANNED_GROUP_HEADINGS) {
  assert.doesNotMatch(
    platformSrc,
    new RegExp(`"label":\\s*"${bad}"`),
    `platform.py must not emit group heading label "${bad}"`,
  );
}
assert.match(platformSrc, /"label": _RENT_GROUP_LABELS\["surface"\]/);
assert.match(platformSrc, /"Land"/);
assert.match(platformSrc, /"Natural resource rents"/);
assert.match(platformSrc, /"Services of nature"/);

// Place card UI: Map reference + figure Why? (SW-021 wording).
const placeCardUi = readFileSync(
  join(frontendRoot, "components/PlaceCard.tsx"),
  "utf8",
);
assert.match(placeCardUi, /PLACE_CARD_MAP_REFERENCE_LABEL/);
assert.match(placeCardUi, /PLACE_CARD_FIGURE_WHY/);
assert.doesNotMatch(placeCardUi, />Square reference</);
assert.match(placeCardUi, /place-card-figure-why/);

assert.match(
  placeCardLibForRemap,
  /PLACE_CARD_FIGURE_WHY\s*=\s*"Figures will appear once the valuation rules are signed off\."/,
);
assert.match(
  placeCardLibForRemap,
  /PLACE_CARD_MAP_REFERENCE_LABEL\s*=\s*"Map reference"/,
);
assert.match(
  placeCardLibForRemap,
  /PLACE_CARD_LIMITS_HEADING\s*=\s*"Limits"/,
);
assert.doesNotMatch(
  placeCardLibForRemap,
  /PLACE_CARD_LIMITS_HEADING\s*=\s*"What limits how it's used"/,
);
// Defence in depth: legacy Surface/Resource/Nature labels remapped by text too.
assert.match(placeCardLibForRemap, /AGR_ROW_LABEL_BY_LEGACY/);
assert.match(placeCardLibForRemap, /Surface:\s*RENT_GROUP_NAME\.land/);
assert.match(placeCardLibForRemap, /Resource:\s*RENT_GROUP_NAME\.resources/);
assert.match(placeCardLibForRemap, /Nature:\s*RENT_GROUP_NAME\.nature/);

console.log("test-prereview-rent-groups: ok");
