#!/usr/bin/env node
/**
 * Capture LayersPanel screenshots into the Project media folder.
 * Expects Next on http://localhost:3100 (reuseExisting).
 */

import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MEDIA =
  process.env.LAYERS_PANEL_MEDIA ||
  "/cursor/stores/self/media/frontend-layers-panel";
const BASE = process.env.BASE_URL || "http://localhost:3100";

const FIXTURE_CATALOG = {
  version: 2,
  brief: "docs/PLATFORM.md",
  principle: "AGR first",
  layers: [
    {
      id: "agr_value",
      group: "value",
      status: "live",
      label: "Annual Ground Rent",
      description: "Residual site-value AGR on W3W cells and notional plots.",
    },
    {
      id: "boundaries",
      group: "spatial",
      status: "live",
      label: "ROS INSPIRE parcels",
      description: "Registered cadastral extents (geometry only — no owners).",
      licence: "OGL / INSPIRE (Crown)",
      source_url: "https://www.ros.gov.uk/open-data",
    },
    {
      id: "cell_grid",
      group: "value",
      status: "live",
      label: "W3W cell grid",
      minzoom: 12,
    },
    {
      id: "vdl",
      group: "spatial",
      status: "live",
      label: "Vacant and derelict land",
      licence: "OGL-3.0",
      source_url:
        "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
    },
    {
      id: "public_crown",
      group: "ownership",
      status: "live",
      label: "Public and Crown Estate land",
      source_url:
        "https://www.arcgis.com/apps/dashboards/a10668ccd4784209bf22e3adcef6b897",
    },
    {
      id: "la_holdings",
      group: "ownership",
      status: "gap",
      label: "Local-authority land holdings",
      description:
        "Spatial Hub ‘Land Ownership – Scotland’ is not an open public layer. Shown as a gap, not scraped.",
      source_url: "https://data.spatialhub.scot/dataset/land_ownership-is",
    },
    {
      id: "planning",
      group: "spatial",
      status: "linked",
      label: "Planning applications",
      description: "Verified official view pages; no national drawable WMS.",
      source_url: "https://www.eplanning.scot/ePlanningClient/",
    },
    {
      id: "common_good",
      group: "ownership",
      status: "linked",
      label: "Common Good registers",
      description: "Linked registers. No national open spatial layer.",
    },
    {
      id: "sasine_private",
      group: "ownership",
      status: "gap",
      label: "Private owners and Sasine land",
      description: "Incomplete or paid. Gaps are shown; names are not invented.",
    },
  ],
};

async function fulfillCatalog(route) {
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(FIXTURE_CATALOG),
  });
}

async function main() {
  mkdirSync(MEDIA, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1100, height: 1400 } });
  await page.route("**/layers/catalog", fulfillCatalog);
  await page.route("**/backend/layers/catalog", fulfillCatalog);
  await page.goto(`${BASE}/layers-panel`, { waitUntil: "networkidle" });
  await page.getByTestId("layers-panel").waitFor();

  await page.screenshot({
    path: join(MEDIA, "desktop-layers-panel.png"),
    fullPage: true,
  });

  await page.getByTestId("layer-toggle-agr_value").click();
  await page.getByTestId("layer-unavailable-agr_value").waitFor();
  await page.screenshot({
    path: join(MEDIA, "desktop-layers-panel-agr-withheld.png"),
    fullPage: true,
  });

  const mobile = await browser.newPage({
    viewport: { width: 390, height: 844 },
  });
  await mobile.route("**/layers/catalog", fulfillCatalog);
  await mobile.route("**/backend/layers/catalog", fulfillCatalog);
  await mobile.goto(`${BASE}/layers-panel`, { waitUntil: "networkidle" });
  await mobile.getByTestId("layers-panel").waitFor();
  await mobile.screenshot({
    path: join(MEDIA, "mobile-layers-panel.png"),
    fullPage: true,
  });

  await browser.close();
  console.log(`Wrote screenshots to ${MEDIA}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
