import { registerOpenFreeMapFontStub, stubLayersCouncilsQuiet, stubCiTileDataQuiet, attachConsoleGate, assertConsoleClean } from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * Developer glossary at /developers/glossary.
 * Linked from /developers only — never from visitor pages.
 * Console / pageerror traps must fail (do not loosen).
 */

const GLOSSARY_TERMS = [
  "Land value",
  "Land rent",
  "Location value",
  "Annual Ground Rent",
  "market",
  "proxy",
  "Estimate",
  "Best permitted use",
  "Constraint",
  "Residual",
  "Rent rate",
  "Data zone",
  "Blocked",
  "Research estimate",
  "Partly estimated",
  "Fully estimated",
  "Not applicable",
  "Common Good land",
] as const;

const VISITOR_PATHS = ["/", "/about", "/methodology", "/data"] as const;

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };








async function stubBackend(page: Page) {
  // Catch-all first (Playwright is LIFO — later routes win).
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
  await page.route("**/downloads/manifest.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ generated_at: "2026-01-01", bundles: [] }),
    });
  });
  await stubLayersAddQuiet(page);
}

test.describe("developers glossary", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("renders every term heading, no £, linked from /developers only", async ({
    page,
  }) => {
    const gate = attachConsoleGate(page);
    await stubBackend(page);

    await page.goto("/developers/glossary");
    const root = page.getByTestId("developers-glossary-page");
    await expect(root).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Scot-LAND glossary", level: 1 }),
    ).toBeVisible();

    for (const term of GLOSSARY_TERMS) {
      await expect(
        page.getByRole("heading", { name: term, exact: true }),
      ).toBeVisible();
    }

    await expect(root).not.toContainText("£");
    assertConsoleClean(gate);

    // Linked from /developers.
    await page.goto("/developers");
    const glossaryLink = page.locator('a[href="/developers/glossary"]');
    await expect(glossaryLink).toBeVisible();
    assertConsoleClean(gate);

    // Visitor pages must not link to it.
    for (const path of VISITOR_PATHS) {
      await page.goto(path);
      await expect(
        page.locator('a[href="/developers/glossary"]'),
      ).toHaveCount(0);
      await expect(
        page.locator('a[href*="/developers/glossary"]'),
      ).toHaveCount(0);
      assertConsoleClean(gate);
    }
  });
});
