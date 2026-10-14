/**
 * Node asserts for data-state quality tag helpers (no Playwright / browser).
 * Mirrors frontend/lib/qualityTag.ts — keep in sync when changing logic.
 */
import assert from "node:assert/strict";

const QUALITY_TAGS = ["live", "derived", "modelled", "placeholder"];

const QUALITY_TAG_GLOSS = {
  live: "observed from a public source as-is",
  derived: "computed from open inputs by a stated method",
  modelled:
    "estimated by the residual / mass model; money figures stay unpublished until calibration is checked",
  placeholder: "not ready; never served on the public API or map",
};

function isQualityTag(value) {
  if (!value) return false;
  return QUALITY_TAGS.includes(value);
}

assert.deepEqual(QUALITY_TAGS, ["live", "derived", "modelled", "placeholder"]);
for (const tag of QUALITY_TAGS) {
  assert.equal(isQualityTag(tag), true);
  assert.equal(typeof QUALITY_TAG_GLOSS[tag], "string");
  assert.ok(QUALITY_TAG_GLOSS[tag].length > 8);
}
assert.equal(isQualityTag("linked"), false);
assert.equal(isQualityTag("gap"), false);
assert.equal(isQualityTag("market"), false);
assert.equal(isQualityTag("proxy"), false);
assert.equal(isQualityTag(""), false);
assert.equal(isQualityTag(null), false);

// Placeholder gloss must never claim public map service.
assert.match(QUALITY_TAG_GLOSS.placeholder, /never served/i);

console.log("test-quality-tags: ok");
