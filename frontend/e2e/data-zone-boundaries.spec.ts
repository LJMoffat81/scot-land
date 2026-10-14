import { expect, test, type Page } from "@playwright/test";

const FIXTURE_ZONES = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-4.30, 55.84],
            [-4.20, 55.84],
            [-4.20, 55.89],
            [-4.30, 55.89],
            [-4.30, 55.84],
          ],
        ],
      },
      properties: {
        code: "S01014567",
        name: "City Centre South",
        vintage: 2022,
        la_name: "Glasgow City",
        population: 812,
        pop_year: 2022,
        dwellings: 410,
        dw_year: 2025,
        layer: "data_zones",
      },
    },
  ],
  meta: {
    ok: true,
    layer: "data_zones",
    count: 1,
    vintage: 2022,
    serve: "postgis:dz_boundaries",
    licence: "Open Government Licence v3.0",
    note: "Boundaries and open rollups only. No Annual Ground Rent.",
  },
};

async function mockDzRoutes(page: Page) {
  await page.route("**/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_ZONES),
    });
  });
  await page.route("**/backend/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_ZONES),
    });
  });
  await page.route("**/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: "S01014567",
        name: "City Centre South",
        vintage: 2022,
      }),
    });
  });
  await page.route("**/backend/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: "S01014567",
        name: "City Centre South",
        vintage: 2022,
      }),
    });
  });
}

test.describe("Data Zone boundaries layer", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("place card shows DZ2022 identity without £; HUD is Layers drawer", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await mockDzRoutes(page);
    await page.route("**/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat: 55.8609,
          lng: -4.2514,
          place_label: "City Centre South",
          council_name: "Glasgow City",
          data_zone: {
            status: "ok",
            code: "S01014567",
            name: "City Centre South",
            vintage: 2022,
          },
          intermediate_zone: { status: "ok", name: "City Centre" },
          agr_rows: [],
          constraints: [],
          layers: [],
          links: [],
        }),
      });
    });
    await page.goto("/?lat=55.8609&lng=-4.2514");
    await page.locator(".maplibregl-canvas").waitFor();

    await expect(
      page.getByRole("button", { name: "Ledger", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("layers-panel")).toBeVisible();
    await expect(panel.getByTestId("layer-toggle-data_zones")).toBeVisible();

    const card = page.locator("aside.place-card-stub");
    await expect(card).toBeVisible({ timeout: 20_000 });
    await expect(card.getByTestId("place-card-data-zone")).toContainText(/S01014567|City Centre/i);
    await expect(card).not.toContainText("£0");
    await expect(card.getByText(/£\d/)).toHaveCount(0);

    await page.getByRole("button", { name: "Layers", exact: true }).click();
    await page.waitForTimeout(800);
    await page.locator("#map").click({ position: { x: 720, y: 420 } });
    await expect(card.getByTestId("place-card-data-zone")).toContainText(/S01014567|City Centre/i, {
      timeout: 10_000,
    });
  });
});

test.describe("Data Zone catalog panel", () => {
  test.use({ viewport: { width: 1100, height: 900 } });

  test("LayersPanel lists live data_zones with OGL licence", async ({ page }) => {
    test.setTimeout(60_000);
    await page.route("**/layers/catalog", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          version: 2,
          layers: [
            {
              id: "data_zones",
              group: "spatial",
              status: "live",
              label: "Data Zone boundaries",
              description:
                "2011 outlines. Boundaries and open rollups — no money figures.",
              licence: "Open Government Licence v3.0",
              licence_url:
                "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
              source_url:
                "https://www.spatialdata.gov.scot/geonetwork/srv/eng/catalog.search#/metadata/7d564e13-a967-495a-ae2f-048ffdfa4b03",
            },
            {
              id: "agr_value",
              group: "value",
              status: "live",
              label: "Annual Ground Rent",
            },
            {
              id: "boundaries",
              group: "spatial",
              status: "live",
              label: "ROS INSPIRE parcels",
            },
            {
              id: "cell_grid",
              group: "value",
              status: "live",
              label: "W3W cell grid",
            },
            {
              id: "vdl",
              group: "spatial",
              status: "live",
              label: "Vacant and derelict land",
            },
            {
              id: "public_crown",
              group: "ownership",
              status: "gap",
              label: "Public and Crown Estate land",
              licence: "unverified/not open",
            },
          ],
        }),
      });
    });
    await page.goto("/layers-panel");
    await expect(page.getByTestId("layer-toggle-data_zones")).toBeVisible();
    await expect(page.getByTestId("layer-licence-data_zones")).toContainText(
      /Open Government Licence/i,
    );
    await expect(
      page.getByTestId("layer-licence-data_zones").locator("a"),
    ).toHaveAttribute("href", /open-government-licence/);
    await expect(page.getByTestId("layer-source-data_zones")).toBeVisible();
  });
});
