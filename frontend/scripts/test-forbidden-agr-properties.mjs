/**
 * Public frontend source must not reference FORBIDDEN_PUBLIC_AGR_PROPERTIES
 * (kept in sync with georgist.publication_rules / check_publishable.py).
 */
import assert from "node:assert/strict";
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const FORBIDDEN_PUBLIC_AGR_PROPERTIES = [
  "annual_ground_rent_plot_gbp",
  "site_rental_per_sqm_gbp",
  "site_capital_per_sqm_gbp",
  "net_contribution_plot_gbp",
  "gross_plot_liability_gbp",
  "vacant_full_agr_gbp",
  "agr_as_pct_of_price",
];

const here = dirname(fileURLToPath(import.meta.url));
const frontendRoot = join(here, "..");

/** Public app surfaces — not Dev/QA-only scripts that list the forbidden set. */
const SCAN_DIRS = ["app", "components", "lib"];

const SKIP_FILES = new Set([
  // This test file names the forbidden set on purpose.
  "scripts/test-forbidden-agr-properties.mjs",
]);

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    const st = statSync(path);
    if (st.isDirectory()) {
      if (name === "node_modules" || name === ".next") continue;
      walk(path, out);
      continue;
    }
    if (!/\.(ts|tsx|js|mjs|jsx)$/.test(name)) continue;
    out.push(path);
  }
  return out;
}

const hits = [];
for (const dir of SCAN_DIRS) {
  const abs = join(frontendRoot, dir);
  for (const file of walk(abs)) {
    const rel = relative(frontendRoot, file).replaceAll("\\", "/");
    if (SKIP_FILES.has(rel)) continue;
    const text = readFileSync(file, "utf8");
    for (const prop of FORBIDDEN_PUBLIC_AGR_PROPERTIES) {
      if (text.includes(prop)) {
        hits.push(`${rel}: ${prop}`);
      }
    }
  }
}

assert.equal(
  hits.length,
  0,
  `Public frontend must not reference forbidden AGR £ properties:\n${hits.join("\n")}`,
);

// ScotlandMap must not import the removed AgrBreakdown panel.
const scotlandMap = readFileSync(
  join(frontendRoot, "components/ScotlandMap.tsx"),
  "utf8",
);
assert.equal(
  /from\s+["']\.\/AgrBreakdown["']/.test(scotlandMap),
  false,
  "ScotlandMap must not import AgrBreakdown",
);
assert.equal(
  /AgrBreakdown/.test(scotlandMap),
  false,
  "ScotlandMap must not reference AgrBreakdown",
);

console.log("test-forbidden-agr-properties: ok");
