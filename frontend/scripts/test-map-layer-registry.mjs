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
assert.equal(mapLayerGroupLabel("tenure"), "Who holds the land");
assert.equal(mapLayerGroupLabel("resources"), RENT_GROUP_NAME.resources);
assert.equal(mapLayerGroupLabel("nature"), RENT_GROUP_NAME.nature);
assert.equal(mapLayerGroupLabel("places"), "Places and boundaries");

const liveIds = MAP_LAYER_REGISTRY.map((e) => e.id);
assert.deepEqual(liveIds, [
  "1",
  "access_services",
  "flood",
  "vdl",
  // PLANNING-PUBLISH-1 PR-B
  "hls-open",
  "ldp-highland",
  "grid3",
  "contaminated_land",
  "3",
  "4",
  "9",
  "8",
  "designations",
  "crofting",
  "who_holds",
  "idle_land",
  "councils",
  "data_zones",
  "deprivation",
  "conservation",
  "listed",
  "stops",
  "green_belt",
  "school_catchments",
]);
// LAYERS-ADD-1a: legacy hla / ldp ids are not live switches (the planning rows are
// the manifest-only hls-open / ldp-highland, PLANNING-PUBLISH-1).
assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "hla"),
  undefined,
  "hla must not be a live Layers switch (LAYER_HLS_ENABLED default OFF)",
);
assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "ldp"),
  undefined,
  "ldp must not be a live Layers switch",
);

assert.equal(resolveMapLayerId("agr"), "1");
assert.equal(resolveMapLayerId("1"), "1");
assert.deepEqual(defaultOnLayerIds(), ["data_zones"]);

const removed = [
  "1a",
  "2",
  "5",
  "6",
  "7",
  "10",
  "lca",
  "hla",
  "ldp",
  "ldp_allocations",
  "hls",
  "sepa_frm_maps",
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
  "Neighbourhood",
  "neighbourhood",
  "Neighborhood",
  "neighborhood",
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
  "Local areas (data zones)",
);
assert.notEqual(
  MAP_LAYER_REGISTRY.find((e) => e.id === "data_zones")?.label,
  "Area boundaries",
);
assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "councils")?.label,
  "Council areas",
);
assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "flood")?.label,
  "Flood risk (SEPA)",
);
assert.equal(
  MAP_LAYER_REGISTRY.find((e) => e.id === "flood")?.group,
  "land",
);
assert.ok(
  MAP_LAYER_REGISTRY.every((e) => e.defaultOn !== true || e.id === "data_zones"),
);

