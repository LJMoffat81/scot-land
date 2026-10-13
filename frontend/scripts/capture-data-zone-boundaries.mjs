#!/usr/bin/env node
/**
 * Capture Data Zone boundaries screenshots into Project media.
 * Expects Next on http://localhost:3100.
 */

import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const MEDIA =
  process.env.DZ_MEDIA ||
  "/cursor/stores/self/media/data-zone-boundaries";
const BASE = process.env.BASE_URL || "http://localhost:3100";

const FIXTURE_ZONES = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-4.28, 55.84],
            [-4.22, 55.84],
            [-4.22, 55.89],
            [-4.28, 55.89],
            [-4.28, 55.84],
          ],
        ],
      },
      properties: {
        code: "S01009859",
        name: "Ibrox - 01",
        vintage: 2011,
        layer: "data_zones",
      },
    },
  ],
  meta: { ok: true, layer: "data_zones", count: 1, vintage: 2011 },
};

const FIXTURE_CATALOG = {
  version: 2,
  layers: [
    {
      id: "data_zones",
      group: "spatial",
      status: "live",
      label: "Data Zone boundaries",
      description: "2011 outlines. Boundaries only — no AGR £.",
      licence: "OGL v3.0",
      source_url: "https://www.spatialdata.gov.scot/",
    },
    {
      id: "agr_value",
      group: "value",
      status: "live",
      label: "Annual Ground Rent",
    },
    {
      id: "boundaries",
      group: "spatial",
      status: "live",
      label: "ROS INSPIRE parcels",
    },
    {
      id: "cell_grid",
      group: "value",
      status: "live",
      label: "W3W cell grid",
    },
    {
      id: "vdl",
      group: "spatial",
      status: "live",
      label: "Vacant and derelict land",
    },
    {
      id: "public_crown",
      group: "ownership",
      status: "gap",
      label: "Public and Crown Estate land",
      licence: "unverified/not open",
    },
  ],
};

async function main() {
  mkdirSync(MEDIA, { recursive: true });
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });

  await page.route("**/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_ZONES),
    });
  });
  await page.route("**/backend/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_ZONES),
    });
  });
  await page.route("**/layers/catalog", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_CATALOG),
    });
  });
  await page.route("**/backend/layers/catalog", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_CATALOG),
    });
  });

  // 1) Map at readable zoom with layer on
  await page.goto(`${BASE}/?lat=55.8609&lng=-4.2514`, {
    waitUntil: "networkidle",
  });
  await page.locator(".maplibregl-canvas").waitFor();
  await page.waitForTimeout(1500);
  const layersBtn = page.getByRole("button", { name: "Layers", exact: true });
  await layersBtn.click();
  const toggle = page.getByTestId("layer-data-zones");
  await toggle.waitFor();
  if (!(await toggle.getAttribute("class"))?.includes("active")) {
    await toggle.click();
  }
  await page.waitForTimeout(800);
  await page.screenshot({
    path: join(MEDIA, "map-data-zones-readable-zoom.png"),
    fullPage: false,
  });

  // 2) Layers panel with Data Zone toggle
  await page.screenshot({
    path: join(MEDIA, "layers-panel-data-zones.png"),
    fullPage: false,
  });

  // 3) Hover / click → place card
  await layersBtn.click(); // close tools for clearer card
  await page.waitForTimeout(300);
  await page.locator("#map").click({ position: { x: 720, y: 420 } });
  await page.locator("aside.place-card-stub").waitFor({ timeout: 15000 });
  await page.waitForTimeout(400);
  await page.screenshot({
    path: join(MEDIA, "click-place-card-zone.png"),
    fullPage: false,
  });

  // 4) Catalog LayersPanel route
  await page.goto(`${BASE}/layers-panel`, { waitUntil: "networkidle" });
  await page.getByTestId("layer-toggle-data_zones").waitFor();
  await page.screenshot({
    path: join(MEDIA, "catalog-layers-panel.png"),
    fullPage: false,
  });

  await browser.close();
  console.log("Wrote screenshots to", MEDIA);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
