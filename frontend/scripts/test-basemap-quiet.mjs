/**
 * Basemap quiet rule — residential land-use stays hidden, buildings
 * return at zoom 16, and every other style layer is left alone.
 */
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const {
  BASEMAP_BUILDING_MIN_ZOOM,
  applyBasemapQuiet,
  basemapQuietVisibility,
} = await import(pathToFileURL(join(frontendRoot, "lib/mapBasemap.ts")).href);

assert.equal(BASEMAP_BUILDING_MIN_ZOOM, 16);

const residential = { id: "landuse_residential", "source-layer": "landuse" };
assert.equal(basemapQuietVisibility(residential, 5), "none");
assert.equal(basemapQuietVisibility(residential, 16), "none");
assert.equal(basemapQuietVisibility(residential, 18), "none");
assert.equal(
  basemapQuietVisibility({ id: "landuse_residential" }, 4),
  "none",
);
assert.equal(
  basemapQuietVisibility(
    { id: "landuse_residential_pattern", "source-layer": "landuse" },
    12,
  ),
  "none",
);

for (const id of [
  "landuse_school",
  "landuse_pitch",
  "landuse_park",
  "landuse_cemetery",
  "landuse_hospital",
  "landuse_track",
]) {
  assert.equal(
    basemapQuietVisibility({ id, "source-layer": "landuse" }, 8),
    "leave",
    id,
  );
}

assert.equal(
  basemapQuietVisibility(
    { id: "poi_residential", "source-layer": "poi" },
    10,
  ),
  "leave",
);
assert.equal(
  basemapQuietVisibility({ id: "road_primary", "source-layer": "transportation" }, 14),
  "leave",
);

const building = { id: "building", "source-layer": "building" };
assert.equal(basemapQuietVisibility(building, 0), "none");
assert.equal(basemapQuietVisibility(building, 15.9), "none");
assert.equal(basemapQuietVisibility(building, 16), "visible");
assert.equal(basemapQuietVisibility(building, 17), "visible");
assert.equal(basemapQuietVisibility(building, Number.NaN), "none");
assert.equal(
  basemapQuietVisibility({ id: "building-3d", "source-layer": "building" }, 15),
  "none",
);
assert.equal(
  basemapQuietVisibility({ id: "building-3d", "source-layer": "building" }, 16),
  "visible",
);
assert.equal(
  basemapQuietVisibility({ id: "housenumber", "source-layer": "building" }, 10),
  "none",
);
assert.equal(
  basemapQuietVisibility({ id: "housenumber", "source-layer": "building" }, 16),
  "visible",
);

const layers = [
  { id: "background" },
  { id: "landuse_school", "source-layer": "landuse" },
  residential,
  building,
  { id: "building-3d", "source-layer": "building" },
  { id: "council-line" },
];
const visibility = new Map(layers.map((layer) => [layer.id, "visible"]));
const writes = [];
const fake = {
  getStyle: () => ({ layers }),
  getZoom: () => 6,
  getLayer: (id) => (visibility.has(id) ? { id } : undefined),
  getLayoutProperty: (id) => visibility.get(id),
  setLayoutProperty: (id, _name, value) => {
    writes.push([id, value]);
    visibility.set(id, value);
  },
};

applyBasemapQuiet(fake);
assert.deepEqual(writes, [
  ["landuse_residential", "none"],
  ["building", "none"],
  ["building-3d", "none"],
]);
assert.equal(visibility.get("landuse_school"), "visible");
assert.equal(visibility.get("council-line"), "visible");
assert.equal(visibility.get("background"), "visible");

writes.length = 0;
fake.getZoom = () => 16;
applyBasemapQuiet(fake);
assert.deepEqual(writes, [
  ["building", "visible"],
  ["building-3d", "visible"],
]);
assert.equal(visibility.get("landuse_residential"), "none");

writes.length = 0;
applyBasemapQuiet(fake);
assert.deepEqual(writes, []);

fake.getStyle = () => {
  throw new Error("Style is not done loading");
};
assert.doesNotThrow(() => applyBasemapQuiet(fake));

console.log("test-basemap-quiet: ok");
