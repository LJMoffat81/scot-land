#!/usr/bin/env node
/** Unit checks for catalogUiDrift logic (no test runner required). */

import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function assert(cond, msg) {
  if (!cond) {
    console.error(`FAIL: ${msg}`);
    process.exit(1);
  }
}

function checkCatalogUiDrift(liveIds, toggleIds) {
  const live = [...new Set(liveIds)].sort();
  const toggles = [...new Set(toggleIds)].sort();
  const toggleSet = new Set(toggles);
  const missingToggles = live.filter((id) => !toggleSet.has(id));
  return { ok: missingToggles.length === 0, missingToggles };
}

const ok = checkCatalogUiDrift(
  ["agr_value", "boundaries", "vdl"],
  ["agr_value", "boundaries", "vdl", "public_crown"],
);
assert(ok.ok, "expected coverage OK");

const bad = checkCatalogUiDrift(
  ["agr_value", "boundaries", "new_live"],
  ["agr_value", "boundaries"],
);
assert(!bad.ok, "expected drift failure");
assert(
  bad.missingToggles.includes("new_live"),
  "missing toggle should include new_live",
);

const run = spawnSync("node", [join(root, "scripts", "check-catalog-ui-drift.mjs")], {
  encoding: "utf8",
});
assert(run.status === 0, `check-catalog-ui-drift failed: ${run.stderr || run.stdout}`);

const driftRun = spawnSync(
  "node",
  [join(root, "scripts", "check-catalog-ui-drift.mjs")],
  {
    encoding: "utf8",
    env: {
      ...process.env,
      LIVE_CATALOG_IDS: JSON.stringify(["agr_value", "ghost_live"]),
    },
  },
);
assert(driftRun.status !== 0, "expected exit 1 when live id lacks toggle");
assert(
  (driftRun.stderr + driftRun.stdout).includes("ghost_live"),
  "stderr should name ghost_live",
);

console.log("OK: catalog UI drift unit checks passed");
