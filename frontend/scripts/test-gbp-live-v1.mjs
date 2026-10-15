/**
 * GBP-LIVE-V1 — flag default OFF; under-review; range+label; yield "up to";
 * placeholder hidden; no totals. Run: node --experimental-strip-types scripts/test-gbp-live-v1.mjs
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
assert.equal(gbp.GBP_LIVE_UNDER_REVIEW, "Under review");
assert.match(gbp.GBP_LIVE_YIELD_UP_TO, /^up to /);

const formatted = gbp.formatGbpCentralWithRange(6000, 12000, 18000);
assert.match(formatted.central, /^\u00a3/);
assert.match(formatted.range, /\u00a3.*\u2013\u00a3/);
assert.equal(formatted.central, "\u00a312,000");
assert.equal(formatted.range, "\u00a36,000\u2013\u00a318,000");

// Place card wires GBP-LIVE surfaces
{
  const ui = readSrc("components/PlaceCard.tsx");
  assert.match(ui, /formatGbpCentralWithRange/);
  assert.match(ui, /place-card-figure-range/);
  assert.match(ui, /place-card-figure-estimate/);
  assert.match(ui, /place-card-under-review/);
  assert.match(ui, /PLACE_CARD_PRE_POUND/);
  assert.match(ui, /gbpLiveFromCard/);
}

// Map legend allowRentGbp gate + surface rent legend
{
  const credits = readSrc("lib/mapLicenceCredits.ts");
  assert.match(credits, /allowRentGbp/);
  const map = readSrc("components/ScotlandMap.tsx");
  assert.match(map, /SURFACE_RENT_LEGEND_TITLE/);
  assert.match(map, /allowRentGbp:\s*true/);
  assert.match(map, /fetchGbpLiveSettings/);
}

// How it works + banner
{
  const method = readSrc("components/MethodologyContent.tsx");
  assert.match(method, /GbpLiveBannerNote/);
  const note = readSrc("components/GbpLiveBannerNote.tsx");
  assert.match(note, /GBP_LIVE_EARLY_BANNER/);
  assert.match(note, /up to/);
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
  const client = readSrc("lib/gbpLive.ts");
  assert.match(client, /\/api\/gbp-live/);
  const proxy = readSrc("app/backend/[...path]/route.ts");
  assert.match(proxy, /platform\/gbp-live/);
  assert.match(proxy, /GBP_LIVE_FLAG_OFF/);
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

// Desktop place-open: Legend pill stays clickable above the left card.
{
  const chrome = readSrc("app/map-chrome.css");
  assert.match(chrome, /z-index:\s*15/);
  assert.match(chrome, /bottom:\s*5\.25rem/);
  // Still bottom-left under the card column — not docked bottom-right.
  assert.match(
    chrome,
    /\.app-shell\.place-open \.hud-scotland\s*\{[^}]*left:\s*1\.1rem/s,
  );
}

console.log("test-gbp-live-v1: ok");
