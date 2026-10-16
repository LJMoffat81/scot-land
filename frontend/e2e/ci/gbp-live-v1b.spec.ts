import { expect, test, type Page } from "@playwright/test";

/**
 * GBP-LIVE-V1b — MAP-CARDS §5 answer row: flag OFF shows status + pre-pound
 * (no £); flag ON shows £a to £b a year + chip. Widths 390 and 1280.
 * Surface Rent per-m² lens is not the public PlaceCard figure (AGR residual).
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
      gloss: "The yearly value of the land under homes.",
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

async function stubShell(
  page: Page,
  place: Record<string, unknown>,
  gbpLiveEnabled: boolean,
) {
  await page.route("**/health", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  const gbpLiveBody = gbpLiveEnabled
    ? {
        enabled: true,
        banner: "Early estimates; ranges are wide and will change.",
        rent_rate_wording: RENT_RATE_HOW_IT_WORKS,
      }
    : {
        enabled: false,
        banner: null,
        rent_rate_wording: null,
      };
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
    const url = route.request().url();
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ version: 2, layers: [] }),
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
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/boundaries/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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

/** Open via deep-link coords — map tap is unreliable at 390 (mobile sheet). */
async function openPlaceCard(page: Page) {
  await page.goto("/?lat=55.860900&lng=-4.251400");
  await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });
}

const okPlace = () =>
  placeFixture({
    gbp_live: {
      enabled: true,
      banner: "Early estimates; ranges are wide and will change.",
      rent_rate_wording: RENT_RATE_HOW_IT_WORKS,
    },
    surface_rent_display: {
      state: "ok",
      low: 6000,
      central: 12000,
      high: 18000,
      estimate_label: "Partly estimated",
      rent_rate_wording: RENT_RATE_CARD,
      grain: "data_zone",
    },
  });

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`GBP-LIVE-V1b ${viewport.width}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("flag OFF: no £ on place card", async ({ page }) => {
      await stubShell(page, placeFixture(), false);
      await openPlaceCard(page);
      const card = page.getByTestId("place-card");
      const figure = card.getByTestId("place-card-figure");
      await expect(figure.getByTestId("place-card-figure-status")).toHaveText(
        "Not published yet",
      );
      await expect(figure).toContainText(PRE_POUND);
      await expect(card).not.toContainText("£");
      await expect(card.getByTestId("place-card-figure-range")).toHaveCount(0);
    });

    test("flag ON: £a to £b a year range and chip (MAP-CARDS §5)", async ({
      page,
    }) => {
      await stubShell(page, okPlace(), true);
      await openPlaceCard(page);
      const card = page.getByTestId("place-card");
      const range = card.getByTestId("place-card-figure-range");
      await expect(range).toContainText("£6,000");
      await expect(range).toContainText("to");
      await expect(range).toContainText("£18,000");
      await expect(range).toContainText("a year");
      await expect(card.getByTestId("place-card-figure")).not.toContainText(
        /^£12,000$/,
      );
      await expect(
        card.getByTestId("place-card-figure").getByTestId("place-tag-proxy"),
      ).toBeVisible();
      await expect(card).not.toContainText(/Scotland total|national total/i);
      await expect(card).not.toContainText(/\byield\b/i);
    });

    test("flag ON missing area / under review: no £", async ({ page }) => {
      const place = placeFixture({
        gbp_live: { enabled: true },
        surface_rent_display: {
          state: "under_review",
          label: "Under review",
          low: null,
          central: null,
          high: null,
          estimate_label: null,
        },
        agr_rows: agrRows().map((row) =>
          row.id === "surface" ? { ...row, range: "Under review" } : row,
        ),
      });
      await stubShell(page, place, true);
      await openPlaceCard(page);
      const card = page.getByTestId("place-card");
      await expect(card.getByTestId("place-card-under-review")).toHaveText(
        "Under review",
      );
      await expect(card).not.toContainText("£");
    });
  });
}
