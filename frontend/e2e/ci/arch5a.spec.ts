/**
 * ARCH-5a — registry legends/credits negatives (N5a-1..3) and oil e2e (E5a-1).
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
  readCreditShortNames,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import {
  buildInlineLegendFromRegistry,
  getMapLayer,
  manifestLegendsForDrawerLayer,
} from "../../lib/mapLayerRegistry";
import { asOfMapForDrawerLayers } from "../../lib/tileAsOf";
import {
  buildMapAttributionPieces,
  formatAttributionLine,
  resolveTileCredit,
} from "../../lib/mapAttributionLine";
import type { Page } from "@playwright/test";

registerOpenFreeMapFontStub();

const OIL_MVT = readFileSync(
  join(process.cwd(), "e2e", "fixtures", "arch2b", "oil-fields.mvt"),
);

async function stubOilTiles(page: Page) {
  await page.route("**/backend/v1/tiles/**/*.mvt", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: OIL_MVT,
    });
  });
}

test("N5a-1 manifestLegendsForDrawerLayer + manifestClasses", () => {
  for (const drawerId of [
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
      manifestLegendsForDrawerLayer(drawerId as never),
    ).toThrowError(/^REGISTRY-LEGEND: drawerId must be a non-empty string$/);
  }

  for (const badMap of ["str", 123, 1.5, true, false, []]) {
    expect(() =>
      manifestLegendsForDrawerLayer("9", badMap),
    ).toThrowError(/^REGISTRY-LEGEND: 9: tileLegends must be an object$/);
  }

  for (const badList of ["str", 123, 1.5, true, false, {}]) {
    expect(() =>
      manifestLegendsForDrawerLayer("9", { "oil-fields": badList }),
    ).toThrowError(
      /^REGISTRY-LEGEND: 9: tileset 'oil-fields' legend must be an array$/,
    );
  }

  for (const badItem of [
    null,
    undefined,
    "str",
    123,
    1.5,
    true,
    false,
    [],
  ]) {
    expect(() =>
      manifestLegendsForDrawerLayer("9", { "oil-fields": [badItem] }),
    ).toThrowError(
      /^REGISTRY-LEGEND: 9: tileset 'oil-fields' legend item must be an object$/,
    );
  }

  for (const badLabel of [
    undefined,
    null,
    "",
    "  ",
    123,
    1.5,
    true,
    false,
    [],
    {},
  ]) {
    expect(() =>
      manifestLegendsForDrawerLayer("9", {
        "oil-fields": [{ label: badLabel, color: "#abcdef" }],
      }),
    ).toThrowError(
      /^REGISTRY-LEGEND: 9: tileset 'oil-fields' legend item label must be a non-empty string$/,
    );
  }

  for (const badColor of [
    undefined,
    null,
    "",
    "red",
    "#12345",
    "#1234567",
    "#zzzzzz",
    123,
    1.5,
    true,
    false,
  ]) {
    expect(() =>
      manifestLegendsForDrawerLayer("9", {
        "oil-fields": [{ label: "ok", color: badColor }],
      }),
    ).toThrowError(
      /^REGISTRY-LEGEND: 9: tileset 'oil-fields' legend item color must be #RRGGBB$/,
    );
  }

  const oilEntry = getMapLayer("9");
  expect(oilEntry).toBeTruthy();
  for (const badMc of ["str", 123, 1.5, true, false, {}]) {
    expect(() =>
      buildInlineLegendFromRegistry(oilEntry!, {
        manifestClasses: badMc as never,
      }),
    ).toThrowError(/^REGISTRY-LEGEND: 9: manifestClasses must be an array$/);
  }

  expect(manifestLegendsForDrawerLayer("9", undefined)).toBeNull();
  expect(manifestLegendsForDrawerLayer("9", null)).toBeNull();
  expect(manifestLegendsForDrawerLayer("unknown", {})).toBeNull();
});

test("N5a-2 asOfMapForDrawerLayers", () => {
  for (const bad of ["str", 123, 1.5, true, false, []]) {
    expect(() => asOfMapForDrawerLayers(bad)).toThrowError(
      /^REGISTRY-ASOF: tilesets must be an object$/,
    );
    expect(() => asOfMapForDrawerLayers({}, bad as never)).toThrowError(
      /^REGISTRY-ASOF: mapping must be an object$/,
    );
  }

  for (const badKeys of [
    null,
    "str",
    123,
    1.5,
    true,
    false,
    {},
    [""],
    [123],
  ]) {
    expect(() =>
      asOfMapForDrawerLayers({}, { councils: badKeys as never }),
    ).toThrowError(/^REGISTRY-ASOF: councils: keys must be an array of strings$/);
  }

  for (const badEntry of ["str", 123, 1.5, true, false, []]) {
    expect(() =>
      asOfMapForDrawerLayers({ councils: badEntry }),
    ).toThrowError(
      /^REGISTRY-ASOF: councils: tileset 'councils' must be an object$/,
    );
  }

  expect(asOfMapForDrawerLayers(undefined)).toEqual({});
  expect(asOfMapForDrawerLayers(null)).toEqual({});
  expect(
    asOfMapForDrawerLayers({
      "oil-fields": { version: "2026-10-15.abcdef12" },
    }),
  ).toEqual({ "9": "15 Oct 2026" });
});

