import { readFileSync } from "node:fs";
import { join } from "node:path";
import { test, expect, routeManifestOverride } from "./_fixtures";
import { type Page } from "@playwright/test";
import { assertConsoleClean, attachConsoleGate, ensureLayersGroupOpen, openLayers, openMap, registerOpenFreeMapFontStub, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

/**
 * LAYERS-PERF-3 — ARCH-2b: oil and gas via tiles (no GeoJSON zoom hint).
 * Protected-sites hint / simplified outlines chip stay as before.
 */

// Playwright CI cwd is frontend/; avoid import.meta (not an ESM module here).
const ARCH2B = join(process.cwd(), "e2e", "fixtures", "arch2b");
const OIL_MVT = readFileSync(join(ARCH2B, "oil-fields.mvt"));
const TILE_VERSION = "2026-10-22.d28ecc72";

const OUTLINE = {
  type: "Feature",
  properties: { name: "Highland site" },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [-5.4, 56.8],
        [-4.1, 57.05],
        [-4.6, 57.7],
        [-5.6, 57.35],
        [-5.4, 56.8],
      ],
    ],
  },
};

function oilTileManifest() {
  return JSON.stringify({
    schema: 1,
    tilesets: {
      "oil-fields": {
        layer: "oil-fields",
        version: TILE_VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "polygon",
        source_layer: "oil-fields",
        measure: null,
        attribution: "Synthetic oil attribution",
        style: {
          fill: { "fill-color": "#8a3b00", "fill-opacity": 0.28 },
          line: { "line-color": "#8a3b00", "line-width": 1.6, "line-opacity": 0.95 },
        },
        legend: [{ label: "Oil and gas fields", color: "#8a3b00" }],
      },
    },
  });
}

async function stubOilTiles(page: Page) {
  await routeManifestOverride(page, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: oilTileManifest(),
    });
  });
  await page.route("**/backend/v1/tiles/oil-fields/**/*.mvt", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: OIL_MVT,
    });
  });
}

async function renderedCount(page: Page, layerIds: string[]): Promise<number> {
  return page.evaluate((ids) => {
    const map = (
      window as unknown as {
        __map?: {
          getLayer(id: string): unknown;
          queryRenderedFeatures(opts: { layers: string[] }): unknown[];
        };
      }
    ).__map;
    if (!map) return 0;
    const present = ids.filter((id) => map.getLayer(id));
    if (present.length === 0) return 0;
    return map.queryRenderedFeatures({ layers: present }).length;
  }, layerIds);
}

async function jump(page: Page, zoom: number) {
  await page.evaluate((z) => {
    const map = (
      window as unknown as {
        __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
      }
    ).__map;
    map?.jumpTo({ center: [-4.5, 57.2], zoom: z });
  }, zoom);
}

/** people/km² adds /layers/councils; wait until jump has actually landed. */
async function waitZoomAtLeast(page: Page, zoom: number) {
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const map = (window as unknown as { __map?: { getZoom(): number } })
          .__map;
        return map?.getZoom() ?? 0;
      }),
    )
    .toBeGreaterThanOrEqual(zoom);
}

test.describe("LAYERS-PERF-3", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("oil and gas tiles visible at z5 without zoom hint", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    let contextHits = 0;
    await stubMapCardsBackend(page);
    page.on("request", (req) => {
      if (/\/layers\/context\/oil-fields/.test(req.url())) contextHits += 1;
    });
    await stubOilTiles(page);

    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "resources");
    const toggle = page.getByTestId("layer-toggle-9");
    const hint = page.getByTestId("oil-gas-zoom-hint");

    await jump(page, 5);
    await toggle.click();
    await expect
      .poll(async () => renderedCount(page, ["tile-oil-fields-fill"]), {
        timeout: 20_000,
      })
      .toBeGreaterThan(0);
    await expect(hint).toHaveCount(0);
    expect(contextHits).toBe(0);

    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-checked", "false");
    await toggle.click();
    await expect
      .poll(async () => renderedCount(page, ["tile-oil-fields-fill"]), {
        timeout: 20_000,
      })
      .toBeGreaterThan(0);
    assertConsoleClean(gate);
  });

  // QUARANTINE CI-DEDUP-1 Q2: flaky on unrelated PRs, runs 38979369689, 39494972071; owner Eng Lead; exit = 10 consecutive green quarantine runs then remove tag, or fix by 2026-11-21.
  test("simplified outlines chip is shown at z6 and hidden at z10 @quarantine", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    const body = JSON.stringify({
      type: "FeatureCollection",
      features: [OUTLINE],
    });
    await stubMapCardsBackend(page);
    await page.route("**/layers/open/naturescot-designations**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body,
      });
    });
    await page.route("**/layers/open/sssi**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body,
      });
    });

    await openMap(page);
    await waitForMap(page);
    await jump(page, 6);
    // FRONTEND-BATCH-1 diagnosis: people/km² adds /layers/councils; wait for
    // zoom ≥6 before the chip assert (test timing, not a product bug).
    await waitZoomAtLeast(page, 6);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "limits");
    await page.getByTestId("layer-toggle-designations").click();

    const chip = page.getByTestId("simplified-outlines-chip");
    await expect(chip).toHaveText(
      "Simplified outlines at this zoom. Zoom in for detail.",
      { timeout: 20_000 },
    );

    await jump(page, 10);
    await expect(chip).toBeHidden({ timeout: 20_000 });
    assertConsoleClean(gate);
  });

  // QUARANTINE CI-DEDUP-1 Q1: title must match QUARANTINE.md exactly (ci-dedup-1a P6).
  // ARCH-2b: oil GeoJSON hint removed; assert oil tiles under the protected-sites hint.
  test("oil and gas hint stacks under the protected-sites hint @quarantine", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    const hiddenSites = JSON.stringify({
      type: "FeatureCollection",
      features: [],
      meta: { hidden_below_zoom: true },
    });
    await stubMapCardsBackend(page);
    await stubOilTiles(page);
    await page.route("**/layers/open/naturescot-designations**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: hiddenSites,
      });
    });
    await page.route("**/layers/open/sssi**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: hiddenSites,
      });
    });

    await openMap(page);
    await waitForMap(page);
    await jump(page, 6);
    await waitZoomAtLeast(page, 6);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "limits");
    await page.getByTestId("layer-toggle-designations").click();
    await ensureLayersGroupOpen(page, "resources");
    await page.getByTestId("layer-toggle-9").click();

    const sites = page.getByTestId("protected-sites-zoom-hint");
    await expect(sites).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("oil-gas-zoom-hint")).toHaveCount(0);
    await expect
      .poll(async () => renderedCount(page, ["tile-oil-fields-fill"]), {
        timeout: 20_000,
      })
      .toBeGreaterThan(0);
    assertConsoleClean(gate);
  });
});
