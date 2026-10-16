/**
 * Site-watch PR B — DZ2022 default, IZ names, banned wording, parcels, place title.
 * Prefer built HTML under .next when present; fall back to source.
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const repoRoot = join(frontendRoot, "..");

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

function read(path) {
  return readFileSync(path, "utf8");
}

// --- 1. Map attribution + legend say Data Zone boundaries 2022 ---
const mapSrc = read(join(frontendRoot, "components/ScotlandMap.tsx"));
assert.match(
  mapSrc,
  /Data Zone boundaries 2022/,
  "map attribution must say Data Zone boundaries 2022",
);
assert.doesNotMatch(
  mapSrc,
  /Data Zone boundaries 2011/,
  "map attribution must not default to 2011",
);
const layerRegistry = read(join(frontendRoot, "lib/mapLayerRegistry.ts"));
assert.match(layerRegistry, /Area boundaries/);
assert.doesNotMatch(layerRegistry, /neighbo(u)?rhood/i);
assert.match(layerRegistry, /DZ2022_EXTRACTION_YEAR/);
const dzAttr = read(join(frontendRoot, "lib/dzAttribution.mjs"));
assert.match(dzAttr, /Copyright Scottish Government/);
assert.match(dzAttr, /dz2022ExtractionYear\.mjs/);
const dzYear = read(join(frontendRoot, "lib/dz2022ExtractionYear.mjs"));
const dzJson = JSON.parse(
  read(join(frontendRoot, "lib/dz2022Attribution.json")),
);
assert.match(dzYear, /DZ2022_EXTRACTION_YEAR/);
assert.equal(
  Number(dzYear.match(/DZ2022_EXTRACTION_YEAR\s*=\s*(\d+)/)?.[1]),
  dzJson.extraction_year,
  "extraction year export must match dz2022Attribution.json",
);

const catalog = read(join(frontendRoot, "lib/layerCatalog.ts"));
assert.match(catalog, /Data Zone boundaries 2022/);

// --- 2. No plot-level parcels / w3w on the public map (MAP-CARDS GIS 16) ---
assert.doesNotMatch(
  mapSrc,
  /<strong>Cadastral parcel<\/strong>/,
  "no Cadastral parcel popup HTML",
);
assert.doesNotMatch(
  mapSrc,
  /\.addSource\(\s*["'](?:parcels|w3w|selected-parcel|selected-square)/,
  "plot-level parcel / w3w sources must not be added on the public map",
);
assert.doesNotMatch(
  mapSrc,
  /\.addLayer\(\s*\{[^}]*["'](?:parcels-wms|w3w-grid)/,
  "plot-level parcel / w3w layers must not be added on the public map",
);

// --- 3. Place card: council row; no parcel ID; land_outline stays on payload (UX10-4 moves diagnostics) ---
const placeCard = read(join(frontendRoot, "components/PlaceCard.tsx"));
assert.match(placeCard, /place-card-council/);
assert.match(placeCard, /PLACE_CARD_AGR_LABEL/);
assert.doesNotMatch(
  placeCard,
  /inspire_id/,
  "place card must not render parcel inspire_id",
);
const placeCardContract = read(join(frontendRoot, "lib/placeCard.ts"));
assert.match(placeCardContract, /land_outline/);
assert.match(placeCardContract, /Registered extent outline only/);

// --- 4. Banned wording absent from developers sources ---
const banned = ["£0", "market+proxy"];
for (const page of [
  "app/developers/page.tsx",
  "app/developers/checks/page.tsx",
]) {
  const src = read(join(frontendRoot, page));
  for (const phrase of banned) {
    assert.ok(
      !src.includes(phrase),
      `${page} must not contain ${phrase}`,
    );
  }
}

// --- 5. Built HTML when available ---
const nextDir = join(frontendRoot, ".next");
if (existsSync(nextDir)) {
  const htmlFiles = walk(nextDir).filter((p) => p.endsWith(".html"));
  const blob = htmlFiles.map((p) => read(p)).join("\n");
  if (blob.length) {
    for (const phrase of banned) {
      assert.ok(
        !blob.includes(phrase),
        `built HTML must not contain ${phrase}`,
      );
    }
    // Prefer 2022 wording somewhere in the built app when map chunks are present.
    const mapChunk = walk(join(nextDir, "static")).filter((p) =>
      /ScotlandMap|page-/.test(p),
    );
    const mapBlob = mapChunk.map((p) => read(p)).join("\n");
    if (mapBlob.includes("Data Zone boundaries")) {
      assert.match(mapBlob, /Data Zone boundaries 2022/);
    }
  }
}

// --- 6. Backend defaults ---
const dzLookup = read(join(repoRoot, "backend/georgist/dz_lookup.py"));
assert.ok(
  dzLookup.includes("by_vintage.get(2022)") &&
    dzLookup.includes("by_vintage.get(2011)"),
  "dz_lookup must prefer 2022 then 2011",
);
assert.match(dzLookup, /Default public grain is DZ2022/);
const dataZones = read(join(repoRoot, "backend/layers/data_zones.py"));
assert.match(dataZones, /DEFAULT_VINTAGE = 2022/);
assert.match(dataZones, /Data Zone boundaries 2022/);

const izCsv = read(
  join(repoRoot, "data/reference/intermediate_zone_names.csv"),
);
assert.match(
  izCsv,
  /S02002727,2022,"?Old Town, Princes Street and Leith Street"?/,
);
assert.match(izCsv, /S02003284,2022,Badenoch and Strathspey Central/);
assert.match(
  izCsv,
  /S02001622,2011,"?Old Town, Princes Street and Leith Street"?/,
);
assert.match(izCsv, /S02001983,2011,Badenoch and Strathspey Central/);

// --- 7. Item 8: IZ pending copy stays in sanitize; DZ prefer helper kept ---
const placeCardLibB = read(join(frontendRoot, "lib/placeCard.ts"));
assert.match(placeCardLibB, /PLACE_CARD_NAME_NOT_LOADED/);
assert.match(placeCardLibB, /name not loaded yet/);
const placeCardDz = read(join(frontendRoot, "lib/placeCardDz.ts"));
assert.match(placeCardDz, /preferDz2022/);
assert.match(placeCardDz, /Data zone \(2011\)|2011/);

// --- 8. Item 9: Zone set gloss ---
const developers = read(join(frontendRoot, "app/developers/page.tsx"));
assert.match(
  developers,
  /Which Data Zone map these figures use/,
);

// --- 9. Item 6: catalogue plain English + developer notes ---
const catalogCopy = read(
  join(repoRoot, "backend/layers/catalog_copy.py"),
);
assert.match(catalogCopy, /PLAIN_DESCRIPTIONS/);
assert.match(catalogCopy, /developer_note/);
assert.doesNotMatch(catalogCopy, /PLAIN_DESCRIPTIONS[\s\S]{0,200}PostGIS/);
const apiPage = read(join(frontendRoot, "app/developers/api/page.tsx"));
assert.match(apiPage, /catalog-developer-notes/);
assert.match(apiPage, /developer_note/);

// --- 10. Item 7: /data groups harden ---
const dataPage = read(join(frontendRoot, "app/data/page.tsx"));
assert.match(dataPage, /groupCatalogSources/);
assert.match(dataPage, /data-sources-groups/);
assert.match(dataPage, /grouping failed/);

console.log("test-site-watch-pr-b: ok");
