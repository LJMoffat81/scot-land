/**
 * VDL-DZ-3 download rule. Unconditional: no network and no built CSV.
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  assertPublishedVdlDownloadRows,
  publishVdlDownloadRow,
} from "./vdl-download-publish.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..", "..");

const headers = [
  "code",
  "vintage",
  "n_sites",
  "ha_register",
  "n_vacant",
  "n_derelict",
  "ha_vacant",
  "ha_derelict",
];

const fixture = publishVdlDownloadRow(
  {
    code: "S01013482",
    vintage: "2022",
    n_sites: "4",
    ha_register: "12.2",
    n_vacant: "3",
    n_derelict: "1",
    ha_vacant: "9.1",
    ha_derelict: "3.1",
  },
  headers,
);
assert.equal(fixture.n_sites, "4");
assert.equal(fixture.n_vacant, "3");
assert.equal(fixture.ha_vacant, "9");
assert.equal(fixture.n_derelict, "<3");
assert.equal(fixture.ha_derelict, "");
assert.notEqual(fixture.ha_register, "");

const zero = publishVdlDownloadRow(
  {
    n_sites: "0",
    ha_register: "0.000000",
    ha_derelict: "0.000000",
    n_derelict: "0",
    n_vacant: "0",
  },
  ["n_sites", "ha_register", "ha_derelict", "n_derelict", "n_vacant"],
);
assert.equal(zero.ha_register, "0");
assert.equal(zero.ha_derelict, "0");
assert.equal(zero.n_derelict, "0");

assert.throws(
  () =>
    assertPublishedVdlDownloadRows(
      [{ n_sites: "4", n_derelict: "2", ha_derelict: "1.5" }],
      ["n_sites", "n_derelict", "ha_derelict"],
    ),
  /per-type count/,
);
assert.throws(
  () =>
    assertPublishedVdlDownloadRows(
      [{ n_sites: "4", n_vacant: "1", ha_vacant: "0.5" }],
      ["n_sites", "n_vacant", "ha_vacant"],
    ),
  /per-type count/,
);

const retired = [
  "Survey sites, not a title",
  "Owner class is a survey field",
  "Survey polygons are indicative",
];
const sources = readFileSync(join(repoRoot, "data/config/sources.yaml"), "utf8");
const api = readFileSync(join(repoRoot, "backend/layers/open_stats.py"), "utf8");
for (const phrase of retired) {
  assert.equal(sources.includes(phrase), false, phrase);
  assert.equal(api.includes(phrase), false, phrase);
}
assert.match(
  api,
  /Scotland-wide totals from the Scottish Vacant and Derelict Land Survey, by owner type\./,
);

console.log("test-vdl-dz-3: ok");
