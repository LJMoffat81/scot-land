
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "./_fixtures";
import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean, ensureLayersGroupOpen, getMapZoom, openLayers, openMap, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

const ARCH2B = join(dirname(fileURLToPath(import.meta.url)), "../fixtures/arch2b");
const OIL_MVT = readFileSync(join(ARCH2B, "oil-fields.mvt"));
const TILE_VERSION = "2026-10-22.d28ecc72";

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

/**
 * LAYERS-FIX-1 — every visible switch draws or shows a zoom hint.
 * On 1bdfdf6 the empty stubs are switches, upstream 204 becomes 503,
 * protected sites and oil and gas draw nothing, and AGR has no zoom-out hint.
 * ARCH-2b: oil and gas uses /v1/tiles (route swap).
 */

const HIDDEN_STUBS = [
  "flood",
  "deprivation",
  "conservation",
  "listed",
  "stops",
  "8",
] as const;

const SCOTLAND_POLYGON = {
  type: "Feature",
  properties: { population_density_per_km2: 40 },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [-7.8, 55.0],
        [-1.0, 55.0],
        [-1.0, 59.0],
        [-7.8, 59.0],
        [-7.8, 55.0],
      ],
    ],
  },
};

const NORTH_SEA_POLYGON = {
  type: "Feature",
  properties: { name: "North Sea field" },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [0.4, 56.6],
        [2.0, 56.6],
        [2.0, 58.6],
        [0.4, 58.6],
        [0.4, 56.6],
      ],
    ],
  },
};

const CAIRNGORMS_POLYGON = {
  type: "Feature",
  properties: { name: "Cairngorms" },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [-3.9, 57.0],
        [-3.5, 57.0],
        [-3.5, 57.2],
        [-3.9, 57.2],
        [-3.9, 57.0],
      ],
    ],
  },
};

function featureCollection(
  features: Array<Record<string, unknown>>,
): string {
  return JSON.stringify({ type: "FeatureCollection", features });
}

function polygonInBbox(url: string): string {
  const parsed = new URL(url);
  const south = Number(parsed.searchParams.get("south"));
  const west = Number(parsed.searchParams.get("west"));
  const north = Number(parsed.searchParams.get("north"));
  const east = Number(parsed.searchParams.get("east"));
  const lngPad = (east - west) * 0.2;
  const latPad = (north - south) * 0.2;
  return featureCollection([
    {
      type: "Feature",
      properties: { name: "in view" },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [west + lngPad, south + latPad],
            [east - lngPad, south + latPad],
            [east - lngPad, north - latPad],
            [west + lngPad, north - latPad],
            [west + lngPad, south + latPad],
          ],
        ],
      },
    },
  ]);
}

