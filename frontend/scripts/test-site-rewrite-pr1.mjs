/**
 * Site rewrite PR1: nav, banner, redirects, titles (items 6, 8, 13).
 * Run: npm run test:site-rewrite-pr1
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

const {
  SITE_NAV_ITEMS,
  RESEARCH_BANNER_LEAD,
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_TEXT,
} = await import(pathToFileURL(join(frontendRoot, "lib/siteNav.ts")).href);

assert.equal(SITE_NAV_ITEMS.length, 6);
assert.deepEqual(
  SITE_NAV_ITEMS.map((i) => i.label),
  [
    "Map",
    "About",
    "How we built this",
    "How it works",
    "Data & sources",
    "Downloads & API",
  ],
);
assert.deepEqual(
  SITE_NAV_ITEMS.map((i) => i.href),
  ["/", "/about", "/how-we-built-this", "/methodology", "/data", "/developers"],
);
assert.equal(RESEARCH_BANNER_LEAD, "Research estimate.");
assert.equal(
  RESEARCH_BANNER_BODY,
  "Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.",
);
assert.equal(
  RESEARCH_BANNER_TEXT,
  "Research estimate. Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.",
);
assert.doesNotMatch(RESEARCH_BANNER_BODY, /experimental/i);
assert.doesNotMatch(RESEARCH_BANNER_BODY, /still being built|rates bill|tax proposal/i);

for (const rel of [
  "components/SiteNav.tsx",
  "components/ResearchBanner.tsx",
  "components/HashRedirect.tsx",
  "app/about/page.tsx",
  "app/developers/page.tsx",
  "app/developers/checks/page.tsx",
]) {
  assert.ok(existsSync(join(frontendRoot, rel)), `missing ${rel}`);
}

const nextConfig = readSrc("next.config.ts");
for (const pair of [
  ["/downloads", "/developers?moved=1#downloads"],
  ["/open-api", "/developers?moved=1#api"],
  ["/mission", "/about"],
]) {
  assert.match(
    nextConfig,
    new RegExp(
      `source:\\s*"${pair[0].replace("/", "\\/")}"[\\s\\S]*?destination:\\s*"${pair[1].replace(/[/#?]/g, "\\$&")}"[\\s\\S]*?permanent:\\s*true`,
    ),
    `redirect ${pair[0]} → ${pair[1]}`,
  );
}
for (const pair of [
  ["/docs", "/developers/api"],
  ["/backend/docs", "/developers/api"],
]) {
  assert.match(
    nextConfig,
    new RegExp(
      `source:\\s*"${pair[0].replace("/", "\\/")}"[\\s\\S]*?destination:\\s*"${pair[1].replace(/[/#?]/g, "\\$&")}"[\\s\\S]*?statusCode:\\s*301`,
    ),
    `301 redirect ${pair[0]} → ${pair[1]}`,
  );
}
assert.doesNotMatch(
  nextConfig,
  /destination:\s*"\/backend\/docs"/,
  "API reference must not redirect away to /backend/docs",
);
assert.doesNotMatch(
  nextConfig,
  /cdn\.jsdelivr\.net/,
  "site CSP must not allow jsDelivr after self-hosting Swagger",
);

assert.ok(
  existsSync(join(frontendRoot, "public/swagger-ui/swagger-ui-bundle.js")),
  "missing vendored swagger-ui-bundle.js",
);
assert.ok(
  existsSync(join(frontendRoot, "public/swagger-ui/swagger-ui.css")),
  "missing vendored swagger-ui.css",
);
const apiPage = readSrc("app/developers/api/page.tsx");
assert.match(apiPage, /Developer API and bulk data: later/);
assert.match(
  apiPage,
  /Bulk data and the API may be paid services\s+later\./,
);
assert.doesNotMatch(apiPage, /Bulk data and the API will be paid/);
assert.match(apiPage, /Register interest/);
assert.match(apiPage, /href="\/about#contact"/);
assert.doesNotMatch(apiPage, /\/swagger-ui\/swagger-ui-bundle\.js/);
assert.doesNotMatch(apiPage, /\/backend\/openapi\.json/);
assert.doesNotMatch(apiPage, /\/api\//);
assert.doesNotMatch(apiPage, /cdn\.jsdelivr\.net/);

const titles = {
  "app/methodology/page.tsx": "How it works | Scot-LAND",
  "app/data/layout.tsx": "Data & sources | Scot-LAND",
  "app/about/page.tsx": "About | Scot-LAND",
  "app/how-we-built-this/page.tsx": "How we built this | Scot-LAND",
  "app/developers/layout.tsx": "Downloads & API | Scot-LAND",
  "app/layout.tsx": "Map | Scot-LAND",
};
for (const [rel, title] of Object.entries(titles)) {
  assert.match(
    readSrc(rel),
    new RegExp(`title:\\s*"${title.replace(/[|]/g, "\\$&")}"`),
    `${rel} title`,
  );
}

const scotlandMap = readSrc("components/ScotlandMap.tsx");
assert.match(scotlandMap, /SiteNav current="map" variant="map"/);
// MAP-HINTS-OFF-1: ResearchBanner removed from map; content pages keep it.
assert.doesNotMatch(scotlandMap, /\bResearchBanner\b/);
assert.doesNotMatch(scotlandMap, /not a rates bill/);

const oldStrings = [
  "not a rates bill",
  "not shown yet",
  "Until yield calibration",
  "Data Zone band level",
];
const publicGlobs = [
  "components/ScotlandMap.tsx",
  "components/MethodologyContent.tsx",
  "components/MissionContent.tsx",
  "components/PlaceCard.tsx",
  "components/PlaceHectareStack.tsx",
  "components/LayersPanel.tsx",
  "lib/layerCatalog.ts",
  "app/data/page.tsx",
  "app/developers/page.tsx",
  "app/about/page.tsx",
  "app/methodology/page.tsx",
  "app/how-we-built-this/page.tsx",
  "app/layout.tsx",
];
for (const rel of publicGlobs) {
  const src = readSrc(rel);
  for (const needle of oldStrings) {
    assert.equal(
      src.includes(needle),
      false,
      `${rel} must not contain "${needle}"`,
    );
  }
}

assert.match(readSrc("components/MethodologyContent.tsx"), /HashRedirect fromHash="why"/);
assert.match(readSrc("app/data/page.tsx"), /HashRedirect fromHash="checks"/);
assert.doesNotMatch(
  readSrc("lib/placeCard.ts"),
  /export function defaultConstraints/,
);
assert.match(
  readSrc("scripts/test-place-card-hotfix.mjs"),
  /preferDz2022, dataZoneFieldLabel \} = await import\([\s\S]*placeCardDz\.ts/,
);
assert.doesNotMatch(
  readSrc("scripts/test-place-card-hotfix.mjs"),
  /function preferDz2022\(/,
  "hotfix test must not keep a local preferDz2022 copy",
);

// Site-watch PR A chrome checks (wired here to avoid package.json / CI edits
// parallel with other drafts).
await import(pathToFileURL(join(here, "test-site-watch-pr-a.mjs")).href);

console.log("test-site-rewrite-pr1: ok");
