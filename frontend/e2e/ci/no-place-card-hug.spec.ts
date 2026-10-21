import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * UX-05 / MAP-CARDS P6 — search miss is an inline message under the search box.
 * Card stays closed; old pin is cleared. (Legacy "no-match card hug" retired.)
 */

/** MAP-CARDS §5.2 — exact under-search no-match copy. */
const NO_MATCH_LINE =
  /couldn't find that place|Try a town or a postcode/i;

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };






async function stubNoMatchSearch(page: Page) {
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
    if (/\/boundaries\//i.test(url) || /\/layers\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
      return;
    }
    if (/\/place\?/i.test(url) && !/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({}),
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
}

async function openNoMatchInline(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();

  await page.locator("#place-query").fill("zzzz");
  await page.locator(".hud-search-go").click();

  const line = page.getByTestId("search-no-match");
  await expect(line).toBeVisible({ timeout: 30_000 });
  await expect(line).toContainText(NO_MATCH_LINE);
  await expect(page.getByTestId("place-card")).toHaveCount(0);
  await expect(page.locator(".maplibregl-marker")).toHaveCount(0);
  return line;
}

async function runNoMatchChecks(page: Page) {
  const gate = attachConsoleGate(page);
  await stubNoMatchSearch(page);
  await openNoMatchInline(page);
  assertConsoleClean(gate);
}

test.describe("UX-05 no-place card hug 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });
  test("zzzz search-miss card height hugs content", async ({ page }) => {
    test.setTimeout(90_000);
    await runNoMatchChecks(page);
  });
});

test.describe("UX-05 no-place card hug 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });
  test("zzzz search-miss card height hugs content", async ({ page }) => {
    test.setTimeout(90_000);
    await runNoMatchChecks(page);
  });
});
