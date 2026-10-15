import { expect, test, type Page } from "@playwright/test";

/**
 * MAP-CARDS E7 — Planning uplift / Minerals / aquaculture / LCA are not in
 * Layers; they appear on /roadmap#map-layers instead.
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
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
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

async function openLayersDrawer(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByTestId("hud-layers-btn").click();
  const panel = page.getByTestId("layers-panel");
  await expect(panel).toBeVisible();
  return panel;
}

async function assertDeferredOnRoadmap(page: Page) {
  const panel = await openLayersDrawer(page);
  for (const id of ["1a", "2", "5", "lca"]) {
    await expect(panel.getByTestId(`map-layer-${id}`)).toHaveCount(0);
    await expect(panel.getByTestId(`layer-coming-soon-${id}`)).toHaveCount(0);
  }
  await expect(panel).not.toContainText(/coming soon|coming later/i);
  await expect(panel.getByTestId("map-layers-roadmap-link").locator("a")).toHaveAttribute(
    "href",
    "/roadmap#map-layers",
  );

  await page.goto("/roadmap#map-layers");
  const section = page.getByTestId("roadmap-map-layers");
  await expect(section).toBeVisible();
  await expect(section).toContainText(/Fish and shellfish farms|Landscape character/i);
}

test.describe("MAP-CARDS deferred layers on roadmap (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Planning uplift / Minerals not in Layers; roadmap lists deferred", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await assertDeferredOnRoadmap(page);
  });
});

test.describe("MAP-CARDS deferred layers on roadmap (390)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Planning uplift / Minerals not in Layers; roadmap lists deferred", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await assertDeferredOnRoadmap(page);
  });
});
