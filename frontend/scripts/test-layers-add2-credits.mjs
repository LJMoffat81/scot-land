/**
 * LAYERS-ADD-2 credits, coverage legend, and free-style guard.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const { LAYERS_ADD2_CREDITS, coverageLegend, assertFreeStyleUrl, layersAdd2Credit } =
  await import(pathToFileURL(join(frontendRoot, "lib/layersAdd2Credits.ts")).href);
const { MAP_BASEMAP_STYLE_URL, mapErrorLogLine } = await import(
  pathToFileURL(join(frontendRoot, "lib/mapBasemap.ts")).href
);

const licencePage = readFileSync(
  join(frontendRoot, "lib/layerLicenceCredits.ts"),
  "utf8",
);
const attributionLine = readFileSync(
  join(frontendRoot, "lib/mapAttributionLine.ts"),
  "utf8",
);
assert.match(licencePage, /LAYERS_ADD2_CREDITS/);
assert.match(attributionLine, /layersAdd2Credit/);
for (const [layerId, meta] of Object.entries(LAYERS_ADD2_CREDITS)) {
  assert.equal(layersAdd2Credit(layerId), meta.attribution);
  assert.equal(meta.attribution.includes("£"), false);
}

const uncovered = coverageLegend("uncovered", null);
assert.equal(uncovered.label, "no open data");
assert.equal(uncovered.fill, "#bdbdbd");
assert.notEqual(uncovered.label, "no allocation");
assert.notEqual(uncovered.label, "none");
assert.notEqual(uncovered.label, "zero");

const covered = coverageLegend("covered", "0");
assert.equal(covered.label, "0");

assert.throws(
  () => assertFreeStyleUrl("https://tiles.example/style.json?key=secret"),
  /keyed tile endpoint/,
);
for (const url of Object.values(MAP_BASEMAP_STYLE_URL)) {
  assertFreeStyleUrl(url);
}

const registry = readFileSync(join(frontendRoot, "lib/mapLayerRegistry.ts"), "utf8");
for (const id of ["epc_domestic", "os_open_uprn", "ldp_highland", "vdl_glasgow_city"]) {
  assert.equal(registry.includes(`id: "${id}"`), false, `${id} must not be an empty switch`);
}
assert.equal(registry.includes('id: "os_open_roads"'), false);

const ajax = new Error(
  "Not Found (404): https://tiles.openfreemap.org/fonts/Noto%20Sans%20Regular/0-255.pbf",
);
ajax.name = "AJAXError";
assert.match(mapErrorLogLine(ajax), /openfreemap/);
assert.match(mapErrorLogLine(ajax), /AJAXError/);
assert.match(mapErrorLogLine(new Error("Failed to fetch")), /Failed to fetch/);
assert.match(mapErrorLogLine(new Error("net::ERR_FAILED")), /net::ERR_FAILED/);
assert.match(mapErrorLogLine(new Error("glyph load failed")), /glyph/);
assert.match(mapErrorLogLine(new Error("sprite load failed")), /sprite/);
assert.equal(mapErrorLogLine(new Error("AbortError")), null);
const domAbort = new Error("The user aborted a request.");
domAbort.name = "AbortError";
assert.equal(mapErrorLogLine(domAbort), null);

console.log("test-layers-add2-credits: ok");
