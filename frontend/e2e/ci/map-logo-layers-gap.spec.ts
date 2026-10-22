import {
  fulfillEmptyGlyph,
  registerOpenFreeMapFontStub,
  stubArch2bTilesQuiet,
  stubLayersCouncilsQuiet,
} from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * SW-020 follow-up — at 390px the map logo must not touch Layers, and the
 * mark needs a solid backing so map labels cannot show through the clear
 * header. Load tiles, assert bounding boxes do not overlap, fail on console
 * errors.
 */


const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };


/** 1×1 PNG — stub raster tiles so MapLibre never depends on live CDN in CI. */
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

/** Minimal style replacing OpenFreeMap positron (no glyphs → no font CDN). */
const STUB_MAP_STYLE = {
  version: 8,
  name: "e2e-stub",
  sources: {
    stub: {
      type: "raster",
      tiles: ["https://tiles.openfreemap.org/e2e-stub/{z}/{x}/{y}.png"],
      tileSize: 256,
    },
  },
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#e8eef4" },
    },
    { id: "stub-raster", type: "raster", source: "stub" },
  ],
};


function boxesOverlap(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
): boolean {
  const overlapX = a.x < b.x + b.width && a.x + a.width > b.x;
  const overlapY = a.y < b.y + b.height && a.y + a.height > b.y;
  return overlapX && overlapY;
}

async function stubMapBasemap(page: Page) {
  // One host handler: style JSON vs raster (LIFO would otherwise serve PNG for
  // https://tiles.openfreemap.org/styles/positron).
  await page.route("**/tiles.openfreemap.org/**", async (route) => {
    const url = route.request().url();
    if (/\/styles\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(STUB_MAP_STYLE),
      });
      return;
    }
    if (/\/fonts\//i.test(url)) {
      await fulfillEmptyGlyph(route);
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/ArcGIS/rest/services/World_Imagery/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/api/parcels/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/api/context/**/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
}

test.describe("SW-020 map logo vs Layers gap (390×844)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test.beforeEach(async ({ page }) => {

    
    

    // Basemap first — MapLibre must not hit live CDN (CI pageerror "Error").
    await stubMapBasemap(page);

    await page.route("**/backend/**", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
        }),
      });
    });
    // ARCH-2b: quiet tiles manifest so the catch-all 404 does not trip the gate.
    await stubArch2bTilesQuiet(page);

    await page.route("**/backend/boundaries/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
    });
    await stubLayersCouncilsQuiet(page);

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
    await page.route("**/backend/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat: 55.95,
          lng: -3.19,
          place_label: null,
          agr_rows: [],
          constraints: [],
          layers: [],
          links: [],
        }),
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
    await page.route(
      "**/backend/layers/context/data-zones/at**",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            code: null,
            name: null,
            vintage: null,
          }),
        });
      },
    );
    await page.route("**/api/catalog.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
    });
    await stubLayersAddQuiet(page);
  });

  

  test("logo does not overlap Layers after tiles load", async ({ page }) => {
    test.setTimeout(90_000);
    await openMapWithTiles(page);

    const logo = page.getByTestId("site-nav-brand");
    const layers = page.getByTestId("hud-layers-btn");
    await expect(logo).toBeVisible();
    await expect(layers).toBeVisible();

    const logoBox = await logo.boundingBox();
    const layersBox = await layers.boundingBox();
    expect(logoBox, "logo bounding box").toBeTruthy();
    expect(layersBox, "Layers bounding box").toBeTruthy();
    if (!logoBox || !layersBox) return;

    expect(
      boxesOverlap(logoBox, layersBox),
      `logo overlaps Layers: logo=${JSON.stringify(logoBox)} layers=${JSON.stringify(layersBox)}`,
    ).toBe(false);

    // Same row: enforce the ≥8px product gap (logo must not touch Layers).
    const sameRow =
      logoBox.y < layersBox.y + layersBox.height &&
      logoBox.y + logoBox.height > layersBox.y;
    if (sameRow) {
      const gap = layersBox.x - (logoBox.x + logoBox.width);
      expect(
        gap,
        `logo→Layers horizontal gap must be ≥8px (got ${gap})`,
      ).toBeGreaterThanOrEqual(8);
    }
  });
});

async function openMapWithTiles(page: Page) {
  const tileResponse = page.waitForResponse(
    (response) => {
      const url = response.url();
      return (
        response.ok() &&
        (/openfreemap\.org/i.test(url) ||
          /styles\/positron/i.test(url) ||
          /\/e2e-stub\//i.test(url))
      );
    },
    { timeout: 60_000 },
  );

  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await tileResponse;

  await page.waitForFunction(() => {
    const canvas = document.querySelector(
      ".maplibregl-canvas",
    ) as HTMLCanvasElement | null;
    return Boolean(canvas && canvas.width > 0 && canvas.height > 0);
  });
}
