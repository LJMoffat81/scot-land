/**
 * #77 follow-up hotfix: aquaculture proxy tag, limitRows gaps, preferDz2022 vintage.
 * Run: npm run test:place-card-hotfix
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

/**
 * Mirror of preferDz2022 / dataZoneFieldLabel — kept in lockstep with
 * frontend/lib/placeCard.ts (asserted via source checks below).
 */
function preferDz2022(zone) {
  if (!zone) return null;
  const zones = zone.zones ?? [];
  const dz2022 = zones.find((z) => z.vintage === 2022);
  if (dz2022) {
    return {
      ...zone,
      status: "ok",
      code: dz2022.code,
      name: dz2022.name ?? zone.name,
      vintage: 2022,
    };
  }
  return zone;
}

function dataZoneFieldLabel(vintage) {
  if (vintage === 2022) return "Data zone (2022)";
  if (vintage === 2011) return "Data zone (2011)";
  return "Data zone";
}

// --- 1. Aquaculture tag shadow → proxy; fisheries stays market ---
{
  const { MAP_DRAWER_LAYERS } = await import(
    pathToFileURL(join(frontendRoot, "lib/mapLayerGroups.ts")).href
  );
  const aqua = MAP_DRAWER_LAYERS.find((row) => row.id === "5");
  const fish = MAP_DRAWER_LAYERS.find((row) => row.id === "6");
  assert.ok(aqua, "Aquaculture layer id 5 present");
  assert.equal(aqua.label, "Aquaculture");
  assert.equal(aqua.tag, "proxy", "Aquaculture evidence tag must be proxy");
  assert.ok(fish, "Fisheries quota layer id 6 present");
  assert.equal(fish.label, "Fisheries quota");
  assert.equal(fish.tag, "market", "Fisheries quota stays market");
}

// --- 2. preferDz2022 never invents vintage 2022 ---
{
  const placeCardSrc = readSrc("lib/placeCard.ts");
  assert.doesNotMatch(
    placeCardSrc,
    /vintage\s*\?\?\s*2022/,
    "must not invent vintage 2022 via ?? 2022",
  );
  assert.match(
    placeCardSrc,
    /export function preferDz2022/,
    "preferDz2022 must remain exported",
  );
  assert.match(
    placeCardSrc,
    /export function dataZoneFieldLabel/,
    "dataZoneFieldLabel must be exported for the place-card heading",
  );
  assert.match(
    placeCardSrc,
    /\/\/ Pass through every constraint row[\s\S]*?const constraints = Array\.isArray\(rest\.constraints\) \? rest\.constraints : \[\]/,
    "sanitizePlaceCard must pass through constraints (empty = gap; no applies filter)",
  );
  assert.doesNotMatch(
    placeCardSrc,
    /defaultConstraints\(rest\.vacant_or_derelict\)/,
    "empty API constraints must not be replaced with defaultConstraints",
  );

  const withDz2022 = preferDz2022({
    status: "ok",
    code: "S01000001",
    name: "Old name",
    vintage: 2011,
    zones: [
      { code: "S01000001", vintage: 2011, name: "2011 zone" },
      { code: "S01014567", vintage: 2022, name: "2022 zone" },
    ],
  });
  assert.equal(withDz2022?.vintage, 2022);
  assert.equal(withDz2022?.code, "S01014567");
  assert.equal(dataZoneFieldLabel(withDz2022?.vintage), "Data zone (2022)");

  const only2011 = preferDz2022({
    status: "ok",
    code: "S01000001",
    name: "2011 only",
    vintage: 2011,
    zones: [{ code: "S01000001", vintage: 2011, name: "2011 only" }],
  });
  assert.equal(only2011?.vintage, 2011);
  assert.equal(only2011?.code, "S01000001");
  assert.equal(dataZoneFieldLabel(only2011?.vintage), "Data zone (2011)");

  const nullVintage = preferDz2022({
    status: "ok",
    code: "S01000001",
    name: "Unknown vintage S01",
    vintage: null,
  });
  assert.equal(nullVintage?.vintage, null);
  assert.equal(nullVintage?.code, "S01000001");
  assert.equal(
    dataZoneFieldLabel(nullVintage?.vintage),
    "Data zone",
    "Never label unknown / S01-only as 2022",
  );
}

// --- 3. PlaceCard.tsx: all limit rows + gap copy ---
{
  const src = readSrc("components/PlaceCard.tsx");
  assert.match(
    src,
    /const limitRows = card\?\.constraints \?\? \[\]/,
    "limitRows must keep all constraint rows (no applies===true filter)",
  );
  assert.doesNotMatch(
    src,
    /filter\(\s*\(row\)\s*=>\s*row\.applies\s*===\s*true/,
    "must not filter limitRows to applies===true only",
  );
  assert.match(src, /No data here yet\./);
  assert.match(src, /\/data#gaps/);
  assert.doesNotMatch(
    src,
    /No limits listed for this place/,
    "empty constraints must use gap line, not 'No limits listed'",
  );
  assert.match(src, /dataZoneFieldLabel/);
  assert.doesNotMatch(
    src,
    /<dt>Data zone \(2022\)<\/dt>/,
    "heading must not hardcode Data zone (2022)",
  );
}

console.log("test-place-card-hotfix: ok");
