/**
 * CI-DEDUP-1b-r2 static pins P1–P10.
 * Run: npm run test:ci-dedup-1b-r2
 * Smoke S1–S3 live in scripts/ci-smoke-paths.test.mjs (same npm script).
 */
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "../..");
const repoRoot = join(frontendRoot, "..");
const ciDir = join(frontendRoot, "e2e", "ci");
const fixturesDir = join(frontendRoot, "e2e", "fixtures");

const ESRI_SHA =
  "56cd9e94db57af5bffb9f4ed5982d81b9b7a3c5dd85edd0976b74fd11afd7efd";
const OFM_SHA = "9770f2771e416b31cf3157de297d11b015c1f5712bafe5730baa7da34bf4cefe";

const POSITRON_IDS = new Set(["background", "park", "water", "landcover_ice_shelf", "landcover_glacier", "landuse_residential", "landcover_wood", "waterway", "building", "tunnel_motorway_casing", "tunnel_motorway_inner", "aeroway-taxiway", "aeroway-runway-casing", "aeroway-area", "aeroway-runway", "road_area_pier", "road_pier", "highway_path", "highway_minor", "highway_major_casing", "highway_major_inner", "highway_major_subtle", "highway_motorway_casing", "highway_motorway_inner", "highway_motorway_subtle", "railway_transit", "railway_transit_dashline", "railway_service", "railway_service_dashline", "railway", "railway_dashline", "highway_motorway_bridge_casing", "highway_motorway_bridge_inner", "boundary_3", "boundary_2", "boundary_disputed", "waterway_line_label", "water_name_point_label", "water_name_line_label", "highway-name-path", "highway-name-minor", "highway-name-major", "highway-shield-non-us", "highway-shield-us-interstate", "road_shield_us", "airport", "label_other", "label_village", "label_town", "label_state", "label_city", "label_city_capital", "label_country_3", "label_country_2", "label_country_1"]);

const BANNED_P1 = [
  "skipStrictConsoleAssert",
  "filterNoise",
  "CI_OPTIONAL_FAIL_URL",
  "/404|503/",
  "(404|503)",
  "400|404|503",
];

function sha256(path) {
  return createHash("sha256").update(readFileSync(path)).digest("hex");
}

function listCiFiles() {
  const out = [];
  for (const name of readdirSync(ciDir)) {
    const p = join(ciDir, name);
    out.push(p);
  }
  return out;
}

test("P1 no banned console opt-outs or 404/503 filters in e2e/ci", () => {
  for (const file of listCiFiles()) {
    if (!file.endsWith(".ts") && !file.endsWith(".tsx") && !file.endsWith(".mjs")) continue;
    // Gate proof mentions banned tokens in assertion strings — still scanned; those
    // strings must not contain the literal banned substrings.
    const src = readFileSync(file, "utf8");
    const base = file.split("/").pop();
    for (const token of BANNED_P1) {
      if (src.includes(token)) {
        assert.fail(`P1: ${base} contains ${token}`);
      }
    }
  }
});

