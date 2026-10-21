import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * MAP-CARDS — floating legend fold removed. Layers accordion aria-expanded
 * must match group visibility. Console / pageerror fail the test.
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
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
}

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
  await stubMapBackend(page);
});

test.afterEach(() => {
  const meaningful = consoleErrors.filter((line) => {
    if (/favicon|Download the React DevTools|AbortError|aborted/i.test(line)) {
      return false;
    }
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
});

test.describe("MAP-CARDS layers accordion aria-expanded (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("group toggle aria-expanded tracks open state; no legend fold", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await expect(page.locator("button.hud-scotland-fold")).toHaveCount(0);

    await page.getByTestId("hud-layers-btn").click();
    await expect(page.getByTestId("layers-panel")).toBeVisible();

    const land = page.getByTestId("layers-group-toggle-land");
    const before = await land.getAttribute("aria-expanded");
    await land.click();
    const after = await land.getAttribute("aria-expanded");
    expect(after).not.toBe(before);
    // Toggle a few more times — must stay boolean strings
    for (let i = 0; i < 4; i += 1) {
      await land.click();
      const v = await land.getAttribute("aria-expanded");
      expect(v === "true" || v === "false").toBe(true);
    }
  });
});
