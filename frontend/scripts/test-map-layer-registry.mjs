/**
 * MAP-CARDS addendum A1 — every registry layer has minzoom, maxzoom, group.
 * Also locks live switch ids and banned row-name tokens.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const {
  MAP_LAYER_REGISTRY,
  MAP_LAYER_GROUP_ORDER,
  assertRegistryZoomAndGroup,
  resolveMapLayerId,
  mapLayerGroupLabel,
  buildInlineLegendFromRegistry,
  defaultOnLayerIds,
} = await import(
  pathToFileURL(join(frontendRoot, "lib/mapLayerRegistry.ts")).href
);
const { RENT_GROUP_NAME } = await import(
  pathToFileURL(join(frontendRoot, "lib/rentGroupNames.mjs")).href
);
const { DZ2022_EXTRACTION_YEAR, dz2022CopyrightLine } = await import(
  pathToFileURL(join(frontendRoot, "lib/dzAttribution.mjs")).href
);

assertRegistryZoomAndGroup();
for (const entry of MAP_LAYER_REGISTRY) {
  assert.equal(typeof entry.minzoom, "number");
  assert.equal(typeof entry.maxzoom, "number");
  assert.ok(entry.group && String(entry.group).trim());
  assert.ok(entry.sourceCaption && entry.sourceCaption.trim());
  assert.ok(Array.isArray(entry.classes));
}

assert.equal(mapLayerGroupLabel("land"), RENT_GROUP_NAME.land);
assert.equal(mapLayerGroupLabel("resources"), RENT_GROUP_NAME.resources);
assert.equal(mapLayerGroupLabel("nature"), RENT_GROUP_NAME.nature);
assert.equal(mapLayerGroupLabel("places"), "Places and boundaries");

const liveIds = MAP_LAYER_REGISTRY.map((e) => e.id);
assert.deepEqual(liveIds, [
  "1",
  "access_services",
  "vdl",
  "hla",
  "3",
  "4",
  "9",
  "8",
  "designations",
  "flood",
  "crofting",
  "councils",
  "data_zones",
]);

assert.equal(resolveMapLayerId("agr"), "1");
assert.equal(resolveMapLayerId("1"), "1");
assert.deepEqual(defaultOnLayerIds(), ["councils"]);

const removed = [
  "1a",
  "2",
  "5",
  "6",
  "7",
  "10",
  "lca",
  "builtup_mask",
  "settlements",
  "localities",
  "boundaries",
];
for (const id of removed) {
  assert.equal(
    MAP_LAYER_REGISTRY.find((e) => e.id === id),
    undefined,
    `${id} must not be a live Layers switch`,
  );
}

const banned = [
  "SSSI",
  "best permitted use",
  "licence rent",
  "unpriced",
  "mask",
  "constraint",
  "natural capital",
  "ledger",
  "headline",
  "DZ",
  "IZ",
  "People per km²",
];
for (const entry of MAP_LAYER_REGISTRY) {
  for (const token of banned) {
    assert.ok(
      !entry.label.includes(token),
      `banned token "${token}" in label for ${entry.id}`,
    );
  }
}

assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "1")?.label,
  "Annual Ground Rent",
);
assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "designations")?.label,
  "Protected nature sites",
);
assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "data_zones")?.label,
  "Neighbourhood lines",
);
assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "councils")?.label,
  "Council areas",
);

// Four accordion groups; every live id maps to one of them.
assert.deepEqual([...MAP_LAYER_GROUP_ORDER], [
  "land",
  "resources",
  "nature",
  "places",
]);
for (const entry of MAP_LAYER_REGISTRY) {
  assert.ok(MAP_LAYER_GROUP_ORDER.includes(entry.group));
}

// A5 — legend built from registry classes / caption.
const agr = MAP_LAYER_REGISTRY.find((e) => e.id === "1");
const legend = buildInlineLegendFromRegistry(agr, { mapZoom: 10 });
assert.equal(legend.zoomGated, false);
assert.equal(legend.rampScale, "Lower → Higher");
assert.ok(legend.classes.some((c) => c.label === "Striped = less sure"));
assert.ok(legend.classes.some((c) => c.label === "No figure here"));
assert.equal(legend.sourceCaption, agr.sourceCaption);
const gated = buildInlineLegendFromRegistry(agr, { mapZoom: 3 });
assert.equal(gated.zoomGated, true);
assert.equal(gated.zoomHint, "Zoom in to see this layer");

const dzJson = JSON.parse(
  readFileSync(join(frontendRoot, "lib/dz2022Attribution.json"), "utf8"),
);
assert.equal(DZ2022_EXTRACTION_YEAR, dzJson.extraction_year);
assert.equal(
  dz2022CopyrightLine(),
  `Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right ${dzJson.extraction_year}.`,
);

console.log("test-map-layer-registry: ok");