async function stubOverviewShapes(page: Page) {
  // FRONTEND-BATCH-1: map loads /layers/councils first; keep density + geometry.
  const councilsBody = featureCollection([SCOTLAND_POLYGON]);
  await page.route("**/layers/councils**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: councilsBody,
    });
  });
  await page.route("**/boundaries/councils**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: councilsBody,
    });
  });
  await page.route("**/backend/v1/tiles/manifest.json", async (route) => {
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
  await page.route("**/layers/open/crown-estate-leases**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: polygonInBbox(route.request().url()),
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

test.describe("LAYERS-FIX-1", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("hidden stubs are absent; every visible switch draws or hints", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await stubOverviewShapes(page);
    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    for (const key of ["land", "resources", "nature", "places"]) {
      await ensureLayersGroupOpen(page, key);
    }

    for (const id of HIDDEN_STUBS) {
      await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
    }
    await expect(page.getByTestId("layer-toggle-vdl")).toHaveCount(0);

    await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: {
            jumpTo(opts: { center: [number, number]; zoom: number }): void;
          };
        }
      ).__map;
      map?.jumpTo({ center: [-4.2, 56.8], zoom: 5.5 });
    });
    await expect.poll(async () => getMapZoom(page)).toBeLessThan(6);
    await expect.poll(async () => getMapZoom(page)).toBeGreaterThanOrEqual(5);

    const rows = page.locator("[data-testid^='map-layer-']");
    const discovered = await rows.evaluateAll((els) =>
      els.map((el) => ({
        id: (el.getAttribute("data-testid") || "").replace("map-layer-", ""),
        minzoom: Number(el.getAttribute("data-minzoom")),
        maxzoom: Number(el.getAttribute("data-maxzoom")),
        zoomOutAbove: el.getAttribute("data-zoom-out-above") || "",
        paintLayers: (el.getAttribute("data-paint-layers") || "")
          .split(" ")
          .filter(Boolean),
      })),
    );
    expect(discovered.length).toBeGreaterThan(0);

    for (const row of discovered) {
      // FRONTEND-BATCH-4: pop-density-key is a legend/key row (no switch). Every
      // other map-layer-* row must still expose a toggle.
      const toggle = page.getByTestId(`layer-toggle-${row.id}`);
      if (row.id === "pop-density-key") {
        await expect(toggle).toHaveCount(0);
        continue;
      }
      await expect(
        toggle,
        `map-layer-${row.id} must expose layer-toggle-${row.id}`,
      ).toHaveCount(1);

      await page.evaluate(() => {
        const map = (
          window as unknown as {
            __map?: {
              jumpTo(opts: { center: [number, number]; zoom: number }): void;
            };
          }
        ).__map;
        map?.jumpTo({ center: [-4.2, 56.8], zoom: 5.5 });
      });
      if ((await toggle.getAttribute("aria-checked")) !== "true") {
        await toggle.click();
      }
      const zoom = await getMapZoom(page);
      const zoomOutAbove =
        row.zoomOutAbove === "" ? null : Number(row.zoomOutAbove);
      const gated =
        zoom < row.minzoom ||
        zoom > row.maxzoom ||
        (zoomOutAbove != null && zoom > zoomOutAbove);
      if (gated) {
        await expect(page.getByTestId(`layer-zoom-gate-${row.id}`)).toBeVisible();
        continue;
      }
      expect(row.paintLayers.length, `${row.id} has no paint layers`).toBeGreaterThan(
        0,
      );
      await expect
        .poll(async () => renderedCount(page, row.paintLayers), {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
    }

    await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
        }
      ).__map;
      map?.jumpTo({ center: [-4.2, 56.8], zoom: 12 });
    });
    const agr = page.getByTestId("layer-toggle-1");
    if ((await agr.getAttribute("aria-checked")) !== "true") {
      await agr.click();
    }
    await expect(page.getByTestId("layer-zoom-gate-1")).toHaveText(
      "Zoom out to see this layer",
    );
    const grid = page.getByTestId("layer-toggle-grid3");
    if ((await grid.getAttribute("aria-checked")) !== "true") {
      await grid.click();
    }
    await expect(page.getByTestId("layer-zoom-gate-grid3")).toHaveText(
      "Zoom in to see the grid",
    );

    assertConsoleClean(gate);
  });

  test("Cairngorms z9 protected sites draw; z5 does not fetch", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    let fetches = 0;
    await stubMapCardsBackend(page);
    await page.route("**/layers/open/naturescot-designations**", async (route) => {
      fetches += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: featureCollection([CAIRNGORMS_POLYGON]),
      });
    });
    await page.route("**/layers/open/sssi**", async (route) => {
      fetches += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: featureCollection([CAIRNGORMS_POLYGON]),
      });
    });
    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "nature");
    await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
        }
      ).__map;
      map?.jumpTo({ center: [-4.2, 56.8], zoom: 5 });
    });
    await page.getByTestId("layer-toggle-designations").click();
    await page.waitForTimeout(1200);
    expect(fetches).toBe(0);

    await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
        }
      ).__map;
      map?.jumpTo({ center: [-3.7, 57.1], zoom: 9 });
    });
    await expect
      .poll(async () => renderedCount(page, ["designations-fill"]), {
        timeout: 20_000,
      })
      .toBeGreaterThan(0);
    expect(fetches).toBeGreaterThan(0);
    assertConsoleClean(gate);
  });

  test("North Sea z6 oil-fields draw", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await stubOverviewShapes(page);
    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "resources");
    await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
        }
      ).__map;
      map?.jumpTo({ center: [1.2, 57.6], zoom: 6 });
    });
    await page.getByTestId("layer-toggle-9").click();
    await expect
      .poll(async () => renderedCount(page, ["tile-oil-fields-fill"]), {
        timeout: 20_000,
      })
      .toBeGreaterThan(0);
    assertConsoleClean(gate);
  });
});
