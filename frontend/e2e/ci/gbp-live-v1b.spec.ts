import { expect, test, type Page } from "@playwright/test";

/**
 * GBP-LIVE-V1b — every £ behind the flag is per m² (range + most likely +
 * estimate label). Flag OFF: no £. Widths 390 and 1280 (_COMMON.md).
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
        unit: "per m²",
        unit_wording: "per m² of land a year",
      }
    : {
        enabled: false,
        banner: null,
        rent_rate_wording: null,
        unit: null,
        unit_wording: null,
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
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
}

/** Open via search/coords query — map tap is unreliable at 390 (mobile sheet). */
async function openPlaceCard(page: Page) {
  await page.goto("/?lat=55.860900&lng=-4.251400");
  await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });
}

/** Every text node that contains £ must also contain "per m²". */
async function assertEveryPoundHasPerM2(page: Page, rootTestId: string) {
  const violations = await page.locator(`[data-testid="${rootTestId}"]`).evaluate(
    (root) => {
      const bad: string[] = [];
      const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
      let node = walker.nextNode();
      while (node) {
        const text = (node.textContent || "").trim();
        if (text.includes("£") && !text.includes("per m²")) {
          bad.push(text);
        }
        node = walker.nextNode();
      }
      return bad;
    },
  );
  expect(violations, `£ without per m²: ${violations.join(" | ")}`).toEqual([]);
}

const okPlace = () =>
  placeFixture({
    gbp_live: {
      enabled: true,
      banner: "Early estimates; ranges are wide and will change.",
      rent_rate_wording: RENT_RATE_HOW_IT_WORKS,
      unit: "per m²",
      unit_wording: "per m² of land a year",
    },
    surface_rent_display: {
      state: "ok",
      low: 0.06,
      central: 0.12,
      high: 0.18,
      estimate_label: "Partly estimated",
      rent_rate_wording: RENT_RATE_CARD,
      unit: "per m²",
      unit_wording: "per m² of land a year",
      central_label: "most likely",
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
      await expect(card.getByTestId("place-card-figure")).toHaveText(PRE_POUND);
      await expect(card).not.toContainText("£");
    });

    test("flag ON: every £ has per m², range, most likely, estimate label", async ({
      page,
    }) => {
      await stubShell(page, okPlace(), true);
      await openPlaceCard(page);
      const card = page.getByTestId("place-card");
      await expect(card.getByTestId("place-card-figure")).toContainText(
        "£0.12 per m²",
      );
      await expect(card.getByTestId("place-card-figure-range")).toContainText(
        "per m²",
      );
      await expect(card.getByTestId("place-card-figure-central-label")).toHaveText(
        "most likely",
      );
      await expect(card.getByTestId("place-card-figure-estimate")).toHaveText(
        "Partly estimated",
      );
      await expect(card.getByTestId("place-card-figure-unit")).toContainText(
        "per m² of land a year",
      );
      await expect(card.getByTestId("place-card-range-surface")).toContainText(
        "per m²",
      );
      await assertEveryPoundHasPerM2(page, "place-card");
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
      await expect(card.getByTestId("place-card-figure")).toHaveText(
        "Under review",
      );
      await expect(card).not.toContainText("£");
    });
  });
}
