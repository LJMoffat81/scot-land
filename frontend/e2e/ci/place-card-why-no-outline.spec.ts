import {
  assertConsoleClean,
  attachConsoleGate,
  registerOpenFreeMapFontStub,
} from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * MAP-CARDS §6 — "Why no outline?" / LAND OUTLINE removed from the public card.
 * Replacement: no outline status row; parcels stay off.
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const PLACE_NO_OUTLINE = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "Glasgow",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre" },
  land_register_outline: { status: "no_outline", note: "Sasine note" },
  land_outline: {
    status: "no_outline",
    label: "Land outline",
    area_sqm: null,
    note: "Sasine note",
  },
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "proxy",
      status: "in_progress",
      applies: true,
    },
  ],
  constraints: [],
  layers: [],
  links: [],
};

async function stubBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_NO_OUTLINE),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(/\/layers\//i.test(url) || /\/boundaries\//i.test(url) ? EMPTY_FC : {}),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
}

test.beforeEach(async ({ page }) => {
  await stubBackend(page);
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`MAP-CARDS no outline UI (${viewport.width})`, () => {
    test.use({ viewport });

    test("outline status / Why no outline? absent from card", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await page.goto("/?lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      const card = page.getByTestId("place-card");
      await expect(card).toBeVisible({ timeout: 30_000 });

      await expect(page.getByTestId("place-card-outline-status")).toHaveCount(0);
      await expect(
        page.getByTestId("place-card-why-no-outline-btn"),
      ).toHaveCount(0);
      await expect(card).not.toContainText(/Why no outline/i);
      await expect(card).not.toContainText(/No registered outline/i);
      await expect(card).not.toContainText(/LAND OUTLINE/i);
      assertConsoleClean(gate);
    });
  });
}
