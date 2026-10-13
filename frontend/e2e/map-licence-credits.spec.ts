import { expect, test, type Page } from "@playwright/test";

const GLASGOW = { lng: -4.2514, lat: 55.8609 };

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
  await page.locator(".maplibregl-ctrl-attrib").waitFor();
}

test.describe("map licence credits (catalog-driven)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("range legend and no-data swatch; Locate / postcode / zone still work", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await openMap(page);

    // Range legend (population density bands) + hatched/grey no-data — no rent £.
    const legend = page.getByTestId("map-range-legend");
    await expect(legend).toBeVisible();
    await expect(legend.getByTestId("map-range-legend-no-data")).toContainText(
      /no data/i,
    );
    await expect(legend.getByText(/£\d/)).toHaveCount(0);

    // Must frame Scotland before any user zoom (zoom marks userMoved and skips framing).
    await page.locator("#map[data-framed='1']").waitFor({ timeout: 30_000 });
    await panToGlasgow(page);

    const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
    for (let step = 0; step < 14; step += 1) {
      const ready = await page.locator(".maplibregl-ctrl-attrib").textContent();
      if (ready?.includes("Registers of Scotland")) break;
      await zoomIn.click({ timeout: 10_000 });
      await page.waitForTimeout(500);
    }

    await expect(page.locator(".maplibregl-ctrl-attrib")).toContainText(
      "Registers of Scotland",
      { timeout: 45_000 },
    );

    // Enable boundaries credit in the catalog-driven control (zoom ≥ 14 auto-enables).
    const credits = page.getByTestId("map-licence-credits");
    await expect(credits).toBeVisible({ timeout: 45_000 });
    await expect(page.getByTestId("map-credit-boundaries")).toBeVisible({
      timeout: 30_000,
    });
    await expect(
      page.getByTestId("map-credit-licence-link-boundaries"),
    ).toHaveAttribute("href", /open-government-licence/);

    // Coordinate search still opens a place card (no public rent £).
    const search = page.locator("#place-query");
    await search.fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.locator("aside.place-card-stub");
    await expect(card).toBeVisible({ timeout: 45_000 });
    await expect(card.getByText(/£\d/)).toHaveCount(0);

    // Locate control remains present and clickable (geolocation may be denied).
    const locate = page.getByRole("button", { name: "Locate" });
    await expect(locate).toBeVisible();
    await locate.click();
  });

  test("non-commercial badge when ledger row 9 (NSTA) is on", async ({ page }) => {
    test.setTimeout(90_000);

    await page.route("**/layers/catalog**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          version: 2,
          layers: [
            {
              id: "nsta_oil_gas",
              group: "natural_capital",
              status: "linked",
              label: "NSTA oil and gas",
              licence: "non-commercial",
              licence_url: "https://www.nstauthority.co.uk/data-and-insights/",
              attribution:
                "Contains information provided by the North Sea Transition Authority and/or other third parties. Non-commercial use only.",
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
        }),
      });
    });
    await page.route("**/backend/layers/catalog**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          version: 2,
          layers: [
            {
              id: "nsta_oil_gas",
              group: "natural_capital",
              status: "linked",
              label: "NSTA oil and gas",
              licence: "non-commercial",
              licence_url: "https://www.nstauthority.co.uk/data-and-insights/",
              attribution:
                "Contains information provided by the North Sea Transition Authority and/or other third parties. Non-commercial use only.",
              ledger_row: "9",
              ui_surface: "ledger",
            },
          ],
        }),
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
    await page.getByRole("button", { name: "Ledger", exact: true }).click();
    const toggle = page.getByTestId("ledger-toggle-9");
    await expect(toggle).toBeVisible({ timeout: 20_000 });
    await toggle.click();

    await expect(page.getByTestId("map-non-commercial-badge")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("map-credit-nsta_oil_gas")).toBeVisible();
    await expect(page.getByTestId("map-credit-nsta_oil_gas")).toHaveAttribute(
      "data-non-commercial",
      "1",
    );
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

