/**
 * Designer live-check: burger closed, Looking… clears, /data groups, moved note.
 * Run: node --experimental-strip-types scripts/test-designer-live-check.mjs
 */
import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

const css = readSrc("app/globals.css");
assert.match(
  css,
  /\.site-nav-panel\[hidden\]\s*\{[^}]*display:\s*none/,
  "burger panel must stay display:none while hidden",
);

const map = readSrc("components/ScotlandMap.tsx");
assert.match(map, /clearSuggestions[\s\S]*setSuggesting\(false\)/);
assert.match(map, /AbortController/);
assert.match(map, /,\s*250\)/);
assert.match(
  map,
  /event\.key === "Escape" &&\s*\(suggestions\.length \|\| suggestNote \|\| suggesting\)/,
  "Escape must clear Looking…",
);
assert.match(
  map,
  /onBlur[\s\S]*clearSuggestions/,
  "blur must clear Looking…",
);

const dataPage = readSrc("app/data/page.tsx");
assert.match(dataPage, /groupCatalogSources/);
assert.match(dataPage, /data-sources-group/);
assert.match(dataPage, /Land|Resources|Nature|Limits/);

const {
  DATA_SOURCE_GROUP_ORDER,
  dataSourceGroupLabel,
  groupCatalogSources,
} = await import(pathToFileURL(join(frontendRoot, "lib/dataSourceGroups.ts")).href);

assert.deepEqual(DATA_SOURCE_GROUP_ORDER, [
  "land",
  "resources",
  "nature",
  "limits",
]);
assert.equal(dataSourceGroupLabel("land"), "Land");
assert.equal(dataSourceGroupLabel("limits"), "Limits");

const grouped = groupCatalogSources([
  { id: "vdl", licence_url: "x" },
  { id: "repd_onshore_wind", licence_url: "x" },
  { id: "carbon_peatland", licence_url: "x" },
  { id: "sssi", ledger_role: "constraint", licence_url: "x" },
]);
assert.deepEqual(
  grouped.map((g) => g.key),
  ["land", "resources", "nature", "limits"],
);

const nextConfig = readSrc("next.config.ts");
assert.match(nextConfig, /\/developers\?moved=1#downloads/);
assert.match(nextConfig, /\/developers\?moved=1#api/);

const developers = readSrc("app/developers/page.tsx");
assert.match(developers, /This page has moved to Downloads/);
assert.match(developers, /developers-moved-note/);

assert.ok(existsSync(join(frontendRoot, "lib/dataSourceGroups.ts")));

console.log("test-designer-live-check: ok");
