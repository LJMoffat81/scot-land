
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test, expect } from "./_fixtures";
import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean, ensureLayersGroupOpen, openLayers, openMap, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * LAYERS-PERF-1 — protected sites draw inside the payload budget, and
 * Oil and gas tiles load once per session (ARCH-2b route swap).
 */

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

async function stubOilTiles(page: Page, onManifest: () => void) {
  await page.route("**/backend/v1/tiles/manifest.json", async (route) => {
    onManifest();
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

const HIGHLAND_POLYGON = {
  type: "Feature",
  properties: { name: "Highland site" },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [-5.2, 56.9],
        [-4.2, 56.9],
        [-4.2, 57.6],
        [-5.2, 57.6],
        [-5.2, 56.9],
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

function featureCollection(features: Array<Record<string, unknown>>): string {
  return JSON.stringify({ type: "FeatureCollection", features });
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

async function jump(page: Page, center: [number, number], zoom: number) {
  await page.evaluate(
    ({ center: next, zoom: z }) => {
      const map = (
        window as unknown as {
          __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
        }
      ).__map;
      map?.jumpTo({ center: next, zoom: z });
    },
    { center, zoom },
  );
}

test.describe("LAYERS-PERF-1", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("protected sites draw at Scotland z6 and Highlands z8", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    // CI has no live NatureScot extract, so this spec cannot measure a real
    // payload. The 500 KB cap stays in the backend tests. Here we record the
    // zoom the browser actually requests.
    const requestedZooms: string[] = [];
    await stubMapCardsBackend(page);
    const body = featureCollection([HIGHLAND_POLYGON]);
    const fulfill = async (route: {
      request(): { url(): string };
      fulfill(opts: {
        status: number;
        contentType: string;
        body: string;
      }): Promise<void>;
    }) => {
      requestedZooms.push(new URL(route.request().url()).searchParams.get("z") ?? "");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body,
      });
    };
    await page.route("**/layers/open/sssi**", fulfill);
    await page.route("**/layers/open/naturescot-designations**", fulfill);
    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "nature");
    await jump(page, [-4.5, 57.2], 6);
    await page.getByTestId("layer-toggle-designations").click();
    await expect
      .poll(async () => renderedCount(page, ["designations-fill"]), {
        timeout: 20_000,
      })
      .toBeGreaterThan(0);
    expect(requestedZooms.length).toBeGreaterThan(0);
    for (const zoom of requestedZooms) expect(Number(zoom)).toBeGreaterThanOrEqual(6);

    const beforeHighlands = requestedZooms.length;
    await jump(page, [-4.7, 57.25], 8);
    await expect
      .poll(async () => requestedZooms.length, { timeout: 20_000 })
      .toBeGreaterThan(beforeHighlands);
    await expect
      .poll(async () => renderedCount(page, ["designations-fill"]), {
        timeout: 20_000,
      })
      .toBeGreaterThan(0);
    for (const zoom of requestedZooms.slice(beforeHighlands)) {
      expect(Number(zoom)).toBeGreaterThanOrEqual(8);
    }
    assertConsoleClean(gate);
  });

  test("Oil and gas on/off/on three times fetches once", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    let manifestHits = 0;
    let contextHits = 0;
    await stubMapCardsBackend(page);
    page.on("request", (req) => {
      if (/\/layers\/context\/oil-fields/.test(req.url())) contextHits += 1;
    });
    await stubOilTiles(page, () => {
      manifestHits += 1;
    });
    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "resources");
    await jump(page, [1.2, 57.6], 6);
    const toggle = page.getByTestId("layer-toggle-9");
    for (let cycle = 0; cycle < 3; cycle += 1) {
      if ((await toggle.getAttribute("aria-checked")) !== "true") {
        await toggle.click();
      }
      await expect
        .poll(async () => renderedCount(page, ["tile-oil-fields-fill"]), {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-checked", "false");
      await toggle.click();
      await expect
        .poll(async () => renderedCount(page, ["tile-oil-fields-fill"]), {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
    }
    expect(manifestHits).toBe(1);
    expect(contextHits).toBe(0);
    assertConsoleClean(gate);
  });
});
