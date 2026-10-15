/**
 * DZ-HIERARCHY — placeCardTitle prefers IZ name; never "unknown".
 */
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const {
  placeCardTitle,
  PLACE_CARD_MORE_ABOUT_LABEL,
  PLACE_CARD_DATA_SOURCES_LABEL,
  PLACE_CARD_DATA_SOURCES_HREF,
} = await import(
  pathToFileURL(join(frontendRoot, "lib/placeCardDz.ts")).href
);

assert.equal(PLACE_CARD_MORE_ABOUT_LABEL, "More about this area");
assert.equal(PLACE_CARD_DATA_SOURCES_LABEL, "Data & sources");
assert.equal(PLACE_CARD_DATA_SOURCES_HREF, "/data");

assert.equal(
  placeCardTitle({
    place_label: "Edinburgh Old Town",
    council_name: "City of Edinburgh",
    data_zone: { status: "ok", name: "Old Town East", vintage: 2022 },
    intermediate_zone: {
      status: "ok",
      name: "Old Town, Princes Street and Leith Street",
      code: "S02002727",
    },
  }),
  "Old Town, Princes Street and Leith Street",
);

assert.equal(
  placeCardTitle({
    place_label: "Edinburgh Old Town",
    council_name: "City of Edinburgh",
    data_zone: { status: "ok", name: "Old Town East" },
    intermediate_zone: {
      status: "ok",
      name: null,
      code: "S02002727",
      note: "name not loaded yet",
    },
  }),
  "Edinburgh Old Town",
);

assert.equal(
  placeCardTitle({
    place_label: null,
    council_name: "City of Edinburgh",
    data_zone: { status: "ok", name: null },
    intermediate_zone: { status: "no_data", name: null },
  }),
  "City of Edinburgh",
);

const title = placeCardTitle({
  place_label: null,
  council_name: null,
  postcode: "EH1 1YZ",
  intermediate_zone: { status: "ok", name: null, code: "S02002727" },
});
assert.equal(title, "EH1 1YZ");
assert.notEqual(title.toLowerCase(), "unknown");

console.log("test-dz-hierarchy: ok");
