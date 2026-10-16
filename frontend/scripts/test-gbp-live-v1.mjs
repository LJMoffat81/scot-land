/**
 * GBP-LIVE-V1 — flag default OFF; under-review; range+label; rent-rate wording;
 * placeholder hidden; no totals; shadow never visible as visitor text.
 * Run: node --experimental-strip-types scripts/test-gbp-live-v1.mjs
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
  assert.match(cfg, /under_review_zones:\s*\[\]/);
}

const gbp = await import(pathToFileURL(join(frontendRoot, "lib/gbpLive.ts")).href);

assert.equal(
  gbp.GBP_LIVE_EARLY_BANNER,
  "Early estimates; ranges are wide and will change.",
);
assert.equal(gbp.GBP_LIVE_ESTIMATE_UNAVAILABLE, "estimate unavailable");
assert.equal(gbp.GBP_LIVE_UNDER_REVIEW, "estimate unavailable");
assert.equal(
  gbp.GBP_LIVE_RENT_RATE_CARD,
  "Yearly rent: up to 4.5% of the land's value",
);
assert.equal(
  gbp.GBP_LIVE_RENT_RATE_HOW_IT_WORKS,
  "We turn land value into a yearly rent of up to 4.5% of that value.",
);
assert.equal(gbp.GBP_LIVE_YIELD_UP_TO, undefined);
assert.ok(!/\byield\b/i.test(gbp.GBP_LIVE_RENT_RATE_CARD));
assert.ok(!/\byield\b/i.test(gbp.GBP_LIVE_RENT_RATE_HOW_IT_WORKS));

const formatted = gbp.formatGbpCentralWithRange(6000, 12000, 18000);
assert.match(formatted.central, /^\u00a3/);
assert.match(formatted.range, /\u00a3.*\u2013\u00a3/);
assert.equal(formatted.central, "\u00a312,000");
assert.equal(formatted.range, "\u00a36,000\u2013\u00a318,000");

// GBP-LIVE-V1c: unit label + 3 sf per m²
assert.equal(gbp.GBP_LIVE_UNIT, "per m²");
assert.equal(
  gbp.GBP_LIVE_UNIT_WORDING,
  "£ per square metre of land, per year",
);
assert.equal(gbp.formatGbpPerM2(0.12), "\u00a30.120 per m²");

// Place card wires GBP-LIVE per-m² range + unit label (MAP-CARDS §5; never yield)
{
  const ui = readSrc("components/PlaceCard.tsx");
  assert.match(ui, /formatPlaceCardGbpRange/);
  assert.match(ui, /place-card-figure-range/);
  assert.match(ui, /place-card-figure-unit/);
  assert.match(ui, /GBP_LIVE_UNIT_WORDING/);
  assert.match(ui, /GBP_LIVE_ESTIMATE_UNAVAILABLE/);
  assert.match(ui, /place-card-under-review/);
  assert.doesNotMatch(ui, /yield_wording/);
  assert.doesNotMatch(ui, /place-card-yield-/);
  assert.match(ui, /PLACE_CARD_PRE_POUND/);
  assert.match(ui, /gbpLiveFromCard/);
  // API class "shadow" remapped to visitor tone/chip "estimate" / "Estimate"
  assert.match(ui, /case "shadow":\s*return "estimate"/);
  assert.match(ui, /data-testid=\{`place-tag-\$\{tone\}`\}/);
}

// Chip map: shadow → Estimate (visitor never sees the word "shadow")
{
  const placeCard = readSrc("lib/placeCard.ts");
  assert.match(placeCard, /shadow:\s*"Estimate"/);
  assert.match(placeCard, /rent_rate_wording/);
  assert.doesNotMatch(placeCard, /yield_wording/);
}

// Map credits allowRentGbp gate + GBP-LIVE fetch (legend is registry/inline)
{
  const credits = readSrc("lib/mapLicenceCredits.ts");
  assert.match(credits, /allowRentGbp/);
  const map = readSrc("components/ScotlandMap.tsx");
  assert.match(map, /fetchGbpLiveSettings/);
  assert.match(map, /legend-strip/);
  const registry = readSrc("lib/mapLayerRegistry.ts");
  assert.match(registry, /Annual Ground Rent/);
}

// How it works + banner — signed-off rent-rate sentence
{
  const method = readSrc("components/MethodologyContent.tsx");
  assert.match(method, /GbpLiveBannerNote/);
  const note = readSrc("components/GbpLiveBannerNote.tsx");
  assert.match(note, /GBP_LIVE_EARLY_BANNER/);
  assert.match(note, /GBP_LIVE_RENT_RATE_HOW_IT_WORKS/);
  assert.match(note, /gbp-live-rent-rate-wording/);
  assert.match(note, /rent_rate_wording/);
  assert.doesNotMatch(note, /yield_wording/);
  assert.match(note, /Data Zone only/);
  const banner = readSrc("components/ResearchBanner.tsx");
  assert.match(banner, /fetchGbpLiveSettings/);
  assert.match(banner, /GBP_LIVE_EARLY_BANNER/);
}

// Flag-off probe always HTTP 200 (never 404) via same-origin /api/gbp-live
{
  const probe = readSrc("app/api/gbp-live/route.ts");
  assert.match(probe, /enabled:\s*false/);
  assert.match(probe, /status:\s*200/);
  assert.match(probe, /platform\/gbp-live/);
  assert.match(probe, /rent_rate_wording/);
  assert.doesNotMatch(probe, /yield_wording/);
  const client = readSrc("lib/gbpLive.ts");
  assert.match(client, /\/api\/gbp-live/);
  assert.match(client, /rent_rate_wording/);
  assert.doesNotMatch(client, /yield_wording/);
  const proxy = readSrc("app/backend/[...path]/route.ts");
  assert.match(proxy, /platform\/gbp-live/);
  assert.match(proxy, /GBP_LIVE_FLAG_OFF/);
  assert.match(proxy, /rent_rate_wording/);
  assert.doesNotMatch(proxy, /yield_wording/);
}

// E2e mock keeps API tag/class "shadow" but asserts it is never visible text
{
  const e2e = readSrc("e2e/ci/gbp-live-v1.spec.ts");
  assert.match(e2e, /tag:\s*"shadow"/);
  assert.match(e2e, /class:\s*"shadow"/);
  assert.match(e2e, /API class shadow never shows as visible text/);
  assert.match(e2e, /not\.toContainText\(\/\\bshadow\\b\/i\)/);
  assert.match(e2e, /data-class.*estimate|toHaveAttribute\("data-class", "estimate"\)/);
  assert.match(e2e, /rent_rate_wording/);
  assert.doesNotMatch(e2e, /yield_wording/);
  assert.match(
    e2e,
    /Yearly rent: up to 4\.5% of the land's value/,
  );
  assert.match(
    e2e,
    /We turn land value into a yearly rent of up to 4\.5% of that value\./,
  );
  assert.match(e2e, /per m²/);
  assert.match(e2e, /£ per square metre of land, per year/);
  assert.match(e2e, /estimate unavailable/);
  // Real no-single-point guard (substring, not whole-text-anchored).
  assert.match(e2e, /not\.toContainText\("£0\.120"\)/);
}

// Negative control: central-only render contains £0.120 so the e2e guard can fail.
{
  const CENTRAL_GUARD = "£0.120";
  const centralOnly = gbp.formatGbpPerM2(0.12).replace(/\u00a3/g, "£");
  assert.ok(
    centralOnly.includes(CENTRAL_GUARD),
    "central-only £0.120 per m² must match the e2e no-single-point guard",
  );
  const rangeOnly = `${gbp.formatGbpPerM2Amount(0.06)} to ${gbp.formatGbpPerM2Amount(0.18)} ${gbp.GBP_LIVE_UNIT}`.replace(
    /\u00a3/g,
    "£",
  );
  assert.ok(
    !rangeOnly.includes(CENTRAL_GUARD),
    "range-only £0.0600 to £0.180 must not false-hit the central guard",
  );
}

// Rank band stays OFF; pre-£ copy preserved for flag-off path
{
  const placeCard = readSrc("lib/placeCard.ts");
  assert.match(
    placeCard,
    /PLACE_CARD_PRE_POUND\s*=\s*"We're not showing amounts yet while we check our method\."/,
  );
  assert.match(placeCard, /PLACE_CARD_RANK_BAND_ENABLED\s*=\s*false/);
}

// Desktop: legend strip / panel slot stay above the map chrome.
{
  const chrome = readSrc("app/map-chrome.css");
  assert.match(chrome, /legend-strip|map-panel-slot/);
  assert.match(chrome, /z-index:\s*1[0-9]/);
}

console.log("test-gbp-live-v1: ok");
