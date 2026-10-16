/**
 * MAPREF-FIX — OSGB36 British National Grid easting,northing (±50 m).
 * Run: npm run test:map-reference-osgb
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const { osgb36MapReference, wgs84ToOsgb36 } = await import(
  pathToFileURL(join(frontendRoot, "lib/osgb36.ts")).href
);

/** Known WGS84 points → EPSG:27700 (pyproj) reference, ±50 m. */
const KNOWN = [
  {
    name: "Edinburgh EH1",
    lat: 55.9533,
    lng: -3.1883,
    easting: 325_897,
    northing: 674_001,
  },
  {
    name: "Inverness",
    lat: 57.4778,
    lng: -4.2247,
    easting: 266_700,
    northing: 845_245,
  },
  {
    name: "Glasgow centre",
    lat: 55.8609,
    lng: -4.2514,
    easting: 259_189,
    northing: 665_372,
  },
];

for (const pt of KNOWN) {
  const { easting, northing } = wgs84ToOsgb36(pt.lat, pt.lng);
  assert.ok(
    Math.abs(easting - pt.easting) <= 50,
    `${pt.name} easting ${easting} vs ${pt.easting}`,
  );
  assert.ok(
    Math.abs(northing - pt.northing) <= 50,
    `${pt.name} northing ${northing} vs ${pt.northing}`,
  );
  const ref = osgb36MapReference(pt.lat, pt.lng);
  assert.match(ref, /^\d+,\d+$/, `${pt.name} format easting,northing`);
  // Must not be the old lat/lng index (millions / negatives).
  const [eStr, nStr] = ref.split(",");
  assert.ok(
    Number(eStr) > 50_000 && Number(eStr) < 700_000,
    `${pt.name} easting band`,
  );
  assert.ok(
    Number(nStr) > 0 && Number(nStr) < 1_300_000,
    `${pt.name} northing band`,
  );
}

const placeCardSrc = readFileSync(
  join(frontendRoot, "lib/placeCard.ts"),
  "utf8",
);
assert.match(
  placeCardSrc,
  /PLACE_CARD_MAP_REFERENCE_ENABLED = false/,
  "MAP-CARDS §6 — Map reference row off on the place card",
);
assert.match(
  placeCardSrc,
  /from "\.\/osgb36"/,
  "placeCard imports osgb36",
);
assert.match(
  placeCardSrc,
  /return osgb36MapReference\(lat, lng\)/,
  "scotLandSquareReference delegates to OSGB36",
);
assert.match(
  placeCardSrc,
  /scotLandSquareReference\(rest\.lat, rest\.lng\)/,
  "sanitizePlaceCard always recomputes OSGB from lat/lng",
);

const registrySrc = readFileSync(
  join(frontendRoot, "lib/mapLayerRegistry.ts"),
  "utf8",
);
// MAP-CARDS: aquaculture / LCA are roadmap items, not Layers switches.
assert.doesNotMatch(
  registrySrc,
  /id:\s*"5"/,
  "Aquaculture must not be a live Layers registry id",
);
assert.doesNotMatch(
  registrySrc,
  /id:\s*"lca"/,
  "LCA must not be a live Layers registry id",
);

console.log("test-map-reference-osgb: ok");
