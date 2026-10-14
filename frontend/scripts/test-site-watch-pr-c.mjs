/**
 * Site-watch PR C — SLRG copy change list v2 acceptance (source scan).
 * Built-HTML grep runs in CI after `next build` when .next exists.
 */
import assert from "node:assert/strict";
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

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

// Source checks for approved public strings.
const mission = readFileSync(
  join(frontendRoot, "components/MissionContent.tsx"),
  "utf8",
);
assert.match(mission, /Why it matters/);
assert.match(mission, /deadweight loss/);
assert.match(
  mission,
  /It is not a bill or an official valuation\.\s*It does not propose a\s*rate\.\s*It shows the evidence\./,
);
assert.match(
  mission,
  /built around\s*Annual Ground Rent, the yearly rental value of the land itself/,
);

const method = readFileSync(
  join(frontendRoot, "components/MethodologyContent.tsx"),
  "utf8",
);
assert.match(
  method,
  /The land&apos;s value is\s*created by the community around it and by nature, not by the owner/,
);
assert.match(
  method,
  /Natural resource rents and the services of nature/,
);
assert.match(method, /Constraint: changes best use, adds no value/);
// SW-024: glossary heading; chip → label; no duplicate totals sentence.
assert.match(method, /Words we use/);
assert.doesNotMatch(method, /Three kinds of figure/);
assert.match(method, /different labels are never added into one total/);
assert.doesNotMatch(method, /\bchips?\b/i);
assert.doesNotMatch(
  method,
  /Totals per chip only, never across chips or price years/,
);
// SW-017: restored towns bullet word-for-word; no public yield jargon.
const TOWNS_BULLET =
  "In towns, we start from local house prices. We take away what it would cost to rebuild the house. What is left is roughly the value of the land. We turn that into a yearly rent.";
