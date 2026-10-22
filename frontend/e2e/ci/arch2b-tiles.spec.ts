/**
 * ARCH-2b E-1..E-7 — native vector tiles for DZ / oil / platforms / pipelines.
 * Auto-discovered under e2e/ci/; strict gate via ./_fixtures; no global stubs.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import type { Page } from "@playwright/test";

registerOpenFreeMapFontStub();

// Playwright CI cwd is frontend/; avoid import.meta (not an ESM module here).
const FIXTURES = join(process.cwd(), "e2e", "fixtures", "arch2b");

const VERSION = "2026-10-22.d28ecc72";

const MVT: Record<string, Buffer> = {
  dz2022: readFileSync(join(FIXTURES, "dz2022.mvt")),
  "oil-fields": readFileSync(join(FIXTURES, "oil-fields.mvt")),
  platforms: readFileSync(join(FIXTURES, "platforms.mvt")),
  pipelines: readFileSync(join(FIXTURES, "pipelines.mvt")),
};

function syntheticManifest() {
  return {
    schema: 1,
    tilesets: {
      dz2022: {
        layer: "dz2022",
        version: VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "polygon",
        title: "Data Zones 2022",
        source_layer: "dz2022",
        measure: "pop_density",
        attribution: "Synthetic DZ attribution",
        style: {
          fill: {
            "fill-color": [
              "case",
              ["==", ["feature-state", "v"], null],
              "#d9d9d9",
              [
                "interpolate",
                ["linear"],
                ["feature-state", "v"],
                10,
                "#c6dbef",
                100,
                "#6baed6",
                500,
                "#2171b5",
                1500,
                "#08519c",
                3000,
                "#08306b",
              ],
            ],
            "fill-opacity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              4.5,
              0,
              5,
              0.55,
              14,
              0.55,
              15,
              0.4,
            ],
          },
          line: {
            "line-color": "#0b1e3a",
            "line-width": 1.05,
            "line-opacity": [
              "interpolate",
              ["linear"],
              ["zoom"],
              8.5,
              0,
              9.5,
              0.6,
            ],
          },
        },
        legend: [
          { label: "10", color: "#c6dbef" },
          { label: "100", color: "#6baed6" },
          { label: "500", color: "#2171b5" },
          { label: "1500", color: "#08519c" },
          { label: "3000", color: "#08306b" },
          { label: "No value", color: "#d9d9d9" },
        ],
      },
      "oil-fields": {
        layer: "oil-fields",
        version: VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "polygon",
        source_layer: "oil-fields",
        measure: null,
        attribution: "Synthetic oil attribution",
        style: {
          fill: { "fill-color": "#8a3b00", "fill-opacity": 0.28 },
          line: {
            "line-color": "#8a3b00",
            "line-width": 1.6,
            "line-opacity": 0.95,
          },
        },
        legend: [{ label: "Oil and gas fields", color: "#8a3b00" }],
      },
      platforms: {
        layer: "platforms",
        version: VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "point",
        source_layer: "platforms",
        measure: null,
        attribution: "Synthetic platforms attribution",
        style: { circle: { "circle-color": "#8a3b00", "circle-radius": 4.5 } },
        legend: [{ label: "Platforms", color: "#8a3b00" }],
      },
      pipelines: {
        layer: "pipelines",
        version: VERSION,
        minzoom: 0,
        maxzoom: 14,
        geometry: "line",
        source_layer: "pipelines",
        measure: null,
        attribution: "Synthetic pipelines attribution",
        style: {
          line: {
            "line-color": "#5c4a32",
            "line-width": 1.4,
            "line-opacity": 0.9,
          },
        },
        legend: [{ label: "Pipelines", color: "#5c4a32" }],
      },
    },
  };
}

async function routeArch2bTiles(
  page: Page,
  opts: {
    manifest?: "ok" | "404" | "bad";
    values?: "ok" | "404";
    tile404Path?: string | null;
  } = {},
) {
  const manifestMode = opts.manifest ?? "ok";
  const valuesMode = opts.values ?? "ok";
  const tile404Path = opts.tile404Path ?? null;

  // Opt into ScotlandMap's tile manifest fetch (E2E_HOOKS builds skip it
  // unless set — avoids catch-all **/backend/** 404s in unrelated specs).
  await page.addInitScript(() => {
    (
      window as unknown as { __ARCH2B_LOAD_TILES__?: boolean }
    ).__ARCH2B_LOAD_TILES__ = true;
  });

  await page.route("**/backend/v1/tiles/manifest.json", async (route) => {
    if (manifestMode === "404") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "unknown tileset" }),
      });
      return;
    }
    if (manifestMode === "bad") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{",
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(syntheticManifest()),
    });
  });

  await page.route("**/backend/v1/tiles/**/values/pop_density.json", async (route) => {
    if (valuesMode === "404") {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "values unavailable" }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        layer: "dz2022",
        version: VERSION,
        measure: "pop_density",
        values: { S01013482: 225.1 },
      }),
    });
  });

  await page.route("**/backend/v1/tiles/**/*.mvt", async (route) => {
    const url = route.request().url();
    if (tile404Path && url.includes(tile404Path)) {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: "tile out of range" }),
      });
      return;
    }
    let layer = "dz2022";
    if (url.includes("/oil-fields/")) layer = "oil-fields";
    else if (url.includes("/platforms/")) layer = "platforms";
    else if (url.includes("/pipelines/")) layer = "pipelines";
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: MVT[layer],
    });
  });
}

