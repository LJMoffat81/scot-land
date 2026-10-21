import {
  injectEsriBasemapKey,
  registerOpenFreeMapFontStub,
  stubLayersCouncilsQuiet,
  stubCiTileDataQuiet,
} from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test, type Locator, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * MAP-CARDS desktop layout at 1280×800 — one panel slot (place XOR Layers);
 * no bbox intersections among slot, zoom, basemap, banner ×.
 */

const pageErrors: string[] = [];
const consoleErrors: string[] = [];

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
  place_label: "Glasgow",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre" },
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

type Box = { x: number; y: number; width: number; height: number };

function boxesOverlap(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function stubBackend(page: Page) {
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
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
    });
  });
  await page.route("**/backend/layers/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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
  await stubLayersAddQuiet(page);
}

async function boxOf(locator: Locator, label: string): Promise<Box> {
  await expect(locator, label).toBeVisible();
  // MapLibre markers can report visible before layout has a box (null bbox).
  // Retry until a positive box exists — same width/height asserts, no loosen.
  let box: Box | null = null;
  await expect(async () => {
    box = await locator.boundingBox();
    expect(box, `${label} bounding box`).toBeTruthy();
    expect(box!.width, `${label} width`).toBeGreaterThan(0);
    expect(box!.height, `${label} height`).toBeGreaterThan(0);
  }).toPass({ timeout: 15_000 });
  return box!;
}

function assertPairClear(a: Box, b: Box, label: string) {
  expect(boxesOverlap(a, b), label).toBe(false);
}

test.describe("MAP-CARDS desktop one-panel layout 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test.beforeEach(async ({ page }) => {
    pageErrors.length = 0;
    consoleErrors.length = 0;
    page.on("pageerror", (err) => pageErrors.push(String(err)));
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await stubBackend(page);
  });

  test.afterEach(() => {
    expect(pageErrors, `pageerrors:\n${pageErrors.join("\n")}`).toEqual([]);
    const meaningful = consoleErrors.filter((text) => {
      if (/\bAbortError\b|aborted/i.test(text)) return false;
      if (/Failed to load resource:.*(?:404|503)/i.test(text)) return false;
      return true;
    });
    expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
  });

  test("place XOR Layers; no chrome intersections; floating legend gone", async ({
    page,
  }) => {
    test.setTimeout(120_000);

    await injectEsriBasemapKey(page);
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.locator("#place-query").waitFor();

    await page.locator("#place-query").fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible({ timeout: 45_000 });
    await expect(page.getByTestId("layers-panel")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Show legend" })).toHaveCount(
      0,
    );
    await expect(page.getByTestId("map-legend-panel")).toHaveCount(0);

    const layersBtn = page.getByTestId("hud-layers-btn");
    await layersBtn.click();
    await expect(page.getByTestId("layers-panel")).toBeVisible();
    await expect(page.getByTestId("place-card")).toBeVisible();
    const layersCol = page.getByTestId("layers-column");
    await expect(layersCol).toBeVisible();
    const layersBox = await boxOf(layersCol, "layers column");
    expect(layersBox.x, "layers column is on the right").toBeGreaterThan(640);

    const slot = page.getByTestId("map-panel-slot");
    const zoom = page.locator(".maplibregl-ctrl-zoom-in");
    const basemap = page.getByTestId("basemap-switcher");
    await expect(zoom).toBeVisible();
    await expect(basemap).toBeVisible();

    const slotBox = await boxOf(slot, "panel slot");
    const zoomBox = await boxOf(zoom, "zoom +");
    const basemapBox = await boxOf(basemap, "basemap");

    expect(slotBox.x + slotBox.width, "slot stays leftish").toBeLessThan(520);

    assertPairClear(slotBox, zoomBox, "slot vs zoom");
    assertPairClear(slotBox, basemapBox, "slot vs basemap");
    assertPairClear(zoomBox, basemapBox, "zoom vs basemap");
  });
});
