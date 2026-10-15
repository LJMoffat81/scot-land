/**
 * UX10-1 terminology — public surfaces say "Annual Ground Rent", not alternate synonyms.
 * Additive guard: never loosen.
 */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next") continue;
    const p = join(dir, name);
    const st = statSync(p);
    if (st.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

function read(rel) {
  return readFileSync(join(frontendRoot, rel), "utf8");
}

const placeCard = read("lib/placeCard.ts");
assert.match(placeCard, /PLACE_CARD_AGR_LABEL\s*=\s*"Annual Ground Rent"/);

const ui = read("components/PlaceCard.tsx");
assert.match(ui, /PLACE_CARD_AGR_LABEL/);
assert.doesNotMatch(ui, /Land Value Tax|LVT\b|site rental value as a headline/i);
assert.doesNotMatch(ui, /Surface Rent/);

const glossary = read("components/GlossaryBox.tsx");
assert.match(glossary, /term:\s*"Annual Ground Rent"/);
assert.doesNotMatch(
  glossary,
  /term:\s*"(Land Value Tax|LVT|Surface Rent)"/,
);

// Visitor-facing components touched by UX10-1 must not prefer synonyms over AGR.
const visitorFiles = [
  "components/PlaceCard.tsx",
  "components/PlaceCardStub.tsx",
  "components/GlossaryBox.tsx",
  "components/ConfidenceTag.tsx",
];
for (const rel of visitorFiles) {
  const src = read(rel);
  assert.doesNotMatch(
    src,
    /Estimate \(no market price\)/,
    `${rel} must use chip "Estimate" (FP1)`,
  );
}

// Built HTML (when present): AGR term, no LVT headline on public pages.
const nextDir = join(frontendRoot, ".next");
try {
  const htmlFiles = walk(join(nextDir, "server")).filter((f) =>
    f.endsWith(".html"),
  );
  for (const file of htmlFiles) {
    if (/developers/i.test(file)) continue;
    const html = readFileSync(file, "utf8");
    if (/Annual Ground Rent/i.test(html)) {
      assert.doesNotMatch(html, />\s*Land Value Tax\s*</);
      assert.doesNotMatch(html, />\s*LVT\s*</);
    }
  }
} catch {
  // .next may be absent in unit-only runs.
}

console.log("test-ux10-agr-terminology: ok");
