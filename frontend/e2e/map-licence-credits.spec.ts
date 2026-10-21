import {
  injectEsriBasemapKey,
} from "./ci/_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

const GLASGOW = { lng: -4.2514, lat: 55.8609 };

const BOUNDARIES_ATTRIBUTION =
  "© Crown copyright. Reproduced with the permission of Registers of Scotland. Contains OS data © Crown copyright and database right 2026. OGL-3.0.";

const NSTA_ATTRIBUTION =
  "Contains information provided by the North Sea Transition Authority and/or other third parties. Non-commercial use only.";

async function openMap(page: Page) {
  await injectEsriBasemapKey(page);
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
  await page.getByTestId("map-credit-line").waitFor();
  await expect(page.locator(".maplibregl-ctrl-attrib")).toHaveCount(0);
}

async function openSources(page: Page) {
  // r6: Sources stays on the visible credit line at every width.
  await page.getByTestId("map-all-sources").click();
  await expect(page).toHaveURL(/\/data#licences/);
}

test.describe("map licence credits (catalog-driven)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("range legend and no-data swatch; postcode / zone still work", async ({
    page,
  }) => {
    test.setTimeout(120_000);

    const catalogBody = {
      version: 2,
      layers: [
        {
          id: "boundaries",
          group: "spatial",
          status: "live",
          label: "ROS INSPIRE parcels",
          licence: "OGL-3.0",
          licence_url:
            "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
          attribution: BOUNDARIES_ATTRIBUTION,
          source_url: "https://www.ros.gov.uk/open-data",
        },
      ],
    };
    await page.route("**/layers/catalog**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(catalogBody),
      });
    });
    await page.route("**/backend/layers/catalog**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(catalogBody),
      });
    });
    await page.route("**/api/catalog.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(catalogBody),
      });
    });

    await openMap(page);

    // At national zoom the density legend shows the zoom hint (no bands yet).
    const legend = page.getByTestId("map-range-legend");
    await expect(legend).toBeVisible();
    await expect(legend).toContainText(/population density/i);
    await expect(legend).toContainText(/Zoom in to see colours/i);
    await expect(legend.getByText(/£\d/)).toHaveCount(0);

    // Must frame Scotland before any user zoom (zoom marks userMoved and skips framing).
    await page.locator("#map[data-framed='1']").waitFor({ timeout: 30_000 });
    await panToGlasgow(page);

    const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
    for (let step = 0; step < 14; step += 1) {
      await zoomIn.click({ timeout: 10_000 });
      await page.waitForTimeout(500);
    }

    // Zoomed in: density bands + hatched no-data — still no rent £.
    await expect(legend).toHaveAttribute("data-mode", "bands", {
      timeout: 45_000,
    });
    await expect(legend.getByTestId("map-range-legend-no-data")).toContainText(
      /no data/i,
    );
    await expect(legend.getByText(/£\d/)).toHaveCount(0);

    // Catalog-driven boundaries credit via Sources (MF3).
    await openSources(page);
    await expect(page.getByText("ROS INSPIRE parcels").first()).toBeVisible({
      timeout: 30_000,
    });
    await expect(
      page.locator('a[href*="open-government-licence"]').first(),
    ).toBeVisible();
    const catalogOnSources = await page.evaluate(async () => {
      const res = await fetch("/api/catalog.json");
      return (await res.json()) as {
        layers?: Array<{ attribution?: string; licence_url?: string }>;
      };
    });
    const boundaries = catalogOnSources.layers?.find(
      (layer) =>
        typeof layer.attribution === "string" &&
        layer.attribution.includes("Registers of Scotland"),
    );
    expect(boundaries?.attribution).toBe(BOUNDARIES_ATTRIBUTION);
    expect(boundaries?.licence_url).toMatch(/open-government-licence/);

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.getByTestId("map-credit-line").waitFor();

    // Coordinate search still opens a place card (no public rent £).
    const search = page.locator("#place-query");
    await search.fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.locator("aside.place-card-stub");
    await expect(card).toBeVisible({ timeout: 45_000 });
    await expect(card.getByText(/£\d/)).toHaveCount(0);

    // Locate control was removed (SW-023); basemap switcher is the chrome control.
    await expect(page.getByRole("button", { name: "Locate" })).toHaveCount(0);
    await expect(page.getByTestId("basemap-switcher")).toBeVisible();
  });

  test("non-commercial badge when ledger row 9 (NSTA) is on", async ({ page }) => {
    test.setTimeout(90_000);

    const catalogBody = {
      version: 2,
      layers: [
        {
          id: "nsta_oil_gas",
          group: "natural_capital",
          status: "linked",
          label: "NSTA oil and gas",
          licence: "non-commercial",
          licence_url: "https://www.nstauthority.co.uk/data-and-insights/",
          attribution: NSTA_ATTRIBUTION,
          ledger_row: "9",
          ui_surface: "ledger",
        },
        {
          id: "boundaries",
          group: "spatial",
          status: "live",
          label: "ROS INSPIRE parcels",
          licence: "OGL-3.0",
          licence_url:
            "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
          attribution:
            "© Crown copyright. Reproduced with the permission of Registers of Scotland.",
        },
      ],
    };
    await page.route("**/layers/catalog**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(catalogBody),
      });
    });
    await page.route("**/backend/layers/catalog**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(catalogBody),
      });
    });
    await page.route("**/api/catalog.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(catalogBody),
      });
    });
    await page.route("**/ledger**", async (route) => {
      if (route.request().resourceType() === "document") {
        await route.continue();
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          version: 1,
          rows: [
            {
              id: "9",
              label: "Oil & gas",
              tag: "reported",
              status: "partial",
              note: "Outside Scottish total",
            },
          ],
          constraints: [],
        }),
      });
    });

    await openMap(page);
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const toggle = page.getByTestId("layer-toggle-9");
    await expect(toggle).toBeVisible({ timeout: 20_000 });
    await toggle.click();

    await openSources(page);
    await expect(page.getByText(/NSTA oil and gas/i).first()).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByText(/non-commercial/i).first()).toBeVisible();
    await expect(page.getByText(/ROS INSPIRE parcels/i).first()).toBeVisible();
    const catalogOnSources = await page.evaluate(async () => {
      const res = await fetch("/api/catalog.json");
      return (await res.json()) as {
        layers?: Array<{
          id?: string;
          attribution?: string;
          licence?: string;
        }>;
      };
    });
    const nsta = catalogOnSources.layers?.find((l) => l.id === "nsta_oil_gas");
    expect(nsta?.attribution).toBe(NSTA_ATTRIBUTION);
    expect(nsta?.licence).toMatch(/non-commercial/i);
    expect(
      catalogOnSources.layers?.some(
        (l) =>
          typeof l.attribution === "string" &&
          l.attribution.includes("Registers of Scotland"),
      ),
    ).toBe(true);
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
