import {
  assertConsoleClean,
  attachConsoleGate,
  registerOpenFreeMapFontStub,
} from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * PEEK-REACH-1 — mobile place-card handle.
 * Search opens at half. Handle taps cycle peek → half → full → peek.
 * A 250px drag down from half snaps to peek. A 60px drag stays put.
 * Peek keeps the place name, the Annual Ground Rent line, and the
 * disclaimer visible. "More about this area" stays hidden.
 * Widths: 390 and 360. Console/pageerror gate.
 */

const POSTCODE = "EH1 1YZ";
const PLACE_NAME = "Old Town, Princes Street and Leith Street";
const AGR_LINE = "Annual Ground Rent";
const MORE_ABOUT = "More about this area";
const DRAG_DOWN_PX = 250;
const SHORT_DRAG_PX = 60;

const EH1 = { lat: 55.9533, lng: -3.1883 };

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const VIEWPORTS = [
  { width: 390, height: 844 },
  { width: 360, height: 740 },
] as const;

function eh1Card() {
  return {
    contract: "place_card_v1",
    lat: EH1.lat,
    lng: EH1.lng,
    place_label: "Edinburgh Old Town",
    postcode: POSTCODE,
    council_name: "City of Edinburgh",
    dwellings: 410,
    sales_year_from: 2019,
    sales_year_to: 2023,
    confidence: "Medium",
    data_zone: {
      status: "ok",
      code: "S01014713",
      name: "Old Town East",
      vintage: 2022,
    },
    intermediate_zone: {
      status: "ok",
      name: PLACE_NAME,
      code: "S02002727",
    },
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
  };
}

async function stubMap(page: Page) {
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
        body: JSON.stringify(eh1Card()),
      });
      return;
    }
    if (/\/place\?/i.test(url) && !/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          kind: "point",
          lat: EH1.lat,
          lng: EH1.lng,
          label: PLACE_NAME,
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
}

async function openSearchedCard(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await page.locator("#place-query").fill(POSTCODE);
  await page.locator(".hud-search-go").click();
  const slot = page.getByTestId("map-panel-slot");
  await expect(slot).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("place-card-place")).toHaveText(PLACE_NAME, {
    timeout: 30_000,
  });
  await expect(slot).toHaveAttribute("data-detent", "half");
  return slot;
}

async function dragHandleDown(page: Page, pixels: number) {
  const handle = page.getByTestId("map-panel-handle");
  const box = await handle.boundingBox();
  expect(box, "place-card handle").toBeTruthy();
  const x = box!.x + box!.width / 2;
  const y = box!.y + box!.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x, y + pixels, { steps: 12 });
  await page.mouse.up();
}

async function assertPeekContent(page: Page) {
  const slot = page.getByTestId("map-panel-slot");
  await expect(slot).toHaveAttribute("data-detent", "peek");
  await expect(page.getByTestId("place-card-place")).toBeVisible();
  await expect(page.getByTestId("place-card-place")).toHaveText(PLACE_NAME);
  const agr = page.getByTestId("place-card-agr-label");
  await expect(agr).toBeVisible();
  await expect(agr).toHaveText(AGR_LINE);
  await expect(page.getByTestId("place-card-footer")).toBeVisible();
  const more = page.getByText(MORE_ABOUT, { exact: false });
  await expect(more).toHaveCount(1);
  await expect(more).toBeHidden();
}

for (const viewport of VIEWPORTS) {
  test.describe(`PEEK-REACH-1 ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("EH1 1YZ tap cycle and drag down to peek", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMap(page);
      const slot = await openSearchedCard(page);
      const handle = page.getByTestId("map-panel-handle");

      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "full");
      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "peek");

      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "half");
      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "full");
      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "peek");

      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "half");
      await dragHandleDown(page, DRAG_DOWN_PX);
      await expect(slot).toHaveAttribute("data-detent", "peek");
      await assertPeekContent(page);

      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "half");
      await dragHandleDown(page, SHORT_DRAG_PX);
      await expect(slot).toHaveAttribute("data-detent", "half");

      assertConsoleClean(gate);
    });

    test("EH1 1YZ tap-only cycle asserts half, full, and peek", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMap(page);
      const slot = await openSearchedCard(page);
      const handle = page.getByTestId("map-panel-handle");

      await expect(slot).toHaveAttribute("data-detent", "half");
      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "full");
      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "peek");
      await handle.click();
      await expect(slot).toHaveAttribute("data-detent", "half");

      assertConsoleClean(gate);
    });
  });
}
