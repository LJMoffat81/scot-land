import { expect, test, type Page } from "@playwright/test";

/**
 * SW-044 slim map view — 390 and 1280; place card + Layers open.
 * No hard-coded counts of DOM nodes beyond the frozen acceptance checks.
 * Fail on console errors. No £ / banned visitor words.
 */

const BANNED =
  /\b(natural capital|ledger|headline|shadow|yield|what3words)\b/i;

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
  postcode: "G2 1DU",
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
    zones: [
      {
        code: "S01010264",
        vintage: 2011,
        name: "City Centre South",
      },
      {
        code: "S01014567",
        vintage: 2022,
        name: "City Centre South",
      },
    ],
  },
  intermediate_zone: {
    status: "ok",
    name: "City Centre",
    code: "S02002645",
  },
  square_reference: "1234,5678",
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "proxy",
      class: "proxy",
      status: "in_progress",
      applies: true,
      range: "not yet estimated",
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
};

const consoleErrors: string[] = [];

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    const wantsGeo =
      /\/layers\//i.test(url) ||
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
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ version: 2, layers: [] }),
    });
  });
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
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
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
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

function attachConsoleGate(page: Page) {
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
}

function assertConsoleClean() {
  const meaningful = consoleErrors.filter((line) => {
    if (/favicon/i.test(line)) return false;
    if (/Download the React DevTools/i.test(line)) return false;
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(line)) {
      return false;
    }
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
}

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
  await page.locator("#map[data-framed='1']").waitFor({ timeout: 30_000 });
}

async function openPlaceCard(page: Page) {
  await page.locator("#place-query").fill("55.86090, -4.25140");
  await page.locator(".hud-search-go").click();
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 45_000 });
  return card;
}

async function openLayers(page: Page) {
  await page.getByTestId("hud-layers-btn").click();
  await expect(page.getByTestId("layers-panel")).toBeVisible();
}

async function ensureLegendBodyVisible(page: Page) {
  const body = page.locator("#hud-scotland-body");
  if (await body.isVisible().catch(() => false)) return;
  const fold = page.locator("button.hud-scotland-fold");
  await expect(fold).toBeVisible({ timeout: 15_000 });
  await fold.click();
  await expect(body).toBeVisible({ timeout: 15_000 });
}

function countVisibleOgl(text: string): number {
  const re = /Open Government Licence/gi;
  let n = 0;
  while (re.exec(text)) n += 1;
  return n;
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`SW-044 slim map ${viewport.width}`, () => {
    test.use({ viewport });

    test.beforeEach(async ({ page }) => {
      consoleErrors.length = 0;
      attachConsoleGate(page);
      await stubMapBackend(page);
    });

    test.afterEach(() => {
      assertConsoleClean();
    });

    test("slim panel, chip key once, area fold, no licence in left panel", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      await openMap(page);
      const card = await openPlaceCard(page);
      await openLayers(page);

      // Intro hides after first search; legend stays.
      await expect(page.locator(".app-shell")).toHaveClass(/find-intro-dismissed/);
      await expect(page.locator(".hud-scotland-job")).toBeHidden();
      await ensureLegendBodyVisible(page);
      await expect(page.getByTestId("map-legend-panel")).toBeVisible();

      // Chip key once (legend only).
      await expect(page.getByTestId("evidence-tag-legend")).toHaveCount(1);
      await expect(
        page.locator("#hud-scotland-body").getByTestId("evidence-tag-legend"),
      ).toHaveCount(1);
      await expect(
        page.getByTestId("layers-panel").getByTestId("evidence-tag-legend"),
      ).toHaveCount(0);

      // Every chip (legend + place card) has an accessible description.
      const chips = page.locator(
        "[data-testid='confidence-tag'], [data-testid^='place-tag-']",
      );
      const chipCount = await chips.count();
      expect(chipCount).toBeGreaterThan(0);
      for (let i = 0; i < chipCount; i += 1) {
        const desc = await chips.nth(i).getAttribute("aria-description");
        expect(desc?.trim().length ?? 0).toBeGreaterThan(0);
      }

      // Card header + Area details fold.
      await expect(card.getByTestId("place-card-place")).toBeVisible();
      await expect(card.getByTestId("place-card-postcode")).toHaveText("G2 1DU");
      await expect(card.getByTestId("place-card-council")).toContainText(
        "Glasgow City",
      );
      await expect(card.getByTestId("place-card-map-reference-value")).toHaveText(
        "1234,5678",
      );
      await expect(card.getByTestId("place-card-map-reference-copy")).toBeVisible();
      const area = card.getByTestId("place-card-area-details");
      await expect(area).toBeVisible();
      await expect(area.locator("summary")).toHaveText("Area details");
      await area.locator("summary").click();
      await expect(card.getByTestId("place-card-data-zone")).toContainText(
        "S01014567",
      );
      await expect(card.getByTestId("place-card-data-zone-2011")).toContainText(
        "S01010264",
      );
      await expect(card.getByTestId("place-card-intermediate-zone")).toContainText(
        "City Centre",
      );

      await expect(card.getByTestId("place-card-agr-subtitle")).toHaveText(
        "What gives this land value",
      );
      await expect(card.getByTestId("place-card-figures-not-published")).toHaveText(
        "Figures not published yet",
      );
      await expect(card.getByTestId("place-card-range-surface")).toHaveCount(0);
      await expect(card.getByText("Figure not published yet")).toHaveCount(0);

      if (viewport.width >= 1280) {
        const valueHeading = card.getByTestId("place-card-agr-subtitle");
        const box = await valueHeading.boundingBox();
        expect(box).toBeTruthy();
        expect(box!.y).toBeGreaterThanOrEqual(0);
        expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height);
      }

      // Turn a layer on — left panel has no Licence / DATA LICENCES text.
      const dzToggle = page.getByTestId("layer-toggle-data_zones");
      await expect(dzToggle).toBeVisible();
      if ((await dzToggle.getAttribute("aria-pressed")) !== "true") {
        await dzToggle.click();
      }
      await expect(dzToggle).toHaveAttribute("aria-pressed", "true");
      await expect(page.getByTestId("layer-licence-data_zones")).toHaveCount(0);
      await expect(page.getByTestId("map-licence-credits")).toHaveCount(0);

      const leftText = await page.locator("#hud-scotland-body").innerText();
      expect(leftText).not.toMatch(/\bLicence\b/i);
      expect(leftText).not.toMatch(/DATA LICENCES/i);

      const layersText = await page.getByTestId("layers-panel").innerText();
      expect(layersText).not.toMatch(/^Licence:/m);
      expect(layersText).not.toMatch(/Figures for land value are being checked/);

      // Layer descriptions are short and not just the layer name.
      const landDesc = page.getByTestId("layer-desc-1");
      await expect(landDesc).toBeVisible();
      const landDescText = (await landDesc.innerText()).trim();
      expect(landDescText.length).toBeGreaterThan(0);
      expect(landDescText.toLowerCase()).not.toBe("land");

      const visible = await page.locator("body").innerText();
      expect(countVisibleOgl(visible)).toBeLessThanOrEqual(2);
      expect(visible).not.toMatch(/£\d/);
      expect(visible).not.toMatch(BANNED);
    });
  });
}
