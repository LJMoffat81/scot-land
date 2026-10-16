import { expect, test, type Page } from "@playwright/test";

/**
 * GBP-LIVE-V1 — flag OFF: no £. Flag ON (mocked): range + estimate label;
 * under-review hides £; placeholder hidden; no total; rent-rate wording;
 * API class "shadow" never appears as visible visitor text.
 */

const PRE_POUND =
  "We're not showing amounts yet while we check our method.";

const RENT_RATE_CARD =
  "Yearly rent: up to 4.5% of the land's value";

const RENT_RATE_HOW_IT_WORKS =
  "We turn land value into a yearly rent of up to 4.5% of that value.";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

function agrRows() {
  return [
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
      gloss: "The yearly rental value of the land under homes, without the buildings.",
      of_which: [{ id: "planning_uplift", label: "of which: planning uplift" }],
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
      gloss: "Rent from natural resources such as wind, water, minerals and fish farm sites.",
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
      gloss: "What nature gives us for free, such as peat holding carbon. Estimate only.",
    },
  ];
}

function placeFixture(overrides: Record<string, unknown> = {}) {
  return {
    contract: "place_card_v1",
    lat: 55.8609,
    lng: -4.2514,
    place_label: "Glasgow City Centre",
    council_name: "Glasgow City",
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
    agr_rows: agrRows(),
    constraints: [],
    holder: { status: "private_not_shown", label: "private, not shown" },
    layers: [
      {
        id: "boundaries",
        label: "Boundaries",
        status: "live",
        intersects: true,
        licence: "Open Government Licence v3.0",
      },
    ],
    links: [{ id: "methodology", label: "How we work this out", url: "/methodology" }],
    land_outline: { status: "inside_outline", label: "Land outline", area_sqm: 120 },
    gbp_live: { enabled: false },
    ...overrides,
  };
}

async function stubShell(page: Page, place: Record<string, unknown>, gbpLiveEnabled: boolean) {
  const gbpLiveBody = gbpLiveEnabled
    ? {
        enabled: true,
        banner: "Early estimates; ranges are wide and will change.",
        rent_rate_wording: RENT_RATE_HOW_IT_WORKS,
      }
    : { enabled: false, banner: null, rent_rate_wording: null };
  // Quiet FastAPI: boundaries must be FeatureCollection (MapLibre rejects {}).
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
    if (/\/platform\/gbp-live/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(gbpLiveBody),
      });
      return;
    }
    if (/\/platform\/place/i.test(url) || /\/api\/place\.json/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(place),
      });
      return;
    }
    if (/\/layers\/context\/data-zones\/at/i.test(url)) {
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
  await page.route("**/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  // Same-origin probe + backend path both return 200 (never 404 when flag off).
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(gbpLiveBody),
    });
  });
  await page.route("**/platform/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(gbpLiveBody),
    });
  });
  await page.route("**/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(place),
    });
  });
  await page.route("**/api/place.json**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(place),
    });
  });
  await page.route("**/layers/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
}

async function openPlaceCard(page: Page) {
  // Deep-link boot (?lat=&lng=) — reliable under MAP-CARDS panel slot.
  await page.goto("/?lat=55.8609&lng=-4.2514");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const card = page.getByTestId("place-card");
  if ((await card.count()) === 0) {
    await page.locator(".maplibregl-canvas").click({
      position: { x: 400, y: 300 },
    });
  }
  await expect(card).toBeVisible({ timeout: 45_000 });
}

test.describe("GBP-LIVE-V1 flag OFF", () => {
  test("no £ on place card", async ({ page }) => {
    test.setTimeout(90_000);
    await stubShell(page, placeFixture(), false);
    await openPlaceCard(page);
    const card = page.getByTestId("place-card");
    // MAP-CARDS §5: status + pre-pound live in the answer row.
    const figure = card.getByTestId("place-card-figure");
    await expect(figure.getByTestId("place-card-figure-status")).toHaveText(
      "Not published yet",
    );
    await expect(figure).toContainText(PRE_POUND);
    await expect(card).not.toContainText("£");
    await expect(card.getByTestId("place-card-figure-range")).toHaveCount(0);
  });
});

