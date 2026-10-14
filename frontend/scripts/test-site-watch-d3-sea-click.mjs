/**
 * Site-watch D3: sea / outside-Scotland click → one plain line, not No-data rows.
 * Run: npm run test:site-watch-d3-sea-click
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

const LINE =
  "That point is outside Scotland. Search a Scottish postcode or click the map.";

const placeCardLib = readSrc("lib/placeCard.ts");
assert.match(
  placeCardLib,
  new RegExp(
    `PLACE_CARD_OUT_OF_SCOTLAND_LINE\\s*=\\s*\\n?\\s*"${LINE.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`,
  ),
);
assert.match(placeCardLib, /export function isPlaceCardSeaMiss/);
assert.match(
  placeCardLib,
  /return zone\?\.status === "miss"/,
  "sea miss must be data_zone.status === miss",
);

const placeCard = readSrc("components/PlaceCard.tsx");
assert.match(placeCard, /isPlaceCardSeaMiss/);
assert.match(placeCard, /PLACE_CARD_OUT_OF_SCOTLAND_LINE/);
assert.match(placeCard, /data-testid="place-card-out-of-scotland"/);
assert.match(placeCard, /place-card-sea-line/);
assert.match(
  placeCard,
  /!isLoading && !error && card && seaMiss/,
  "sea miss must render the plain line branch",
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

const stub = readSrc("components/PlaceCardStub.tsx");
assert.match(stub, /PLACE_CARD_OUT_OF_SCOTLAND_LINE/);
assert.doesNotMatch(
  stub,
  /status: "miss", note: "No data"/,
  "synthetic miss must not use No data note",
);

const e2e = readSrc("e2e/sea-click-plain-line.spec.ts");
assert.match(e2e, /place-card-out-of-scotland/);
assert.match(e2e, /No data/);
assert.match(e2e, /getByTestId\("place-card-value"\)\)\.toHaveCount\(0\)/);

console.log("test-site-watch-d3-sea-click: ok");
