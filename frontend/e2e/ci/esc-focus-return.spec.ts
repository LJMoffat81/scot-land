import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * UX-03 — Esc to close Layers or the mobile nav returns focus to its toggle.
 * Viewport: 1280 (Layers) and 390 (nav). Console / pageerror fail the test.
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

/**
 * Quiet map API traffic so the Next `/backend` proxy never returns 503 in CI
 * (no live FastAPI). Console-error afterEach stays strict.
 */
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
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ version: 2, layers: [] }),
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
      body: JSON.stringify({ code: null, name: null, vintage: null }),
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

test.afterEach(async () => {
  const meaningful = consoleErrors.filter((line) => {
    if (/favicon/i.test(line)) return false;
    if (/Download the React DevTools/i.test(line)) return false;
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
});

test.describe("UX-03 Esc focus return", () => {
  test("Layers Esc returns focus to Layers toggle @1280", async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();

    const layersBtn = page.getByTestId("hud-layers-btn");
    await layersBtn.waitFor();
    await layersBtn.click();
    const panel = page.getByTestId("layers-panel");
    await expect(panel).toBeVisible();

    // Move focus into the drawer so Esc is not acting on the toggle itself.
    await panel.getByRole("button").first().focus();
    await expect(panel.getByRole("button").first()).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(layersBtn).toBeFocused();
    await expect(layersBtn).toHaveAttribute("aria-pressed", "false");
  });

  test("nav Esc returns focus to menu toggle @390", async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/about");

    const menuBtn = page.getByTestId("site-nav-menu-btn");
    await expect(menuBtn).toBeVisible();
    await menuBtn.click();
    const panel = page.getByTestId("site-nav-panel");
    await expect(panel).toBeVisible();

    // Move focus into the panel so Esc is not acting on the toggle itself.
    await panel.getByRole("link").first().focus();
    await expect(panel.getByRole("link").first()).toBeFocused();

    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
    await expect(menuBtn).toBeFocused();
    await expect(menuBtn).toHaveAttribute("aria-expanded", "false");
  });
});
