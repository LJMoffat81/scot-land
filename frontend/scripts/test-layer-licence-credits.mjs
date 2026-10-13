/**
 * Node asserts for Methodology layer licence credits (no Playwright).
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const catalogSrc = readFileSync(join(root, "lib/layerCatalog.ts"), "utf8");
const creditsSrc = readFileSync(
  join(root, "lib/layerLicenceCredits.ts"),
  "utf8",
);

assert.match(creditsSrc, /allLayerLicenceCredits/);
assert.match(creditsSrc, /LAYER_ATTRIBUTION/);

const attributionBlock = catalogSrc.match(
  /export const LAYER_ATTRIBUTION[\s\S]*?^};/m,
);
assert.ok(attributionBlock, "LAYER_ATTRIBUTION block missing");
const ids = [...attributionBlock[0].matchAll(/^\s{2}([a-z0-9_]+):\s*\{/gm)].map(
  (m) => m[1],
);
assert.ok(ids.length > 20, `expected many layer ids, got ${ids.length}`);
assert.ok(ids.includes("boundaries"));
assert.ok(ids.includes("data_zones"));
assert.ok(ids.includes("sssi"));

// Credit helper must not invent numeric rent £ amounts.
assert.doesNotMatch(creditsSrc, /£\s*[\d,]+/);

console.log(`test-layer-licence-credits: OK (${ids.length} LAYER_ATTRIBUTION ids)`);
