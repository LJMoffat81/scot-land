import { expect, test, type Page } from "@playwright/test";

/**
 * MAPREF-HIDE — place card must not show "Map reference" (or Copy) at 390 and 1280.
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
  lat: 55.8609,
  lng: -4.2514,
  place_label: "Glasgow City Centre",
  council_name: "Glasgow City",
  square_reference: "2068927,-157234",
  dwellings: 410,
  sales_year_from: 2019,
  sales_year_to: 2023,
  confidence: "Medium",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre", code: "S02002645" },
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
    {
      id: "resource",
      label: "Natural resource rents",
      tag: "market",
      class: "market",
      status: "coming_soon",
      applies: true,
      range: "not yet estimated",
      unit: null,
      confidence: null,
      method: null,
      gloss: "Rents from things like wind, minerals and fish farming.",
    },
    {
      id: "nature",
      label: "Services of nature",
      tag: "shadow",
      class: "shadow",
      status: "coming_soon",
      applies: true,
      range: "not yet estimated",
      unit: null,
      confidence: null,
      method: null,
      gloss: "Value from nature's services, such as peat holding carbon.",
    },
  ],
  constraints: [],
  layers: [],
  links: [],
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
  return errors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    if (
      /Failed to load resource: the server responded with a status of (400|404|503)/i.test(
        text,
      )
    ) {
      return false;
    }
    return true;
  });
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
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/backend/layers/**", async (route) => {
    const url = route.request().url();
    if (/data-zones\/at/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: "S01014567",
          name: "City Centre South",
          vintage: 2022,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
    });
  });
  await page.route("**/backend/api/place.json**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
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

async function openPlaceCard(page: Page, clickX: number, clickY: number) {
  await page.goto("/?lat=55.8609&lng=-4.2514");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const card = page.getByTestId("place-card");
  if ((await card.count()) === 0) {
    await page.locator(".maplibregl-canvas").click({
      position: { x: clickX, y: clickY },
    });
  }
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

async function assertNoMapReference(page: Page) {
  const card = page.getByTestId("place-card");
  await expect(card).not.toContainText("Map reference");
  await expect(card.getByTestId("place-card-map-reference")).toHaveCount(0);
  await expect(card.getByTestId("place-card-map-reference-copy")).toHaveCount(0);
}

test.describe("MAPREF-HIDE place card (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("no Map reference text or Copy on place card", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page);
    await openPlaceCard(page, 400, 300);
    await assertNoMapReference(page);
    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});

test.describe("MAPREF-HIDE place card (390)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("no Map reference text or Copy on place card", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page);
    await openPlaceCard(page, 195, 400);
    await assertNoMapReference(page);
    expect(filterNoise(gate.consoleErrors)).toEqual([]);
    expect(filterNoise(gate.pageErrors)).toEqual([]);
  });
});
