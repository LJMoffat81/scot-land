/**
 * SHARE-FIX — source contracts: place-lookup retry/backoff + Try again,
 * Coming soon on 503 tile layers, CSP allows Cloudflare Web Analytics.
 * Run: npm run test:share-fix
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

const api = readSrc("lib/api.ts");
assert.match(api, /export const TRY_AGAIN = "Try again"/);
assert.match(api, /PLACE_LOOKUP_RETRY_STATUSES = \[502, 503, 504\]/);
assert.match(api, /placeLookupBackoffMs/);
assert.match(api, /retryStatuses/);
assert.match(api, /export function placeLookupFetch/);
assert.doesNotMatch(
  api,
  /Service busy, please try again/,
  "visitor copy must be Try again, not Service busy",
);

const nextConfig = readSrc("next.config.ts");
assert.match(
  nextConfig,
  /static\.cloudflareinsights\.com/,
  "CSP script-src must allow Cloudflare Web Analytics",
);
assert.match(
  nextConfig,
  /cloudflareinsights\.com/,
  "CSP connect-src must allow Cloudflare Web Analytics beacon",
);

const map = readSrc("components/ScotlandMap.tsx");
assert.match(map, /placeLookupFetch/);
assert.match(map, /TRY_AGAIN/);
assert.match(map, /markTileUnavailable/);
assert.match(map, /tileUnavailableIds/);
// SHARE-FIX layer ids
for (const id of ['"hla"', '"3"', '"5"', '"lca"']) {
  assert.match(
    map,
    new RegExp(`markTileUnavailable\\(${id}\\)`),
    `503 Coming soon must mark ${id}`,
  );
}

const drawer = readSrc("components/MapLayersDrawer.tsx");
assert.match(drawer, /Coming soon/);
assert.match(drawer, /unavailableIds/);

console.log("test-share-fix: ok");
