/**
 * SRC-C — estimate chips (N14), as-of helper (N15), drawer as-of (N16).
 * N14/N15 are pure (no page); N16 uses routeManifestOverride.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, routeManifestOverride } from "./_fixtures";
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
import {
  MAP_LAYER_REGISTRY,
  checkEstimateChips,
} from "../../lib/mapLayerRegistry";
import { asOfFromVersion } from "../../lib/tileAsOf";
import type { Page } from "@playwright/test";

registerOpenFreeMapFontStub();

const DZ_MVT = readFileSync(
  join(process.cwd(), "e2e", "fixtures", "arch2b", "dz2022.mvt"),
);

async function stubDzTiles(page: Page) {
  await page.route("**/backend/v1/tiles/**/values/pop_density.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        layer: "dz2022",
        version: "2026-10-01.abcdef12",
        measure: "pop_density",
        values: {},
      }),
    });
  });
  await page.route("**/backend/v1/tiles/**/*.mvt", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: DZ_MVT,
    });
  });
}

test("N14 checkEstimateChips", () => {
  expect(
    checkEstimateChips([
      {
        id: "x",
        sourceCaption: "Scot-LAND model · 2023",
        chip: "market",
      },
    ]),
  ).toEqual([
    "EST: x: Scot-LAND model layer must carry a proxy or shadow chip",
  ]);
  expect(
    checkEstimateChips([
      {
        id: "x",
        sourceCaption: "Scot-LAND model · 2023",
        chip: null,
      },
    ]),
  ).toEqual([
    "EST: x: Scot-LAND model layer must carry a proxy or shadow chip",
  ]);
  expect(
    checkEstimateChips([
      {
        id: "x",
        sourceCaption: "Scot-LAND model · 2023",
      },
    ]),
  ).toEqual([
    "EST: x: Scot-LAND model layer must carry a proxy or shadow chip",
  ]);
  expect(checkEstimateChips(MAP_LAYER_REGISTRY)).toEqual([]);
});

test("N15 asOfFromVersion", () => {
  for (const v of [
    undefined,
    "",
    "garbage",
    "2026-13-01.abcdef12",
    "2026-02-30.abcdef12",
    20261001,
    true,
    1.5,
  ]) {
    expect(asOfFromVersion(v)).toBeNull();
  }
  expect(asOfFromVersion("2026-10-01.abcdef12")).toBe("1 Oct 2026");
});

test("N16 layer-asof-data_zones from manifest version", async ({
  page,
  gate,
}) => {
  test.setTimeout(120_000);
  attachConsoleGate(page);
  await stubMapCardsBackend(page);
  await routeManifestOverride(page, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        schema: 1,
        tilesets: {
          dz2022: {
            layer: "dz2022",
            version: "2026-10-01.abcdef12",
            minzoom: 0,
            maxzoom: 14,
            geometry: "polygon",
            source_layer: "dz2022",
            measure: "pop_density",
            attribution: "Synthetic DZ attribution",
            style: {
              fill: { "fill-color": "#d9d9d9", "fill-opacity": 0.55 },
              line: {
                "line-color": "#0b1e3a",
                "line-width": 1.05,
                "line-opacity": 0.6,
              },
            },
            legend: [{ label: "No value", color: "#d9d9d9" }],
          },
        },
      }),
    });
  });
  await stubDzTiles(page);
  await openMap(page, "/?layers=data_zones&z=10&c=-3.2,55.95");
  await waitForMap(page);
  await openLayers(page);
  await ensureLayersGroupOpen(page, "places");
  await expect(page.getByTestId("layer-asof-data_zones")).toHaveText(
    " · Data as of 1 Oct 2026",
  );
  assertConsoleClean(gate);
});

test("N16b no as-of when dz2022 absent from manifest", async ({
  page,
  gate,
}) => {
  test.setTimeout(120_000);
  attachConsoleGate(page);
  await stubMapCardsBackend(page);
  await routeManifestOverride(page, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ schema: 1, tilesets: {} }),
    });
  });
  await openMap(page, "/?layers=data_zones&z=10&c=-3.2,55.95");
  await waitForMap(page);
  await openLayers(page);
  await ensureLayersGroupOpen(page, "places");
  await expect(page.getByTestId("layer-asof-data_zones")).toHaveCount(0);
  assertConsoleClean(gate);
});
