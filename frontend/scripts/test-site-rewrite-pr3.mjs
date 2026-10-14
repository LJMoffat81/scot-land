/**
 * Site rewrite PR3 — developers page + downloads (items 3, 4, 5).
 * Run: npm run test:site-rewrite-pr3
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

const {
  formatDownloadBytes,
} = await import(pathToFileURL(join(frontendRoot, "lib/downloadManifest.ts")).href);

assert.equal(formatDownloadBytes(null), "—");
assert.equal(formatDownloadBytes(512), "512 B");
assert.match(formatDownloadBytes(2048), /KB/);
assert.match(formatDownloadBytes(2_500_000), /MB/);

// --- Item 5: manifest + files ---
const downloadsDir = join(frontendRoot, "public/downloads");
assert.ok(existsSync(downloadsDir), "public/downloads missing — run build-download-bundles");
const manifest = JSON.parse(
  readFileSync(join(downloadsDir, "manifest.json"), "utf8"),
);
assert.equal(manifest.version, 1);
assert.ok(Array.isArray(manifest.bundles));
assert.equal(manifest.bundles.length, 5);

const expectedIds = ["vdl", "ldp", "dz2022", "crofting", "catalog"];
assert.deepEqual(
  manifest.bundles.map((b) => b.id),
  expectedIds,
);

for (const bundle of manifest.bundles) {
  assert.ok(bundle.name);
  assert.ok(bundle.format);
  assert.ok(bundle.licence);
  assert.ok(bundle.api_anchor);
  if (bundle.file) {
    assert.ok(bundle.href?.startsWith("/downloads/"));
    const filePath = join(downloadsDir, bundle.file);
    assert.ok(existsSync(filePath), `missing ${bundle.file}`);
    assert.equal(statSync(filePath).size, bundle.bytes);
  } else {
    assert.equal(bundle.href, null);
  }
}

assert.ok(
  manifest.bundles.some((b) => b.id === "vdl" && b.file),
  "VDL CSV should be packaged when rollup exists",
);
assert.ok(
  manifest.bundles.some((b) => b.id === "catalog" && b.file),
  "source catalogue CSV should always be packaged",
);
assert.ok(
  manifest.bundles.some((b) => b.id === "ldp" && !b.file),
  "LDP GeoJSON missing → JSON (for developers)",
);

const catalogue = readFileSync(
  join(downloadsDir, "source-catalogue.csv"),
  "utf8",
);
assert.equal(catalogue.includes("£"), false);
assert.equal(/agr_plot|rent_per_sqm|site_capital/i.test(catalogue), false);

// --- Item 5: Content-Disposition headers in next.config ---
const nextConfig = readSrc("next.config.ts");
assert.match(nextConfig, /Content-Disposition/);
assert.match(nextConfig, /\/downloads\/:file\*\.csv/);
assert.match(nextConfig, /\/downloads\/:file\*\.geojson/);
assert.match(nextConfig, /\/downloads\/:file\*\.zip/);

// --- Developers page structure (items 3–5) ---
const developers = readSrc("app/developers/page.tsx");
assert.match(developers, /id="downloads"/);
assert.match(developers, /id="api"/);
assert.match(developers, /JSON \(for developers\)/);
assert.match(developers, /manifest\.json/);
assert.match(developers, /CopyCodeButton/);
assert.match(developers, /\/layers\/…\?south=&west=&north=&east=/);
assert.match(developers, /Full API reference/);
assert.match(developers, /Technical checks/);
assert.match(developers, /Source code/);

// Item 4: each /api/*.json address appears once (API table only).
const apiPaths = [
  "/api/place.json?pc=EH1+1YZ",
  "/api/catalog.json",
  "/api/ledger.json",
  "/api/vdl.json",
  "/api/ldp.json",
  "/api/registers.json",
  "/api/common-good.json",
  "/api/crofting.json",
];
for (const path of apiPaths) {
  const count = developers.split(path).length - 1;
  assert.equal(count, 1, `${path} must appear exactly once on developers page`);
}

// Downloads section must not list GET /api/*.json as separate download links.
const downloadsSection = developers.slice(
  developers.indexOf('id="downloads"'),
  developers.indexOf('id="api"'),
);
assert.doesNotMatch(downloadsSection, /href=\{?["'`]\/api\//);
assert.doesNotMatch(downloadsSection, /GET \/api\//);

// Item 3: layers bbox is code, not an <a href="/layers...">
assert.doesNotMatch(developers, /<a[^>]+href=["']\/layers/);
assert.match(developers, /<code className="api-path-code">\{LAYERS_BBOX\}<\/code>/);

// --- Checks page: no fake "Pre-registered test log" link ---
const checks = readSrc("app/developers/checks/page.tsx");
assert.doesNotMatch(checks, /Pre-registered test log/);
assert.match(checks, /Known issue/);
assert.match(checks, /check-test-log/);
assert.doesNotMatch(checks, /<a[^>]*>\s*Pre-registered/);

console.log("test-site-rewrite-pr3: ok");
