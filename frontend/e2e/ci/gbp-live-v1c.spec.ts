import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * GBP-LIVE-V1c — unit label, 3 sf / <£0.01, estimate unavailable.
 * Flag OFF: no £. Widths 390 and 1280 (_COMMON.md). Auto-discovered under e2e/ci/.
 * Answer row follows MAP-CARDS §5 (place-card-figure / figure-range).
 */

const PRE_POUND =
  "We're not showing amounts yet while we check our method.";

const RENT_RATE_CARD =
  "Yearly rent: up to 4.5% of the land's value";

const RENT_RATE_HOW_IT_WORKS =
  "We turn land value into a yearly rent of up to 4.5% of that value.";

const UNIT_WORDING = "£ per square metre of land, per year";

const ESTIMATE_UNAVAILABLE = "estimate unavailable";

const HEALTH_OK = {
  status: "ok",
  version: "test",
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
        unit_wording: "per square metre of land, per year",
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

async function openPlaceCard(page: Page) {
  await page.goto("/?lat=55.860900&lng=-4.251400");
  await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 45_000 });
}

const okPlace = () =>
  placeFixture({
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
      central_label: "most likely",
      grain: "data_zone",
    },
  });

const tinyPlace = () =>
  placeFixture({
    gbp_live: {
      enabled: true,
      banner: "Early estimates; ranges are wide and will change.",
      rent_rate_wording: RENT_RATE_HOW_IT_WORKS,
      unit: "per m²",
      unit_wording: "per square metre of land, per year",
    },
    surface_rent_display: {
      state: "ok",
      low: 0.004,
      central: 0.006,
      high: 0.008,
      estimate_label: "Fully estimated",
      rent_rate_wording: RENT_RATE_CARD,
      unit: "per m²",
      unit_wording: "per square metre of land, per year",
      central_label: "most likely",
      grain: "data_zone",
    },
  });

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`GBP-LIVE-V1c ${viewport.width}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("flag OFF: no £ on place card", async ({ page }) => {
      test.setTimeout(90_000);
      await stubShell(page, placeFixture(), false);
      await openPlaceCard(page);
      const card = page.getByTestId("place-card");
      const figure = card.getByTestId("place-card-figure");
      await expect(figure.getByTestId("place-card-figure-status")).toHaveText(
        "Not published yet",
      );
      await expect(figure).toContainText(PRE_POUND);
      await expect(card).not.toContainText("£");
    });

    test("flag ON: unit label exact + 3 significant figures", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      await stubShell(page, okPlace(), true);
      await openPlaceCard(page);
      const card = page.getByTestId("place-card");
      await expect(card.getByTestId("place-card-figure-unit")).toHaveText(
        UNIT_WORDING,
      );
      const range = card.getByTestId("place-card-figure-range");
      await expect(range).toContainText("£0.0600");
      await expect(range).toContainText("£0.180");
      await expect(range).toContainText("per m²");
      await expect(card).not.toContainText("£0.00");
      await expect(card).not.toContainText(/Scotland total|national total/i);
    });

    test("flag ON: values below £0.01 show <£0.01, never £0.00", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      await stubShell(page, tinyPlace(), true);
      await openPlaceCard(page);
      const card = page.getByTestId("place-card");
      const range = card.getByTestId("place-card-figure-range");
      await expect(range).toContainText("<£0.01");
      await expect(range).toContainText("per m²");
      await expect(card).not.toContainText("£0.00");
    });

    test("flag ON unavailable: estimate unavailable, no £", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const place = placeFixture({
        gbp_live: { enabled: true },
        surface_rent_display: {
          state: "under_review",
          label: ESTIMATE_UNAVAILABLE,
          low: null,
          central: null,
          high: null,
          estimate_label: null,
        },
        agr_rows: agrRows().map((row) =>
          row.id === "surface" ? { ...row, range: ESTIMATE_UNAVAILABLE } : row,
        ),
      });
      await stubShell(page, place, true);
      await openPlaceCard(page);
      const card = page.getByTestId("place-card");
      await expect(card.getByTestId("place-card-under-review")).toHaveText(
        ESTIMATE_UNAVAILABLE,
      );
      await expect(card).not.toContainText("£");
      await expect(card).not.toContainText("Under review");
    });
  });
}
