/**
 * T-C3 — pin Esri CSP origins on the real contentSecurityPolicy export.
 * Default: import from next.config.ts. Self-test passes --csp <string>.
 */
import assert from "node:assert/strict";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

const EXPECTED_ARCGIS = [
  "https://basemapstyles-api.arcgis.com",
  "https://ibasemaps-api.arcgis.com",
  "https://basemaps-api.arcgis.com",
  "https://cdn.arcgis.com",
].sort();

/** Base sha e3b18452 — every non-Esri token must stay. */
const BASE_DIRECTIVES = {
  "default-src": ["'self'"],
  "base-uri": ["'self'"],
  "object-src": ["'none'"],
  "form-action": ["'self'", "https://formspree.io"],
  "frame-ancestors": ["'self'"],
  "script-src": [
    "'self'",
    "'unsafe-inline'",
    "https://static.cloudflareinsights.com",
  ],
  "style-src": ["'self'", "'unsafe-inline'"],
  "img-src": ["'self'", "data:", "blob:", "https://tiles.openfreemap.org"],
  "font-src": ["'self'"],
  "connect-src": [
    "'self'",
    "https://formspree.io",
    "https://tiles.openfreemap.org",
    "https://cloudflareinsights.com",
    "http://localhost:*",
    "http://127.0.0.1:*",
    "https://localhost:*",
    "https://127.0.0.1:*",
    "ws://localhost:*",
    "ws://127.0.0.1:*",
    "wss://localhost:*",
    "wss://127.0.0.1:*",
  ],
  "worker-src": ["'self'", "blob:"],
  "child-src": ["'self'", "blob:"],
};

const NO_ARCGIS_DIRECTIVES = [
  "script-src",
  "style-src",
  "worker-src",
  "child-src",
  "font-src",
  "default-src",
];

/**
 * @param {string} csp
 * @returns {Map<string, string[]>}
 */
export function parseCsp(csp) {
  /** @type {Map<string, string[]>} */
  const out = new Map();
  for (const part of csp.split(";")) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const [name, ...rest] = trimmed.split(/\s+/);
    out.set(name, rest);
  }
  return out;
}

/**
 * @param {string} src
 */
function isArcGisOrigin(src) {
  try {
    const u = new URL(src);
    return u.hostname === "arcgis.com" || u.hostname.endsWith(".arcgis.com");
  } catch {
    return /arcgis\.com/i.test(src);
  }
}

/**
 * @param {string} csp
 * @returns {{ ok: true } | { ok: false, message: string }}
 */
export function checkEsriCsp(csp) {
  const directives = parseCsp(csp);

  // (ii) wildcards — before (i) so M-C3 reports the wildcard message.
  for (const [name, sources] of directives) {
    for (const src of sources) {
      if (src === "https:" || src === "*") {
        return {
          ok: false,
          message: `esri-csp: wildcard source ${src} in ${name}`,
        };
      }
      if (/arcgis/i.test(src) && src.includes("*")) {
        return {
          ok: false,
          message: `esri-csp: wildcard source ${src} in ${name}`,
        };
      }
    }
  }

  // (iii) no arcgis outside connect-src / img-src — before (iv) exact match.
  for (const name of NO_ARCGIS_DIRECTIVES) {
    const sources = directives.get(name) ?? [];
    if (sources.some((src) => /arcgis/i.test(src))) {
      return { ok: false, message: `esri-csp: arcgis origin in ${name}` };
    }
  }

  // (i) exact Esri origin sets on connect-src and img-src.
  for (const name of ["connect-src", "img-src"]) {
    const actual = directives.get(name) ?? [];
    const arcgis = [...new Set(actual.filter(isArcGisOrigin))].sort();
    if (arcgis.join("\0") !== EXPECTED_ARCGIS.join("\0")) {
      return {
        ok: false,
        message: `esri-csp: ${name} arcgis origins are ${JSON.stringify(arcgis)}, expected ${JSON.stringify(EXPECTED_ARCGIS)}`,
      };
    }
  }

  // (iv) every base directive still present and unchanged (Esri only added to img/connect).
  for (const name of Object.keys(BASE_DIRECTIVES)) {
    if (!directives.has(name)) {
      return { ok: false, message: `esri-csp: base directive changed: ${name}` };
    }
  }

  for (const [name, baseSources] of Object.entries(BASE_DIRECTIVES)) {
    const actual = directives.get(name) ?? [];
    for (const src of baseSources) {
      if (!actual.includes(src)) {
        return { ok: false, message: `esri-csp: base directive changed: ${name}` };
      }
    }
    if (name !== "img-src" && name !== "connect-src") {
      if (
        actual.length !== baseSources.length ||
        actual.join(" ") !== baseSources.join(" ")
      ) {
        return { ok: false, message: `esri-csp: base directive changed: ${name}` };
      }
    }
  }

  return { ok: true };
}

async function loadCspFromNextConfig() {
  const mod = await import(
    pathToFileURL(join(frontendRoot, "next.config.ts")).href
  );
  assert.equal(
    typeof mod.contentSecurityPolicy,
    "string",
    "next.config.ts must export named contentSecurityPolicy",
  );
  return /** @type {string} */ (mod.contentSecurityPolicy);
}

async function main() {
  const { values } = parseArgs({
    options: {
      csp: { type: "string" },
    },
    allowPositionals: true,
  });

  const csp =
    typeof values.csp === "string" && values.csp.length > 0
      ? values.csp
      : await loadCspFromNextConfig();

  const result = checkEsriCsp(csp);
  if (!result.ok) {
    console.error(result.message);
    process.exit(1);
  }
  console.log("test-esri-csp: ok");
}

const isMain =
  process.argv[1] &&
  pathToFileURL(process.argv[1]).href === import.meta.url;

if (isMain) {
  await main();
}