assert.ok(
  method.replace(/\s+/g, " ").includes(TOWNS_BULLET),
  "How it works must restore the approved In towns bullet word for word",
);
assert.doesNotMatch(method, /residual method|Data Zone grain|configured land yield/i);
assert.doesNotMatch(method, /4\.499%|4654e513|agr\.wide_range|× yield|→/);
assert.doesNotMatch(method, /\(agr\.\w+\)/);
assert.match(method, /about half to double\./);
assert.doesNotMatch(method, /about half to double\s*\(/);

const banner = readFileSync(join(frontendRoot, "lib/siteNav.ts"), "utf8");
assert.match(
  banner,
  /Annual Ground Rent figures are not published yet\. They are not a bill or an official valuation\./,
);
assert.doesNotMatch(banner, /still being built/);
assert.doesNotMatch(banner, /rates bill|tax proposal/i);

const chips = readFileSync(
  join(frontendRoot, "components/ConfidenceTag.tsx"),
  "utf8",
);
assert.match(chips, /Modelled/);
assert.match(chips, /Estimate \(no market price\)/);
assert.doesNotMatch(chips, /proxy: "Proxy"/);
assert.doesNotMatch(chips, /shadow: "Shadow"/);

// tagLabel visitor chips: Market / Modelled (API tags stay market / proxy / shadow).
for (const rel of ["lib/ledger.ts", "lib/placeStack.ts"]) {
  const src = readFileSync(join(frontendRoot, rel), "utf8");
  assert.match(src, /case "market":\s*return "Market"/);
  assert.match(src, /case "proxy":\s*return "Modelled"/);
  assert.match(src, /case "shadow":\s*return "Estimate"/);
  assert.match(src, /case "market_or_proxy":\s*return "Market \/ Modelled"/);
  assert.doesNotMatch(src, /return "market"/);
  assert.doesNotMatch(src, /return "proxy"/);
  assert.doesNotMatch(src, /return "shadow"/);
  assert.doesNotMatch(src, /return "market \/ proxy"/);
}

const placeCard = readFileSync(
  join(frontendRoot, "components/PlaceCard.tsx"),
  "utf8",
);
assert.match(placeCard, /name not loaded yet/);
assert.match(
  placeCard,
  /izCode\s*\?\s*izNote \|\| "name not loaded yet"/,
);

// SW-012: /developers must point at the public API page, not repo mdx paths.
const developers = readFileSync(
  join(frontendRoot, "app/developers/page.tsx"),
  "utf8",
);
assert.match(developers, /href=["']\/developers\/api["']/);
assert.doesNotMatch(developers, /docs\/mintlify|api-reference\.mdx/);
// SW-025: keep quality tags; lock the map-label line after them (add-only).
assert.match(developers, /quality-tag-inline/);
assert.match(developers, /QUALITY_TAGS\.map/);
assert.match(
  developers,
  /These describe where the input data comes from\. On the map, figures\s+are labelled Market, Modelled or Estimate\./,
);
assert.doesNotMatch(developers, /£/);

// SW-031: GET /ledger OpenAPI summary renamed (source pin; backend also asserts schema).
const platformRoutes = readFileSync(
  join(frontendRoot, "..", "backend/api/platform_routes.py"),
  "utf8",
);
assert.match(
  platformRoutes,
  /summary\s*=\s*["']Land rent by Data Zone \(developer\)["']/,
);
assert.doesNotMatch(
  platformRoutes,
  /summary\s*=\s*["']Natural Capital Ledger["']/,
);

// SW-031/032: OpenAPI summaries (when a schema is available locally / in CI).
const openapiCandidates = [
  join(frontendRoot, "public/openapi.json"),
  join(frontendRoot, ".next/openapi.json"),
  process.env.OPENAPI_JSON_PATH,
].filter(Boolean);
for (const openapiPath of openapiCandidates) {
  if (!existsSync(openapiPath)) continue;
  const schema = JSON.parse(readFileSync(openapiPath, "utf8"));
  const openapiViolations = [];
  for (const [path, methods] of Object.entries(schema.paths || {})) {
    for (const [method, op] of Object.entries(methods || {})) {
      if (!op || typeof op !== "object") continue;
      const summary = String(op.summary || "");
      if (!summary) continue;
      for (const { name, re } of [
        { name: "natural capital", re: /natural capital/i },
        { name: "ledger", re: /\bledger\b/i },
        { name: "£", re: /£/ },
      ]) {
        if (re.test(summary)) {
          openapiViolations.push(`${method.toUpperCase()} ${path}: ${name} in summary`);
        }
      }
    }
  }
  assert.equal(
    openapiViolations.length,
    0,
    `OpenAPI summary bans (${openapiPath}):\n${openapiViolations.join("\n")}`,
  );
}

// Built HTML acceptance (when present after next build).
const nextHtml = join(frontendRoot, ".next");
if (existsSync(nextHtml)) {
  const htmlFiles = walk(join(nextHtml, "server")).filter((f) =>
    f.endsWith(".html"),
  );
  // SW-031/032: £ / natural capital / ledger banned case-insensitively on every
  // rendered public page (including /developers/api). No path exemptions.
  // OpenAPI *summaries* are checked below (and in backend test_openapi_public_summaries).
  const forbidden = [
    { name: "natural capital", re: /natural capital/i },
    { name: "ledger", re: /\bledger\b/i },
    { name: "headline/shadow", re: /headline\s*\/\s*shadow/i },
    // SW-015: ban each word alone in visitor prose (CSS box-shadow is in <style>).
    { name: "headline", re: /\bheadline\b/i },
    { name: "shadow", re: /\bshadow\b/i },
    { name: "rates bill", re: /rates bill/i },
    { name: "tax proposal", re: /tax proposal/i },
    { name: "£", re: /£/ },
    { name: "chip Proxy", re: />\s*Proxy\s*</ },
    { name: "chip Shadow", re: />\s*Shadow\s*</ },
    { name: ".env", re: /\.env\b/ },
  ];
  // SW-017: add-only bans for public HTML outside /developers (yield details OK there).
  // Scope narrowings (cleanup): × excludes aria-labelled buttons; \d+% only yield wording.
  const forbiddenOutsideDevelopers = [
    { name: "residual", re: /\bresidual\b/i },
    { name: "grain", re: /\bgrain\b/i },
    { name: "config", re: /\bconfig\b/i },
    { name: "hash", re: /\bhash\b/i },
    { name: "agr.*", re: /\bagr\.\w+/i },
    { name: "×", re: /×/ },
    { name: "→", re: /→/ },
    {
      name: "yield %",
      re: /(?:\byield\b[\s\S]{0,80}?\d+(\.\d+)?\s*%|\d+(\.\d+)?\s*%[\s\S]{0,80}?\byield\b)/i,
    },
  ];
  const violations = [];
  let methodologyProse = "";
  let developersProse = "";
  for (const file of htmlFiles) {
    const rel = relative(frontendRoot, file).replace(/\\/g, "/");
    const html = readFileSync(file, "utf8");
    // Strip scripts/styles, then code samples (keep scanning /developers prose).
    // Styles removed first so CSS box-shadow never hits the shadow word ban.
    // Aria-labelled buttons (close/dismiss ×) are stripped before the × ban only.
    const withoutAriaButtons = html.replace(
      /<button\b[^>]*\baria-label\b[^>]*>[\s\S]*?<\/button>/gi,
      " ",
    );
    const prose = html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<(pre|code)\b[\s\S]*?<\/\1>/gi, " ")
      .replace(/<[^>]+>/g, " ");
    const proseForTimes = withoutAriaButtons
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ")
      .replace(/<(pre|code)\b[\s\S]*?<\/\1>/gi, " ")
      .replace(/<[^>]+>/g, " ");
    for (const { name, re } of forbidden) {
      if (re.test(prose)) {
        violations.push(`${rel}: ${name}`);
      }
    }
    const isDevelopers = /(^|\/)developers(\/|$)/.test(rel);
    if (!isDevelopers) {
      for (const { name, re } of forbiddenOutsideDevelopers) {
        const scan = name === "×" ? proseForTimes : prose;
        if (re.test(scan)) {
          violations.push(`${rel}: ${name}`);
        }
      }
    } else {
      developersProse += ` ${prose}`;
    }
    if (/land value tax/i.test(prose)) {
      const agr = prose.search(/Annual Ground Rent/i);
      const lvt = prose.search(/land value tax/i);
      if (agr === -1 || agr > lvt) {
        violations.push(`${rel}: Annual Ground Rent must precede land value tax`);
      }
    }
    if (rel.includes("/methodology")) {
      methodologyProse += ` ${prose}`;
    }
  }
  if (methodologyProse) {
    const flat = methodologyProse.replace(/\s+/g, " ");
    assert.ok(
      flat.includes(TOWNS_BULLET),
      "built How it works HTML must contain the approved In towns bullet word for word",
    );
  }
  // SW-025: add-only — /developers is a client page (Suspense fallback in HTML);
  // the map-label line ships in SSR/static chunks after build.
  const SW025_LINE =
    "These describe where the input data comes from. On the map, figures are labelled Market, Modelled or Estimate.";
  if (developersProse) {
    const flat = developersProse.replace(/\s+/g, " ");
    let found = flat.includes(SW025_LINE);
    if (!found) {
      for (const dir of [
        join(nextHtml, "server", "chunks"),
        join(nextHtml, "static", "chunks"),
      ]) {
        if (!existsSync(dir)) continue;
        for (const file of walk(dir)) {
          if (!/\.(js|map)$/.test(file)) continue;
          if (readFileSync(file, "utf8").includes(SW025_LINE)) {
            found = true;
            break;
          }
        }
        if (found) break;
      }
    }
    assert.ok(
      found,
      "built /developers output must include the quality-tag map-label line (HTML or chunks)",
    );
  }
  assert.equal(
    violations.length,
    0,
    `PR C built-HTML acceptance:\n${violations.join("\n")}`,
  );
  console.log(
    `test-site-watch-pr-c: ok (source + ${htmlFiles.length} built HTML files)`,
  );
} else {
  console.log("test-site-watch-pr-c: ok (source; no .next — HTML grep skipped)");
}
