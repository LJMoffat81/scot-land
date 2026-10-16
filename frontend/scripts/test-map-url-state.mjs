/**
 * HOTFIX-VIEW-1 — fresh URLs must not become c=0,0, and c= is 5 d.p.
 * Run: npm run test:map-url-state
 */
import assert from "node:assert/strict";
import { register } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

await register(pathToFileURL(join(here, "ts-specifier-hook.mjs")).href, {
  parentURL: import.meta.url,
});

const {
  formatMapCenterParam,
  isScotlandViewCenter,
  readMapUrlState,
  writeMapUrlSearch,
} = await import(pathToFileURL(join(frontendRoot, "lib/mapUrlState.ts")).href);

assert.equal(readMapUrlState("").center, null);
assert.equal(readMapUrlState("?").center, null);
assert.equal(readMapUrlState("?layers=grid3").center, null);

// Number(null) === 0. Missing lat/lng must not become the Gulf of Guinea.
assert.equal(readMapUrlState("?lat=").center, null);
assert.equal(readMapUrlState("?lng=").center, null);
assert.equal(readMapUrlState("?lat=&lng=").center, null);

assert.equal(isScotlandViewCenter(0, 0), false);
assert.equal(readMapUrlState("?c=0.00,0.00").center, null);
assert.equal(readMapUrlState("?c=0,0&z=12").center, null);
assert.equal(readMapUrlState("?c=0.00000,0.00000&z=19").center, null);
assert.equal(readMapUrlState("?lat=0&lng=0").center, null);
assert.equal(readMapUrlState("?lat=0&lon=0").center, null);
// A present out-of-Scotland c is ignored outright (no lat/lng fallthrough).
assert.equal(readMapUrlState("?c=0.00,0.00&lat=55.95&lng=-3.19").center, null);

assert.equal(isScotlandViewCenter(-9.5, 54.5), true);
assert.equal(isScotlandViewCenter(-0.5, 61), true);
assert.equal(isScotlandViewCenter(-9.50001, 56), false);
assert.equal(isScotlandViewCenter(-3, 54.49999), false);
assert.equal(isScotlandViewCenter(-0.49999, 56), false);
assert.equal(isScotlandViewCenter(-3, 61.00001), false);

const shared = readMapUrlState("?c=-3.19000,55.95000&z=12");
assert.deepEqual(shared.center, { lng: -3.19, lat: 55.95 });
assert.equal(shared.z, 12);

const legacy = readMapUrlState("?lat=55.95331&lng=-3.18827");
assert.deepEqual(legacy.center, { lng: -3.18827, lat: 55.95331 });

const freshLayers = writeMapUrlSearch({
  href: "http://local/?layers=grid3",
  layers: ["grid3"],
});
assert.equal(freshLayers.includes("c="), false);

const dropped = writeMapUrlSearch({
  href: "http://local/?c=0.00,0.00&z=12&layers=grid3",
  layers: ["grid3"],
});
assert.equal(dropped.includes("c="), false);
assert.match(dropped, /z=12/);

const outside = writeMapUrlSearch({
  href: "http://local/",
  center: { lng: 0, lat: 0 },
  z: 5,
});
assert.equal(outside.includes("c="), false);

// A point that is not exact at 2 d.p. must survive at 5 d.p. (~1 m, not ~100 m).
const precise = { lng: -3.18827, lat: 55.95331 };
const written = writeMapUrlSearch({
  href: "http://local/",
  center: precise,
  z: 19,
});
assert.equal(
  new URLSearchParams(written.slice(1)).get("c"),
  "-3.18827,55.95331",
);
assert.match(written, /z=19/);
assert.equal(formatMapCenterParam(precise.lng, precise.lat), "-3.18827,55.95331");

const roundTrip = readMapUrlState(written);
assert.ok(roundTrip.center);
const dLng = Math.abs(roundTrip.center.lng - precise.lng);
const dLat = Math.abs(roundTrip.center.lat - precise.lat);
const metres = Math.hypot(dLng * 62_400, dLat * 111_320);
assert.ok(metres < 5, `round-trip ${metres} m`);

const twoDpMetres = Math.hypot(0.00173 * 62_400, 0.00331 * 111_320);
assert.ok(twoDpMetres > 5);
