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

const { preferDz2022, dataZoneFieldLabel } = await import(
  pathToFileURL(join(frontendRoot, "lib/placeCardDz.ts")).href
);

// --- 1. MAP-CARDS: aquaculture / fisheries left the live Layers registry ---
{
  const { MAP_LAYER_REGISTRY } = await import(
    pathToFileURL(join(frontendRoot, "lib/mapLayerRegistry.ts")).href
  );
  assert.equal(
    MAP_LAYER_REGISTRY.find((row) => row.id === "5"),
    undefined,
    "Aquaculture is roadmap-only, not a live switch",
  );
  assert.equal(
    MAP_LAYER_REGISTRY.find((row) => row.id === "6"),
    undefined,
    "Fisheries quota is roadmap-only, not a live switch",
  );
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
    /export \{\s*dataZoneFieldLabel,[\s\S]*?preferDz2022,[\s\S]*?\} from "\.\/placeCardDz"/,
    "preferDz2022 and dataZoneFieldLabel must remain re-exported from placeCard",
  );
  assert.match(
    readSrc("lib/placeCardDz.ts"),
    /export function preferDz2022/,
    "preferDz2022 must live in placeCardDz",
  );
  assert.match(
    readSrc("lib/placeCardDz.ts"),
    /export function dataZoneFieldLabel/,
    "dataZoneFieldLabel must live in placeCardDz",
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
  assert.doesNotMatch(
    placeCardSrc,
    /export function defaultConstraints/,
    "unused defaultConstraints export must be removed",
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

// --- 3. PlaceCard.tsx: UX10-1 skeleton + loading placeholders (limits UI → UX10-6) ---
{
  const src = readSrc("components/PlaceCard.tsx");
  assert.match(src, /PLACE_CARD_AGR_LABEL/);
  assert.match(src, /PLACE_CARD_PRE_POUND/);
  assert.match(src, /PLACE_CARD_EXPERIMENTAL_FOOTER/);
  assert.match(src, /place-card-parts/);
  assert.doesNotMatch(
    src,
    /filter\(\s*\(row\)\s*=>\s*row\.applies\s*===\s*true/,
    "must not filter agr/limit rows to applies===true only",
  );
  assert.doesNotMatch(
    src,
    /No limits listed for this place/,
    "must not use retired 'No limits listed' copy",
  );
  assert.doesNotMatch(
    src,
    /<dt>Data zone \(2022\)<\/dt>/,
    "heading must not hardcode Data zone (2022)",
  );
  // Grey placeholder rows while a place is being looked up (MAP-CARDS §5.2).
  assert.match(src, /PLACE_CARD_LOADING_LABEL|Looking up…/);
  assert.match(src, /place-card-placeholder-rows/);
  assert.match(src, /data-testid="place-card-placeholders"/);
  assert.match(src, /place-card-placeholder-row/);
  const css = readSrc("app/globals.css");
  assert.match(css, /\.place-card-placeholder-row/);
  assert.match(css, /place-card-placeholder-pulse/);
}

console.log("test-place-card-hotfix: ok");
