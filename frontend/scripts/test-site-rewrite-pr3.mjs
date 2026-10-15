/**
 * Site rewrite PR3 — developers page + downloads (items 3, 4, 5).
 * Run: npm run test:site-rewrite-pr3
 */
import assert from "node:assert/strict";
import { existsSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

function readSrc(relPath) {
  return readFileSync(join(frontendRoot, relPath), "utf8");
}

const { formatDownloadBytes } = await import(
  pathToFileURL(join(frontendRoot, "lib/downloadManifest.ts")).href
);

assert.equal(formatDownloadBytes(null), "Not packaged yet");
assert.equal(formatDownloadBytes(undefined), "Not packaged yet");
assert.equal(formatDownloadBytes(512), "512 B");
assert.match(formatDownloadBytes(2048), /KB/);
assert.match(formatDownloadBytes(2_500_000), /MB/);
assert.doesNotMatch(
  readSrc("app/developers/page.tsx"),
  /Size\s*—|Size —/,
);
assert.match(
  readSrc("app/developers/page.tsx"),
  /Not packaged yet/,
);

// --- Item 5: manifest + files ---
const downloadsDir = join(frontendRoot, "public/downloads");
assert.ok(
  existsSync(downloadsDir),
  "public/downloads missing — run build-download-bundles",
);
const manifest = JSON.parse(
  readFileSync(join(downloadsDir, "manifest.json"), "utf8"),
);
assert.equal(manifest.version, 1);
assert.ok(Array.isArray(manifest.bundles));

const expectedIds = [
  "vdl-dz2022",
  "vdl-dz2011",
  "ldp",
  "dz2022",
  "crofting",
  "catalog",
];
assert.deepEqual(
  manifest.bundles.map((b) => b.id),
  expectedIds,
);

// DZ2022 is the main VDL pack (first). updated = survey year; zone_set = DZ vintage.
assert.equal(manifest.bundles[0].id, "vdl-dz2022");
assert.equal(manifest.bundles[0].updated, "2025");
assert.equal(manifest.bundles[0].zone_set, "2022");
assert.equal(manifest.bundles[1].id, "vdl-dz2011");
assert.equal(manifest.bundles[1].updated, "2025");
assert.equal(manifest.bundles[1].zone_set, "2011");

// Top-level updated is the VDL survey year (data date), not a zone set or placeholder.
assert.equal(manifest.updated, "2025");
assert.notEqual(manifest.updated, "2026-06-08");
for (const bundle of manifest.bundles) {
  assert.notEqual(
    bundle.updated,
    "2026-06-08",
    `${bundle.id} updated must be a real vintage, not 2026-06-08`,
  );
}

for (const bundle of manifest.bundles) {
  assert.ok(bundle.name);
  assert.ok(bundle.format);
  assert.ok(bundle.licence);
  assert.ok(bundle.api_anchor);
  assert.ok(bundle.updated);
  if (bundle.file) {
    assert.ok(bundle.href?.startsWith("/downloads/"));
    const filePath = join(downloadsDir, bundle.file);
    assert.ok(existsSync(filePath), `missing ${bundle.file}`);
    assert.equal(statSync(filePath).size, bundle.bytes);
    if (bundle.file.endsWith(".csv")) {
      const header = readFileSync(filePath, "utf8").split(/\r?\n/, 1)[0];
      assert.match(header, /estimate_label/);
      assert.match(header, /licence_attribution/);
    }
  } else {
    assert.equal(bundle.href, null);
  }
}

assert.ok(
  manifest.bundles.some((b) => b.id === "vdl-dz2022" && b.file),
  "VDL DZ2022 CSV should be packaged when rollup exists",
);
assert.ok(
  manifest.bundles.some((b) => b.id === "vdl-dz2011" && b.file),
  "VDL DZ2011 CSV should be packaged when rollup exists",
);
assert.ok(
  manifest.bundles.some((b) => b.id === "catalog" && b.file),
  "source catalogue CSV should always be packaged",
);
assert.ok(
  manifest.bundles.some((b) => b.id === "ldp" && !b.file),
  "LDP GeoJSON missing → JSON (for developers)",
);
assert.equal(
  existsSync(join(downloadsDir, "vacant-derelict-land.csv")),
  false,
  "combined vacant-derelict-land.csv must be removed",
);

const catalogue = readFileSync(
  join(downloadsDir, "source-catalogue.csv"),
  "utf8",
);
assert.equal(catalogue.includes("£"), false);
assert.equal(/agr_plot|rent_per_sqm|site_capital/i.test(catalogue), false);
assert.match(catalogue, /not applicable: catalogue entry/);
assert.equal(
  catalogue.includes("not applicable: hectares and counts"),
  false,
  "catalogue must use catalogue-entry estimate_label, not hectares/counts",
);
assert.match(
  catalogue,
  /Contains OS data © Crown copyright and database right 2026/,
);
assert.match(catalogue, /Registers of Scotland/);
const inspireLine = catalogue
  .split(/\r?\n/)
  .find((line) => line.startsWith("inspire_parcels,"));
assert.ok(inspireLine);
assert.match(inspireLine, /Registers of Scotland/);
assert.match(inspireLine, /not applicable: catalogue entry/);
assert.match(
  inspireLine,
  /Contains OS data © Crown copyright and database right 2026/,
);

const vdl2022 = readFileSync(
  join(downloadsDir, "vacant-derelict-land-dz2022.csv"),
  "utf8",
);
assert.match(vdl2022, /estimate_label/);
assert.match(vdl2022, /licence_attribution/);
assert.match(vdl2022, /Scottish Vacant and Derelict Land Survey 2025/);
assert.equal(vdl2022.includes("£"), false);
// All data rows are vintage 2022
const vdlRows = vdl2022.trim().split(/\r?\n/).slice(1);
assert.ok(vdlRows.length > 0);
for (const row of vdlRows.slice(0, 20)) {
  assert.match(row, /,2022,/);
}

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
assert.match(developers, /zone_set/);
assert.match(developers, /Zone set/);
assert.match(developers, /download-card-summary/);
assert.match(developers, /formatDownloadBytes\(bundle\.bytes\)/);
assert.match(developers, /bundle\.whats_in_it/);
assert.match(developers, /\/layers\/…\?south=&west=&north=&east=/);
assert.match(developers, /Full API reference/);
assert.match(developers, /Technical checks/);
assert.match(developers, /Source code/);

// Each packaged bundle has bytes + a one-line grain note (e.g. One row per Data Zone).
for (const bundle of manifest.bundles) {
  assert.ok(
    typeof bundle.whats_in_it === "string" && bundle.whats_in_it.length > 0,
    `${bundle.id} needs whats_in_it`,
  );
  assert.doesNotMatch(
    bundle.whats_in_it,
    /£/,
    `${bundle.id} whats_in_it must not contain £`,
  );
  if (bundle.file) {
    assert.ok(
      typeof bundle.bytes === "number" && bundle.bytes > 0,
      `${bundle.id} packaged file must report bytes`,
    );
  }
}
assert.match(
  manifest.bundles.find((b) => b.id === "vdl-dz2022").whats_in_it,
  /One row per Data Zone, 2022 set/,
);
assert.match(
  manifest.bundles.find((b) => b.id === "vdl-dz2011").whats_in_it,
  /One row per Data Zone, 2011 set/,
);

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

const downloadsSection = developers.slice(
  developers.indexOf('id="downloads"'),
  developers.indexOf('id="api"'),
);
assert.doesNotMatch(downloadsSection, /href=\{?["'`]\/api\//);
assert.doesNotMatch(downloadsSection, /GET \/api\//);

assert.doesNotMatch(developers, /<a[^>]+href=["']\/layers/);
assert.match(
  developers,
  /<code className="api-path-code">\{LAYERS_BBOX\}<\/code>/,
);

const checks = readSrc("app/developers/checks/page.tsx");
assert.doesNotMatch(checks, /Pre-registered test log/);
assert.match(checks, /Known issue/);
assert.match(checks, /check-test-log/);
assert.doesNotMatch(checks, /<a[^>]*>\s*Pre-registered/);

console.log("test-site-rewrite-pr3: ok");
