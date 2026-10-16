/**
 * LOGO-FIX-1 (SW-054 / SW-055):
 * - metadataBase + absolute og/twitter images default to https://scot-land.scot
 * - production build output must not embed localhost in those tags
 * - "Noun Project" / "Coquet" must not appear on the site
 *
 * Run: npm run test:logo-fix
 * After `npm run build`, also scans .next for og/twitter image URLs.
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const PROD = "https://scot-land.scot";
const OG_ABS = `${PROD}/og-image.png?v=h3`;

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

function walk(dir, out = []) {
  if (!existsSync(dir)) return out;
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".git") continue;
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) walk(full, out);
    else out.push(full);
  }
  return out;
}

// --- SW-054 source contracts ---
const social = readSrc("lib/socialMeta.ts");
assert.match(social, /DEFAULT_SITE_URL\s*=\s*"https:\/\/scot-land\.scot"/);
assert.match(social, /NEXT_PUBLIC_SITE_URL/);
assert.match(social, /function getSiteUrl/);
assert.match(social, /function getMetadataBase/);
assert.match(social, /function absoluteOgImageUrl/);
assert.match(social, /\/og-image\.png/);
assert.match(social, /\?v=h3/);

const layout = readSrc("app/layout.tsx");
assert.match(layout, /metadataBase:\s*getMetadataBase\(\)/);
assert.match(layout, /absoluteOgImageUrl\(\)/);
assert.doesNotMatch(
  layout,
  /images:\s*\[\s*"\/og-image\.png"\s*\]/,
  "twitter.images must not stay as a relative /og-image.png path",
);

// Default (no env override) must be prod absolute URL.
delete process.env.NEXT_PUBLIC_SITE_URL;
const { getSiteUrl, getMetadataBase, absoluteOgImageUrl, DEFAULT_SITE_URL } =
  await import(join(frontendRoot, "lib/socialMeta.ts"));
assert.equal(DEFAULT_SITE_URL, PROD);
assert.equal(getSiteUrl(), PROD);
assert.equal(getMetadataBase().origin, PROD);
assert.equal(absoluteOgImageUrl(), OG_ABS);
assert.doesNotMatch(absoluteOgImageUrl(), /localhost/i);

// --- SW-055: no Noun Project / Coquet on the site (app / components / lib) ---
const sourceRoots = [
  join(frontendRoot, "app"),
  join(frontendRoot, "components"),
  join(frontendRoot, "lib"),
];
const banned = [/Noun Project/i, /Coquet/i, /thenounproject\.com/i];
const hits = [];
for (const root of sourceRoots) {
  for (const file of walk(root)) {
    const rel = relative(frontendRoot, file).replace(/\\/g, "/");
    if (!/\.(tsx?|jsx?|mjs|mdx?|html|css)$/.test(rel)) continue;
    const text = readFileSync(file, "utf8");
    for (const re of banned) {
      if (re.test(text)) hits.push(`${rel} matches ${re}`);
    }
  }
}
assert.equal(
  hits.length,
  0,
  `SW-055: Noun Project / Coquet must not appear on the site:\n${hits.join("\n")}`,
);

const mission = readSrc("components/MissionContent.tsx");
assert.match(mission, /Scot-LAND logo: original design\./);
assert.doesNotMatch(mission, /Noun Project|Coquet|thenounproject/i);

// --- Build output scan (when .next exists) ---
const nextDir = join(frontendRoot, ".next");
if (existsSync(nextDir)) {
  const metaRe =
    /(?:property|name)=["'](?:og:image|twitter:image)["'][^>]*content=["']([^"']+)["']|content=["']([^"']+)["'][^>]*(?:property|name)=["'](?:og:image|twitter:image)["']/gi;
  const urlHits = [];
  const bad = [];
  const nounHits = [];
  for (const file of walk(nextDir)) {
    if (!/\.(html|rsc|js|json)$/.test(file)) continue;
    let text;
    try {
      text = readFileSync(file, "utf8");
    } catch {
      continue;
    }
    if (/Noun Project|Coquet|thenounproject\.com/i.test(text)) {
      nounHits.push(relative(frontendRoot, file));
    }
    if (!/og:image|twitter:image|og-image\.png/.test(text)) continue;
    let m;
    metaRe.lastIndex = 0;
    while ((m = metaRe.exec(text)) !== null) {
      const url = m[1] || m[2] || "";
      urlHits.push(url);
      if (!url.startsWith(PROD) || /localhost/i.test(url)) {
        bad.push(`${relative(frontendRoot, file)}: ${url}`);
      }
    }
    // Also catch JSON-ish absolute paths baked for social images.
    if (/localhost[^\s"']*og-image\.png/i.test(text)) {
      bad.push(
        `${relative(frontendRoot, file)}: localhost … og-image.png in build`,
      );
    }
  }
  assert.equal(
    nounHits.length,
    0,
    `SW-055: Noun Project / Coquet must not appear in build:\n${nounHits.join("\n")}`,
  );
  assert.ok(
    urlHits.length > 0 ||
      walk(nextDir).some((f) => {
        try {
          return /og-image\.png/.test(readFileSync(f, "utf8"));
        } catch {
          return false;
        }
      }),
    "expected built output to mention og-image.png",
  );
  assert.equal(
    bad.length,
    0,
    `SW-054: production build must not use localhost og/twitter images:\n${bad.join("\n")}`,
  );
  // Every captured meta URL must be the prod absolute image.
  for (const url of urlHits) {
    assert.ok(
      url.startsWith(PROD) && url.includes("og-image.png"),
      `og/twitter image must be absolute under ${PROD}: got ${url}`,
    );
    assert.doesNotMatch(url, /localhost/i);
  }
}

console.log("test-logo-fix: ok");
