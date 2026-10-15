import { expect, test, type Page } from "@playwright/test";

/**
 * UX10-2 built-up mask — 390 and 1280; NRS+OS attribution visible; no £;
 * no parcel polygons; faint DZ outlines stay available; console/pageerror gate.
 */

const ATTRIBUTION = "NRS Settlements 2022 (OGL v3), contains OS data";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const MASK_FC = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { code: "S01014567", layer: "dz2022_masked" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-4.26, 55.858],
            [-4.25, 55.858],
            [-4.25, 55.865],
            [-4.26, 55.865],
            [-4.26, 55.858],
          ],
        ],
      },
    },
  ],
  meta: {
    ok: true,
    attribution: ATTRIBUTION,
    licence: "OGL-3.0",
  },
};

const CATALOG = {
  version: 2,
  layers: [
    {
      id: "data_zones",
      group: "spatial",
      status: "live",
      label: "Data Zone boundaries",
      licence: "OGL-3.0",
      attribution:
        "Scottish Government Data Zone boundaries 2022 (OGL). Outlines only — not a rent.",
    },
    {
      id: "builtup_mask",
      group: "spatial",
      status: "live",
      label: "Built-up display mask",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      attribution: ATTRIBUTION,
      endpoint: "/layers/open/dz2022-masked",
      tile_endpoint: "/layers/open/dz2022-masked/tiles/{z}/{x}/{y}",
    },
    {
      id: "boundaries",
      group: "spatial",
      status: "live",
      label: "ROS INSPIRE parcels",
      licence: "OGL-3.0",
    },
  ],
};

type ConsoleGate = {
  consoleErrors: string[];
  pageErrors: string[];
};

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    pageErrors.push(String(err));
  });
  return { consoleErrors, pageErrors };
}

function filterNoise(errors: string[]): string[] {
  return errors.filter(
    (text) =>
      !/AbortError|aborted|Failed to fetch|net::ERR_|400|404|503/i.test(text),
  );
}

async function stubMapBackend(page: Page) {
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
      body: JSON.stringify(CATALOG),
    });
  });
  await page.route("**/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(CATALOG),
    });
  });
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract: "place_card_v1",
        lat: 55.86,
        lng: -4.25,
        place_label: "Glasgow",
      }),
    });
  });
  await page.route("**/backend/layers/open/dz2022-masked**", async (route) => {
    const url = route.request().url();
    if (/\/tiles\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/vnd.mapbox-vector-tile",
        body: Buffer.alloc(0),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MASK_FC),
    });
  });
  await page.route("**/backend/layers/open/builtup-mask**", async (route) => {
    const url = route.request().url();
    if (/\/tiles\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/vnd.mapbox-vector-tile",
        body: Buffer.alloc(0),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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
      body: JSON.stringify({
        code: "S01014567",
        name: "City Centre South",
        vintage: 2022,
      }),
    });
  });
  await page.route("**/backend/layers/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/backend/platform/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false, banner: null, rent_rate_wording: null }),
    });
  });
}

async function openTools(page: Page) {
  const tools = page.getByRole("button", { name: /Map layers|Layers/i }).first();
  if (await tools.isVisible().catch(() => false)) {
    await tools.click();
  }
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`UX10-2 built-up mask ${viewport.width}`, () => {
    test.use({ viewport });

    test("attribution visible; no £; parcels stay off", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);

      await page.goto("/?lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });

      await openTools(page);
      const maskToggle = page.getByTestId("layer-toggle-builtup_mask");
      await expect(maskToggle).toBeVisible({ timeout: 30_000 });
      if ((await maskToggle.getAttribute("aria-pressed")) !== "true") {
        await maskToggle.click();
      }
      await expect(maskToggle).toHaveAttribute("aria-pressed", "true");

      // Faint full DZ outlines remain available as a toggle (click target).
      await expect(page.getByTestId("layer-toggle-data_zones")).toBeVisible();

      // Parcels stay off (PARCELS-OFF).
      await expect(page.getByTestId("layer-toggle-boundaries")).toHaveCount(0);
      const parcelTile = await page.request.get("/api/parcels/tiles/14/8045/5230");
      expect(parcelTile.status()).toBe(404);

      const credits = page.getByTestId("map-licence-credits");
      await expect(credits).toBeVisible({ timeout: 45_000 });
      await expect(page.getByTestId("map-credit-builtup_mask")).toBeVisible({
        timeout: 30_000,
      });
      await expect(credits).toContainText("NRS Settlements 2022");
      await expect(credits).toContainText("OS data");
      await expect(credits).toContainText(ATTRIBUTION);

      const bodyText = await page.locator("body").innerText();
      expect(bodyText).not.toMatch(/£\d/);
      expect(bodyText.toLowerCase()).not.toContain("natural capital");
      expect(bodyText.toLowerCase()).not.toMatch(/\bledger\b/);

      const attrib = page.locator(".maplibregl-ctrl-attrib");
      await expect(attrib).toContainText(/NRS Settlements 2022|OS data/i, {
        timeout: 45_000,
      });

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });
  });
}
