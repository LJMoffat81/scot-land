import { expect, test, type Page } from "@playwright/test";

/**
 * MAPREF-FIX — place card shows OSGB36 Map reference + Copy at 390 and 1280.
 * Replaces mapref-hide.spec.ts (temporary hide).
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
  sales_year_from: 2019,
  sales_year_to: 2023,
  confidence: "Medium",
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
      unit: null,
      confidence: null,
      method: null,
      gloss: "The yearly value of the land under homes.",
      of_which: [],
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
}

async function openCard(page: Page, width: number) {
  await page.goto("/?lat=55.8609&lng=-4.2514");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const card = page.getByTestId("place-card");
  if ((await card.count()) === 0) {
    await page.locator(".maplibregl-canvas").click({
      position: { x: Math.floor(width / 2), y: Math.floor(800 / 2) },
    });
  }
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

for (const width of [1280, 390] as const) {
  test.describe(`MAPREF-FIX ${width}`, () => {
    test.use({
      viewport: { width, height: width === 390 ? 844 : 800 },
    });

    test("Map reference OSGB + Copy same string", async ({ page }) => {
      test.setTimeout(90_000);
      await stubBackend(page);
      const card = await openCard(page, width);

      await expect(card).toContainText("Map reference");
      const ref = card.getByTestId("place-card-square-reference");
      await expect(ref).toBeVisible();
      const text = (await ref.innerText()).trim();
      expect(text).toMatch(/^\d+,\d+$/);
      const [e, n] = text.split(",").map(Number);
      // Glasgow ~259189,665372
      expect(e).toBeGreaterThan(200_000);
      expect(e).toBeLessThan(320_000);
      expect(n).toBeGreaterThan(600_000);
      expect(n).toBeLessThan(750_000);
      expect(text).not.toBe("2068927,-157234");

      await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
      await card.getByTestId("place-card-map-reference-copy").click();
      const clipped = await page.evaluate(() => navigator.clipboard.readText());
      expect(clipped.trim()).toBe(text);
    });
  });
}
