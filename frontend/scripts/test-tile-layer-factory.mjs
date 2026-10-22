/**
 * ARCH-2b TF-1..TF-8 — tileLayerFactory + ScotlandMap grep pins.
 * Run: npm run test:tile-layer-factory
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const mod = await import(
  pathToFileURL(join(frontendRoot, "lib/tileLayerFactory.ts")).href
);
const {
  parseTileManifest,
  parseTileManifestText,
  buildTileLayers,
  applyMeasureValues,
  TILE_WANTED_IDS,
  TileManifestError,
} = mod;

const VERSION = "2026-10-22.d28ecc72";

function goodEntry(over = {}) {
  return {
    layer: "dz2022",
    version: VERSION,
    minzoom: 0,
    maxzoom: 14,
    geometry: "polygon",
    style: {
      fill: {
        "fill-color": "#c6dbef",
        "fill-opacity": [
          "interpolate",
          ["linear"],
          ["zoom"],
          4.5,
          0,
          5,
          0.55,
          14,
          0.55,
          15,
          0.4,
        ],
      },
      line: {
        "line-opacity": [
          "interpolate",
          ["linear"],
          ["zoom"],
          8.5,
          0,
          9.5,
          0.6,
        ],
      },
    },
    legend: [
      { label: "10", color: "#c6dbef" },
      { label: "No value", color: "#d9d9d9" },
    ],
    attribution: "Test attribution",
    measure: "pop_density",
    source_layer: "dz2022",
    ...over,
  };
}

function goodManifest(tilesets) {
  return { schema: 1, tilesets };
}

// --- TF-1: refusal table ---
const refusals = [
  [undefined, "manifest: not an object"],
  [null, "manifest: not an object"],
  [[], "manifest: not an object"],
  [true, "manifest: not an object"],
  [1, "manifest: not an object"],
  ["x", "manifest: not an object"],
  [{ schema: "1", tilesets: {} }, "manifest: unsupported schema"],
  [{ schema: true, tilesets: {} }, "manifest: unsupported schema"],
  [{ schema: 2, tilesets: {} }, "manifest: unsupported schema"],
  [{ schema: 1 }, "manifest: tilesets missing"],
  [{ schema: 1, tilesets: null }, "manifest: tilesets missing"],
  [{ schema: 1, tilesets: [] }, "manifest: tilesets missing"],
];

for (const [input, message] of refusals) {
  assert.throws(() => parseTileManifest(input), { message });
}

assert.throws(() => parseTileManifestText(""), { message: "manifest: invalid json" });
assert.throws(() => parseTileManifestText("{"), { message: "manifest: invalid json" });

assert.throws(
  () =>
    parseTileManifest(
      goodManifest({ "Bad_Id": goodEntry({ layer: "Bad_Id" }) }),
    ),
  { message: "manifest: bad layer id Bad_Id" },
);
assert.throws(
  () =>
    parseTileManifest(
      goodManifest({ dz2022: goodEntry({ layer: "other" }) }),
    ),
  { message: "manifest: bad layer id other" },
);
assert.throws(
  () =>
    parseTileManifest(
      goodManifest({ dz2022: goodEntry({ version: "../x" }) }),
    ),
  { message: "manifest: bad version dz2022" },
);
assert.throws(
  () =>
    parseTileManifest(
      goodManifest({ dz2022: goodEntry({ version: "2026-10-22.DEADBEEF" }) }),
    ),
  { message: "manifest: bad version dz2022" },
);

for (const badZoom of [
  { minzoom: true, maxzoom: 14 },
  { minzoom: 5.5, maxzoom: 14 },
  { minzoom: "5", maxzoom: 14 },
  { minzoom: -1, maxzoom: 14 },
  { minzoom: 10, maxzoom: 5 },
]) {
  assert.throws(
    () => parseTileManifest(goodManifest({ dz2022: goodEntry(badZoom) })),
    { message: "manifest: bad zoom dz2022" },
  );
}

assert.throws(
  () =>
    parseTileManifest(
      goodManifest({ dz2022: goodEntry({ geometry: "raster" }) }),
    ),
  { message: "manifest: bad geometry dz2022" },
);
assert.throws(
  () =>
    parseTileManifest(
      goodManifest({
        dz2022: goodEntry({
          style: { fill: { "fill-color": "#000000" }, symbol: {} },
        }),
      }),
    ),
  { message: "manifest: bad style dz2022" },
);
assert.throws(
  () =>
    parseTileManifest(
      goodManifest({
        dz2022: goodEntry({
          style: { fill: { "text-field": "x" } },
        }),
      }),
    ),
  { message: "manifest: bad style dz2022" },
);
assert.throws(
  () =>
    parseTileManifest(
      goodManifest({
        dz2022: goodEntry({ legend: [{ label: "x", color: "red" }] }),
      }),
    ),
  { message: "manifest: bad legend dz2022" },
);
assert.throws(
  () =>
    parseTileManifest(
      goodManifest({ dz2022: goodEntry({ attribution: "" }) }),
    ),
  { message: "manifest: bad attribution dz2022" },
);

// --- TF-2: empty tilesets ---
{
  const m = parseTileManifest(goodManifest({}));
  const built = buildTileLayers(m, TILE_WANTED_IDS);
  assert.equal(Object.keys(built.sources).length, 0);
  assert.equal(built.layers.length, 0);
  assert.deepEqual(built.missing, [...TILE_WANTED_IDS]);
}

// --- TF-3: unknown id ignored; missing wanted ---
{
  const m = parseTileManifest(
    goodManifest({
      zzz: {
        ...goodEntry({ layer: "zzz" }),
        geometry: "point",
        style: { circle: { "circle-color": "#8a3b00" } },
        measure: null,
        source_layer: "zzz",
      },
      "oil-fields": {
        layer: "oil-fields",
        version: VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "polygon",
        style: {
          fill: { "fill-color": "#8a3b00", "fill-opacity": 0.28 },
          line: { "line-color": "#8a3b00", "line-width": 1.6 },
        },
        legend: [{ label: "Oil", color: "#8a3b00" }],
        attribution: "NSTA",
        measure: null,
        source_layer: "oil-fields",
      },
    }),
  );
  assert.ok(m.tilesets.zzz);
  const built = buildTileLayers(m, TILE_WANTED_IDS);
  assert.ok(built.sources["tile-oil-fields"]);
  assert.ok(!built.sources["tile-zzz"]);
  assert.ok(built.missing.includes("dz2022"));
  assert.ok(built.missing.includes("platforms"));
  assert.ok(built.missing.includes("pipelines"));
  assert.ok(!built.missing.includes("oil-fields"));
}

// --- TF-4: tiles template + bad version ---
{
  const m = parseTileManifest(goodManifest({ dz2022: goodEntry() }));
  const built = buildTileLayers(m, ["dz2022"]);
  assert.equal(
    built.sources["tile-dz2022"].tiles[0],
    `/backend/v1/tiles/dz2022/${VERSION}/{z}/{x}/{y}.mvt`,
  );
  assert.throws(
    () =>
      parseTileManifest(
        goodManifest({ dz2022: goodEntry({ version: "2026-10-22.abcdefgh/../x" }) }),
      ),
    { message: "manifest: bad version dz2022" },
  );
}

// --- TF-5: opacity stops, no minzoom > 0 ---
{
  const m = parseTileManifest(
    goodManifest({
      dz2022: goodEntry(),
      "oil-fields": {
        layer: "oil-fields",
        version: VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "polygon",
        style: {
          fill: { "fill-color": "#8a3b00", "fill-opacity": 0.28 },
          line: { "line-color": "#8a3b00", "line-width": 1.6, "line-opacity": 0.95 },
        },
        legend: [{ label: "Oil", color: "#8a3b00" }],
        attribution: "NSTA",
        measure: null,
        source_layer: "oil-fields",
      },
      platforms: {
        layer: "platforms",
        version: VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "point",
        style: { circle: { "circle-color": "#8a3b00" } },
        legend: [{ label: "P", color: "#8a3b00" }],
        attribution: "NSTA",
        measure: null,
        source_layer: "platforms",
      },
      pipelines: {
        layer: "pipelines",
        version: VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "line",
        style: { line: { "line-color": "#5c4a32" } },
        legend: [{ label: "Pipe", color: "#5c4a32" }],
        attribution: "NSTA",
        measure: null,
        source_layer: "pipelines",
      },
    }),
  );
  const built = buildTileLayers(m, TILE_WANTED_IDS);
  const fill = built.layers.find((l) => l.id === "tile-dz2022-fill");
  assert.deepEqual(fill.paint["fill-opacity"], [
    "interpolate",
    ["linear"],
    ["zoom"],
    4.5,
    0,
    5,
    0.55,
    14,
    0.55,
    15,
    0.4,
  ]);
  const line = built.layers.find((l) => l.id === "tile-dz2022-line");
  assert.deepEqual(line.paint["line-opacity"], [
    "interpolate",
    ["linear"],
    ["zoom"],
    8.5,
    0,
    9.5,
    0.6,
  ]);
  for (const layer of built.layers) {
    assert.ok(
      layer.minzoom === undefined || layer.minzoom === 0,
      `layer ${layer.id} must not gate with minzoom > 0`,
    );
  }
}

// --- TF-6: applyMeasureValues ---
{
  const calls = [];
  const map = {
    setFeatureState(target, state) {
      calls.push({ target, state });
    },
  };
  applyMeasureValues(map, "tile-dz2022", "dz2022", {
    values: { S01013482: 12.5, S01013483: 100 },
  });
  assert.deepEqual(calls, [
    {
      target: { source: "tile-dz2022", sourceLayer: "dz2022", id: "S01013482" },
      state: { v: 12.5 },
    },
    {
      target: { source: "tile-dz2022", sourceLayer: "dz2022", id: "S01013483" },
      state: { v: 100 },
    },
  ]);

  for (const bad of [
    { values: { a: "1" } },
    { values: { a: NaN } },
    { values: null },
  ]) {
    const before = calls.length;
    assert.throws(
      () => applyMeasureValues(map, "tile-dz2022", "dz2022", bad),
      { message: "values: bad payload" },
    );
    assert.equal(calls.length, before);
  }
}

// --- TF-8: ScotlandMap grep pins ---
{
  const src = readFileSync(
    join(frontendRoot, "components/ScotlandMap.tsx"),
    "utf8",
  );
  assert.ok(!src.includes('"/layers/open/data-zones"'));
  assert.ok(!src.includes("/layers/open/data-zones?"));
  assert.ok(!src.includes('loadContextFeature("oil-fields")'));
  assert.ok(!src.includes('loadContextFeature("platforms")'));
  assert.ok(!src.includes('loadContextFeature("pipelines")'));
  // layers/context/${ must not be reachable for TILE_LAYER_IDS — the template
  // may remain for other layers; assert oil/platforms/pipelines are not passed.
  const loadCalls = [...src.matchAll(/loadContextFeature\(([^)]+)\)/g)].map(
    (m) => m[1],
  );
  for (const arg of loadCalls) {
    assert.ok(
      !/oil-fields|platforms|pipelines/.test(arg),
      `loadContextFeature still reachable for tile layer: ${arg}`,
    );
  }
}

console.log("test-tile-layer-factory: ok");
