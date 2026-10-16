/**
 * OpenFreeMap proxy: TileJSON stays on /api/ofm, and paths cannot escape the host.
 * Run: npm run test:ofm-proxy
 */
import assert from "node:assert/strict";
import { register } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));

await register(pathToFileURL(join(here, "ts-specifier-hook.mjs")).href, {
  parentURL: import.meta.url,
});

const {
  ofmDocumentIsJson,
  ofmProxyUrl,
  ofmUpstreamFromSegments,
  rewriteOfmUrls,
} = await import(pathToFileURL(join(here, "../lib/ofmProxy.ts")).href);
const { basemapStyleUrl, MAP_BASEMAP_STYLE_URL } = await import(
  pathToFileURL(join(here, "../lib/mapBasemap.ts")).href
);

assert.equal(
  ofmProxyUrl("https://tiles.openfreemap.org/styles/positron"),
  "/api/ofm/styles/positron",
);
assert.equal(
  ofmProxyUrl("https://tiles.openfreemap.org/planet"),
  "/api/ofm/planet",
);
assert.equal(ofmProxyUrl("https://example.test/style.json"), "https://example.test/style.json");

const rewritten = rewriteOfmUrls(
  '{"url":"https://tiles.openfreemap.org/planet","glyphs":"https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf","tiles":["https://tiles.openfreemap.org/planet/20261011_080001_pt/{z}/{x}/{y}.pbf"]}',
  "http://localhost:3100",
);
assert.equal(rewritten.includes("https://tiles.openfreemap.org"), false);
assert.match(rewritten, /http:\/\/localhost:3100\/api\/ofm\/planet"/);
assert.match(
  rewritten,
  /http:\/\/localhost:3100\/api\/ofm\/fonts\/\{fontstack\}\/\{range\}\.pbf/,
);
assert.match(
  rewritten,
  /http:\/\/localhost:3100\/api\/ofm\/planet\/20261011_080001_pt\/\{z\}\/\{x\}\/\{y\}\.pbf/,
);

assert.equal(
  ofmUpstreamFromSegments(["styles", "positron"]),
  "https://tiles.openfreemap.org/styles/positron",
);
assert.equal(
  ofmUpstreamFromSegments(["planet", "20261011_080001_pt", "6", "31", "20.pbf"]),
  "https://tiles.openfreemap.org/planet/20261011_080001_pt/6/31/20.pbf",
);
assert.equal(ofmUpstreamFromSegments(["..", "styles"]), null);
assert.equal(ofmUpstreamFromSegments(["styles", ".."]), null);
assert.equal(ofmUpstreamFromSegments([]), null);

assert.equal(ofmDocumentIsJson("application/json", ["planet"]), true);
assert.equal(ofmDocumentIsJson("application/octet-stream", ["styles", "liberty"]), true);
assert.equal(
  ofmDocumentIsJson("application/x-protobuf", ["planet", "v", "1", "2", "3.pbf"]),
  false,
);

assert.equal(basemapStyleUrl("light"), "/api/ofm/styles/positron");
assert.equal(basemapStyleUrl("detailed"), "/api/ofm/styles/liberty");
assert.equal(
  MAP_BASEMAP_STYLE_URL.light,
  "https://tiles.openfreemap.org/styles/positron",
);

console.log("test-ofm-proxy: ok");
