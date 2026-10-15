/**
 * Unit: CHECK_MEANINGS ids === LEDGER_CHECK_ORDER (exact order + set).
 * Run: npm run test:check-meanings
 */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const { CHECK_MEANINGS } = await import(
  pathToFileURL(join(frontendRoot, "lib/checkMeanings.ts")).href
);

const ledgerSrc = readFileSync(join(frontendRoot, "lib/ledger.ts"), "utf8");
const orderBlock = ledgerSrc.match(
  /export const LEDGER_CHECK_ORDER = \[([\s\S]*?)\] as const/,
);
assert.ok(orderBlock, "LEDGER_CHECK_ORDER export missing in lib/ledger.ts");
const ledgerCheckOrder = [...orderBlock[1].matchAll(/"([^"]+)"/g)].map(
  (m) => m[1],
);

const meaningIds = Object.keys(CHECK_MEANINGS);
assert.deepEqual(
  meaningIds,
  ledgerCheckOrder,
  "CHECK_MEANINGS keys must equal LEDGER_CHECK_ORDER exactly",
);

const EXPECTED = {
  "C-hectare": "Each hectare is counted once.",
  "C-turbine":
    "Wind turbine sites are counted once and only where they stand.",
  "C-aqua": "Fish farm sites are counted once and only at sea.",
  "C-mineral": "Mineral sites are counted once.",
  "C-forest": "Woodland is counted once.",
  "C-planning":
    "Planning allocations change best use but add no value on their own.",
  "C-overlay": "Limits on use change best use and add no value.",
  "C-overlap": "Where layers overlap, the land is not counted twice.",
  "C-totals":
    "Totals are added up per label only, never across labels or price years.",
  "C-cap": "The yield used stays inside its agreed cap.",
};

assert.deepEqual(CHECK_MEANINGS, EXPECTED);
assert.equal(meaningIds.length, 10);

console.log("test-check-meanings: ok");
