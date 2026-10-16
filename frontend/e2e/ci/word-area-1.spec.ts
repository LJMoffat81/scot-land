import { expect, test, type Page } from "@playwright/test";

/**
 * WORD-AREA-1 — no "neighbourhood" on visitor surfaces.
 * Auto-discovered under e2e/ci/. Widths 390 and 1280. Console errors fail.
 */

const NEIGHBOURHOOD = /neighbo(u)?rhood/i;
const TYPICAL_HOME = "For a typical home in this area, not your home.";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const EH1 = { lat: 55.9533, lng: -3.1883, label: "Edinburgh" };
const PERTH = { lat: 56.395, lng: -3.4308, label: "Perth" };

function placeStub(label: string, lat: number, lng: number) {
  return {
    contract: "place_card_v1",
    lat,
    lng,
    place_label: label,
    council_name: label === "Perth" ? "Perth and Kinross" : "City of Edinburgh",
    data_zone: {
      status: "ok",
      code: label === "Perth" ? "S01011858" : "S01008680",
      name: label,
      vintage: 2022,
    },
    intermediate_zone: { status: "ok", name: label },
    dwellings: 120,
    agr_rows: [
      {
        id: "surface",
        label: "Land",
        tag: "proxy",
        class: "proxy",
        status: "in_progress",
        applies: true,
        gloss:
          "The yearly rental value of the land under homes, without the buildings.",
        range: "not yet estimated",
      },
      {
        id: "resource",
        label: "Natural resource rents",
        tag: "market",
        class: "market",
        status: "coming_soon",
        applies: true,
        gloss:
          "Rent from natural resources such as wind, water, minerals and fish farm sites.",
        range: "not yet estimated",
      },
      {
        id: "nature",
        label: "Services of nature",
        tag: "shadow",
        class: "shadow",
        status: "coming_soon",
        applies: true,
        gloss:
          "What nature gives us for free, such as peat holding carbon. Estimate only.",
        range: "not yet estimated",
      },
    ],
    constraints: [],
    layers: [],
    links: [],
  };
}

type ConsoleGate = {
  consoleErrors: string[];
  pageErrors: string[];
};

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  return { consoleErrors, pageErrors };
}

function filterNoise(errors: string[]): string[] {
  return errors.filter(
    (text) =>
      !/AbortError|aborted|Failed to fetch|net::ERR_|400|404|503/i.test(text),
  );
}

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/platform\/place/i.test(url)) {
      const parsed = new URL(url);
      const lat = Number(parsed.searchParams.get("lat"));
      const perth = Number.isFinite(lat) && lat > 56;
      const spot = perth ? PERTH : EH1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(placeStub(spot.label, spot.lat, spot.lng)),
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
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        layers: [
          {
            id: "data_zones",
            label: "Area boundaries",
            description: "The small areas we report on",
            licence: "OGL v3.0",
            licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
          },
          {
            id: "nfi",
            label: "Woodland",
            description: "Woodland map, shown for context.",
            licence: "OGL v3.0",
            licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
          },
        ],
      }),
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

async function assertNoNeighbourhood(page: Page) {
  const visible = await page.locator("body").innerText();
  expect(visible).not.toMatch(NEIGHBOURHOOD);
  const aria = await page.evaluate(() => {
    const bits: string[] = [];
    document.querySelectorAll("*").forEach((el) => {
      for (const name of [
        "aria-label",
        "aria-description",
        "aria-roledescription",
        "title",
        "alt",
        "placeholder",
      ]) {
        const value = el.getAttribute(name);
        if (value) bits.push(value);
      }
    });
    return bits.join("\n");
  });
  expect(aria).not.toMatch(NEIGHBOURHOOD);
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

async function openPlace(page: Page, lat: number, lng: number) {
  await page.goto(`/?lat=${lat}&lng=${lng}`);
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const card = page.getByTestId("place-card");
  if ((await card.count()) === 0) {
    const canvas = page.locator(".maplibregl-canvas");
    const box = await canvas.boundingBox();
    await canvas.click({
      position: {
        x: box ? Math.min(200, box.width / 2) : 120,
        y: box ? Math.min(240, box.height / 2) : 160,
      },
    });
  }
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(card.getByTestId("place-card-typical-home")).toHaveText(
    TYPICAL_HOME,
  );
  await assertNoNeighbourhood(page);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`WORD-AREA-1 no neighbourhood ${viewport.width}`, () => {
    test.use({ viewport });

    test("home, place cards, layers, data, roadmap", async ({ page }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await stubMapBackend(page);

      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await assertNoNeighbourhood(page);

      await openLayers(page);
      await expect(page.getByTestId("layers-panel")).toContainText(
        "Area boundaries",
      );
      await assertNoNeighbourhood(page);

      await openPlace(page, EH1.lat, EH1.lng);
      await openPlace(page, PERTH.lat, PERTH.lng);

      await page.goto("/data");
      await expect(page.getByRole("heading", { name: "Data & sources" })).toBeVisible({
        timeout: 30_000,
      });
      await assertNoNeighbourhood(page);

      await page.goto("/roadmap");
      await expect(page.getByTestId("roadmap-page")).toBeVisible({
        timeout: 30_000,
      });
      await assertNoNeighbourhood(page);

      expect(filterNoise(gate.consoleErrors)).toEqual([]);
      expect(filterNoise(gate.pageErrors)).toEqual([]);
    });
  });
}
