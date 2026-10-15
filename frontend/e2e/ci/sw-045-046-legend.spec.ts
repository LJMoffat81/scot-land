import { expect, test, type Page } from "@playwright/test";

/**
 * SW-045 + SW-046 — legend follows the active layer; desktop legend clear of
 * the place card. Fail on console errors. No £ / banned visitor words.
 */

const LAND_TITLE =
  "What the land is worth each year: lower to higher";
const LAND_PALER = "Paler = less sure";
const DENSITY_TITLE = "Population density — people per km²";
const VDL_TITLE = "Vacant and derelict land";

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
  place_label: "Glasgow",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre" },
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "proxy",
      status: "in_progress",
      applies: true,
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
      body: JSON.stringify({ code: null, name: null, vintage: null }),
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

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  await stubMapBackend(page);
});

test.afterEach(async () => {
  const meaningful = consoleErrors.filter((line) => {
    if (/favicon/i.test(line)) return false;
    if (/Download the React DevTools/i.test(line)) return false;
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(line)) {
      return false;
    }
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
});

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
  await expect(page.locator(".app-shell.place-open")).toBeVisible();
  return card;
}

async function openLayers(page: Page) {
  await page.getByTestId("hud-layers-btn").click();
  await expect(page.getByTestId("layers-panel")).toBeVisible();
  await expect(page.locator(".app-shell.tools-open")).toBeVisible();
}

type Box = { x: number; y: number; width: number; height: number };

function boxesIntersect(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function boxOf(
  locator: ReturnType<Page["locator"]>,
  label: string,
): Promise<Box> {
  const box = await locator.boundingBox();
  if (!box) throw new Error(`${label}: missing bounding box`);
  return box;
}

test.describe("SW-045 legend follows active layer (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("switching layer changes legend title and bands", async ({ page }) => {
    test.setTimeout(120_000);
    await openMap(page);

    const legend = page.getByTestId("map-range-legend");
    await expect(legend).toBeVisible();
    await expect(page.getByTestId("map-range-legend-title")).toHaveText(
      DENSITY_TITLE,
    );
    await expect(legend.getByText(/£\d/)).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText(BANNED);

    await openLayers(page);

    // Land on → Land worth cividis wording (not people-per-km²).
    await page.getByTestId("layer-toggle-1").click();
    await expect(page.getByTestId("map-legend-panel")).toHaveAttribute(
      "data-legend-layer",
      "1",
    );
    await expect(page.getByTestId("map-range-legend-title")).toHaveText(
      LAND_TITLE,
    );
    await expect(page.getByTestId("map-range-legend-paler")).toHaveText(
      LAND_PALER,
    );
    await expect(page.getByTestId("map-range-legend-bands")).toBeVisible();
    await expect(legend.getByText(/£\d/)).toHaveCount(0);
    await expect(page.getByTestId("map-range-legend-title")).not.toHaveText(
      DENSITY_TITLE,
    );

    // VDL on → vacant/derelict bands replace Land.
    await page.getByTestId("layer-toggle-vdl").click();
    await expect(page.getByTestId("map-legend-panel")).toHaveAttribute(
      "data-legend-layer",
      "vdl",
    );
    await expect(page.getByTestId("map-range-legend-title")).toHaveText(
      VDL_TITLE,
    );
    await expect(page.getByTestId("map-range-legend-paler")).toHaveCount(0);

    // Land again → back to Land worth (active layer only).
    await page.getByTestId("layer-toggle-1").click(); // off
    await page.getByTestId("layer-toggle-1").click(); // on → focus Land
    await expect(page.getByTestId("map-range-legend-title")).toHaveText(
      LAND_TITLE,
    );

    // Data zones → density title/bands.
    await page.getByTestId("layer-toggle-data_zones").click();
    await expect(page.getByTestId("map-legend-panel")).toHaveAttribute(
      "data-legend-layer",
      "data_zones",
    );
    await expect(page.getByTestId("map-range-legend-title")).toHaveText(
      DENSITY_TITLE,
    );
    await expect(legend.getByText(/£\d/)).toHaveCount(0);
  });
});

test.describe("SW-046 legend clear of place card (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("expanded legend does not intersect place card", async ({ page }) => {
    test.setTimeout(120_000);
    await openMap(page);
    const card = await openPlaceCard(page);

    const showLegend = page.getByRole("button", { name: "Show legend" });
    await expect(showLegend).toBeVisible();
    await showLegend.click();
    await expect(page.locator(".hud-scotland.legend-open")).toBeVisible();

    const legendPanel = page.getByTestId("map-legend-panel");
    await expect(legendPanel.getByTestId("map-range-legend")).toBeVisible();
    await expect(page.getByTestId("map-range-legend-title")).toBeVisible();

    const cardBox = await boxOf(card, "place card");
    const legendBox = await boxOf(legendPanel, "legend panel");
    expect(
      boxesIntersect(cardBox, legendBox),
      `legend must not sit under the card\ncard=${JSON.stringify(cardBox)}\nlegend=${JSON.stringify(legendBox)}`,
    ).toBe(false);
    // Full legend sits below the shortened card (same left column).
    expect(legendBox.y, "legend below card").toBeGreaterThanOrEqual(
      cardBox.y + cardBox.height - 1,
    );
    await expect(legendPanel.getByText(/£\d/)).toHaveCount(0);

    // Again with Layers drawer open — still no card/legend intersection.
    await openLayers(page);
    const cardBox2 = await boxOf(card, "place card (layers open)");
    const legendBox2 = await boxOf(legendPanel, "legend (layers open)");
    expect(
      boxesIntersect(cardBox2, legendBox2),
      `legend must not intersect card with Layers open\ncard=${JSON.stringify(cardBox2)}\nlegend=${JSON.stringify(legendBox2)}`,
    ).toBe(false);
  });
});

test.describe("SW-045/046 legend usable at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Show legend reveals bands; no £ or banned words", async ({ page }) => {
    test.setTimeout(90_000);
    await openMap(page);

    const toggle = page.locator("button.hud-scotland-fold");
    await expect(toggle).toBeVisible();
    // Narrow fold starts collapsed.
    if (await page.locator(".hud-scotland.legend-open").count() === 0) {
      await toggle.click();
    }
    await expect(page.locator(".hud-scotland.legend-open")).toBeVisible();
    const legend = page.getByTestId("map-range-legend");
    await expect(legend).toBeVisible();
    await expect(page.getByTestId("map-range-legend-title")).toBeVisible();
    await expect(legend.getByText(/£\d/)).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText(BANNED);

    // Hit area usable (UX-01 floor).
    const box = await toggle.boundingBox();
    expect(box, "legend toggle box").toBeTruthy();
    expect(Math.min(box!.width, box!.height)).toBeGreaterThanOrEqual(44);
  });
});
