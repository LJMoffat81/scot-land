import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * SHARE-FIX aligned with MAP-CARDS — deferred layers are not in Layers;
 * place lookup shows Try again (not Service busy) after exhausted retries.
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };




async function openLayers(page: Page) {
  const btn = page.getByTestId("hud-layers-btn");
  await expect(btn).toBeVisible({ timeout: 30_000 });
  if ((await page.getByTestId("layers-panel").count()) === 0) {
    await btn.click();
  }
  await expect(page.getByTestId("layers-panel")).toBeVisible({
    timeout: 15_000,
  });
}

/** Layers that MAP-CARDS moved off the drawer onto the roadmap. */
const DEFERRED_LAYER_TOGGLES = ["5", "lca", "1a", "2", "builtup_mask"] as const;

test.describe("MAP-CARDS deferred layers not in drawer", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("aquaculture / LCA / planning uplift / minerals / builtup absent", async ({
    page,
  }) => {
    test.setTimeout(90_000);
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(/\/layers\//i.test(url) || /\/boundaries\//i.test(url) ? EMPTY_FC : {}),
      });
    });
    await page.route("**/api/gbp-live**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ enabled: false }),
      });
    });

    await page.goto("/?lat=55.8609&lng=-4.2514");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
    await openLayers(page);

    for (const id of DEFERRED_LAYER_TOGGLES) {
      await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
      await expect(page.getByTestId(`layer-coming-soon-${id}`)).toHaveCount(0);
    }
    await expect(page.getByTestId("layers-panel")).not.toContainText(
      /coming soon/i,
    );
    await expect(
      page.getByTestId("map-layers-roadmap-link").locator("a"),
    ).toHaveAttribute("href", "/roadmap#map-layers");
  });
});

test.describe("SHARE-FIX place lookup Try again", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("exhausted 503 retries show Try again, not Service busy", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    let placeHits = 0;
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
      // HEALTH-TRIM: AGR capability is probed via /layers/catalog (not /health routers).
      if (/\/layers\/catalog/i.test(url)) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ version: 2, layers: [] }),
        });
        return;
      }
      // Place *search* only — do not 503 /platform/place identify.
      if (
        (/\/place\?/i.test(url) || /\/place$/i.test(url)) &&
        !/platform\/place/i.test(url)
      ) {
        placeHits += 1;
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: JSON.stringify({
            detail: "Place search is busy. Try again in a moment.",
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          /\/layers\//i.test(url) || /\/boundaries\//i.test(url)
            ? EMPTY_FC
            : {},
        ),
      });
    });

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
    const input = page.locator(".hud-search input");
    await expect(input).toBeVisible({ timeout: 15_000 });
    await input.fill("Leith Walk");
    await page.keyboard.press("Enter");

    await expect(page.locator("body")).toContainText("Try again", {
      timeout: 20_000,
    });
    await expect(page.locator("body")).not.toContainText(/Service busy/i);
    expect(placeHits).toBeGreaterThanOrEqual(2);
  });
});
