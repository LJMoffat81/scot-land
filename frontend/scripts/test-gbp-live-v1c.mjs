/**
 * GBP-LIVE-V1c — unit label, 3 sf / <£0.01, estimate unavailable; flag OFF.
 * Run: node --experimental-strip-types scripts/test-gbp-live-v1c.mjs
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

// Config flag DEFAULT OFF
{
  const cfg = readFileSync(
    join(repoRoot, "data/config/gbp_live.yaml"),
    "utf8",
  );
  assert.match(cfg, /enabled:\s*false/);
  assert.match(cfg, /estimate unavailable/);
}

const gbp = await import(
  pathToFileURL(join(frontendRoot, "lib/gbpLive.ts")).href
);

assert.equal(
  gbp.GBP_LIVE_UNIT_WORDING,
  "£ per square metre of land, per year",
);
assert.equal(gbp.GBP_LIVE_ESTIMATE_UNAVAILABLE, "estimate unavailable");
assert.equal(gbp.GBP_LIVE_UNDER_REVIEW, "estimate unavailable");

// 3 significant figures
assert.equal(gbp.formatGbpPerM2(0.12), "\u00a30.120 per m²");
assert.equal(gbp.formatGbpPerM2(0.06), "\u00a30.0600 per m²");
assert.equal(gbp.formatGbpPerM2(1.234), "\u00a31.23 per m²");

// Below £0.01 → <£0.01; never £0.00
assert.equal(gbp.formatGbpPerM2(0.006), "<\u00a30.01 per m²");
assert.equal(gbp.formatGbpPerM2(0), "<\u00a30.01 per m²");
assert.equal(gbp.formatGbpPerM2Amount(0.009), "<\u00a30.01");
assert.ok(!gbp.formatGbpPerM2(0.006).includes("\u00a30.00"));
assert.ok(!gbp.formatGbpPerM2(0).includes("0.00 per"));

const range = gbp.formatGbpCentralWithRangePerM2(0.004, 0.006, 0.008);
assert.match(range.central, /<\u00a30\.01 per m²/);
assert.match(range.range, /<\u00a30\.01/);
assert.match(range.range, /per m²/);
assert.doesNotMatch(range.central, /0\.00/);
assert.doesNotMatch(range.range, /0\.00/);

// Place card (MAP-CARDS) wires unit label + estimate unavailable
{
  const ui = readSrc("components/PlaceCard.tsx");
  assert.match(ui, /GBP_LIVE_UNIT_WORDING/);
  assert.match(ui, /GBP_LIVE_ESTIMATE_UNAVAILABLE/);
  assert.match(ui, /place-card-figure-unit/);
  assert.match(ui, /formatPlaceCardGbpRange/);
  assert.doesNotMatch(ui, /GBP_LIVE_UNDER_REVIEW/);
}

{
  const placeCard = readSrc("lib/placeCard.ts");
  assert.match(placeCard, /formatGbpPerM2Amount/);
  assert.match(placeCard, /GBP_LIVE_UNIT/);
  assert.match(placeCard, /formatPlaceCardGbpRange/);
}

{
  const note = readSrc("components/GbpLiveBannerNote.tsx");
  assert.match(note, /GBP_LIVE_UNIT_WORDING/);
  assert.doesNotMatch(note, /setUnitWording/);
}

// Legend copy carries the V1c unit phrase
assert.match(
  gbp.SURFACE_RENT_LEGEND_TITLE,
  /£ per square metre of land, per year/,
);
assert.match(
  gbp.SURFACE_RENT_LEGEND_BLURB,
  /£ per square metre of land, per year/,
);

// E2e auto-discovered under e2e/ci/
{
  const e2e = readSrc("e2e/ci/gbp-live-v1c.spec.ts");
  assert.match(e2e, /width:\s*1280/);
  assert.match(e2e, /width:\s*390/);
  assert.match(e2e, /£ per square metre of land, per year/);
  assert.match(e2e, /estimate unavailable/);
  assert.match(e2e, /<£0\.01/);
  assert.match(e2e, /£0\.0600/);
  assert.match(e2e, /not\.toContainText\("£0\.00"\)/);
}

// Backend numerator / unavailable label (source scan)
{
  const backend = readFileSync(
    join(repoRoot, "backend/georgist/gbp_live.py"),
    "utf8",
  );
  assert.match(backend, /NUMERATOR_CENTRAL_FIELD = "measured_rent"/);
  assert.match(backend, /AREA_FIELD = "residential_land_ha"/);
  assert.match(backend, /ESTIMATE_UNAVAILABLE_LABEL = "estimate unavailable"/);
  assert.match(backend, /EXCLUDED_AREA_FIELDS/);
  assert.match(backend, /other_land_ha/);
  assert.match(backend, /UNIT_WORDING = "per square metre of land, per year"/);
  assert.doesNotMatch(backend, /UNIT_WORDING = "per m² of land a year"/);
}

console.log("test-gbp-live-v1c: ok");
