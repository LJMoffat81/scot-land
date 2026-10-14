/**
 * Pre-review checklist — rent/value group names come from RENT_GROUP_NAMES only.
 * Asserts against the exported constant (not by scanning source for return "Land").
 */
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

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
}

console.log("test-prereview-rent-groups: ok");