test.describe("GBP-LIVE-V1 flag ON", () => {
  test("place card shows per-m² range, unit label, and chip (GBP-LIVE-V1c)", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const place = placeFixture({
      gbp_live: {
        enabled: true,
        banner: "Early estimates; ranges are wide and will change.",
        rent_rate_wording: RENT_RATE_HOW_IT_WORKS,
        unit: "per m²",
        unit_wording: "per square metre of land, per year",
      },
      surface_rent_display: {
        state: "ok",
        low: 0.06,
        central: 0.12,
        high: 0.18,
        estimate_label: "Partly estimated",
        rent_rate_wording: RENT_RATE_CARD,
        unit: "per m²",
        unit_wording: "per square metre of land, per year",
        grain: "data_zone",
      },
    });
    await stubShell(page, place, true);
    await openPlaceCard(page);
    const card = page.getByTestId("place-card");
    const range = card.getByTestId("place-card-figure-range");
    await expect(range).toContainText("£0.0600");
    await expect(range).toContainText("to");
    await expect(range).toContainText("£0.180");
    await expect(range).toContainText("per m²");
    await expect(card.getByTestId("place-card-figure-unit")).toHaveText(
      "£ per square metre of land, per year",
    );
    await expect(card).not.toContainText("£0.00");
    // No single-point central £ without the range (MAP-CARDS / V1c).
    // Whole-card substring: anchored /^£0.120$/ can never fail on multi-node text.
    // Fixture low/high are £0.0600 / £0.180 — no false hit on "£0.120".
    await expect(card).not.toContainText("£0.120");
    // Chip on the answer row (parts accordion also tags Land as Modelled).
    await expect(
      card.getByTestId("place-card-figure").getByTestId("place-tag-proxy"),
    ).toBeVisible();
    await expect(card).not.toContainText(/Scotland total|national total/i);
    await expect(card).not.toContainText(/\byield\b/i);
  });

  test("API class shadow never shows as visible text", async ({ page }) => {
    test.setTimeout(90_000);
    const place = placeFixture({
      gbp_live: {
        enabled: true,
        banner: "Early estimates; ranges are wide and will change.",
        rent_rate_wording: RENT_RATE_HOW_IT_WORKS,
      },
      surface_rent_display: {
        state: "ok",
        low: 0.06,
        central: 0.12,
        high: 0.18,
        estimate_label: "Partly estimated",
        rent_rate_wording: RENT_RATE_CARD,
        grain: "data_zone",
      },
    });
    // Fixture includes nature row with tag/class "shadow" — visitor never sees "shadow".
    await stubShell(page, place, true);
    await openPlaceCard(page);
    const card = page.getByTestId("place-card");
    await card.getByTestId("place-card-parts").locator("summary").click();
    const nature = card.getByTestId("place-card-agr-nature");
    await expect(nature).toHaveAttribute("data-class", "estimate");
    await expect(nature).not.toContainText(/\bshadow\b/i);
    await expect(card).not.toContainText(/\bshadow\b/i);
  });

  test("under-review zone shows estimate unavailable and no £", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const place = placeFixture({
      gbp_live: { enabled: true },
      surface_rent_display: {
        state: "under_review",
        label: "estimate unavailable",
        low: null,
        central: null,
        high: null,
        estimate_label: null,
      },
      agr_rows: agrRows().map((row) =>
        row.id === "surface" ? { ...row, range: "estimate unavailable" } : row,
      ),
    });
    await stubShell(page, place, true);
    await openPlaceCard(page);
    const card = page.getByTestId("place-card");
    await expect(card.getByTestId("place-card-under-review")).toHaveText(
      "estimate unavailable",
    );
    await expect(card).not.toContainText("£");
  });

  test("placeholder / hidden display never shows £", async ({ page }) => {
    test.setTimeout(90_000);
    const place = placeFixture({
      gbp_live: { enabled: true },
      surface_rent_display: {
        state: "hidden",
        low: null,
        central: null,
        high: null,
        estimate_label: null,
      },
    });
    await stubShell(page, place, true);
    await openPlaceCard(page);
    const card = page.getByTestId("place-card");
    await expect(card.getByTestId("place-card-figure")).toContainText(PRE_POUND);
    await expect(card).not.toContainText("£");
  });
});
