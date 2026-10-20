/**
 * Self-test for test-esri-csp.mjs — one CSP string per failure case + clean.
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const script = join(here, "test-esri-csp.mjs");

const FOUR = [
  "https://basemapstyles-api.arcgis.com",
  "https://ibasemaps-api.arcgis.com",
  "https://basemaps-api.arcgis.com",
  "https://cdn.arcgis.com",
];

const BASE_PARTS = [
  "default-src 'self'",
  "base-uri 'self'",
  "object-src 'none'",
  "form-action 'self' https://formspree.io",
  "frame-ancestors 'self'",
  "script-src 'self' 'unsafe-inline' https://static.cloudflareinsights.com",
  "style-src 'self' 'unsafe-inline'",
  "font-src 'self'",
  "worker-src 'self' blob:",
  "child-src 'self' blob:",
];

const CONNECT_BASE =
  "'self' https://formspree.io https://tiles.openfreemap.org https://cloudflareinsights.com http://localhost:* http://127.0.0.1:* https://localhost:* https://127.0.0.1:* ws://localhost:* ws://127.0.0.1:* wss://localhost:* wss://127.0.0.1:*";
const IMG_BASE = "'self' data: blob: https://tiles.openfreemap.org";

function buildCsp({ connectExtra = FOUR, imgExtra = FOUR, scriptExtra = "", dropDefault = false } = {}) {
  const parts = [...BASE_PARTS];
  if (dropDefault) {
    const idx = parts.findIndex((p) => p.startsWith("default-src "));
    parts.splice(idx, 1);
  }
  if (scriptExtra) {
    const idx = parts.findIndex((p) => p.startsWith("script-src "));
    parts[idx] = `${parts[idx]} ${scriptExtra}`;
  }
  parts.push(`img-src ${IMG_BASE}${imgExtra.length ? ` ${imgExtra.join(" ")}` : ""}`);
  parts.push(
    `connect-src ${CONNECT_BASE}${connectExtra.length ? ` ${connectExtra.join(" ")}` : ""}`,
  );
  return parts.join("; ");
}

function run(csp) {
  const res = spawnSync(
    process.execPath,
    ["--experimental-strip-types", script, "--csp", csp],
    { encoding: "utf8" },
  );
  return {
    status: res.status ?? 1,
    stderr: (res.stderr || "").trim(),
    stdout: (res.stdout || "").trim(),
  };
}

const expectedSorted = [...FOUR].sort();

// Clean → exit 0
{
  const clean = buildCsp();
  const res = run(clean);
  assert.equal(res.status, 0, `clean failed: ${res.stderr}`);
  assert.match(res.stdout, /test-esri-csp: ok/);
}

// Each of the four origins missing in turn
for (const missing of FOUR) {
  const connectExtra = FOUR.filter((o) => o !== missing);
  const res = run(buildCsp({ connectExtra, imgExtra: FOUR }));
  assert.equal(res.status, 1, `missing ${missing} should exit 1`);
  const actual = connectExtra.slice().sort();
  const msg = `esri-csp: connect-src arcgis origins are ${JSON.stringify(actual)}, expected ${JSON.stringify(expectedSorted)}`;
  assert.equal(res.stderr, msg, `missing ${missing}: got ${res.stderr}`);
}

// Extra origin
{
  const connectExtra = [...FOUR, "https://www.arcgis.com"];
  const res = run(buildCsp({ connectExtra }));
  assert.equal(res.status, 1);
  const actual = [...FOUR, "https://www.arcgis.com"].sort();
  assert.equal(
    res.stderr,
    `esri-csp: connect-src arcgis origins are ${JSON.stringify(actual)}, expected ${JSON.stringify(expectedSorted)}`,
  );
}

// Wildcard
{
  const res = run(buildCsp({ connectExtra: ["https://*.arcgis.com"], imgExtra: FOUR }));
  assert.equal(res.status, 1);
  assert.equal(
    res.stderr,
    "esri-csp: wildcard source https://*.arcgis.com in connect-src",
  );
}

// arcgis in script-src
{
  const res = run(
    buildCsp({ scriptExtra: "https://basemapstyles-api.arcgis.com" }),
  );
  assert.equal(res.status, 1);
  assert.equal(res.stderr, "esri-csp: arcgis origin in script-src");
}

// Dropped base directive
{
  const res = run(buildCsp({ dropDefault: true }));
  assert.equal(res.status, 1);
  assert.equal(res.stderr, "esri-csp: base directive changed: default-src");
}

console.log("test-esri-csp.selftest: ok");
