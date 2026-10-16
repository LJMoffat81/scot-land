import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * PARCELS-OFF: with PARCELS_PUBLIC unset/false (CI default), the Land parcels
 * toggle is hidden and the front-end parcel tile route returns 404.
 */

const consoleErrors: string[] = [];

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const CATALOG = {
  version: 2,
  layers: [
    {
      id: "boundaries",
      group: "spatial",
      status: "live",
      label: "ROS INSPIRE parcels",
      licence: "OGL-3.0",
    },
    {
      id: "data_zones",
      group: "spatial",
      status: "live",
      label: "Data zones",
      licence: "OGL-3.0",
    },
  ],
};

async function stubMapBackend(page: Page) {
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(CATALOG),
    });
  });
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
    });
  });
  await page.route("**/backend/layers/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract: "place_card_v1",
        lat: 55.86,
        lng: -4.25,
        place_label: "Glasgow",
      }),
    });
  });
}

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  await stubMapBackend(page);
});

test.afterEach(() => {
  expect(consoleErrors, `console/pageerror:\n${consoleErrors.join("\n")}`).toEqual(
    [],
  );
});

test.describe("PARCELS-OFF (flag default false)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Land parcels toggle is hidden", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    await expect(page.getByTestId("layers-panel")).toBeVisible();
    await expect(page.getByTestId("layer-toggle-boundaries")).toHaveCount(0);
    // Data zones stay available in the Boundaries group.
    await expect(page.getByTestId("layer-toggle-data_zones")).toBeVisible();
  });

  test("front-end parcel tile route returns 404", async ({ request }) => {
    const res = await request.get("/api/parcels/tiles/14/8045/5230");
    expect(res.status()).toBe(404);
  });
});
