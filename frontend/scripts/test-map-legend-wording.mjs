/**
 * MAP-CARDS-REDESIGN guard: legend lives inline / strip — not a floating density panel.
 * Density is not a visitor layer (Q3). Certainty uses "Striped = less sure", not "Paler".
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const mapSource = readFileSync(
  join(frontendRoot, "components/ScotlandMap.tsx"),
  "utf8",
);
const registrySource = readFileSync(
  join(frontendRoot, "lib/mapLayerRegistry.ts"),
  "utf8",
);
const drawerSource = readFileSync(
  join(frontendRoot, "components/MapLayersDrawer.tsx"),
  "utf8",
);

assert.ok(
  !mapSource.includes('data-testid="legend-strip"') &&
    !mapSource.includes('data-testid="map-key-chip"'),
  "ScotlandMap must not expose floating legend-strip or map-key-chip",
);
assert.doesNotMatch(
  mapSource,
  /data-testid="map-legend-panel"/,
  "floating map-legend-panel must be removed",
);
assert.doesNotMatch(
  mapSource,
  /Show legend|Hide legend/,
  "Show/Hide legend pill must be removed",
);
assert.doesNotMatch(
  mapSource,
  /buildActiveLegendView/,
  "ScotlandMap must not build the old floating active-layer legend",
);

assert.ok(
  registrySource.includes("Striped = less sure"),
  "registry legend must include Striped = less sure",
);
assert.ok(
  registrySource.includes("No figure here"),
  "registry legend must include No figure here",
);
assert.doesNotMatch(
  registrySource,
  /Paler = less sure/,
  "registry must not use Paler = less sure",
);
assert.doesNotMatch(
  drawerSource,
  /Paler = less sure/,
  "Layers drawer must not use Paler = less sure",
);
assert.doesNotMatch(
  mapSource,
  /Paler = less sure/,
  "map shell must not use Paler = less sure",
);

assert.doesNotMatch(
  registrySource,
  /People per km/,
  "population density must not be a Layers registry row",
);
assert.doesNotMatch(registrySource, /£\d/, "registry must not publish £ figures");
assert.doesNotMatch(drawerSource, /£\d/, "drawer must not publish £ figures");

function walk(dir) {
  const out = [];
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, name.name);
    if (name.isDirectory()) out.push(...walk(p));
    else out.push(p);
  }
  return out;
}

const nextHtml = join(frontendRoot, ".next");
if (existsSync(nextHtml)) {
  const htmlFiles = walk(join(nextHtml, "server")).filter((f) =>
    f.endsWith(".html"),
  );
  const violations = [];
  for (const file of htmlFiles) {
    const rel = relative(frontendRoot, file);
    const prose = readFileSync(file, "utf8")
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<(pre|code)\b[\s\S]*?<\/\1>/gi, " ")
      .replace(/<[^>]+>/g, " ");
    if (/Paler = less sure/i.test(prose)) {
      violations.push(`${rel}: Paler = less sure`);
    }
    if (/£\d/.test(prose) && /legend-strip|inline-legend/i.test(prose)) {
      violations.push(`${rel}: £ figure near legend`);
    }
  }
  assert.equal(
    violations.length,
    0,
    `map legend built-HTML guard:\n${violations.join("\n")}`,
  );
  console.log(
    `test-map-legend-wording: ok (MAP-CARDS strip + ${htmlFiles.length} HTML files)`,
  );
} else {
  console.log("test-map-legend-wording: ok (MAP-CARDS strip; no .next)");
}
