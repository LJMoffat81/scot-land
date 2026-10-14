/**
 * CI check: committed /downloads packs match a fresh build:downloads run.
 * Fails when someone edits the builder but forgets to regenerate the manifest.
 *
 * Run: npm run check:download-bundles-fresh
 */
import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");
const repoRoot = join(frontendRoot, "..");
const downloadsDir = join(frontendRoot, "public", "downloads");

function run(cmd, args, cwd) {
  const res = spawnSync(cmd, args, {
    cwd,
    encoding: "utf8",
    env: process.env,
  });
  if (res.status !== 0) {
    console.error(res.stdout);
    console.error(res.stderr);
    assert.fail(`${cmd} ${args.join(" ")} exited ${res.status}`);
  }
  return res;
}

assert.ok(existsSync(downloadsDir), "public/downloads missing");

// Rebuild in place, then require a clean git tree for that directory.
run("npm", ["run", "build:downloads"], frontendRoot);

const diff = spawnSync(
  "git",
  ["diff", "--exit-code", "--", "frontend/public/downloads"],
  { cwd: repoRoot, encoding: "utf8" },
);

if (diff.status !== 0) {
  console.error(diff.stdout);
  console.error(diff.stderr);
  assert.fail(
    "frontend/public/downloads is stale. Run `npm run build:downloads` and commit the result.",
  );
}

// Extra sanity: every packaged file named in the manifest exists and carries credits.
const manifest = JSON.parse(
  readFileSync(join(downloadsDir, "manifest.json"), "utf8"),
);
assert.ok(Array.isArray(manifest.bundles));
for (const bundle of manifest.bundles) {
  if (!bundle.file) continue;
  const path = join(downloadsDir, bundle.file);
  assert.ok(existsSync(path), `missing ${bundle.file}`);
  if (bundle.file.endsWith(".csv")) {
    const header = readFileSync(path, "utf8").split(/\r?\n/, 1)[0];
    assert.match(header, /estimate_label/, `${bundle.file} missing estimate_label`);
    assert.match(
      header,
      /licence_attribution/,
      `${bundle.file} missing licence_attribution`,
    );
  }
}

// No stale combined VDL file
assert.equal(
  existsSync(join(downloadsDir, "vacant-derelict-land.csv")),
  false,
  "stale vacant-derelict-land.csv must not remain (use per-vintage files)",
);

const names = readdirSync(downloadsDir);
assert.ok(names.includes("manifest.json"));
assert.ok(names.includes("vacant-derelict-land-dz2022.csv"));
assert.ok(names.includes("source-catalogue.csv"));

console.log("check-download-bundles-fresh: ok");
