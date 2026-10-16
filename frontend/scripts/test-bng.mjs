/**
 * GRID-BASE-1 — G7 / G14 unit checks.
 * Run: npm run test:bng
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const {
  BNG_PROJ4,
  BNG_TRANSFORM,
  bngToWgs84,
  floorToGrid3,
  grid3CornersWgs,
  grid3Key,
  grid3OsRef,
  parseGrid3Key,
  wgs84ToBng,
  wgs84ToGrid3,
} = await import(pathToFileURL(join(frontendRoot, "lib/bng.ts")).href);

assert.equal(BNG_TRANSFORM, "helmert-v1");
assert.match(
  BNG_PROJ4,
  /\+towgs84=446\.448,-125\.157,542\.06,0\.15,0\.247,0\.842,-20\.489/,
);

const { easting, northing } = wgs84ToBng(-3.17, 55.975);
assert.ok(Math.abs(easting - 327080.75) < 0.5, `E ${easting}`);
assert.ok(Math.abs(northing - 676396.73) < 0.5, `N ${northing}`);
const square = wgs84ToGrid3(-3.17, 55.975);
assert.ok(square);
assert.equal(square.key, "g3:327078:676395");
assert.equal(square.ref, "NT 27078 76395");
assert.equal(square.easting % 3, 0);
assert.equal(square.northing % 3, 0);

const onLine = floorToGrid3(327081, 676395);
assert.equal(onLine.easting, 327081);
assert.equal(onLine.northing, 676395);
assert.equal(grid3Key(327081, 676395), "g3:327081:676395");

const key = "g3:325890:673452";
const sw = parseGrid3Key(key);
assert.ok(sw);
assert.equal(grid3OsRef(sw.easting, sw.northing), "NT 25890 73452");
const corners = grid3CornersWgs(sw.easting, sw.northing);
const centreLng =
  (corners[0].lng + corners[1].lng + corners[2].lng + corners[3].lng) / 4;
const centreLat =
  (corners[0].lat + corners[1].lat + corners[2].lat + corners[3].lat) / 4;
const again = wgs84ToGrid3(centreLng, centreLat);
assert.ok(again);
assert.equal(again.key, key);

assert.equal(grid3OsRef(325890, 673452), "NT 25890 73452");
assert.equal(grid3Key(325890, 673452), "g3:325890:673452");

const inv = bngToWgs84(327078, 676395);
assert.ok(Number.isFinite(inv.lng) && Number.isFinite(inv.lat));

// G14 — only bng.ts defines proj4.
const allTs = [
  "lib/bng.ts",
  "lib/osgb36.ts",
  "lib/grid3Map.ts",
  "lib/grid3Runtime.ts",
];
for (const rel of allTs) {
  const src = readFileSync(join(frontendRoot, rel), "utf8");
  if (rel === "lib/bng.ts") {
    assert.match(src, /proj4\.defs/);
    assert.match(src, /BNG_TRANSFORM = "helmert-v1"/);
  } else {
    assert.doesNotMatch(src, /proj4\.defs/);
  }
}

console.log("test-bng: ok");
