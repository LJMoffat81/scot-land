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

// Built HTML acceptance (when present after next build).
const nextHtml = join(frontendRoot, ".next");
if (existsSync(nextHtml)) {
  const htmlFiles = walk(join(nextHtml, "server")).filter((f) =>
    f.endsWith(".html"),
  );
  const forbidden = [
    { name: "natural capital", re: /natural capital/i },
    { name: "rates bill", re: /rates bill/i },
    { name: "tax proposal", re: /tax proposal/i },
    { name: "£", re: /£/ },
    { name: "chip Proxy", re: />\s*Proxy\s*</ },
    { name: "chip Shadow", re: />\s*Shadow\s*</ },
  ];
  const violations = [];
  for (const file of htmlFiles) {
    const rel = relative(frontendRoot, file);
    if (rel.includes("developers")) continue; // code samples / API docs
    const html = readFileSync(file, "utf8");
    // Strip script/json blobs roughly
    const prose = html
      .replace(/<script[\s\S]*?<\/script>/gi, " ")
      .replace(/<style[\s\S]*?<\/style>/gi, " ");
    for (const { name, re } of forbidden) {
      if (re.test(prose)) {
        violations.push(`${rel}: ${name}`);
      }
    }
    if (/land value tax/i.test(prose)) {
      const agr = prose.search(/Annual Ground Rent/i);
      const lvt = prose.search(/land value tax/i);
      if (agr === -1 || agr > lvt) {
        violations.push(`${rel}: Annual Ground Rent must precede land value tax`);
      }
    }
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
