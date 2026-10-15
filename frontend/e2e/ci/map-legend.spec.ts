import { expect, test, type Page } from "@playwright/test";

/**
 * SW-022 — population density map legend.
 * National zoom → zoom hint; zoomed in → bands + source. Fail on console errors.
 * Backend stubs quiet proxy 503s (asserts stay strict — no console-error allow-list).
 */

const GLASGOW = { lng: -4.2514, lat: 55.8609 };

const TITLE = "Population density — people per km²";
const BLURB = "Busier places tend to have a higher Annual Ground Rent.";
const SOURCE =
  "Source: National Records of Scotland mid-year estimates, Open Government Licence v3.0";
const ZOOM_HINT = "Zoom in to see colours";

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

/**
 * Quiet map API traffic so the Next `/backend` proxy never returns 503 in CI
 * (no live FastAPI). Console-error afterEach stays strict.
 */
async function stubMapBackend(page: Page) {
  // Catch-all first (Playwright is LIFO — later routes win).
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
        lat: GLASGOW.lat,
        lng: GLASGOW.lng,
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

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
  await page.locator("#map[data-framed='1']").waitFor({ timeout: 30_000 });
}

test.describe("map legend density (1440x900)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("national zoom shows zoom hint, not bands", async ({ page }) => {
    test.setTimeout(90_000);
    await openMap(page);

    const legend = page.getByTestId("map-range-legend");
    await expect(legend).toBeVisible();
    await expect(legend).toHaveAttribute("data-mode", "zoom-hint");
    await expect(page.getByTestId("map-range-legend-title")).toHaveText(TITLE);
    await expect(page.getByTestId("map-range-legend-blurb")).toHaveText(BLURB);
    await expect(page.getByTestId("map-range-legend-zoom-hint")).toHaveText(
      ZOOM_HINT,
    );
    await expect(page.getByTestId("map-range-legend-bands")).toHaveCount(0);
    await expect(page.getByTestId("map-range-legend-source")).toHaveCount(0);
    await expect(legend.getByText(/£\d/)).toHaveCount(0);
  });

  test("zoomed in shows bands, No data hatch, and source line", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await openMap(page);
    await panToGlasgow(page);

    const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
    for (let step = 0; step < 20; step += 1) {
      const zoom = await page.locator("#map").evaluate((el) =>
        Number((el as HTMLElement).dataset.zoom),
      );
      if (zoom >= 10) break;
      await zoomIn.click({ timeout: 10_000 });
      await page.waitForTimeout(450);
    }

    await expect
      .poll(
        async () =>
          page.locator("#map").evaluate((el) =>
            Number((el as HTMLElement).dataset.zoom),
          ),
        { timeout: 30_000 },
      )
      .toBeGreaterThanOrEqual(10);

    const legend = page.getByTestId("map-range-legend");
    await expect(legend).toBeVisible();
    await expect(legend).toHaveAttribute("data-mode", "bands", {
      timeout: 30_000,
    });
    await expect(page.getByTestId("map-range-legend-title")).toHaveText(TITLE);
    await expect(page.getByTestId("map-range-legend-blurb")).toHaveText(BLURB);
    await expect(page.getByTestId("map-range-legend-zoom-hint")).toHaveCount(0);
    await expect(page.getByTestId("map-range-legend-bands")).toBeVisible();
    await expect(page.getByTestId("map-range-legend-no-data")).toContainText(
      /no data/i,
    );
    await expect(page.getByTestId("map-range-legend-source")).toHaveText(SOURCE);
    await expect(legend.getByText(/£\d/)).toHaveCount(0);

    // Chip key stays off the permanent legend; only with chips (drawer / place card).
    await expect(
      page.locator("#hud-scotland-body").getByTestId("evidence-tag-legend"),
    ).toHaveCount(0);
  });
});

function mercator(lng: number, lat: number, zoom: number) {
  const scale = 512 * 2 ** zoom;
  const x = ((lng + 180) / 360) * scale;
  const sin = Math.sin((lat * Math.PI) / 180);
  const y = (0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI)) * scale;
  return { x, y };
}

async function panToGlasgow(page: Page) {
  const cam = await page.locator("#map").evaluate((el) => ({
    lng: Number((el as HTMLElement).dataset.lng),
    lat: Number((el as HTMLElement).dataset.lat),
    zoom: Number((el as HTMLElement).dataset.zoom),
  }));
  const from = mercator(cam.lng, cam.lat, cam.zoom);
  const to = mercator(GLASGOW.lng, GLASGOW.lat, cam.zoom);
  const dx = from.x - to.x;
  const dy = from.y - to.y;
  const start = await page.evaluate(() => {
    const canvas = document.querySelector(".maplibregl-canvas");
    if (!canvas) return null;
    const width = window.innerWidth;
    const height = window.innerHeight;
    for (let y = Math.floor(height * 0.42); y <= Math.floor(height * 0.72); y += 16) {
      for (let x = Math.floor(width * 0.4); x <= Math.floor(width * 0.82); x += 16) {
        if (document.elementFromPoint(x, y) === canvas) return { x, y };
      }
    }
    return null;
  });
  if (!start) throw new Error("No clear canvas point to pan the map to Glasgow");
  await page.mouse.move(start.x, start.y);
  await page.mouse.down();
  await page.mouse.move(start.x + dx, start.y + dy, { steps: 24 });
  await page.waitForTimeout(250);
  await page.mouse.up();
  await page.waitForTimeout(400);
}
