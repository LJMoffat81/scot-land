/**
 * ARCH-5b — every-zoom validators (N5b-1..3) and low-zoom LAYERS-ADD paint (E5b-1).
 */
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
  getMapZoom,
} from "./_mapCardsHelpers";
import {
  assertLayersAddEveryZoom,
  LAYERS_ADD_REGISTRY,
} from "../../lib/layersAddRegistry";
import {
  assertLayersAddPaintEveryZoom,
  LAYERS_ADD_PAINT,
} from "../../lib/layersAddMapPaint";
import {
  assertMapRegistryEveryZoom,
  MAP_LAYER_REGISTRY,
} from "../../lib/mapLayerRegistry";
import type { Page } from "@playwright/test";

registerOpenFreeMapFontStub();

const BASE_ROW = {
  id: "deprivation",
  layerId: "simd2020_domains",
  group: "places" as const,
  label: "Local deprivation by topic, 2020",
  family: "fill" as const,
  minzoom: 0,
  maxzoom: 20,
  defaultOn: false as const,
  caption: "Scottish Government · 2020",
  credit: "credit",
};

const BASE_PAINT = {
  displayId: "access_services",
  catalogLayerId: "access_services",
  kind: "fill" as const,
  color: "#3b528b",
  minzoom: 0,
  attribution: "credit",
};

const BASE_ENTRY = {
  id: "access_services",
  group: "land" as const,
  label: "Why it's valuable: access to services (2020 data)",
  minzoom: 0,
  maxzoom: 20,
  sourceCaption: "Scottish Government · 2020",
  classes: [{ label: "Lower", color: "#000000" }],
  defaultOn: false,
};

const E5B_ROWS = [
  { id: "access_services", group: "land", fill: "access_services-add-fill" },
  {
    id: "contaminated_land",
    group: "land",
    fill: "contaminated_land-add-fill",
  },
  { id: "green_belt", group: "places", fill: "green_belt-add-fill" },
  {
    id: "school_catchments",
    group: "places",
    fill: "school_catchments-add-fill",
  },
] as const;

