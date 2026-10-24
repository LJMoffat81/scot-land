import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";
import { stubLayersAddQuiet } from "./_layersAddStub";

registerOpenFreeMapFontStub();


/**
 * MAP-CARDS — floating legend removed; inline legend + legend strip.
 * Fail on console errors. No £ / banned visitor words.
 */

const BANNED =
  /\b(natural capital|ledger|headline|shadow|yield|what3words)\b/i;

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

const consoleErrors: string[] = [];

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
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

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
  await stubMapBackend(page);
});

test.afterEach(async () => {
  const meaningful = consoleErrors.filter((line) => {
    if (/favicon/i.test(line)) return false;
    if (/Download the React DevTools/i.test(line)) return false;
    if (/\bAbortError\b|aborted/i.test(line)) return false;
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
});

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

async function openLayers(page: Page) {
  await page.getByTestId("hud-layers-btn").click();
  await expect(page.getByTestId("layers-panel")).toBeVisible();
}

test.describe("MAP-CARDS legend strip / inline (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("inline legend follows toggles; no floating Show legend", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await openMap(page);

    await expect(page.getByRole("button", { name: "Show legend" })).toHaveCount(
      0,
    );
    await expect(page.getByTestId("map-legend-panel")).toHaveCount(0);
    await expect(page.getByTestId("map-range-legend")).toHaveCount(0);

    // VDL minzoom 8 — class key still renders when gated, but match GIS zoom.
    await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: { setZoom(n: number): void; getZoom(): number };
        }
      ).__map;
      if (map && map.getZoom() < 8) map.setZoom(8);
    });

    await openLayers(page);
    const landToggle = page.getByTestId("layers-group-toggle-land");
    if ((await landToggle.getAttribute("aria-expanded")) !== "true") {
      await landToggle.click();
    }

    await page.getByTestId("layer-toggle-1").click();
    const agrLegend = page.getByTestId("layer-inline-legend-1");
    await expect(agrLegend).toBeVisible();
    await expect(agrLegend).toContainText("Lower");
    await expect(agrLegend).toContainText("Higher");
    await expect(agrLegend).toContainText("Striped = less sure");
    await expect(agrLegend).not.toContainText("Paler = less sure");
    await expect(agrLegend).not.toContainText(/£\d/);

    await page.getByTestId("layer-toggle-1").click(); // off
    await expect(page.getByTestId("layer-inline-legend-1")).toHaveCount(0);

    await expect(page.locator("body")).not.toContainText(BANNED);
  });

  test("legend strip clear of place card when panel closed", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await openMap(page);
    await openLayers(page);
    const landToggle = page.getByTestId("layers-group-toggle-land");
    if ((await landToggle.getAttribute("aria-expanded")) !== "true") {
      await landToggle.click();
    }
    await page.getByTestId("layer-toggle-access_services").click();
    await page.getByTestId("map-panel-slot-close").click();

    await expect(page.getByTestId("legend-strip")).toHaveCount(0);
    await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
    await page.locator("#place-query").fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible({ timeout: 45_000 });
    // Floating map legend must stay gone (keys live only in Layers)
    await expect(page.getByTestId("map-legend-panel")).toHaveCount(0);
    await expect(page.getByTestId("legend-strip")).toHaveCount(0);
    await expect(page.getByTestId("map-key-chip")).toHaveCount(0);
    await expect(card).not.toContainText(/£\d/);
  });
});

test.describe("MAP-CARDS legend at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("inline legend; no Show legend fold", async ({ page }) => {
    test.setTimeout(90_000);
    await openMap(page);
    await expect(page.locator("button.hud-scotland-fold")).toHaveCount(0);
    await openLayers(page);
    const landToggle = page.getByTestId("layers-group-toggle-land");
    if ((await landToggle.getAttribute("aria-expanded")) !== "true") {
      await landToggle.click();
    }
    await page.getByTestId("layer-toggle-1").click();
    await expect(page.getByTestId("layer-inline-legend-1")).toBeVisible();
    await expect(page.locator("body")).not.toContainText(BANNED);
    await expect(page.getByTestId("layer-inline-legend-1")).not.toContainText(
      /£\d/,
    );
  });
});
