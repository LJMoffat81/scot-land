import { expect, test, type Page } from "@playwright/test";

/**
 * Suggestion 32 — Coming soon grey lines under Planning uplift and Minerals
 * in the Layers drawer. Exact strings; no £ / figures.
 * Viewport: 1280 and 390. Console / pageerror fail the test (do not loosen).
 */

const PLANNING_UPLIFT_LINE =
  "Will show where planning permission could raise land rent.";
const MINERALS_LINE =
  "Will show where mineral rights could add natural resource rent.";

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

async function openLayersDrawer(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByRole("button", { name: "Layers", exact: true }).waitFor();
  await page.getByRole("button", { name: "Layers", exact: true }).click();
  const panel = page.getByTestId("layers-panel");
  await expect(panel).toBeVisible();
  return panel;
}

async function assertComingSoonLines(page: Page) {
  const panel = await openLayersDrawer(page);

  const planning = panel.getByTestId("map-layer-1a");
  await expect(planning.getByTestId("layer-coming-soon-1a")).toHaveText(
    "Coming soon",
  );
  await expect(planning.getByTestId("layer-coming-soon-line-1a")).toHaveText(
    PLANNING_UPLIFT_LINE,
  );

  const minerals = panel.getByTestId("map-layer-2");
  await expect(minerals.getByTestId("layer-coming-soon-2")).toHaveText(
    "Coming soon",
  );
  await expect(minerals.getByTestId("layer-coming-soon-line-2")).toHaveText(
    MINERALS_LINE,
  );

  const body = await panel.innerText();
  expect(body).not.toMatch(/£\d/);
  expect(body).not.toContain("£");
}

test.describe("Suggestion 32 Coming soon lines (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("Planning uplift and Minerals show exact grey lines", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await assertComingSoonLines(page);
  });
});

test.describe("Suggestion 32 Coming soon lines (390)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Planning uplift and Minerals show exact grey lines", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await assertComingSoonLines(page);
  });
});