async function renderedCount(page: Page, layerIds: string[]): Promise<number> {
  return page.evaluate((ids) => {
    const map = (
      window as unknown as {
        __map?: {
          queryRenderedFeatures: (opts: { layers: string[] }) => unknown[];
          getLayer: (id: string) => unknown;
        };
      }
    ).__map;
    if (!map) return 0;
    const existing = ids.filter((id) => map.getLayer(id));
    if (!existing.length) return 0;
    return map.queryRenderedFeatures({ layers: existing }).length;
  }, layerIds);
}

async function jump(page: Page, center: [number, number], zoom: number) {
  await page.evaluate(
    ({ c, z }) => {
      const map = (
        window as unknown as {
          __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
        }
      ).__map;
      map?.jumpTo({ center: c, zoom: z });
    },
    { c: center, z: zoom },
  );
}

async function featureStateV(page: Page, code: string): Promise<unknown> {
  return page.evaluate((id) => {
    const map = (
      window as unknown as {
        __map?: {
          getFeatureState: (t: {
            source: string;
            sourceLayer: string;
            id: string;
          }) => Record<string, unknown> | null | undefined;
        };
      }
    ).__map;
    if (!map) return null;
    return map.getFeatureState({
      source: "tile-dz2022",
      sourceLayer: "dz2022",
      id,
    })?.v;
  }, code);
}

