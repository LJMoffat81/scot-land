/**
 * GBP-LIVE-V1d — zero/-0 unavailable; range takes central; out-of-order → unavailable.
 * Run: node --experimental-strip-types scripts/test-gbp-live-v1d.mjs
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const repoRoot = join(frontendRoot, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

// Flag stays OFF
{
  const cfg = readFileSync(join(repoRoot, "data/config/gbp_live.yaml"), "utf8");
  assert.match(cfg, /enabled:\s*false/);
}

const gbp = await import(
  pathToFileURL(join(frontendRoot, "lib/gbpLive.ts")).href
);

// 1. Zero / -0 → estimate unavailable; 0.004 → <£0.01; 0.01 → £0.0100 (3 s.f.)
assert.equal(gbp.formatGbpPerM2Amount(0), "estimate unavailable");
assert.equal(gbp.formatGbpPerM2Amount(-0), "estimate unavailable");
assert.equal(gbp.formatGbpPerM2(0), "estimate unavailable");
assert.equal(gbp.formatGbpPerM2(-0), "estimate unavailable");
assert.ok(!gbp.formatGbpPerM2Amount(0).includes("£"));
assert.ok(!gbp.formatGbpPerM2Amount(0).includes("\u00a3"));
assert.ok(!gbp.formatGbpPerM2Amount(-0).includes("£"));
assert.equal(gbp.formatGbpPerM2Amount(0.004), "<\u00a30.01");
assert.equal(gbp.formatGbpPerM2Amount(0.01), "\u00a30.0100");

// 2. formatPlaceCardGbpRange(low, central, high) — null central → unavailable, no £
assert.equal(
  gbp.formatPlaceCardGbpRange(0.06, null, 0.18),
  "estimate unavailable",
);
assert.ok(!gbp.formatPlaceCardGbpRange(0.06, null, 0.18).includes("£"));
assert.ok(!gbp.formatPlaceCardGbpRange(0.06, null, 0.18).includes("\u00a3"));
assert.equal(
  gbp.formatPlaceCardGbpRange(0.06, undefined, 0.18),
  "estimate unavailable",
);
assert.equal(
  gbp.formatPlaceCardGbpRange(null, 0.12, 0.18),
  "estimate unavailable",
);
assert.equal(
  gbp.formatPlaceCardGbpRange(0.06, 0.12, null),
  "estimate unavailable",
);

// Valid ordered range still formats low–high
assert.equal(
  gbp.formatPlaceCardGbpRange(0.06, 0.12, 0.18),
  "\u00a30.0600 to \u00a30.180 per m²",
);

// placeCard.ts re-exports formatPlaceCardGbpRange (public API surface)
{
  const placeCard = readSrc("lib/placeCard.ts");
  assert.match(
    placeCard,
    /export \{ formatPlaceCardGbpRange \} from "\.\/gbpLive"/,
  );
}

// Caller passes central
{
  const ui = readSrc("components/PlaceCard.tsx");
  assert.match(
    ui,
    /formatPlaceCardGbpRange\(\s*display\.low,\s*display\.central,\s*display\.high\s*\)/,
  );
}

// 3. Out-of-order → unavailable for both range formatters
assert.equal(
  gbp.formatPlaceCardGbpRange(0.2, 0.1, 0.3),
  "estimate unavailable",
);
assert.ok(!gbp.formatPlaceCardGbpRange(0.2, 0.1, 0.3).includes("\u00a3"));
assert.equal(
  gbp.formatPlaceCardGbpRange(0.1, 0.3, 0.2),
  "estimate unavailable",
);
assert.ok(!gbp.formatPlaceCardGbpRange(0.1, 0.3, 0.2).includes("\u00a3"));

{
  const badLow = gbp.formatGbpCentralWithRangePerM2(0.2, 0.1, 0.3);
  assert.equal(badLow.central, "estimate unavailable");
  assert.equal(badLow.range, "estimate unavailable");
  assert.ok(!badLow.central.includes("\u00a3"));
  assert.ok(!badLow.range.includes("\u00a3"));
}
{
  const badHigh = gbp.formatGbpCentralWithRangePerM2(0.1, 0.3, 0.2);
  assert.equal(badHigh.central, "estimate unavailable");
  assert.equal(badHigh.range, "estimate unavailable");
  assert.ok(!badHigh.central.includes("\u00a3"));
  assert.ok(!badHigh.range.includes("\u00a3"));
}

// Backend _is_clamped uses <= 0 for low/high
{
  const backend = readFileSync(
    join(repoRoot, "backend/georgist/gbp_live.py"),
    "utf8",
  );
  assert.match(
    backend,
    /money\["central"\] <= 0 or money\["low"\] <= 0 or money\["high"\] <= 0/,
  );
  assert.doesNotMatch(
    backend,
    /money\["low"\] < 0 or money\["high"\] < 0/,
  );
}

console.log("test-gbp-live-v1d: ok");
