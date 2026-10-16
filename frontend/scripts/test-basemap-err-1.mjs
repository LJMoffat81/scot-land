/**
 * BASEMAP-ERR-1 — mapErrorLogLine keeps the #198 asserts, and the notice
 * shows on a basemap failure or a style-load timeout, then hides on style.load.
 */
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const {
  BASEMAP_STYLE_TIMEOUT_MS,
  initialBasemapNoticeState,
  isBasemapFailureEvent,
  mapErrorLogLine,
  reduceBasemapNotice,
} = await import(pathToFileURL(join(frontendRoot, "lib/mapBasemap.ts")).href);

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

const styleUrl = "https://tiles.openfreemap.org/styles/positron";
const styleError = new Error(`Failed to fetch (500): ${styleUrl}`);
styleError.name = "AJAXError";
assert.equal(
  isBasemapFailureEvent({ error: styleError }, styleUrl),
  true,
);
assert.equal(
  isBasemapFailureEvent({ error: new Error("AbortError") }, styleUrl),
  false,
);
assert.equal(
  isBasemapFailureEvent({ error: new Error("glyph load failed") }, styleUrl),
  false,
);
const tileError = new Error(
  "AJAXError: Failed to fetch https://tiles.openfreemap.org/planet/0/0/0.pbf",
);
assert.equal(
  isBasemapFailureEvent({ error: tileError, sourceId: "openmaptiles" }, styleUrl),
  true,
);

assert.equal(BASEMAP_STYLE_TIMEOUT_MS, 15_000);

let state = initialBasemapNoticeState();
assert.deepEqual(state, { styleLoaded: false, notice: false });
state = reduceBasemapNotice(state, { type: "error", basemap: false });
assert.equal(state.notice, false);
state = reduceBasemapNotice(state, { type: "error", basemap: true });
assert.equal(state.notice, true);
state = reduceBasemapNotice(state, { type: "style.load" });
assert.deepEqual(state, { styleLoaded: true, notice: false });
state = reduceBasemapNotice(state, { type: "timeout" });
assert.equal(state.notice, false);
state = reduceBasemapNotice(initialBasemapNoticeState(), { type: "timeout" });
assert.deepEqual(state, { styleLoaded: false, notice: true });

console.log("test-basemap-err-1: ok");
