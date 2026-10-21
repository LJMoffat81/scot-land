import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * UX10-2 / MAP-CARDS Q5 — built-up mask is a background style, not a Layers
 * switch. No £; parcels stay off; console/pageerror gate.
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };





async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/health(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ version: 2, layers: [] }),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat: 55.86,
          lng: -4.25,
          place_label: "Glasgow",
          layers: [],
          links: [],
        }),
      });
      return;
    }
    const wantsGeo =
      /\/layers\//i.test(url) ||
      /\/boundaries\//i.test(url) ||
      /\/w3w-grid/i.test(url) ||
      /\/parcels/i.test(url);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(wantsGeo ? EMPTY_FC : {}),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
}

async function openTools(page: Page) {
  await page.getByTestId("hud-layers-btn").click();
  await expect(page.getByTestId("layers-panel")).toBeVisible({
    timeout: 15_000,
  });
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`UX10-2 built-up background ${viewport.width}`, () => {
    test.use({ viewport });

    test("builtup not a switch; parcels off; no £", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);

      await page.goto("/?lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });

      await openTools(page);
      await expect(page.getByTestId("layer-toggle-builtup_mask")).toHaveCount(0);
      await expect(page.getByTestId("map-layer-builtup_mask")).toHaveCount(0);
      await expect(page.getByTestId("layers-panel")).not.toContainText(
        /Built-up display mask/i,
      );

      // Neighbourhood lines remain available as a switch (off at rest).
      await expect(page.getByTestId("layer-toggle-data_zones")).toBeVisible();
      await expect(page.getByTestId("layer-toggle-boundaries")).toHaveCount(0);

      const parcelTile = await page.request.get(
        "/api/parcels/tiles/14/8045/5230",
      );
      expect(parcelTile.status()).toBe(404);

      const bodyText = await page.locator("body").innerText();
      expect(bodyText).not.toMatch(/£\d/);
      expect(bodyText.toLowerCase()).not.toContain("natural capital");
      expect(bodyText.toLowerCase()).not.toMatch(/\bledger\b/);
    assertConsoleClean(gate);
    });
  });
}
