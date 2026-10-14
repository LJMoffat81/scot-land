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

assert.equal(SITE_NAV_ITEMS.length, 5);
assert.deepEqual(
  SITE_NAV_ITEMS.map((i) => i.label),
  ["Map", "About", "How it works", "Data & sources", "Downloads & API"],
);
assert.equal(RESEARCH_BANNER_LEAD, "Research estimate.");
assert.match(RESEARCH_BANNER_BODY, /Land rent figures are not published yet/);
assert.match(RESEARCH_BANNER_TEXT, /^Research estimate\./);

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
  ["/downloads", "/developers#downloads"],
  ["/open-api", "/developers#api"],
  ["/docs", "/developers/api"],
  ["/mission", "/about"],
  ["/developers/api", "/backend/docs"],
]) {
  assert.match(
    nextConfig,
    new RegExp(
      `source:\\s*"${pair[0].replace("/", "\\/")}"[\\s\\S]*?destination:\\s*"${pair[1].replace(/[/#]/g, "\\$&")}"[\\s\\S]*?permanent:\\s*true`,
    ),
    `redirect ${pair[0]} → ${pair[1]}`,
  );
}

const titles = {
  "app/methodology/page.tsx": "How it works | Scot-LAND",
  "app/data/layout.tsx": "Data & sources | Scot-LAND",
  "app/about/page.tsx": "About | Scot-LAND",
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
assert.match(scotlandMap, /ResearchBanner dismissible/);
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

console.log("test-site-rewrite-pr1: ok");
