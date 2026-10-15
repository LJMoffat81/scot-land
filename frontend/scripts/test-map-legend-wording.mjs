/**
 * SW-022 guard: population-density map legend visitor wording (additions only).
 * Checks source strings and, when present, built HTML prose.
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const TITLE = "Population density — people per km²";
const BLURB = "Busier places tend to have a higher Annual Ground Rent.";
const SOURCE =
  "Source: National Records of Scotland mid-year estimates, Open Government Licence v3.0";
const ZOOM_HINT = "Zoom in to see colours";

const rampSource = readFileSync(
  join(frontendRoot, "lib/mapColourRamps.ts"),
  "utf8",
);
const legendSource = readFileSync(
  join(frontendRoot, "components/MapRangeLegend.tsx"),
  "utf8",
);
const mapSource = readFileSync(
  join(frontendRoot, "components/ScotlandMap.tsx"),
  "utf8",
);

assert.ok(rampSource.includes(TITLE), "mapColourRamps.ts must include exact title");
assert.ok(rampSource.includes(BLURB), "mapColourRamps.ts must include exact blurb");
assert.ok(
  rampSource.includes(SOURCE),
  "mapColourRamps.ts must include exact source line",
);
assert.ok(
  rampSource.includes(ZOOM_HINT),
  "mapColourRamps.ts must include zoom hint",
);
assert.ok(
  mapSource.includes("POP_DENSITY_LEGEND_BLURB"),
  "ScotlandMap must wire density blurb",
);
assert.ok(
  mapSource.includes("POP_DENSITY_LEGEND_SOURCE"),
  "ScotlandMap must wire density source",
);
assert.ok(
  mapSource.includes("POP_DENSITY_ZOOM_HINT"),
  "ScotlandMap must wire density zoom hint",
);
assert.ok(
  mapSource.includes("densityLegendMode"),
  "ScotlandMap must gate legend mode by active layer / zoom",
);

assert.ok(
  legendSource.includes("map-range-legend-zoom-hint"),
  "MapRangeLegend must expose zoom-hint test id",
);
assert.ok(
  legendSource.includes("map-range-legend-source"),
  "MapRangeLegend must expose source test id",
);
assert.ok(
  legendSource.includes("map-range-legend-swatch-nodata"),
  "MapRangeLegend must keep hatched No data swatch",
);
assert.doesNotMatch(rampSource, /£\d/, "density ramp source must not publish £ figures");
assert.doesNotMatch(legendSource, /£\d/, "legend component must not publish £ figures");

// Contrast: adjacent density stops must stay clearly distinct (WCAG-ish ratio).
function relativeLuminance(hex) {
  const raw = hex.replace("#", "").trim();
  const channels = [0, 2, 4].map((i) => {
    const c = parseInt(raw.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

const densityStopsMatch = rampSource.match(
  /id:\s*"pop_density"[\s\S]*?stops:\s*\[([\s\S]*?)\]\s*,\s*\n\s*\}/,
);
assert.ok(densityStopsMatch, "pop_density stops must be present");
const stopColors = [...densityStopsMatch[1].matchAll(/"(#[0-9a-fA-F]{6})"/g)].map(
  (m) => m[1],
);
assert.ok(stopColors.length >= 4, "density ramp needs several stops");
for (let i = 0; i < stopColors.length - 1; i += 1) {
  const a = relativeLuminance(stopColors[i]);
  const b = relativeLuminance(stopColors[i + 1]);
  const lighter = Math.max(a, b);
  const darker = Math.min(a, b);
  const ratio = (lighter + 0.05) / (darker + 0.05);
  assert.ok(
    ratio >= 1.25,
    `density stops ${stopColors[i]} → ${stopColors[i + 1]} contrast ${ratio.toFixed(2)} < 1.25`,
  );
}

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
  // Client components may only appear in chunks; still forbid £ in map HTML shells.
  const violations = [];
  for (const file of htmlFiles) {
    const rel = relative(frontendRoot, file);
    const prose = readFileSync(file, "utf8")
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<(pre|code)\b[\s\S]*?<\/\1>/gi, " ")
      .replace(/<[^>]+>/g, " ");
    if (/£\d/.test(prose) && /map-range-legend|Population density/.test(prose)) {
      violations.push(`${rel}: £ figure near density legend`);
    }
  }
  assert.equal(
    violations.length,
    0,
    `map legend built-HTML guard:\n${violations.join("\n")}`,
  );
  console.log(
    `test-map-legend-wording: ok (source + contrast + ${htmlFiles.length} HTML files)`,
  );
} else {
  console.log("test-map-legend-wording: ok (source + contrast; no .next)");
}
