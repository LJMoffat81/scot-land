/**
 * Visitor production build must not ship test hooks.
 * Run after `npm run build` with NEXT_PUBLIC_E2E_HOOKS unset.
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const frontendRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const roots = [join(frontendRoot, ".next", "static"), join(frontendRoot, ".next", "server")];
const needles = [
  "__SC_CONTACT_FORM_ID",
  "__map",
  "__SCOT_LAND_MAP__",
  "__SCOT_LAND_GRID3__",
];

/** @type {string[]} */
const hits = [];

function walk(dir) {
  let entries;
  try {
    entries = readdirSync(dir);
  } catch {
    return;
  }
  for (const name of entries) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) {
      walk(full);
      continue;
    }
    if (!name.endsWith(".js")) continue;
    const text = readFileSync(full, "utf8");
    for (const needle of needles) {
      if (text.includes(needle)) hits.push(`${full}: ${needle}`);
    }
  }
}

for (const root of roots) walk(root);

assert.ok(hits.length === 0, `test hook in production bundle:\n${hits.join("\n")}`);
console.log("test-no-test-hook: ok");
