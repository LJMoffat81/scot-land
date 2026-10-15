import { expect, test, type Page } from "@playwright/test";

/**
 * POST-SHARE-1 (aligned with MAP-CARDS) — map reference removed; Aquaculture/LCA
 * deferred to roadmap; swagger Scot-LAND API badge; PAGE-WIDTH.
 * Viewports 390 and 1280. Fail on console errors.
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const PLACE_STUB = {
  contract: "place_card_v1",
  lat: 55.9533,
  lng: -3.1883,
  place_label: "Edinburgh Old Town",
  council_name: "City of Edinburgh",
  // Stale lat/lng index — UI must recompute OSGB36 from lat/lng.
  square_reference: "2076130,-66340",
  dwellings: 410,
  sales_year_from: 2019,
  sales_year_to: 2023,
  confidence: "Medium",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "Old Town",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "Old Town", code: "S02002645" },
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "proxy",
      class: "proxy",
      status: "in_progress",
      applies: true,
      range: "not yet estimated",
      unit: null,
      confidence: null,
      method: null,
      gloss: "The yearly value of the land under homes.",
      of_which: [],
    },
  ],
  constraints: [],
  layers: [],
  links: [],
  flags: [],
};

const CATALOG_NOT_LIVE = {
  version: 2,
  layers: [
    {
      id: "ces_aquaculture",
      status: "gap",
      label: "CES aquaculture seabed leases",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    },
    {
      id: "lca",
      status: "gap",
      label: "Land capability for agriculture",
      licence: "James Hutton Institute Open Data Licence",
      licence_url:
        "https://www.hutton.ac.uk/wp-content/uploads/2024/05/The-James-Hutton-Institute-Open-Data-Licence-download.pdf",
    },
    {
      id: "boundaries",
      status: "gap",
      label: "ROS INSPIRE parcels",
      licence: "Licensed under the Open Government Licence v3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    },
    {
      id: "data_zones",
      status: "live",
      label: "Data Zone boundaries",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    },
  ],
};

function attachConsoleGate(page: Page) {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  return { consoleErrors, pageErrors };
}

function filterNoise(errors: string[]) {
  return errors.filter(
    (t) =>
      !/favicon|Download the React DevTools|net::ERR_ABORTED/i.test(t) &&
      !/Failed to load resource:.*favicon/i.test(t),
  );
}

async function stubMapBackend(page: Page) {
  const layerHits: string[] = [];
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
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(CATALOG_NOT_LIVE),
      });
      return;
    }
    if (/\/platform\/place/i.test(url) || /\/place\?/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_STUB),
      });
      return;
    }
    if (/\/layers\/open\/ces-aquaculture/i.test(url)) {
      layerHits.push("ces_aquaculture");
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "not loaded" }),
      });
      return;
    }
    if (/\/layers\/open\/lca/i.test(url)) {
      layerHits.push("lca");
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "not loaded" }),
      });
      return;
    }
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
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(CATALOG_NOT_LIVE),
    });
  });
  return layerHits;
}

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

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`POST-SHARE-1 MAP-CARDS card + deferred layers (${viewport.width})`, () => {
    test.use({ viewport });

    test("no map reference; Aquaculture/LCA not in Layers; roadmap link", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      const layerHits = await stubMapBackend(page);

      await page.goto("/?lat=55.9533&lng=-3.1883");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });

      const card = page.getByTestId("place-card");
      if ((await card.count()) === 0) {
        await page.locator(".maplibregl-canvas").click({
          position: {
            x: Math.floor(viewport.width / 2),
            y: Math.floor(viewport.height / 2),
          },
        });
      }
      await expect(card).toBeVisible({ timeout: 30_000 });

      await expect(card.getByTestId("place-card-map-reference")).toHaveCount(0);
      await expect(card).not.toContainText(/map reference/i);
      await expect(page.locator("#place-query")).toHaveAttribute(
        "placeholder",
        /postcode or place/i,
      );

      await openLayers(page);
      for (const id of ["5", "lca"] as const) {
        await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
        await expect(page.getByTestId(`layer-coming-soon-${id}`)).toHaveCount(0);
      }
      await expect(page.getByTestId("layers-panel")).not.toContainText(
        /coming soon/i,
      );
      await expect(
        page.getByTestId("map-layers-roadmap-link").locator("a"),
      ).toHaveAttribute("href", "/roadmap#map-layers");
      await expect(page.getByTestId("layer-toggle-boundaries")).toHaveCount(0);

      expect(layerHits).toEqual([]);
      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });
  });
}

test.describe("POST-SHARE-1 PAGE-WIDTH (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("content max-width matches Across About / methodology / data / developers", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await page.route("**/backend/**", async (route) => {
      const url = route.request().url();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(/\/health/i.test(url) ? HEALTH_OK : {}),
      });
    });
    await page.route("**/api/catalog.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
    });
    await page.route("**/downloads/manifest.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ bundles: [] }),
      });
    });

    const paths = [
      { path: "/about", testId: "mission-page" },
      { path: "/methodology", testId: "methodology-page" },
      { path: "/data", testId: null },
      { path: "/developers", testId: "developers-page" },
      { path: "/downloads", testId: "developers-page" },
    ] as const;

    const widths: number[] = [];
    for (const entry of paths) {
      await page.goto(entry.path);
      const main = entry.testId
        ? page.getByTestId(entry.testId)
        : page.locator("main").first();
      await expect(main).toBeVisible({ timeout: 15_000 });
      const box = await main.boundingBox();
      expect(box, `${entry.path} box`).toBeTruthy();
      widths.push(box!.width);
    }
    const baseline = widths[0]!;
    for (let i = 1; i < widths.length; i += 1) {
      expect(
        Math.abs(widths[i]! - baseline),
        `width ${paths[i]!.path} ${widths[i]} vs about ${baseline}`,
      ).toBeLessThanOrEqual(2);
    }

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});

test.describe("POST-SHARE-1 SW-033 swagger badge", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("swagger shows Scot-LAND API, not wealth-api-boot", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    // Quiet footer /health and other probes so CI has no live FastAPI 503 noise.
    await page.route("**/backend/**", async (route) => {
      const url = route.request().url();
      if (/\/openapi\.json/i.test(url)) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            openapi: "3.0.3",
            info: {
              title: "wealth-api-boot",
              version: "wealth-api-boot",
              description: "Fixture — rewrite must hide legacy badge.",
            },
            paths: {
              "/health": {
                get: {
                  summary: "Health",
                  responses: { "200": { description: "ok" } },
                },
              },
            },
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(/\/health/i.test(url) ? HEALTH_OK : {}),
      });
    });
    await page.route("**/api/catalog.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
    });

    await page.goto("/developers/api");
    await expect(page.getByTestId("api-reference-title")).toHaveText(
      "Scot-LAND API",
    );
    await expect(page.locator(".swagger-ui .info .title").first()).toContainText(
      "Scot-LAND API",
      { timeout: 15_000 },
    );
    await expect(page.locator("body")).not.toContainText("wealth-api-boot");

    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});
