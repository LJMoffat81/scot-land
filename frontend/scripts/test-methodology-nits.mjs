/**
 * Methodology nits after #6 / #91 FAIL:
 * - exact NRS credit on How it works
 * - exact /methodology research banner (experimental)
 * - shared banner and other pages must not show experimental
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const EXACT_NRS =
  "National Records of Scotland: © Crown copyright 2026, licensed under the Open Government Licence v3.0";
const EXACT_METHODOLOGY_BANNER =
  "Research estimate. Scot-LAND is experimental. Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.";
const EXACT_SHARED_BANNER =
  "Research estimate. Annual Ground Rent figures are not published yet. They are not a bill or an official valuation.";

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    if (name === "node_modules") continue;
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else if (/\.(html|tsx|ts|jsx|js)$/.test(name)) out.push(full);
  }
  return out;
}

function proseFromHtml(html) {
  return html
    .replace(/<script[\s\S]*?<\/script>/gi, " ")
    .replace(/<style[\s\S]*?<\/style>/gi, " ")
    .replace(/<(pre|code)\b[\s\S]*?<\/\1>/gi, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const {
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_TEXT,
  METHODOLOGY_RESEARCH_BANNER_BODY,
  METHODOLOGY_RESEARCH_BANNER_TEXT,
} = await import(pathToFileURL(join(frontendRoot, "lib/siteNav.ts")).href);

assert.equal(RESEARCH_BANNER_TEXT, EXACT_SHARED_BANNER);
assert.equal(METHODOLOGY_RESEARCH_BANNER_TEXT, EXACT_METHODOLOGY_BANNER);
assert.doesNotMatch(RESEARCH_BANNER_BODY, /experimental/i);
assert.match(METHODOLOGY_RESEARCH_BANNER_BODY, /experimental/);

const method = readFileSync(
  join(frontendRoot, "components/MethodologyContent.tsx"),
  "utf8",
);
assert.match(method, /variant=["']methodology["']/);
assert.ok(
  method.includes(EXACT_NRS),
  "MethodologyContent must include the exact NRS credit line",
);

const bannerComponent = readFileSync(
  join(frontendRoot, "components/ResearchBanner.tsx"),
  "utf8",
);
assert.match(bannerComponent, /METHODOLOGY_RESEARCH_BANNER_BODY/);
assert.match(bannerComponent, /variant\s*=\s*"default"/);

// Other public page surfaces that host ResearchBanner must not opt into methodology copy.
const otherPages = [
  "components/MissionContent.tsx",
  "app/data/page.tsx",
  "app/developers/page.tsx",
  "app/developers/api/page.tsx",
  "app/developers/checks/page.tsx",
  "app/place/page.tsx",
  "components/ScotlandMap.tsx",
];
for (const rel of otherPages) {
  const src = readFileSync(join(frontendRoot, rel), "utf8");
  assert.doesNotMatch(
    src,
    /variant=["']methodology["']/,
    `${rel} must not use the methodology banner variant`,
  );
  assert.doesNotMatch(
    src,
    /experimental/i,
    `${rel} must not show 'experimental'`,
  );
}

const nextHtml = join(frontendRoot, ".next");
if (existsSync(nextHtml)) {
  const htmlFiles = walk(join(nextHtml, "server")).filter((f) =>
    f.endsWith(".html"),
  );
  let sawMethodologyBanner = false;
  let sawMethodologyNrs = false;
  const violations = [];
  for (const file of htmlFiles) {
    const rel = relative(frontendRoot, file);
    const html = readFileSync(file, "utf8");
    const prose = proseFromHtml(html);
    const isMethodologyPage =
      /data-testid=["']methodology-page["']/.test(html) ||
      /data-banner-variant=["']methodology["']/.test(html) ||
      /[/\\]methodology\.(html|rsc)/i.test(rel);
    if (isMethodologyPage) {
      if (prose.includes(EXACT_METHODOLOGY_BANNER)) {
        sawMethodologyBanner = true;
      } else {
        violations.push(`${rel}: missing exact /methodology banner text`);
      }
      if (prose.includes(EXACT_NRS)) {
        sawMethodologyNrs = true;
      } else {
        violations.push(`${rel}: missing exact NRS credit`);
      }
    } else if (/experimental/i.test(prose)) {
      violations.push(`${rel}: other page shows 'experimental'`);
    }
  }
  assert.ok(
    sawMethodologyBanner,
    "built HTML must include the exact /methodology research banner",
  );
  assert.ok(sawMethodologyNrs, "built HTML must include the exact NRS credit");
  assert.equal(
    violations.length,
    0,
    `methodology nits built-HTML:\n${violations.join("\n")}`,
  );
  console.log(
    `test-methodology-nits: ok (source + ${htmlFiles.length} built HTML files)`,
  );
} else {
  console.log("test-methodology-nits: ok (source; no .next — HTML grep skipped)");
}
