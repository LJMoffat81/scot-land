#!/usr/bin/env node
/**
 * Frontend catalog ↔ UI drift check.
 *
 * Fails if any live catalog layer id (from fixture synced to platform_catalog,
 * or LIVE_CATALOG_IDS env JSON) lacks a UI toggle in catalogUiToggles.json.
 *
 * Backend pytest test_catalog_ui_drift.py asserts the same against live
 * platform_catalog() so CI catches catalog additions that skip the panel.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function checkCatalogUiDrift(liveIds, toggleIds) {
  const live = [...new Set(liveIds)].sort();
  const toggles = [...new Set(toggleIds)].sort();
  const toggleSet = new Set(toggles);
  const missingToggles = live.filter((id) => !toggleSet.has(id));
  return {
    ok: missingToggles.length === 0,
    live,
    toggles,
    missingToggles,
  };
}

/** Keep in sync with backend/layers/platform.py live layers (+ common_good is linked). */
const FIXTURE_LIVE_IDS = [
  "agr_value",
  "boundaries",
  "cell_grid",
  "vdl",
  "public_crown",
  "lca",
];

function main() {
  const togglesPath = join(root, "lib", "catalogUiToggles.json");
  const togglesDoc = JSON.parse(readFileSync(togglesPath, "utf8"));
  const toggleIds = togglesDoc.uiToggleIds;
  if (!Array.isArray(toggleIds) || toggleIds.length === 0) {
    console.error("catalogUiToggles.json missing uiToggleIds");
    process.exit(1);
  }

  let liveIds = FIXTURE_LIVE_IDS;
  if (process.env.LIVE_CATALOG_IDS) {
    liveIds = JSON.parse(process.env.LIVE_CATALOG_IDS);
  }

  const panelPath = join(root, "components", "LayersPanel.tsx");
  const panelSrc = readFileSync(panelPath, "utf8");
  if (!panelSrc.includes("layer-toggle-")) {
    console.error("LayersPanel.tsx missing layer-toggle test ids");
    process.exit(1);
  }
  if (
    !panelSrc.includes("UI_TOGGLE_LAYER_IDS") &&
    !panelSrc.includes("catalogUiToggles")
  ) {
    console.error(
      "LayersPanel.tsx must use UI_TOGGLE_LAYER_IDS / catalogUiToggles for live toggles",
    );
    process.exit(1);
  }

  const result = checkCatalogUiDrift(liveIds, toggleIds);
  if (!result.ok) {
    console.error(
      `DRIFT: live catalog layer(s) have no UI toggle: ${result.missingToggles.join(", ")}`,
    );
    console.error(`live=${result.live.join(",")}`);
    console.error(`toggles=${result.toggles.join(",")}`);
    process.exit(1);
  }

  // Guard: withheld public AGR layers must still have toggles (honest unavailable).
  for (const id of ["agr_value", "cell_grid"]) {
    if (!toggleIds.includes(id)) {
      console.error(`withheld live layer ${id} must keep a UI toggle row`);
      process.exit(1);
    }
  }

  console.log(
    `OK: ${result.live.length} live catalog layer(s) each have a UI toggle.`,
  );
}

main();
