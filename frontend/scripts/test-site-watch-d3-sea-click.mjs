/**
 * Site-watch D3 + SW-019: sea / outside-Scotland → one plain line, not No-data
 * rows, and place 400 must clear the spinner.
 * Run: npm run test:site-watch-d3-sea-click
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

function exists(relPath) {
  return existsSync(join(frontendRoot, relPath));
}

const LINE = "We only cover land in Scotland.";

const SHOW_SCOTLAND = "Show me Scotland";

const placeCardLib = readSrc("lib/placeCard.ts");
assert.match(
  placeCardLib,
  new RegExp(
    `PLACE_CARD_OUT_OF_SCOTLAND_LINE\\s*=\\s*\\n?\\s*"${LINE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`,
  ),
);
assert.match(
  placeCardLib,
  new RegExp(
    `PLACE_CARD_SHOW_SCOTLAND_LABEL\\s*=\\s*"${SHOW_SCOTLAND.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`,
  ),
  "SW-028 exact Show me Scotland label",
);
assert.match(placeCardLib, /export function isPlaceCardSeaMiss/);
assert.match(
  placeCardLib,
  /return zone\?\.status === "miss"/,
  "sea miss must be data_zone.status === miss",
);
assert.match(
  placeCardLib,
  /export function outsideScotlandPlaceCard/,
  "SW-019 miss payload helper required",
);
assert.match(
  placeCardLib,
  /isOutsideScotlandError/,
  "fetchPlaceCard must catch outside-Scotland 400",
);
assert.match(
  placeCardLib,
  /return outsideScotlandPlaceCard\(lat, lng\)/,
  "outside-Scotland 400 must become a sea-miss card",
);

const placeCard = readSrc("components/PlaceCard.tsx");
assert.match(placeCard, /isPlaceCardSeaMiss/);
assert.match(placeCard, /PLACE_CARD_OUT_OF_SCOTLAND_LINE/);
assert.match(placeCard, /data-testid="place-card-out-of-scotland"/);
assert.match(placeCard, /place-card-sea-line/);
assert.match(
  placeCard,
  /!error && card && seaMiss/,
  "sea miss must render the plain line branch (kept mounted across re-inspect loading)",
);
assert.match(
  placeCard,
  /isLoading && !seaMiss/,
  "loading spinner must not replace an already-shown sea-miss line",
);
assert.match(
  placeCard,
  /!isLoading && !error && card && !seaMiss/,
  "full card body must be skipped on sea miss",
);
assert.doesNotMatch(
  placeCard,
  /place-card-out-of-scotland[\s\S]{0,120}No data/,
  "sea-miss line must not be No data",
);
assert.match(
  placeCard,
  /PLACE_CARD_SHOW_SCOTLAND_LABEL/,
  "SW-028 Show me Scotland label required",
);
assert.match(
  placeCard,
  /data-testid="place-card-show-scotland"/,
  "SW-028 Show me Scotland control required",
);
assert.match(
  placeCard,
  /onShowScotland/,
  "SW-028 onShowScotland handler required",
);

const api = readSrc("lib/api.ts");
assert.match(api, /export function isOutsideScotlandError/);
assert.match(
  api,
  /err\.status !== 400/,
  "outside-Scotland detector must require HTTP 400",
);
assert.match(
  api,
  new RegExp(LINE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  "visitorFacingError must use the signed-off outside-Scotland line",
);
assert.match(
  api,
  /lng < -11\.0/,
  "parseCoordinates must accept SW-019 west-of-bounds pastes (lng=-9.196485)",
);

const map = readSrc("components/ScotlandMap.tsx");
assert.match(
  map,
  /no_data_zone_at_point/,
  "map click must document sea 404 and still fetch place card",
);
assert.match(
  map,
  /if \(!knownCode\) \{[\s\S]*?try \{[\s\S]*?data-zones\/at[\s\S]*?\} catch \{/,
  "data-zone lookup must be isolated so a sea miss does not abort place card",
);
assert.match(
  map,
  /isOutsideScotlandError/,
  "map must clear spinner on outside-Scotland 400 (SW-019)",
);
assert.match(
  map,
  /outsideScotlandPlaceCard/,
  "map must install the sea-miss card on outside-Scotland 400",
);
assert.match(
  map,
  /showScotlandNationalView/,
  "SW-028 map must reset to national Scotland view",
);
assert.match(
  map,
  /onShowScotland=\{showScotlandNationalView\}/,
  "SW-028 PlaceCardStub must receive Show me Scotland handler",
);
assert.match(
  map,
  /\[-8\.05,\s*54\.48\]/,
  "SW-028 national view must use Scotland bounds",
);

const stub = readSrc("components/PlaceCardStub.tsx");
assert.match(stub, /PLACE_CARD_OUT_OF_SCOTLAND_LINE/);
assert.doesNotMatch(
  stub,
  /status: "miss", note: "No data"/,
  "synthetic miss must not use No data note",
);

const e2e = readSrc("e2e/ci/sea-click-plain-line.spec.ts");
assert.match(e2e, /place-card-out-of-scotland/);
assert.match(
  e2e,
  new RegExp(LINE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")),
  "e2e must assert the exact outside-Scotland line",
);
assert.match(e2e, /No data/);
assert.match(e2e, /getByTestId\("place-card-value"\)\)\.toHaveCount\(0\)/);
assert.match(
  e2e,
  /page\.on\("console"/,
  "e2e must collect console errors",
);
assert.match(
  e2e,
  /page\.on\("pageerror"/,
  "e2e must collect pageerror",
);
assert.match(
  e2e,
  /consoleErrors/,
  "e2e must assert consoleErrors is empty",
);
assert.match(
  e2e,
  /Looking up this spot/,
  "e2e must assert the Looking up spinner is gone",
);
assert.match(
  e2e,
  /bounds400|Coordinates appear to be outside Scotland/,
  "e2e must cover SW-019 place 400",
);
assert.match(
  e2e,
  /\?lat=.*lng=|lat=\$\{OUTSIDE_LAT\}/,
  "e2e must cover URL / coordinate deep-link",
);
assert.match(
  e2e,
  /mouse\.click|maplibregl-canvas/,
  "e2e must cover a real map click",
);
assert.match(
  e2e,
  /3_000|timeout:\s*3000/,
  "SW-019 e2e must require the line within 3s",
);

const pkg = readSrc("package.json");
assert.match(
  pkg,
  /"test:e2e:ci":\s*"playwright test -c playwright\.ci\.config\.ts"/,
  "test:e2e:ci must auto-discover via playwright.ci.config.ts",
);
assert.ok(
  exists("e2e/ci/sea-click-plain-line.spec.ts"),
  "sea-click-plain-line.spec.ts must live under e2e/ci/ for CI auto-discover",
);
assert.ok(
  exists("e2e/ci/sea-stub-card.spec.ts"),
  "sea-stub-card.spec.ts must live under e2e/ci/ for CI auto-discover",
);
const ciConfig = readSrc("playwright.ci.config.ts");
assert.match(
  ciConfig,
  /testDir:\s*["']e2e\/ci["']/,
  "playwright.ci.config.ts must discover e2e/ci/",
);

const chrome = readSrc("app/map-chrome.css");
assert.match(
  chrome,
  /place-card-sea-miss[\s\S]*bottom:\s*auto/,
  "SW-028 sea stub must not stretch with bottom:auto",
);

const e2eStub = readSrc("e2e/ci/sea-stub-card.spec.ts");
assert.match(e2eStub, /Show me Scotland/);
assert.match(e2eStub, /1280/);
assert.match(e2eStub, /390/);
assert.match(e2eStub, /toBeLessThanOrEqual\(24\)/);
assert.match(e2eStub, /page\.on\("console"/);
assert.match(e2eStub, /page\.on\("pageerror"/);
assert.match(e2eStub, /basemap-switcher/);
assert.match(e2eStub, /maplibregl-ctrl-zoom-in/);

console.log("test-site-watch-d3-sea-click: ok");
