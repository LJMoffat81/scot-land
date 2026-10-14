/**
 * Site-watch PR A — page chrome (items 1–7).
 * Checks source + built HTML when .next/server exists.
 * Run via test-site-rewrite-pr1 (CI) or: node --experimental-strip-types scripts/test-site-watch-pr-a.mjs
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

function walkHtml(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, name.name);
    if (name.isDirectory()) walkHtml(full, out);
    else if (name.name.endsWith(".html")) out.push(full);
  }
  return out;
}

// —— Item 2: map footer exact wording + /data#licences ——
const stamp = readSrc("components/MapStampFooter.tsx");
assert.doesNotMatch(
  stamp,
  /<<<<<<|======|>>>>>>/,
  "MapStampFooter must not contain merge conflict markers",
);
assert.doesNotMatch(stamp, /£/, "map footer must not contain £");
assert.match(
  stamp,
  /Research estimate · Open data ·/,
  "map footer must use the approved one-line wording",
);
assert.match(
  stamp,
  /href="\/data#licences"/,
  "Sources and licences must link to /data#licences",
);
assert.match(stamp, />Sources and licences</);
assert.doesNotMatch(
  stamp,
  /Figures are in development/,
  "map footer must not repeat the research banner notice",
);
assert.doesNotMatch(stamp, /Sources and method/);

// —— Item 3: banner below search on mobile (chrome CSS) ——
const chrome = readSrc("app/map-chrome.css");
assert.match(chrome, /\.research-banner-map/);
assert.match(chrome, /--hud-height/);
assert.match(
  chrome,
  /@media \(max-width:\s*900px\)[\s\S]*\.research-banner-map[\s\S]*top:\s*calc\(var\(--hud-height/,
);

// —— SW-010 / item 1: two-row header through 1366px ——
assert.match(
  chrome,
  /@media \(min-width:\s*901px\) and \(max-width:\s*1440px\)[\s\S]*\.hud-search-dock[\s\S]*flex:\s*1 1 100%/,
);
assert.match(chrome, /order:\s*50/);
assert.match(chrome, /position:\s*relative\s*!important/);

// —— SW-014: suggestions above banner ——
assert.match(chrome, /\.hud-search-dock\.open/);
assert.match(chrome, /\.search-suggest/);
assert.match(chrome, /:has\(\.hud-search-dock\.open\)/);

// —— Find a place collapses when place-open ——
assert.match(chrome, /\.app-shell\.place-open[\s\S]*\.hud-scotland-job/);
assert.match(
  readSrc("components/ScotlandMap.tsx"),
  /collapsedIntroForPlace/,
);

// —— SW-013: Downloads has moved here ——
assert.match(
  readSrc("app/developers/page.tsx"),
  /Downloads has moved here/,
);
assert.match(
  readSrc("app/developers/page.tsx"),
  /searchParams\.get\("moved"\) === "1"/,
);

// —— Map (i) attribution carries RM / ONS / endorsement (footer stays one line) ——
const scotlandMap = readSrc("components/ScotlandMap.tsx");
assert.match(scotlandMap, /attributionControl/);
assert.match(scotlandMap, /customAttribution/);
assert.match(scotlandMap, /Royal Mail data/);
assert.match(scotlandMap, /Office for National Statistics/);
assert.match(scotlandMap, /No data provider endorses this site/);
assert.doesNotMatch(
  stamp,
  /Royal Mail data/,
  "map one-line footer must not re-list Royal Mail (lives in (i))",
);

// —— Item 5: mobile attribution fold + compact footer ——
assert.match(chrome, /maplibregl-ctrl-attrib-inner/);
assert.match(chrome, /maplibregl-compact-show/);
assert.match(
  chrome,
  /@media \(max-width:\s*640px\)[\s\S]*\.map-footer[\s\S]*max-height/,
);

// —— Item 7: Layers button top-right ——
assert.match(
  chrome,
  /\[data-testid="hud-layers-btn"\][\s\S]*order:\s*20/,
);

// —— SW-011: backdrop + closed panel covers nothing ——
assert.match(chrome, /\.site-nav-backdrop/);
assert.match(chrome, /\.site-nav-panel\[hidden\]/);
const siteNav = readSrc("components/SiteNav.tsx");
assert.match(siteNav, /site-nav-backdrop/);
assert.match(siteNav, /Escape/);
assert.match(siteNav, /pointerdown/);

// —— Item 4: content footers ——
assert.ok(existsSync(join(frontendRoot, "components/ContentPageFooter.tsx")));
const contentFooter = readSrc("components/ContentPageFooter.tsx");
assert.match(contentFooter, /href="\/data#licences"/);
assert.match(contentFooter, /Research estimate · Open data ·/);
assert.match(contentFooter, /engineVersionLine/);
assert.match(readSrc("components/MissionContent.tsx"), /ContentPageFooter/);
assert.match(readSrc("components/MethodologyContent.tsx"), /ContentPageFooter/);
assert.match(readSrc("app/data/layout.tsx"), /ContentPageFooter/);
assert.match(readSrc("app/developers/layout.tsx"), /ContentPageFooter/);
assert.match(readSrc("app/data/layout.tsx"), /DataLicencesAnchor/);

// —— Item 6: Swagger validatorUrl null (root layout patch; avoid api/page.tsx) ——
const layout = readSrc("app/layout.tsx");
assert.match(layout, /validatorUrl:null/);
assert.match(layout, /SwaggerUIBundle/);
assert.match(layout, /map-chrome\.css/);

// —— Item 7: drawer licences never research-estimate ——
const {
  mapDrawerLicenceDisplay,
} = await import(
  pathToFileURL(join(frontendRoot, "lib/mapDrawerLicenceDisplay.ts")).href
);
const {
  MAP_DRAWER_LAYERS,
} = await import(pathToFileURL(join(frontendRoot, "lib/mapLayerGroups.ts")).href);

for (const layer of MAP_DRAWER_LAYERS) {
  const display = mapDrawerLicenceDisplay(
    layer.id,
    layer.licence,
    layer.licenceUrl,
  );
  assert.ok(display.label.trim(), `empty licence for ${layer.id}`);
  assert.doesNotMatch(
    display.label,
    /research\s*estimate/i,
    `drawer licence for ${layer.id} must not be research-estimate text`,
  );
}

const drawer = readSrc("components/MapLayersDrawer.tsx");
assert.match(drawer, /mapDrawerLicenceDisplay/);

// —— Built HTML (when present) ——
const htmlFiles = walkHtml(join(frontendRoot, ".next/server"));
if (htmlFiles.length > 0) {
  const joined = htmlFiles.map((f) => readFileSync(f, "utf8")).join("\n");
  assert.match(
    joined,
    /Sources and licences/,
    "built HTML should include Sources and licences",
  );
  assert.match(
    joined,
    /data#licences|data%23licences/,
    "built HTML should link to /data#licences",
  );
  assert.match(
    joined,
    /validatorUrl:null/,
    "built HTML should include Swagger validatorUrl null patch",
  );
  console.log(
    `test-site-watch-pr-a: checked ${htmlFiles.length} built HTML file(s)`,
  );
} else {
  console.log("test-site-watch-pr-a: no .next/server HTML yet (source checks only)");
}

console.log("test-site-watch-pr-a: ok");
