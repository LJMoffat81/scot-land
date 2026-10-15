import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * SW-036 v2 — desktop (≥1024) layout at 1280×800:
 * place card left + Layers right together; no bbox intersections among
 * card, Layers drawer, legend pill, zoom, basemap, banner ×; marker stays
 * in the visible map strip between card and drawer.
 */

const pageErrors: string[] = [];
const consoleErrors: string[] = [];

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

const KNOWN_OPTIONAL_FAIL_URL = [
  /\/favicon\.ico(?:\?|$)/i,
  /\/apple-touch-icon/i,
];

type Box = { x: number; y: number; width: number; height: number };

function boxesOverlap(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function stubBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
      }),
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
      body: JSON.stringify({ layers: [] }),
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
}

async function boxOf(locator: Locator, label: string): Promise<Box> {
  await expect(locator, label).toBeVisible();
  // MapLibre markers can report visible before layout has a box (null bbox).
  // Retry until a positive box exists — same width/height asserts, no loosen.
  let box: Box | null = null;
  await expect(async () => {
    box = await locator.boundingBox();
    expect(box, `${label} bounding box`).toBeTruthy();
    expect(box!.width, `${label} width`).toBeGreaterThan(0);
    expect(box!.height, `${label} height`).toBeGreaterThan(0);
  }).toPass({ timeout: 15_000 });
  return box!;
}

function assertPairClear(a: Box, b: Box, label: string) {
  expect(
    boxesOverlap(a, b),
    `${label} must not intersect: a=${JSON.stringify(a)} b=${JSON.stringify(b)}`,
  ).toBe(false);
}

test.describe("SW-036 v2 desktop layout 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test.beforeEach(async ({ page }) => {
    pageErrors.length = 0;
    consoleErrors.length = 0;
    page.on("pageerror", (err) => {
      pageErrors.push(String(err));
    });
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push(msg.text());
    });
    await stubBackend(page);
  });

  test.afterEach(() => {
    expect(pageErrors, `pageerrors:\n${pageErrors.join("\n")}`).toEqual([]);
    const meaningful = consoleErrors.filter((text) => {
      if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
        return false;
      }
      if (KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(text))) return false;
      if (
        /Failed to load resource: the server responded with a status of (404|503)/i.test(
          text,
        )
      ) {
        return false;
      }
      return true;
    });
    expect(
      meaningful,
      `console errors:\n${meaningful.join("\n")}`,
    ).toEqual([]);
  });

  test("card + Layers open: no chrome intersections; marker in map strip", async ({
    page,
  }) => {
    test.setTimeout(120_000);

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.locator("#place-query").waitFor();

    const bannerDismiss = page.getByTestId("research-banner-dismiss");
    await expect(bannerDismiss).toBeVisible({ timeout: 15_000 });

    await page.locator("#place-query").fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible({ timeout: 45_000 });
    await expect(page.locator(".app-shell.place-open")).toBeVisible();

    const layersBtn = page.getByTestId("hud-layers-btn");
    await layersBtn.click();
    const layersPanel = page.getByTestId("layers-panel");
    await expect(layersPanel).toBeVisible();
    await expect(page.locator(".app-shell.tools-open")).toBeVisible();
    // Use the drawer shell (clipped) — inner panel content can be taller than the stage.
    const layers = page.locator("aside.hud-tools");
    await expect(layers).toBeVisible();

    // Collapsed legend pill while the card is open.
    const legendPill = page.getByRole("button", { name: "Show legend" });
    await expect(legendPill).toBeVisible();
    await expect(page.locator(".hud-scotland.legend-open")).toHaveCount(0);

    const zoom = page.locator(".maplibregl-ctrl-zoom-in");
    const basemap = page.getByTestId("basemap-switcher");
    await expect(zoom).toBeVisible();
    await expect(basemap).toBeVisible();

    const cardBox = await boxOf(card, "place card");
    const layersBox = await boxOf(layers, "Layers drawer");
    const legendBox = await boxOf(legendPill, "legend pill");
    const zoomBox = await boxOf(zoom, "zoom +");
    const basemapBox = await boxOf(basemap, "basemap");
    const dismissBox = await boxOf(bannerDismiss, "banner ×");

    // Drawer must stay within the viewport (not an unclipped content box).
    expect(layersBox.y + layersBox.height, "Layers drawer bottom").toBeLessThanOrEqual(
      800 + 1,
    );

    // Card is the left panel; Layers stays on the right with map between.
    expect(cardBox.x + cardBox.width, "card right edge").toBeLessThan(
      layersBox.x,
    );
    expect(cardBox.width, "card ~360px").toBeLessThanOrEqual(370);
    expect(cardBox.width, "card not tiny").toBeGreaterThan(200);

    const chrome: Array<[string, Box]> = [
      ["place card", cardBox],
      ["Layers drawer", layersBox],
      ["legend pill", legendBox],
      ["zoom", zoomBox],
      ["basemap", basemapBox],
      ["banner ×", dismissBox],
    ];
    for (let i = 0; i < chrome.length; i += 1) {
      for (let j = i + 1; j < chrome.length; j += 1) {
        assertPairClear(chrome[i][1], chrome[j][1], `${chrome[i][0]} vs ${chrome[j][0]}`);
      }
    }

    // Legend pill sits below the card (same left column).
    expect(legendBox.y, "legend pill below card").toBeGreaterThanOrEqual(
      cardBox.y + cardBox.height - 1,
    );

    const marker = page.locator(".maplibregl-marker").first();
    await expect(marker).toBeVisible({ timeout: 15_000 });
    const markerBox = await boxOf(marker, "place marker");
    const markerCx = markerBox.x + markerBox.width / 2;
    const markerCy = markerBox.y + markerBox.height / 2;

    expect(markerCx, "marker right of card").toBeGreaterThan(
      cardBox.x + cardBox.width,
    );
    expect(markerCx, "marker left of Layers").toBeLessThan(layersBox.x);
    expect(markerCy, "marker below header band").toBeGreaterThan(40);
    expect(markerCy, "marker above footer band").toBeLessThan(760);
    expect(markerBox.x, "marker on-screen left").toBeGreaterThanOrEqual(0);
    expect(
      markerBox.x + markerBox.width,
      "marker on-screen right",
    ).toBeLessThanOrEqual(1280);
  });
});
