/**
 * Link-check for /developers and /developers/checks (rewrite item 3).
 *
 * - No <a> without href on those pages
 * - No fake "Pre-registered test log" affordance
 * - Layers bbox pattern is never an <a href="/layers…">
 * - Same-origin string hrefs resolve to known routes or public files
 * - Packaged download files named in the manifest exist on disk
 *
 * Run: npm run check:developers-links
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const publicRoot = join(frontendRoot, "public");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

const pages = [
  "app/developers/page.tsx",
  "app/developers/checks/page.tsx",
  "app/developers/api/page.tsx",
  "app/developers/glossary/page.tsx",
];

const knownRoutes = new Set([
  "/",
  "/about",
  "/methodology",
  "/data",
  "/developers",
  "/developers/api",
  "/developers/checks",
  "/developers/glossary",
]);

function publicExists(urlPath) {
  const rel = urlPath.replace(/^\//, "").split("?")[0].split("#")[0];
  return existsSync(join(publicRoot, rel));
}

/** Match <a ...> including multiline tags. */
const anchorRe = /<a\b[\s\S]*?>/g;
const hrefAttrRe = /\bhref\s*=\s*(?:\{([\s\S]*?)\}|"([^"]*)"|'([^']*)')/;

for (const rel of pages) {
  const src = readSrc(rel);
  // SW-012: public /developers copy must not link repo paths; use /developers/api.
  assert.doesNotMatch(
    src,
    /docs\/mintlify|api-reference\.mdx|\.mdx["'`]/,
    `${rel}: must not link repo docs paths (SW-012); use /developers/api`,
  );
  assert.doesNotMatch(
    src,
    /href=["'`][^"'`]*docs\//,
    `${rel}: must not href repo docs/ paths (SW-012)`,
  );
  assert.doesNotMatch(
    src,
    /Pre-registered test log/,
    `${rel} must not use fake Pre-registered test log`,
  );
  assert.doesNotMatch(
    src,
    /<a[\s\S]*?href=["'`]\/layers/,
    `${rel}: /layers must not be styled as links`,
  );

  // Strip JSX/block comments so prose like "never an <a>" does not false-fail.
  const withoutComments = src.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
  let match;
  while ((match = anchorRe.exec(withoutComments)) !== null) {
    const tag = match[0];
    // Skip closing-only noise
    if (tag.startsWith("</")) continue;
    assert.match(tag, hrefAttrRe, `${rel}: <a> without href: ${tag.slice(0, 120)}`);
    const hm = hrefAttrRe.exec(tag);
    if (!hm) continue;
    const expr = (hm[1] || "").trim();
    const literal = hm[2] ?? hm[3];
    if (literal != null) {
      checkHref(rel, literal);
      continue;
    }
    // Dynamic hrefs allowed when clearly derived from known sources.
    assert.ok(
      /bundle\.href|row\.path|GITHUB_REPO|OPENAPI_URL|api_anchor|MINTLIFY/.test(
        expr,
      ) ||
        expr.includes("bundle.api_anchor") ||
        expr.startsWith("`#") ||
        expr.includes("${"),
      `${rel}: unexpected dynamic href expression: ${expr.slice(0, 80)}`,
    );
  }
}

function checkHref(rel, href) {
  if (!href || href.startsWith("#")) return;
  if (href.startsWith("mailto:")) return;
  if (/^https?:\/\//i.test(href)) return;
  if (href.startsWith("/downloads/")) {
    assert.ok(publicExists(href), `${rel}: missing download file ${href}`);
    return;
  }
  if (href.startsWith("/api/") || href.startsWith("/backend/")) return;
  const pathOnly = href.split("#")[0].split("?")[0];
  if (knownRoutes.has(href) || knownRoutes.has(pathOnly)) return;
  if (publicExists(href)) return;
  if (href.startsWith("/swagger-ui/")) {
    assert.ok(publicExists(href), `${rel}: missing ${href}`);
    return;
  }
  assert.fail(`${rel}: unknown same-origin href ${href}`);
}

const manifest = JSON.parse(
  readFileSync(join(publicRoot, "downloads/manifest.json"), "utf8"),
);
for (const bundle of manifest.bundles) {
  if (!bundle.file) continue;
  assert.ok(
    existsSync(join(publicRoot, "downloads", bundle.file)),
    `manifest file missing: ${bundle.file}`,
  );
}

const checks = readSrc("app/developers/checks/page.tsx");
assert.doesNotMatch(checks, /<summary[\s\S]*?>\s*Pre-registered/);
assert.match(checks, /check-test-log/);
assert.match(checks, /Known issue/);

// Glossary is developers-only — visitor pages must not link to it.
const visitorPages = [
  "app/page.tsx",
  "app/about/page.tsx",
  "app/methodology/page.tsx",
  "app/data/page.tsx",
  "components/MissionContent.tsx",
  "components/MethodologyContent.tsx",
  "lib/siteNav.ts",
];
for (const rel of visitorPages) {
  const src = readSrc(rel);
  assert.doesNotMatch(
    src,
    /\/developers\/glossary/,
    `${rel}: must not link to /developers/glossary`,
  );
}
assert.match(
  readSrc("app/developers/page.tsx"),
  /href=["']\/developers\/glossary["']/,
  "developers page must link to glossary",
);

// docs/GLOSSARY.md must match frontend/lib/developersGlossary.ts (Residual wording locked).
const glossaryMd = readFileSync(
  join(frontendRoot, "..", "docs", "GLOSSARY.md"),
  "utf8",
);
const glossaryTs = readSrc("lib/developersGlossary.ts");
assert.match(
  glossaryMd,
  /\*\*Residual\*\*: what remains of a sale price after taking off the depreciated cost of rebuilding the home \(allowing for its age\)\. The residual is the land value\./,
);
assert.match(
  glossaryTs,
  /term:\s*"Residual"/,
);
assert.match(
  glossaryTs,
  /what remains of a sale price after taking off the depreciated cost of rebuilding the home \(allowing for its age\)\. The residual is the land value\./,
);
assert.match(
  glossaryMd,
  /\*\*Estimate\*\* \(chip: Estimate\): a value for something with no market price, such as peat holding carbon\. It is shown for information only, and never added to other figures\./,
);
assert.match(
  glossaryMd,
  /\*\*Rent rate\*\*: the yearly share of a land's value used to turn it into a yearly rent\. It reflects long-run interest rates, risk and expected growth\./,
);
assert.doesNotMatch(glossaryMd, /£/);
assert.doesNotMatch(glossaryTs, /£/);

console.log("check-developers-links: ok");
