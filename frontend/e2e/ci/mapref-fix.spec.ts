import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * MAP-CARDS / SW-052 — Map reference row removed from the place card.
 * Placeholder must not say "map reference".
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const PLACE_STUB = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "Glasgow City Centre",
  council_name: "Glasgow City",
  square_reference: "2068927,-157234",
  dwellings: 410,
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre", code: "S02002645" },
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "proxy",
      class: "proxy",
      status: "in_progress",
      applies: true,
      range: "not yet estimated",
    },
  ],
  constraints: [],
  layers: [],
  links: [],
  flags: [],
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
    if (/\/platform\/place/i.test(url) || /\/place\?/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_STUB),
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
}

async function openCard(page: Page, _width: number) {
  await page.goto("/?lat=55.8609&lng=-4.2514");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const card = page.getByTestId("place-card");
  // URL place boot only — canvas click races the half-panel handle on 390.
  await expect(card).toBeVisible({ timeout: 45_000 });
  return card;
}

for (const width of [1280, 390] as const) {
  test.describe(`MAP-CARDS no map reference ${width}`, () => {
    test.use({
      viewport: { width, height: width === 390 ? 844 : 800 },
    });

    test("place card has no Map reference row; placeholder clean", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      await stubBackend(page);
      const card = await openCard(page, width);

      await expect(card.getByTestId("place-card-map-reference")).toHaveCount(0);
      await expect(card.getByTestId("place-card-square-reference")).toHaveCount(
        0,
      );
      await expect(card).not.toContainText(/map reference/i);
      await expect(page.locator("#place-query")).toHaveAttribute(
        "placeholder",
        "Search a postcode, e.g. G2 1DU",
      );
      await expect(page.locator("#place-query")).not.toHaveAttribute(
        "placeholder",
        /map reference/i,
      );
    });
  });
}