test("P2 no global backend/api/catch-all routes in fixtures/gate/helpers", () => {
  const files = [
    join(ciDir, "_fixtures.ts"),
    join(ciDir, "_consoleGate.ts"),
    join(ciDir, "_mapCardsHelpers.ts"),
  ];
  // Any route pattern whose first string arg mentions /backend/ or /api/
  // (covers **/backend/**, **/backend/**/*, **/api/…, etc.).
  const ROUTE_BACKEND_OR_API =
    /\.route\s*\(\s*(["'`])([^"'`]*?(?:\/backend\/|\/api\/)[^"'`]*)\1/g;

  for (const file of files) {
    const src = readFileSync(file, "utf8");
    const base = file.split("/").pop();
    if (src.includes('route("**/backend/**"') || src.includes("route('**/backend/**'")) {
      assert.fail(`P2: ${base} has a global backend route`);
    }
    if (src.includes('route("/api/') || src.includes("route('/api/")) {
      assert.fail(`P2: ${base} has a global /api/ route`);
    }
    if (src.includes('route("**/*"') || src.includes("route('**/*'")) {
      assert.fail(`P2: ${base} has a catch-all route`);
    }

    // Shared auto-fixture / gate must not stub any backend or /api path.
    // Helpers may still call explicit per-spec stubs (stubMapCardsBackend).
    if (base === "_fixtures.ts" || base === "_consoleGate.ts") {
      // Strip stubExternalHosts body — it only stubs EXTERNAL_HOSTS, never backend/api.
      const withoutExternal = src.replace(
        /export async function stubExternalHosts[\s\S]*?\n}\n/,
        "",
      );
      ROUTE_BACKEND_OR_API.lastIndex = 0;
      const hit = ROUTE_BACKEND_OR_API.exec(withoutExternal);
      if (hit) {
        assert.fail(
          `P2: ${base} has a backend/api route pattern ${hit[2]}`,
        );
      }
    }
  }
});

test("P3 every ci *.spec.ts imports test from ./_fixtures", () => {
  for (const name of readdirSync(ciDir)) {
    if (!name.endsWith(".spec.ts")) continue;
    const src = readFileSync(join(ciDir, name), "utf8");
    const fromFixtures = /import\s*\{[^}]*\btest\b[^}]*\}\s*from\s*["']\.\/_fixtures["']/.test(src);
    const fromPw = /import\s*\{[^}]*\btest\b[^}]*\}\s*from\s*["']@playwright\/test["']/.test(src);
    if (!fromFixtures || fromPw) {
      assert.fail(`P3: ${name} does not use ./_fixtures`);
    }
  }
});

test("P4 externalHostStub: false only in csp-esri-1", () => {
  for (const name of readdirSync(ciDir)) {
    if (!name.endsWith(".spec.ts")) continue;
    const src = readFileSync(join(ciDir, name), "utf8");
    if (!src.includes("externalHostStub: false")) continue;
    assert.equal(
      name,
      "csp-esri-1.spec.ts",
      `P4: externalHostStub: false in ${name}`,
    );
  }
});

test("P5 assertConsoleClean count >= 132", () => {
  let count = 0;
  for (const name of readdirSync(ciDir)) {
    if (!name.endsWith(".ts")) continue;
    const src = readFileSync(join(ciDir, name), "utf8");
    const matches = src.match(/assertConsoleClean\(/g);
    if (matches) count += matches.length;
  }
  assert.ok(count >= 132, `P5: assertConsoleClean count ${count} < 132`);
});

test("P6 fixture sha256 pins", () => {
  assert.equal(sha256(join(fixturesDir, "esri-imagery-style.json")), ESRI_SHA);
  assert.equal(sha256(join(fixturesDir, "ofm-style-min.json")), OFM_SHA);
});

test("P7 ofm-style-min layer ids ⊆ Positron + has symbol", () => {
  const style = JSON.parse(readFileSync(join(fixturesDir, "ofm-style-min.json"), "utf8"));
  const layers = style.layers || [];
  let symbols = 0;
  for (const layer of layers) {
    const id = layer.id;
    if (!POSITRON_IDS.has(id)) {
      assert.fail(`P7: unknown layer id ${id}`);
    }
    if (layer.type === "symbol") symbols += 1;
  }
  assert.ok(symbols >= 1, "P7: need ≥1 symbol layer");
});

test("P8 no empty catch bodies in e2e/ci", () => {
  for (const file of listCiFiles()) {
    if (!file.endsWith(".ts") && !file.endsWith(".tsx")) continue;
    const src = readFileSync(file, "utf8");
    const base = file.split("/").pop();
    if (/catch\s*\(\s*\)\s*\{\s*\}/.test(src) || /catch\s*\(\s*_\s*\)\s*\{\s*\}/.test(src)) {
      assert.fail(`P8: ${base} has empty catch`);
    }
  }
});

test("P9 frontend-batch-3 catalog 404 expectError ×2", () => {
  const src = readFileSync(join(ciDir, "frontend-batch-3.spec.ts"), "utf8");
  const needle = 'expectError({ urlPath: "/backend/layers/catalog", status: 404';
  const count = src.split(needle).length - 1;
  assert.equal(count, 2, `P9: expectError catalog 404 count ${count}`);
  const route404 = (src.match(/status:\s*404,\s*body:\s*"absent"/g) || []).length;
  assert.equal(route404, 2, `P9: catalog 404 routes ${route404}`);
});

test("P10 playwright.ci.config auto-discovery; no spec file lists", () => {
  const cfg = readFileSync(join(frontendRoot, "playwright.ci.config.ts"), "utf8");
  assert.match(cfg, /testDir:\s*"e2e\/ci"/);
  assert.match(cfg, /testMatch:\s*"\*\*\/\*\.spec\.ts"/);
  const pkg = readFileSync(join(frontendRoot, "package.json"), "utf8");
  const ciYml = readFileSync(join(repoRoot, ".github/workflows/ci.yml"), "utf8");
  assert.doesNotMatch(pkg, /\.spec\.ts/);
  // ci.yml may mention spec only in comments — ban explicit file lists of *.spec.ts paths
  assert.doesNotMatch(ciYml, /e2e\/ci\/[a-z0-9_-]+\.spec\.ts/);
});