async function stubViewportShapes(page: Page) {
  await page.route("**/layers/add/viewport/**", async (route) => {
    const url = new URL(route.request().url());
    const south = Number(url.searchParams.get("south"));
    const west = Number(url.searchParams.get("west"));
    const north = Number(url.searchParams.get("north"));
    const east = Number(url.searchParams.get("east"));
    const lngPad = (east - west) * 0.15;
    const latPad = (north - south) * 0.15;
    const body = {
      type: "FeatureCollection",
      features: [
        {
          type: "Feature",
          properties: { name: "in view", q: 1, class: "1" },
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
      ],
    };
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

async function expectLayerDrawn(page: Page, layerId: string) {
  await expect
    .poll(
      async () =>
        page.evaluate((id) => {
          const map = (
            window as unknown as {
              __map?: {
                getLayer(layer: string): unknown;
                queryRenderedFeatures(opts: { layers: string[] }): unknown[];
              };
            }
          ).__map;
          if (!map?.getLayer(id)) return 0;
          return map.queryRenderedFeatures({ layers: [id] }).length;
        }, layerId),
      { timeout: 20_000 },
    )
    .toBeGreaterThan(0);
}

test("N5b-1 assertLayersAddEveryZoom", () => {
  expect(() => assertLayersAddEveryZoom()).not.toThrow();
  expect(LAYERS_ADD_REGISTRY.every((row) => row.minzoom === 0)).toBe(true);

  for (const badRows of [
    undefined,
    null,
    "",
    123,
    1.5,
    true,
    false,
    {},
    [],
  ]) {
    expect(() => assertLayersAddEveryZoom(badRows)).toThrowError(
      /^EVERY-ZOOM: layersAdd rows must be a non-empty array$/,
    );
  }

  for (const badRow of [
    undefined,
    null,
    "str",
    123,
    1.5,
    true,
    false,
    [],
  ]) {
    expect(() => assertLayersAddEveryZoom([badRow])).toThrowError(
      /^EVERY-ZOOM: layersAdd row must be an object$/,
    );
  }

  for (const badId of [
    undefined,
    null,
    "",
    "   ",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertLayersAddEveryZoom([{ ...BASE_ROW, id: badId as never }]),
    ).toThrowError(
      /^EVERY-ZOOM: layersAdd row id must be a non-empty string$/,
    );
  }

  for (const badMin of [
    undefined,
    null,
    "0",
    1.5,
    NaN,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertLayersAddEveryZoom([{ ...BASE_ROW, minzoom: badMin as never }]),
    ).toThrowError(
      /^EVERY-ZOOM: layersAdd 'deprivation': minzoom must be an integer$/,
    );
  }

  for (const nonZero of [-1, 1, 8, 10, 12, 14]) {
    expect(() =>
      assertLayersAddEveryZoom([{ ...BASE_ROW, minzoom: nonZero }]),
    ).toThrowError(
      new RegExp(
        `^EVERY-ZOOM: layersAdd 'deprivation': minzoom must be 0, got ${nonZero}$`,
      ),
    );
  }

  for (const badMax of [
    undefined,
    null,
    "20",
    0,
    -1,
    1.5,
    NaN,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertLayersAddEveryZoom([{ ...BASE_ROW, maxzoom: badMax as never }]),
    ).toThrowError(
      /^EVERY-ZOOM: layersAdd 'deprivation': maxzoom must be a positive integer$/,
    );
  }
});

test("N5b-2 assertLayersAddPaintEveryZoom", () => {
  expect(() => assertLayersAddPaintEveryZoom()).not.toThrow();
  expect(LAYERS_ADD_PAINT.every((spec) => spec.minzoom === 0)).toBe(true);

  for (const badSpecs of [
    undefined,
    null,
    "",
    123,
    1.5,
    true,
    false,
    {},
    [],
  ]) {
    expect(() => assertLayersAddPaintEveryZoom(badSpecs)).toThrowError(
      /^EVERY-ZOOM: layersAddPaint specs must be a non-empty array$/,
    );
  }

  for (const badSpec of [
    undefined,
    null,
    "str",
    123,
    1.5,
    true,
    false,
    [],
  ]) {
    expect(() => assertLayersAddPaintEveryZoom([badSpec])).toThrowError(
      /^EVERY-ZOOM: layersAddPaint spec must be an object$/,
    );
  }

  for (const badId of [
    undefined,
    null,
    "",
    "   ",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertLayersAddPaintEveryZoom([
        { ...BASE_PAINT, displayId: badId as never },
      ]),
    ).toThrowError(
      /^EVERY-ZOOM: layersAddPaint displayId must be a non-empty string$/,
    );
  }

  for (const badMin of [
    undefined,
    null,
    "0",
    1.5,
    NaN,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertLayersAddPaintEveryZoom([
        { ...BASE_PAINT, minzoom: badMin as never },
      ]),
    ).toThrowError(
      /^EVERY-ZOOM: layersAddPaint 'access_services': minzoom must be an integer$/,
    );
  }

  for (const nonZero of [-1, 1, 8, 10, 12, 14]) {
    expect(() =>
      assertLayersAddPaintEveryZoom([{ ...BASE_PAINT, minzoom: nonZero }]),
    ).toThrowError(
      new RegExp(
        `^EVERY-ZOOM: layersAddPaint 'access_services': minzoom must be 0, got ${nonZero}$`,
      ),
    );
  }
});

test("N5b-3 assertMapRegistryEveryZoom", () => {
  expect(() => assertMapRegistryEveryZoom()).not.toThrow();
  for (const id of [
    "access_services",
    "flood",
    "contaminated_land",
    "deprivation",
    "conservation",
    "listed",
    "stops",
    "green_belt",
    "school_catchments",
  ]) {
    const entry = MAP_LAYER_REGISTRY.find((row) => row.id === id);
    expect(entry?.minzoom, id).toBe(0);
  }

  for (const badEntries of [
    undefined,
    null,
    "",
    123,
    1.5,
    true,
    false,
    {},
    [],
  ]) {
    expect(() => assertMapRegistryEveryZoom(badEntries)).toThrowError(
      /^EVERY-ZOOM: registry entries must be a non-empty array$/,
    );
  }

  for (const badEntry of [
    undefined,
    null,
    "str",
    123,
    1.5,
    true,
    false,
    [],
  ]) {
    expect(() => assertMapRegistryEveryZoom([badEntry])).toThrowError(
      /^EVERY-ZOOM: registry entry must be an object$/,
    );
  }

  for (const badId of [
    undefined,
    null,
    "",
    "   ",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertMapRegistryEveryZoom([{ ...BASE_ENTRY, id: badId as never }]),
    ).toThrowError(
      /^EVERY-ZOOM: registry entry id must be a non-empty string$/,
    );
  }

  for (const badMin of [
    undefined,
    null,
    "0",
    -1,
    1.5,
    NaN,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      assertMapRegistryEveryZoom([
        { ...BASE_ENTRY, minzoom: badMin as never },
      ]),
    ).toThrowError(
      /^EVERY-ZOOM: registry 'access_services': minzoom must be a non-negative integer$/,
    );
  }

  for (const nonZero of [1, 8, 10, 12, 14]) {
    expect(() =>
      assertMapRegistryEveryZoom([{ ...BASE_ENTRY, minzoom: nonZero }]),
    ).toThrowError(
      new RegExp(
        `^EVERY-ZOOM: registry 'access_services': minzoom must be 0, got ${nonZero}$`,
      ),
    );
  }
});

for (const width of [1280, 390] as const) {
  test.describe(`E5b-1 every-zoom paint @ ${width}`, () => {
    test.use({
      viewport: { width, height: width === 390 ? 844 : 800 },
    });

    test("LAYERS-ADD fills draw at z=5.5 with no zoom gate", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, {
        spatialHubLayerIds: [
          "vdl",
          "contaminated_land",
          "green_belt",
          "school_catchments",
        ],
      });
      await stubViewportShapes(page);
      await openMap(page);
      await waitForMap(page);

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
      await expect
        .poll(async () => getMapZoom(page))
        .toBeGreaterThanOrEqual(5);

      await openLayers(page);

      for (const row of E5B_ROWS) {
        await ensureLayersGroupOpen(page, row.group);
        const rowEl = page.getByTestId(`map-layer-${row.id}`);
        await expect(rowEl).toBeVisible();
        await expect(rowEl).toHaveAttribute("data-minzoom", "0");
        const toggle = page.getByTestId(`layer-toggle-${row.id}`);
        await expect(toggle).toBeVisible();
        if ((await toggle.getAttribute("aria-checked")) !== "true") {
          await toggle.click();
        }
        await expect(
          page.getByTestId(`layer-inline-legend-${row.id}`),
        ).toBeVisible();
        await expect(
          page.getByTestId(`layer-zoom-gate-${row.id}`),
        ).toHaveCount(0);
        await expectLayerDrawn(page, row.fill);
      }

      assertConsoleClean(gate);
    });
  });
}
