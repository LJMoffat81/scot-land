import { registerOpenFreeMapFontStub, stubLayersCouncilsQuiet } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * DZ-HIERARCHY — Intermediate Zone title, council second line;
 * MAP-CARDS §5 "More about this area ▾" fold (no DZ2011 / IZ codes on card).
 * Widths: 390 and 1280. Console/pageerror gate.
 */

const IZ_NAME = "Old Town, Princes Street and Leith Street";
const IZ_CODE = "S02002727";
const COUNCIL = "City of Edinburgh";
const DZ2011_CODE = "S01008677";
const MORE_ABOUT = "More about this area ▾";
const HOW_LINK = "How we work this out →";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

function eh1PlaceFixture(overrides: Record<string, unknown> = {}) {
  return {
    contract: "place_card_v1",
    lat: 55.952,
    lng: -3.189,
    // Locality must not win over IZ name in the title.
    place_label: "Edinburgh Old Town",
    postcode: "EH1 1YZ",
    council_name: COUNCIL,
    dwellings: 410,
    sales_year_from: 2019,
    sales_year_to: 2023,
    confidence: "Medium",
    data_zone: {
      status: "ok",
      code: "S01014713",
      name: "Old Town East",
      vintage: 2022,
      zones: [
        {
          code: "S01014713",
          vintage: 2022,
          name: "Old Town East",
          on_boundary: false,
        },
        {
          code: DZ2011_CODE,
          vintage: 2011,
          name: "Old Town",
          on_boundary: false,
        },
      ],
    },
    intermediate_zone: {
      status: "ok",
      name: IZ_NAME,
      code: IZ_CODE,
    },
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
      },
      {
        id: "resource",
        label: "Natural resource rents",
        tag: "market",
        class: "market",
        status: "coming_soon",
        applies: true,
        range: "not yet estimated",
      },
      {
        id: "nature",
        label: "Services of nature",
        tag: "shadow",
        class: "shadow",
        status: "coming_soon",
        applies: true,
        range: "not yet estimated",
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

async function stubMapChrome(page: Page, fixture = eh1PlaceFixture()) {
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
      body: JSON.stringify({ version: 2, layers: [] }),
    });
  });
  await page.route("**/backend/boundaries/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });

  await stubLayersCouncilsQuiet(page);

  await page.route("**/backend/layers/**", async (route) => {
    const url = route.request().url();
    if (/data-zones\/at/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: "S01014713",
          name: "Old Town East",
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
  await page.route("**/api/place.json**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(fixture),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
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

async function openEh1Card(page: Page) {
  await page.goto("/?lat=55.952000&lng=-3.189000");
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  return card;
}

async function assertNoZoneCodesOnCard(card: ReturnType<Page["getByTestId"]>) {
  await expect(card).not.toContainText(DZ2011_CODE);
  await expect(card).not.toContainText(IZ_CODE);
  await expect(card).not.toContainText("Also on 2011 map");
  await expect(card.getByTestId("place-card-dz-2011")).toHaveCount(0);
  await expect(card.getByTestId("place-card-iz-code")).toHaveCount(0);
}

test.describe("DZ-HIERARCHY place card desktop 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("EH1 1YZ IZ title; More about fold + methodology; no zone codes", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    const card = await openEh1Card(page);

    await expect(page.getByTestId("place-card-place")).toHaveText(IZ_NAME);
    await expect(page.getByTestId("place-card-council")).toHaveText(COUNCIL);
    await expect(page.getByTestId("place-card-place")).not.toHaveText(
      "Edinburgh Old Town",
    );

    // MAP-CARDS §5: parts fold summary is exact; methodology under the fold.
    const parts = page.getByTestId("place-card-parts");
    await expect(parts).toBeVisible();
    await expect(parts.locator("summary")).toHaveText(MORE_ABOUT);
    await parts.locator("summary").click();
    const howLink = page.getByTestId("place-card-methodology-link");
    await expect(howLink).toBeVisible();
    await expect(howLink).toHaveText(HOW_LINK);
    await expect(howLink).toHaveAttribute("href", "/methodology");
    await assertNoZoneCodesOnCard(card);
    await expect(card).not.toContainText(/\bunknown\b/i);
    await expect(card).not.toContainText("£");
    assertConsoleClean(gate);
  });

  test("falls back to NRS locality when IZ name missing", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(
      page,
      eh1PlaceFixture({
        intermediate_zone: {
          status: "ok",
          name: null,
          code: IZ_CODE,
          note: "name not loaded yet",
        },
      }),
    );
    const card = await openEh1Card(page);
    await expect(page.getByTestId("place-card-place")).toHaveText(
      "Edinburgh Old Town",
    );
    await expect(page.getByTestId("place-card-council")).toHaveText(COUNCIL);
    await assertNoZoneCodesOnCard(card);
    await expect(card).not.toContainText(/\bunknown\b/i);
    assertConsoleClean(gate);
  });
});

test.describe("DZ-HIERARCHY place card mobile 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("EH1 1YZ IZ title; More about closed; methodology under fold; answer above fold", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    const card = await openEh1Card(page);

    await expect(page.getByTestId("place-card-place")).toHaveText(IZ_NAME);
    await expect(page.getByTestId("place-card-council")).toHaveText(COUNCIL);

    const parts = page.getByTestId("place-card-parts");
    await expect(parts).toBeVisible();
    await expect(parts.locator("summary")).toHaveText(MORE_ABOUT);
    await expect
      .poll(async () => parts.evaluate((el) => (el as HTMLDetailsElement).open))
      .toBe(false);
    await expect(page.getByTestId("place-card-methodology-link")).toBeHidden();

    // Answer row sits above the closed fold; value rows live inside it.
    const figure = page.getByTestId("place-card-figure");
    await expect(figure).toBeVisible();
    const figureBox = await figure.boundingBox();
    const partsBox = await parts.boundingBox();
    expect(figureBox).toBeTruthy();
    expect(partsBox).toBeTruthy();
    expect(figureBox!.y + figureBox!.height).toBeLessThanOrEqual(
      partsBox!.y + 1,
    );

    await parts.locator("summary").click();
    await expect(parts).toHaveAttribute("open", "");
    await expect(page.getByTestId("place-card-value-rows")).toBeVisible();
    await expect(page.getByTestId("place-card-agr-surface")).toBeVisible();
    const howLink = page.getByTestId("place-card-methodology-link");
    await expect(howLink).toBeVisible();
    await expect(howLink).toHaveText(HOW_LINK);
    await expect(howLink).toHaveAttribute("href", "/methodology");
    await assertNoZoneCodesOnCard(card);

    await expect(card).not.toContainText(/\bunknown\b/i);
    await expect(card).not.toContainText("£");
    assertConsoleClean(gate);
  });
});
