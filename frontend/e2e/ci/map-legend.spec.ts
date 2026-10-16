import { expect, test, type Page } from "@playwright/test";

/**
 * MAP-CARDS — population density legend removed from default map.
 * Inline registry legends + legend strip replace the floating density panel.
 */

const EMPTY_FC = {
  type: "FeatureCollection",
  features: [],
};

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
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
  const meaningful = consoleErrors.filter(
    (line) => !/favicon|Download the React DevTools|AbortError|aborted/i.test(line),
  );
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
});

test.describe("MAP-CARDS no density legend (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("no population density floating legend; AGR inline key", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();

    await expect(page.getByTestId("map-range-legend")).toHaveCount(0);
    await expect(page.getByTestId("map-legend-panel")).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText(
      "Population density — people per km²",
    );

    await page.getByTestId("hud-layers-btn").click();
    await expect(page.getByTestId("layers-panel")).toBeVisible();
    const land = page.getByTestId("layers-group-toggle-land");
    if ((await land.getAttribute("aria-expanded")) !== "true") {
      await land.click();
    }
    await page.getByTestId("layer-toggle-1").click();
    await expect(page.getByTestId("layer-inline-legend-1")).toBeVisible();
    await expect(page.getByTestId("layer-source-caption-1")).toBeVisible();
  });
});
