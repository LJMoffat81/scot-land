import { expect, test, type Page } from "@playwright/test";

/**
 * SW-022 — population density map legend.
 * National zoom → zoom hint; zoomed in → bands + source. Fail on console errors.
 */

const GLASGOW = { lng: -4.2514, lat: 55.8609 };

const TITLE = "Population density — people per km²";
const BLURB = "Busier places tend to have higher land rents.";
const SOURCE =
  "Source: National Records of Scotland mid-year estimates, Open Government Licence v3.0";
const ZOOM_HINT = "Zoom in to see colours";

const consoleErrors: string[] = [];

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
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
    for (let step = 0; step < 16; step += 1) {
      const zoom = await page.locator("#map").evaluate((el) =>
        Number((el as HTMLElement).dataset.zoom),
      );
      if (zoom >= 10) break;
      await zoomIn.click({ timeout: 10_000 });
      await page.waitForTimeout(400);
    }

    await expect
      .poll(async () =>
        page.locator("#map").evaluate((el) =>
          Number((el as HTMLElement).dataset.zoom),
        ),
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
