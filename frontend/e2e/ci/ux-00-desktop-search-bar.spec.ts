import { registerOpenFreeMapFontStub, stubLayersCouncilsQuiet, stubCiTileDataQuiet } from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * UX-00 — desktop search bar in the top-bar row.
 * Search input height equals Layers button height; top/bottom edges within 1px.
 * Any console error / pageerror fails the test. Never loosen.
 */


const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };



test.beforeEach(async ({ page }) => {

  
  

  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
      }),
    });
  });
  await page.route("**/backend/boundaries/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });

  await stubLayersCouncilsQuiet(page);
  await stubCiTileDataQuiet(page);


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
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
    });
  });
  await page.route("**/backend/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/backend/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: null,
        name: null,
        vintage: null,
      }),
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
  await stubLayersAddQuiet(page);
});



async function openMap(page: Page): Promise<void> {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
  await page.getByTestId("hud-layers-btn").waitFor();
}

for (const width of [1280, 1920] as const) {
  test(`UX-00 @${width}: search input matches Layers height and edges ≤1px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 800 });
    await openMap(page);

    const searchInput = page.locator("#place-query");
    const layersBtn = page.getByTestId("hud-layers-btn");
    await expect(searchInput).toBeVisible();
    await expect(layersBtn).toBeVisible();

    const searchBox = await searchInput.boundingBox();
    const layersBox = await layersBtn.boundingBox();
    expect(searchBox, "search input box").toBeTruthy();
    expect(layersBox, "Layers button box").toBeTruthy();
    if (!searchBox || !layersBox) return;

    expect(
      Math.abs(searchBox.height - layersBox.height),
      `height search=${searchBox.height} layers=${layersBox.height}`,
    ).toBeLessThanOrEqual(1);

    expect(
      Math.abs(searchBox.y - layersBox.y),
      `top search=${searchBox.y} layers=${layersBox.y}`,
    ).toBeLessThanOrEqual(1);

    const searchBottom = searchBox.y + searchBox.height;
    const layersBottom = layersBox.y + layersBox.height;
    expect(
      Math.abs(searchBottom - layersBottom),
      `bottom search=${searchBottom} layers=${layersBottom}`,
    ).toBeLessThanOrEqual(1);

    // Same top-bar row as logo (not a second-row dock).
    const brandBox = await page.locator(".hud-brand").boundingBox();
    expect(brandBox).toBeTruthy();
    if (brandBox) {
      expect(searchBox.y).toBeGreaterThanOrEqual(brandBox.y - 1);
      expect(searchBox.y + searchBox.height).toBeLessThanOrEqual(
        brandBox.y + brandBox.height + 1,
      );
    }
  });
}
