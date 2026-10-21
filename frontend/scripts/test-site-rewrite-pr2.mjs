/**
 * Site rewrite PR2 — section B page copy + place-card wording.
 * Run: npm run test:site-rewrite-pr2
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

// --- Place-card exact wording (UX-10 skeleton + FP1) ---
{
  const placeCard = readSrc("lib/placeCard.ts");
  assert.match(
    placeCard,
    /PLACE_CARD_FIGURE_STATUS\s*=\s*"Not published yet"/,
  );
  assert.match(
    placeCard,
    /PLACE_CARD_LIMITS_HEADING\s*=\s*"Limits"/,
  );
  assert.match(
    placeCard,
    /PLACE_CARD_AGR_LABEL\s*=\s*"Annual Ground Rent"/,
  );
  assert.match(
    placeCard,
    /PLACE_CARD_PRE_POUND\s*=\s*"We're not showing amounts yet while we check our method\."/,
  );
  assert.match(
    placeCard,
    /PLACE_CARD_EXPERIMENTAL_FOOTER\s*=\s*"Experimental estimate, not an official valuation\. It is not a bill, and it does not change what you pay\."/,
  );
  assert.match(placeCard, /PLACE_CARD_RANK_BAND_ENABLED\s*=\s*false/);
  assert.match(placeCard, /case "coming_soon":/);
  assert.match(placeCard, /case "in_progress":/);
  assert.match(placeCard, /return PLACE_CARD_FIGURE_STATUS/);

  const ui = readSrc("components/PlaceCard.tsx");
  assert.match(ui, /PLACE_CARD_AGR_LABEL/);
  assert.match(ui, /PLACE_CARD_PRE_POUND/);
  assert.match(ui, /PLACE_CARD_EXPERIMENTAL_FOOTER/);
  assert.match(ui, /PLACE_CARD_HOW_WE_WORK_LABEL/);
  assert.match(ui, /PLACE_CARD_HOW_WE_WORK_HOMES/);
  assert.match(ui, /PLACE_CARD_PARTS_SUMMARY/);
  assert.doesNotMatch(ui, /What limits how it can be used/);
  assert.doesNotMatch(ui, /Coming soon</);
  assert.doesNotMatch(ui, /In progress/);
  assert.doesNotMatch(ui, /Estimate \(no market price\)/);
}

// --- Map empty-state + search placeholder (MAP-CARDS: no map reference) ---
{
  const map = readSrc("components/ScotlandMap.tsx");
  assert.match(
    map,
    /placeholder="Search a postcode or place"/,
  );
  assert.doesNotMatch(
    map,
    /map reference/i,
    "search chrome must not say map reference",
  );
  // MAP-HINTS-OFF-1: map-rest-prompt removed.
  assert.doesNotMatch(
    map,
    /Search a place or pick a layer/,
  );
  assert.doesNotMatch(map, /map-rest-prompt/);
  assert.doesNotMatch(
    map,
    /Figures for land\s*value are being checked/,
  );
}

// --- About / How it works / Data copy anchors ---
{
  const about = readSrc("components/MissionContent.tsx");
  assert.match(about, /About Scot-LAND/);
  assert.match(about, /id="contact"/);
  assert.match(about, /ContactForm/);
  assert.doesNotMatch(about, /Laurie|Moffat/);
  assert.doesNotMatch(about, /github\.com/i);
  assert.doesNotMatch(about, /mailto:/i);
  assert.match(about, /What Scot-LAND is not/);
  assert.match(about, /landcommission\.gov\.scot/);

  const how = readSrc("components/MethodologyContent.tsx");
  assert.match(how, /How an area is valued/);
  assert.match(how, /Small areas, added up honestly/);
  assert.match(how, /Words we use/);
  assert.match(how, /How sure are these numbers/);
  assert.doesNotMatch(how, /PostGIS|ECONOMIC_RULES|HTTP 503|python -m/);

  const data = readSrc("app/data/page.tsx");
  assert.match(data, /Data &amp; sources|Data \& sources/);
  assert.match(data, /\/api\/catalog\.json/);
  assert.match(data, /licence_url/);
  assert.match(data, /Gaps we know about/);
  assert.match(data, /Technical checks for developers/);

  const glossary = readSrc("components/GlossaryBox.tsx");
  assert.match(glossary, /Annual Ground Rent/);
  assert.match(glossary, /Market \/ Modelled \/ Estimate/);
  assert.doesNotMatch(
    glossary,
    /term:\s*"Market \/ Modelled \/ Estimate \(no market price\)"/,
  );
  assert.match(glossary, /Constraint/);
  assert.match(glossary, /Open Government Licence/);
}

// --- Limits on use explainer (footer; Limits group removed from Layers) ---
{
  const drawer = readSrc("components/MapLayersDrawer.tsx");
  assert.match(drawer, /Limits on use/);
  assert.match(drawer, /map-layers-limits-explainer/);
}

// --- Item 9 jargon sweep (public pages, excludes /developers*) ---
await import("./test-site-rewrite-jargon.mjs");

console.log("test-site-rewrite-pr2: ok");
