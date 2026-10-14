import { expect, test, type Page } from "@playwright/test";

/**
 * UX10-1 place card skeleton — 390 and 1280; exact visitor copy; no £;
 * footer visible without scroll at 1280×800; one banner; console/pageerror gate.
 */

const PRE_POUND =
  "We're not showing amounts yet while we check our method.";
const EXPERIMENTAL_FOOTER =
  "Experimental estimate, not an official valuation. It is not a bill, and it does not change what you pay.";
const TYPICAL_HOME =
  "For a typical home in this neighbourhood, not your home.";
const AGR = "Annual Ground Rent";
const COVERS = "Covers land under homes only.";
const HOW_HOMES =
  "This covers land under homes only. Shops, offices and industrial land aren't included yet.";
const PARTS_NOTE =
  "These are worked out differently, so we don't add them up.";
const FACT =
  "Land is worth more where there are jobs, good transport, schools and shops nearby. Most of that comes from the area, not the house.";

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
        gloss: "The yearly value of the land under homes.",
        of_which: [
          { id: "planning_uplift", label: "of which: planning uplift" },
        ],
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
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    pageErrors.push(String(err));
  });
  return { consoleErrors, pageErrors };
}

function assertConsoleClean(gate: ConsoleGate) {
  const meaningful = gate.consoleErrors.filter((text) => {
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
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
  expect(gate.pageErrors, `pageerrors:\n${gate.pageErrors.join("\n")}`).toEqual(
    [],
  );
}

async function stubMapChrome(page: Page, fixture = placeFixture()) {
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
      body: JSON.stringify(fixture),
    });
  });
  await page.route("**/backend/api/place.json**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture),
    });
  });
}

async function openPlaceViaCoords(page: Page) {
  await page.goto("/?lat=55.860900&lng=-4.251400");
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

async function assertSkeletonCopy(page: Page) {
  const card = page.getByTestId("place-card");
  await expect(page.getByTestId("place-card-place")).toBeVisible();
  await expect(page.getByTestId("place-card-council")).toContainText(
    "Glasgow City",
  );
  await expect(page.getByTestId("place-card-figure")).toHaveText(PRE_POUND);
  await expect(page.getByTestId("place-card-covers-homes")).toHaveText(COVERS);
  await expect(page.getByTestId("place-card-typical-home")).toHaveText(
    TYPICAL_HOME,
  );
  await expect(page.getByTestId("place-card-agr-label")).toHaveText(AGR);
  await expect(page.getByTestId("place-card-agr-subtitle")).toContainText(
    "What the land here is worth each year",
  );
  await expect(page.getByTestId("place-card-sales-basis")).toContainText(
    "Based on local home sales (2019–2023)",
  );
  await expect(page.getByTestId("place-card-sales-basis")).toContainText(
    "How sure we are: Medium",
  );
  await expect(page.getByTestId("place-card-fact")).toHaveText(FACT);

  const parts = page.getByTestId("place-card-parts");
  await expect(parts).toBeVisible();
  await expect(parts).not.toHaveAttribute("open", "");
  await parts.locator("summary").click();
  await expect(page.getByTestId("place-card-agr-surface")).toContainText("Land");
  await expect(page.getByTestId("place-card-agr-resource")).toContainText(
    "Natural resource rents",
  );
  await expect(page.getByTestId("place-card-agr-nature")).toContainText(
    "Services of nature",
  );
  await expect(page.getByTestId("place-card-range-surface")).toHaveText(
    "not yet estimated",
  );
  await expect(page.getByTestId("place-card-of-which-planning_uplift")).toContainText(
    "of which: planning uplift",
  );
  await expect(page.getByTestId("place-tag-shadow")).toHaveText("Estimate");
  await expect(page.getByTestId("place-card-parts-note")).toHaveText(PARTS_NOTE);

  const how = page.getByTestId("place-card-how-we-work");
  await how.locator("summary").click();
  await expect(page.getByTestId("place-card-how-homes-only")).toHaveText(
    HOW_HOMES,
  );

  await expect(card).not.toContainText("£");
  await expect(card).not.toContainText(/Land Value Tax|\bLVT\b/);
  await expect(card).not.toContainText(/Estimate \(no market price\)/);
  await expect(card).not.toContainText(/rank|out of 10 neighbourhoods/i);

  await expect(page.getByTestId("research-banner")).toHaveCount(1);
}

test.describe("UX10-1 place card desktop 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("skeleton copy, sticky footer visible, no £, one banner", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openPlaceViaCoords(page);
    await assertSkeletonCopy(page);

    const sticky = page.getByTestId("place-card-experimental-footer-sticky");
    await expect(sticky).toBeVisible();
    await expect(sticky).toHaveText(EXPERIMENTAL_FOOTER);
    const box = await sticky.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.y + box!.height).toBeLessThanOrEqual(800);
    expect(box!.y).toBeGreaterThanOrEqual(0);

    const close = page.getByRole("button", { name: "Close place card" });
    const closeBox = await close.boundingBox();
    expect(closeBox).toBeTruthy();
    expect(closeBox!.height).toBeGreaterThanOrEqual(44);

    assertConsoleClean(gate);
  });

  test("too few homes never shows 0", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page, placeFixture({ dwellings: 12 }));
    await openPlaceViaCoords(page);
    await expect(page.getByTestId("place-card-figure")).toHaveText(
      "Too few homes here for a typical figure.",
    );
    await expect(page.getByTestId("place-card")).not.toContainText("£0");
    await expect(page.getByTestId("place-card")).not.toContainText("£");
    assertConsoleClean(gate);
  });

  test("no homes is not applicable, never 0", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page, placeFixture({ dwellings: 0 }));
    await openPlaceViaCoords(page);
    await expect(page.getByTestId("place-card-figure")).toHaveText(
      "No homes here, so not applicable",
    );
    await expect(page.getByTestId("place-card")).not.toContainText("£0");
    assertConsoleClean(gate);
  });

  test("fully estimated state", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(
      page,
      placeFixture({ fully_estimated: true, dwellings: 200 }),
    );
    await openPlaceViaCoords(page);
    await expect(page.getByTestId("place-card-fully-estimated")).toHaveText(
      "Mostly worked out from nearby areas: treat as a rough guide",
    );
    await expect(page.getByTestId("place-card-fully-estimated")).toHaveAttribute(
      "data-wider-band",
      "true",
    );
    assertConsoleClean(gate);
  });
});

test.describe("UX10-1 place card mobile 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("bottom sheet peek shows name, figure, disclaimer", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openPlaceViaCoords(page);

    const peek = page.getByTestId("place-card-peek");
    await expect(peek).toBeVisible();
    await expect(peek.getByTestId("place-card-place")).toBeVisible();
    await expect(peek.getByTestId("place-card-figure")).toHaveText(PRE_POUND);
    await expect(peek.getByTestId("place-card-experimental-footer")).toHaveText(
      EXPERIMENTAL_FOOTER,
    );

    const cardBox = await page.getByTestId("place-card").boundingBox();
    expect(cardBox).toBeTruthy();
    // Bottom sheet: lower half, but clears basemap/zoom chrome (bottom ≈ 7.4rem).
    expect(cardBox!.y).toBeGreaterThan(200);
    expect(cardBox!.y + cardBox!.height).toBeLessThan(844 - 64);

    await expect(page.getByTestId("research-banner")).toHaveCount(1);
    await expect(page.getByTestId("place-card")).not.toContainText("£");
    assertConsoleClean(gate);
  });
});