test("N5a-3 resolveTileCredit + attribution entry points", () => {
  for (const badKey of ["", "  ", undefined, null, 123, 1.5, true, false]) {
    expect(() =>
      resolveTileCredit(badKey as never, "fb", {}),
    ).toThrowError(/^REGISTRY-CREDIT: key must be a non-empty string$/);
  }

  for (const badMap of ["str", 123, 1.5, true, false, []]) {
    expect(() =>
      resolveTileCredit("dz2022", "fb", badMap),
    ).toThrowError(/^REGISTRY-CREDIT: tileCredits must be an object$/);
    expect(() =>
      buildMapAttributionPieces([], badMap as never),
    ).toThrowError(/^REGISTRY-CREDIT: tileCredits must be an object$/);
    expect(() =>
      formatAttributionLine([], badMap as never),
    ).toThrowError(/^REGISTRY-CREDIT: tileCredits must be an object$/);
  }

  for (const badVal of ["", "   ", 123, 1.5, true, false, [], {}]) {
    expect(() =>
      resolveTileCredit("dz2022", "fb", { dz2022: badVal as never }),
    ).toThrowError(
      /^REGISTRY-CREDIT: dz2022: credit must be a non-empty string$/,
    );
    expect(() =>
      buildMapAttributionPieces(["9"], {
        "oil-fields": badVal as never,
      }),
    ).toThrowError(
      /^REGISTRY-CREDIT: oil-fields: credit must be a non-empty string$/,
    );
  }
});

test("E5a-1 oil legend, as-of, and NSTA credit from manifest", async ({
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
          "oil-fields": {
            layer: "oil-fields",
            version: "2026-10-15.abcdef12",
            minzoom: 0,
            maxzoom: 14,
            geometry: "polygon",
            source_layer: "oil-fields",
            measure: null,
            attribution: "SYNTH NSTA MANIFEST CREDIT",
            style: {
              fill: { "fill-color": "#8a3b00", "fill-opacity": 0.28 },
              line: {
                "line-color": "#8a3b00",
                "line-width": 1.6,
                "line-opacity": 0.95,
              },
            },
            legend: [{ label: "SYNTH OIL FIELDS", color: "#8a3b00" }],
          },
          platforms: {
            layer: "platforms",
            version: "2026-10-15.abcdef12",
            minzoom: 0,
            maxzoom: 14,
            geometry: "point",
            source_layer: "platforms",
            measure: null,
            attribution: "SYNTH NSTA MANIFEST CREDIT",
            style: {
              circle: { "circle-color": "#8a3b00", "circle-radius": 4.5 },
            },
            legend: [{ label: "SYNTH PLATFORMS", color: "#8a3b00" }],
          },
          pipelines: {
            layer: "pipelines",
            version: "2026-10-15.abcdef12",
            minzoom: 0,
            maxzoom: 14,
            geometry: "line",
            source_layer: "pipelines",
            measure: null,
            attribution: "SYNTH NSTA MANIFEST CREDIT",
            style: {
              line: {
                "line-color": "#5c4a32",
                "line-width": 1.4,
                "line-opacity": 0.9,
              },
            },
            legend: [{ label: "SYNTH PIPELINES", color: "#5c4a32" }],
          },
        },
      }),
    });
  });
  await stubOilTiles(page);
  await openMap(page, "/?z=6&c=1.0,57.5");
  await waitForMap(page);
  await openLayers(page);
  await ensureLayersGroupOpen(page, "resources");
  await page.getByTestId("layer-toggle-9").click();

  const legend = page.getByTestId("layer-inline-legend-9");
  await expect(legend).toBeVisible();
  await expect(legend).toContainText("SYNTH OIL FIELDS");
  await expect(legend).toContainText("SYNTH PLATFORMS");
  await expect(legend).toContainText("SYNTH PIPELINES");
  await expect(page.getByTestId("layer-asof-9")).toHaveText(
    " · Data as of 15 Oct 2026",
  );
  expect(await page.getByTestId("map-credit-line").innerText()).not.toContain(
    "Oil and gas: NSTA",
  );
  expect(await readCreditShortNames(page)).toContain("Oil and gas: NSTA");
  await expect(page.getByTestId("map-attribution-line")).toContainText(
    "SYNTH NSTA MANIFEST CREDIT",
  );
  assertConsoleClean(gate);
});
