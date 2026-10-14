/**
 * Site rewrite item 9 — jargon sweep on public pages (excludes /developers*).
 * Acceptance: visitor-facing prose must not contain internal names.
 * Run via test-site-rewrite-pr2 (CI already wires that script).
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

/** Spec item 9 forbidden terms (word-aware where needed). */
const FORBIDDEN = [
  { name: "PostGIS", re: /PostGIS/i },
  { name: "503", re: /\b503\b/ },
  { name: "ECONOMIC_RULES", re: /ECONOMIC_RULES/ },
  { name: "DATA_LICENSING", re: /DATA_LICENSING/ },
  { name: "python -m", re: /python\s+-m/i },
  { name: "CI", re: /\bCI\b/ },
  { name: "fixture", re: /\bfixture\b/i },
  { name: "run hash", re: /run\s+hash/i },
  { name: "yield calibration", re: /yield\s+calibration/i },
  { name: "band level", re: /band\s+level/i },
  { name: "value_tier", re: /value_tier/i },
  { name: "bbox", re: /\bbbox\b/i },
];

const PUBLIC_ROOTS = ["app", "components", "lib"];

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    if (name === "node_modules" || name === ".next") continue;
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      // Spec: jargon allowed on /developers*
      if (name === "developers") continue;
      walk(full, out);
    } else if (/\.(tsx|ts|jsx|js)$/.test(name)) {
      out.push(full);
    }
  }
  return out;
}

/** Drop // and /* * / comments so identifiers in comments are ignored. */
function stripComments(src) {
  return src
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/(^|[^:])\/\/.*$/gm, "$1");
}

/**
 * Prose candidates: quoted strings that look like visitor copy
 * (contain whitespace), plus JSX text nodes with whitespace.
 */
function extractProse(src) {
  const cleaned = stripComments(src);
  const hits = [];
  const quoted =
    /(["'`])((?:\\.|(?!\1)[\s\S])*?)\1/g;
  let m;
  while ((m = quoted.exec(cleaned)) !== null) {
    const body = m[2];
    if (/\s/.test(body)) hits.push(body);
  }
  // JSX / HTML text between tags: >...words...<
  const jsxText = />([^<>{]+)</g;
  while ((m = jsxText.exec(cleaned)) !== null) {
    const body = m[1].replace(/\s+/g, " ").trim();
    if (body && /\s/.test(body)) hits.push(body);
  }
  return hits;
}

const files = PUBLIC_ROOTS.flatMap((root) =>
  walk(join(frontendRoot, root)),
);

const violations = [];
for (const file of files) {
  const rel = relative(frontendRoot, file).replace(/\\/g, "/");
  // Internal-only preview routes still 404 publicly, but keep them clean.
  const prose = extractProse(readFileSync(file, "utf8"));
  for (const text of prose) {
    for (const { name, re } of FORBIDDEN) {
      if (re.test(text)) {
        violations.push(`${rel}: "${name}" in «${text.slice(0, 120)}»`);
      }
    }
  }
}

assert.equal(
  violations.length,
  0,
  `jargon on public pages:\n${violations.join("\n")}`,
);

console.log(
  `test-site-rewrite-jargon: ok (${files.length} files, prose clean)`,
);
