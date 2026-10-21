import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean } from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * LOGO-SIZE-1 — map header mark matches the content-page header mark.
 * Widths 1280 and 390. No skips. Console errors fail.
 */

const MARK = "/logo-mark-h3.png";
const HOME_LABEL = "Scot-LAND home";

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
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract: "place_card_v1",
        lat: 55.95,
        lng: -3.19,
        place_label: null,
        agr_rows: [],
        constraints: [],
        layers: [],
        links: [],
      }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await stubLayersAddQuiet(page);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`LOGO-SIZE-1 ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("map logo matches the about header logo and keeps a 44px tap target", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);

      await page.goto("/about");
      const aboutLogo = page.getByTestId("site-nav-brand").locator("img");
      await expect(aboutLogo).toBeVisible();
      await expect(aboutLogo).toHaveAttribute("src", MARK);
      const aboutBox = await aboutLogo.boundingBox();
      expect(aboutBox, "about header logo box").not.toBeNull();

      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      const mapLink = page.getByTestId("site-nav-brand");
      const mapLogo = mapLink.locator("img");
      await expect(mapLink).toBeVisible();
      await expect(mapLogo).toBeVisible();
      await expect(mapLink).toHaveAttribute("aria-label", HOME_LABEL);
      await expect(mapLogo).toHaveAttribute("src", MARK);
      const mapBox = await mapLogo.boundingBox();
      const tapBox = await mapLink.boundingBox();
      expect(mapBox, "map logo box").not.toBeNull();
      expect(tapBox, "map logo tap target").not.toBeNull();

      expect(Math.abs(mapBox!.width - aboutBox!.width)).toBeLessThanOrEqual(1);
      expect(Math.abs(mapBox!.height - aboutBox!.height)).toBeLessThanOrEqual(1);
      expect(tapBox!.width).toBeGreaterThanOrEqual(44);
      expect(tapBox!.height).toBeGreaterThanOrEqual(44);

      assertConsoleClean(gate);
    });
  });
}
