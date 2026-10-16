import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * UX10-1 / MAP-CARDS §5 — place card skeleton at 390 and 1280; exact visitor
 * copy; no £; footer visible; one banner; console/pageerror gate.
 */

const PRE_POUND =
  "We're not showing amounts yet while we check our method.";
const EXPERIMENTAL_FOOTER =
  "Experimental estimate, not an official valuation. It is not a bill, and it does not change what you pay.";
const TYPICAL_HOME =
  "For a typical home in this area, not your home.";
const AGR = "Annual Ground Rent";
const HOW_HOMES =
  "This covers land under homes only. Shops, offices and industrial land aren't included yet.";
const HOW_LINK = "How we work this out →";
const FACT =
  "Land is worth more near jobs, transport, schools and shops. That value comes from the area, not the house.";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

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
        gloss: "The yearly rental value of the land under homes, without the buildings.",
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
    ],
    constraints: [],
    layers: [],
    links: [],
    ...overrides,
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

function assertConsoleClean(gate: ConsoleGate) {
  const meaningful = gate.consoleErrors.filter((text) => {
    if (/\bAbortError\b|aborted/i.test(text)) return false;
    if (/Failed to load resource:.*(?:400|404|503|Service Unavailable)/i.test(text))
      return false;
    if (/openfreemap|sprite|glyph|tiles\.openfreemap/i.test(text)) return false;
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
  expect(gate.pageErrors, `pageerrors:\n${gate.pageErrors.join("\n")}`).toEqual(
    [],
  );
}

async function stubMapChrome(page: Page, fixture = placeFixture()) {
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
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(fixture),
      });
      return;
    }
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
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
}

async function openPlaceViaCoords(page: Page) {
  await page.goto("/?lat=55.860900&lng=-4.251400");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 45_000 });
  return card;
}

async function assertSkeletonCopy(page: Page) {
  const card = page.getByTestId("place-card");
  await expect(page.getByTestId("place-card-place")).toHaveText("City Centre");
  await expect(page.getByTestId("place-card-council")).toContainText(
    "Glasgow City",
  );
  await expect(page.getByTestId("place-card-typical-home")).toHaveText(
    TYPICAL_HOME,
  );
  await expect(page.getByTestId("place-card-agr-label")).toHaveText(AGR);
  await expect(page.getByTestId("place-card-agr-subtitle")).toHaveText(
    "What the land under homes here is worth each year",
  );
  await expect(page.getByTestId("place-card-agr-scope")).toHaveText(
    "Covers land used for homes, as it is used today. Values for farm, business and development land will come later.",
  );
  await expect(page.getByTestId("place-card-agr-heading")).toHaveAttribute(
    "aria-label",
    "Annual Ground Rent. What the land under homes here is worth each year. Covers land used for homes, as it is used today. Values for farm, business and development land will come later.",
  );
  await expect(page.getByTestId("place-card-figure-status")).toHaveText(
    "Not published yet",
  );
  await expect(page.getByTestId("place-card-figure")).toContainText(PRE_POUND);
  await expect(page.getByTestId("place-card-fact")).toHaveText(FACT);

  // Removed MAP-CARDS §6 items
  await expect(page.getByTestId("place-card-covers-homes")).toHaveCount(0);
  await expect(page.getByTestId("place-card-sales-basis")).toHaveCount(0);
  await expect(page.getByTestId("place-card-figure-why")).toHaveCount(0);
  await expect(page.getByTestId("place-card-land-values-coming-soon")).toHaveCount(
    0,
  );
  await expect(page.getByTestId("place-card-map-reference")).toHaveCount(0);
  await expect(page.getByTestId("place-card-outline-status")).toHaveCount(0);

  const parts = page.getByTestId("place-card-parts");
  await expect(parts).toBeVisible();
  await expect(parts.locator("summary")).toHaveText("More about this area ▾");
  await parts.locator("summary").click();
  await expect(page.getByTestId("place-card-how-homes-only")).toHaveText(
    HOW_HOMES,
  );
  await expect(page.getByTestId("place-card-methodology-link")).toHaveText(
    HOW_LINK,
  );
  await expect(page.getByTestId("place-card-of-which-planning_uplift")).toHaveCount(
    0,
  );

  await expect(page.getByTestId("place-card-footer")).toHaveText(
    EXPERIMENTAL_FOOTER,
  );
  await expect(card).not.toContainText("£");
  await expect(card).not.toContainText(/Land Value Tax|\bLVT\b/);
  const cardHtml = await card.innerHTML();
  expect(cardHtml).not.toMatch(/\bshadow\b/i);
}

test.describe("UX10-1 / MAP-CARDS place card desktop 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("§5 skeleton copy, footer visible, no £", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openPlaceViaCoords(page);
    await assertSkeletonCopy(page);

    const footer = page.getByTestId("place-card-footer");
    await expect(footer).toBeVisible();
    const box = await footer.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.y + box!.height).toBeLessThanOrEqual(800);

    const close = page.getByRole("button", { name: "Close place card" });
    const closeBox = await close.boundingBox();
    expect(closeBox!.height).toBeGreaterThanOrEqual(44);

    assertConsoleClean(gate);
  });

  test("too few homes never shows 0", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page, placeFixture({ dwellings: 12 }));
    await openPlaceViaCoords(page);
    await expect(page.getByTestId("place-card-too-few")).toHaveText(
      "Too few homes here for a typical figure.",
    );
    await expect(page.getByTestId("place-card")).not.toContainText("£0");
    assertConsoleClean(gate);
  });

  test("dwellings <= 0 is too few homes, never 0", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page, placeFixture({ dwellings: 0 }));
    await openPlaceViaCoords(page);
    await expect(page.getByTestId("place-card-too-few")).toHaveText(
      "Too few homes here for a typical figure.",
    );
    await expect(page.getByTestId("place-card")).not.toContainText("£0");
    assertConsoleClean(gate);
  });
});

test.describe("UX10-1 / MAP-CARDS place card mobile 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("bottom sheet shows name and answer; no £", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openPlaceViaCoords(page);

    await expect(page.getByTestId("map-panel-slot")).toHaveAttribute(
      "data-detent",
      /peek|half/,
    );
    await expect(page.getByTestId("place-card-place")).toBeVisible();
    await expect(page.getByTestId("place-card-figure")).toContainText(PRE_POUND);
    await expect(page.getByTestId("place-card")).not.toContainText("£");
    assertConsoleClean(gate);
  });
});