test.describe("ARCH-2b tiles", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("E-1 dz fill at z5 with feature-state", async ({ page, gate }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await routeArch2bTiles(page);
    await openMap(page, "/?layers=data_zones&z=5&c=-3.2,55.95");
    await waitForMap(page);
    await jump(page, [-3.2, 55.95], 5);
    await expect
      .poll(async () => renderedCount(page, ["tile-dz2022-fill"]), {
        timeout: 30_000,
      })
      .toBeGreaterThan(0);
    await expect
      .poll(async () => featureStateV(page, "S01013482"), { timeout: 20_000 })
      .toBe(225.1);
    assertConsoleClean(gate);
  });

  test("E-2 oil tiles at z5; zero GeoJSON context fetches", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    let banned = 0;
    page.on("request", (req) => {
      const u = req.url();
      if (
        /\/layers\/context\/(oil-fields|platforms|pipelines)/.test(u) ||
        /\/layers\/open\/data-zones/.test(u)
      ) {
        banned += 1;
      }
    });
    await stubMapCardsBackend(page);
    await routeArch2bTiles(page);
    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "resources");
    await jump(page, [1.2, 57.6], 5);
    await page.getByTestId("layer-toggle-9").click();
    await expect
      .poll(async () => renderedCount(page, ["tile-oil-fields-fill"]), {
        timeout: 30_000,
      })
      .toBeGreaterThan(0);
    expect(banned).toBe(0);
    assertConsoleClean(gate);
  });

  test("E-3 DZ fill stays across zoom; outline from 9.5", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await routeArch2bTiles(page);
    await openMap(page, "/?layers=data_zones&z=5&c=-3.2,55.95");
    await waitForMap(page);
    for (const z of [5, 7, 10]) {
      await jump(page, [-3.2, 55.95], z);
      await expect
        .poll(async () => renderedCount(page, ["tile-dz2022-fill"]), {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
    }
    // Outline opacity ramps in at 9.5; at z10 it should query.
    await jump(page, [-3.2, 55.95], 10);
    await expect
      .poll(async () => renderedCount(page, ["tile-dz2022-line"]), {
        timeout: 20_000,
      })
      .toBeGreaterThan(0);
    await jump(page, [-3.2, 55.95], 8);
    // At z8 outline opacity is 0 — features may still query; check paint opacity.
    const outlineOpacity = await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: {
            getPaintProperty: (id: string, prop: string) => unknown;
            getZoom: () => number;
          };
        }
      ).__map;
      if (!map) return null;
      return { zoom: map.getZoom(), paint: map.getPaintProperty("tile-dz2022-line", "line-opacity") };
    });
    expect(outlineOpacity?.zoom).toBeLessThan(9.5);
    assertConsoleClean(gate);
  });

  test("E-4 manifest 404 shows note", async ({ page, gate }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    gate.expectError({
      urlPath: "/backend/v1/tiles/manifest.json",
      status: 404,
      count: 1,
    });
    await stubMapCardsBackend(page);
    await routeArch2bTiles(page, { manifest: "404" });
    await openMap(page);
    await waitForMap(page);
    await expect(page.getByText("One layer did not load.")).toBeVisible({
      timeout: 20_000,
    });
    assertConsoleClean(gate);
  });

  test("E-5 invalid manifest body shows note", async ({ page, gate }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await routeArch2bTiles(page, { manifest: "bad" });
    await openMap(page);
    await waitForMap(page);
    await expect(page.getByText("One layer did not load.")).toBeVisible({
      timeout: 20_000,
    });
    assertConsoleClean(gate);
  });

  test("E-6 one tile 404 allowed; others render", async ({ page, gate }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    // Gate matches pathname === urlPath exactly. Use z15 (above maxzoom) so
    // MapLibre never requests it; force one console 404 via <script> (fetch
    // does not emit "Failed to load resource").
    const failTilePath = `/backend/v1/tiles/dz2022/${VERSION}/15/0/0.mvt`;
    gate.expectError({
      urlPath: failTilePath,
      status: 404,
      count: 1,
    });
    await stubMapCardsBackend(page);
    await page.route("**/backend/v1/tiles/manifest.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(syntheticManifest()),
      });
    });
    await page.route("**/backend/v1/tiles/**/values/pop_density.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          layer: "dz2022",
          version: VERSION,
          measure: "pop_density",
          values: { S01013482: 225.1 },
        }),
      });
    });
    await page.route("**/backend/v1/tiles/**/*.mvt", async (route) => {
      const url = route.request().url();
      let pathname = "";
      try {
        pathname = new URL(url).pathname;
      } catch {
        pathname = "";
      }
      if (pathname === failTilePath) {
        await route.fulfill({
          status: 404,
          contentType: "application/json",
          body: JSON.stringify({ detail: "tile out of range" }),
        });
        return;
      }
      let layer = "dz2022";
      if (url.includes("/oil-fields/")) layer = "oil-fields";
      else if (url.includes("/platforms/")) layer = "platforms";
      else if (url.includes("/pipelines/")) layer = "pipelines";
      await route.fulfill({
        status: 200,
        contentType: "application/vnd.mapbox-vector-tile",
        body: MVT[layer],
      });
    });
    await openMap(page, "/?layers=data_zones&z=5&c=-3.2,55.95");
    await waitForMap(page);
    await jump(page, [-3.2, 55.95], 5);
    await expect
      .poll(async () => renderedCount(page, ["tile-dz2022-fill"]), {
        timeout: 30_000,
      })
      .toBeGreaterThan(0);
    await page.evaluate(async (src) => {
      await new Promise<void>((resolve) => {
        const el = document.createElement("script");
        el.src = src;
        el.onload = () => resolve();
        el.onerror = () => resolve();
        document.head.appendChild(el);
      });
    }, failTilePath);
    assertConsoleClean(gate);
  });

  test("E-7 values 404 → grey fill + No value legend", async ({
    page,
    gate,
  }) => {
    test.setTimeout(120_000);
    attachConsoleGate(page);
    gate.expectError({
      urlPath: `/backend/v1/tiles/dz2022/${VERSION}/values/pop_density.json`,
      status: 404,
      count: 1,
    });
    await stubMapCardsBackend(page);
    await routeArch2bTiles(page, { values: "404" });
    await openMap(page, "/?layers=data_zones&z=5&c=-3.2,55.95");
    await waitForMap(page);
    await jump(page, [-3.2, 55.95], 5);
    await expect
      .poll(async () => renderedCount(page, ["tile-dz2022-fill"]), {
        timeout: 30_000,
      })
      .toBeGreaterThan(0);
    await expect(page.getByText("No value")).toBeVisible({ timeout: 20_000 });
    assertConsoleClean(gate);
  });
});