// Five accordion groups; every live id maps to one of them.
assert.deepEqual([...MAP_LAYER_GROUP_ORDER], [
  "land",
  "tenure",
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
assert.equal(legend.zoomOut, true);
assert.equal(legend.zoomOutHint, "Zoom out to see this layer");
const agrOverview = buildInlineLegendFromRegistry(agr, { mapZoom: 6 });
assert.equal(agrOverview.zoomOut, false);
const grid = MAP_LAYER_REGISTRY.find((e) => e.id === "grid3");
assert.equal(
  buildInlineLegendFromRegistry(grid, { mapZoom: 12 }).zoomHint,
  "Zoom in to see the grid",
);
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

assert.equal(
  MAP_LAYER_REGISTRY.filter((entry) => entry.paintPending).length,
  0,
  "paintPending rows must be painted or left off the live list",
);

const { visitorLayersAddRows, LAYERS_ADD_REGISTRY, LAYERS_ADD_WAITING } =
  await import(pathToFileURL(join(frontendRoot, "lib/layersAddRegistry.ts")).href);
const absent = visitorLayersAddRows().map((row) => row.id);
for (const id of ["vdl", "green_belt", "school_catchments", "contaminated_land"]) {
  assert.equal(absent.includes(id), false, `${id} hidden when extract absent`);
}
assert.equal(
  LAYERS_ADD_REGISTRY.find((row) => row.id === "flood")?.layerId,
  "sepa_nfra_grid",
);
const present = visitorLayersAddRows({
  spatialHubPresent: {
    vdl: true,
    green_belt: true,
    school_catchments: true,
    contaminated_land: true,
  },
}).map((row) => row.id);
assert.equal(present.includes("green_belt"), true);

const roadmap = readFileSync(join(frontendRoot, "app/roadmap/page.tsx"), "utf8");
assert.match(roadmap, /LAYERS_ADD_WAITING/);
assert.equal(
  roadmap.includes('id: "ldp"'),
  false,
  "roadmap LDP/HLS come from LAYERS_ADD_WAITING",
);
// PLANNING-PUBLISH-1 PR-B: hls is on the map (hls-open); ldp stays (Highland only).
assert.equal(LAYERS_ADD_WAITING.map((row) => row.id).join(","), "ldp");

const mapSrc = readFileSync(
  join(frontendRoot, "components/ScotlandMap.tsx"),
  "utf8",
);
assert.match(mapSrc, /sepa_nfra_grid/);
assert.match(mapSrc, /syncLayersAddPaint/);

// CLEANUP-318 G6 — charter v2 §4 rule 1: pure context layers sit under "Places".
// Source of truth: backend registry YAMLs tagged `shows: context`.
{
  const { readdirSync } = await import("node:fs");
  const { REGISTRY_TILESETS_BY_DRAWER_ID } = await import(
    pathToFileURL(join(frontendRoot, "lib/mapLayerRegistry.ts")).href
  );
  const registryDir = join(frontendRoot, "..", "backend", "layers", "registry");
  const contextTilesets = readdirSync(registryDir)
    .filter((name) => name.endsWith(".yaml"))
    .map((name) => readFileSync(join(registryDir, name), "utf8"))
    .filter((text) => /^shows:\s*context\s*$/m.test(text))
    .map((text) => /^id:\s*(\S+)\s*$/m.exec(text)?.[1])
    .sort();
  // Parser sanity: must see the signed context set (cap 6), or the guard is blind.
  assert.deepEqual(contextTilesets, [
    "councils",
    "dz2011",
    "dz2022",
    "scotland-extent",
    "sepa-flood",
    "settlements-2022",
  ]);
  const contextSet = new Set(contextTilesets);
  // Context tilesets with no Layers row, and why (a new one must be placed or listed).
  const NO_DRAWER_ROW = {
    "scotland-extent": "permanent land-and-waters outline (TILE_BASE_OUTLINE_ID)",
    "settlements-2022": "built-up mask input only",
    "sepa-flood": "gated extent overlay; the flood row paints sepa_nfra_grid",
    dz2011: "estimate-status switch, rendered inside the Places section",
  };
  const drawerSrc = readFileSync(
    join(frontendRoot, "components/MapLayersDrawer.tsx"),
    "utf8",
  );
  const limitsIds = [
    ...(/LIMITS_ON_USE_LAYER_IDS = \[([^\]]*)\]/.exec(drawerSrc)?.[1] ?? "").matchAll(
      /"([^"]+)"/g,
    ),
  ].map((m) => m[1]);
  assert.ok(limitsIds.length > 0, "G6: LIMITS_ON_USE_LAYER_IDS not found");
  const placed = new Set();
  for (const entry of MAP_LAYER_REGISTRY) {
    const keys = [
      entry.id,
      ...(entry.aliases ?? []),
      ...(REGISTRY_TILESETS_BY_DRAWER_ID[entry.id] ?? []),
    ];
    const paintsContext = (entry.paintLayerIds ?? []).some((pid) =>
      contextTilesets.some((ctx) => pid.startsWith(`tile-${ctx}-`)),
    );
    const hits = keys.filter((k) => contextSet.has(k));
    if (hits.length === 0 && !paintsContext) continue;
    assert.equal(
      entry.group,
      "places",
      `G6: context layer row ${entry.id} must sit under Places, not ${entry.group}`,
    );
    assert.equal(
      limitsIds.includes(entry.id),
      false,
      `G6: context layer row ${entry.id} must not be in Limits on use`,
    );
    for (const k of hits) placed.add(k);
  }
  const placesAt = drawerSrc.indexOf('data-testid="layers-nav-places"');
  const dzStatusAt = drawerSrc.indexOf("layer-toggle-${DZ_STATUS_LAYER_ID}");
  const footerAt = drawerSrc.indexOf('className="layers-panel-footer"');
  assert.ok(
    placesAt > 0 && dzStatusAt > placesAt && dzStatusAt < footerAt,
    "G6: dz2011 status switch must render inside the Places section",
  );
  for (const ctx of contextTilesets) {
    assert.ok(
      placed.has(ctx) || ctx in NO_DRAWER_ROW,
      `G6: context layer ${ctx} has no Places row and no NO_DRAWER_ROW reason`,
    );
    assert.equal(
      placed.has(ctx) && ctx in NO_DRAWER_ROW,
      false,
      `G6: context layer ${ctx} is both placed and listed as rowless`,
    );
  }
}

console.log("test-map-layer-registry: ok");
