/**
 * MAP-VISION-1 slice 1a (MV-04, MV-05, MV-06, MV-09, MV-11, MV-20):
 * Unit + negative tests for mapVisionTokens.ts and Playwright e2e verification
 * on desktop (1280x800) and mobile (390x844).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, routeManifestOverride } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  registerOpenFreeMapFontStub,
} from "./_mapCardsHelpers";
import {
  MV_CAT_TOKENS,
  MV_DZ_FILL_OPACITY_BASE,
  MV_DZ_FILL_OPACITY_DIMMED,
  MV_HALO,
  MV_INK,
  MV_SEQ_TOKENS,
  MV_SUPPORTING_STROKE_STYLES,
  assertSupportingLayerNotFill,
  buildDzFillOpacityExpression,
  buildSelectedZonePaint,
  hasSupportingOverlayActive,
  prefersReducedMotion,
  resolveCatToken,
  resolveSeqToken,
  resolveSupportingStrokeStyle,
  selectCameraMotionMethod,
} from "../../lib/mapVisionTokens";
import type { Page } from "@playwright/test";

registerOpenFreeMapFontStub();

const DZ_MVT = readFileSync(
  join(__dirname, "..", "fixtures", "arch2b", "dz2022.mvt"),
);
const VERSION = "2026-10-22.d28ecc72";

const MANIFEST_WITH_DZ = {
  schema: 1,
  tilesets: {
    dz2022: {
      version: VERSION,
      dataset_version: "dz2022@2026-10-22-d28ecc72",
      as_of: "2026-10-22",
      file: `dz2022.${VERSION}.pmtiles`,
      bytes: 1024,
      sha256: "d28ecc72".repeat(8),
      minzoom: 0,
      maxzoom: 14,
      layer: "dz2022",
      source_layer: "dz2022",
      geometry: "polygon",
      measure: "pop_density",
      title: "Data Zones 2022",
      attribution:
        "Copyright Scottish Government, contains Ordnance Survey data © Crown copyright and database right 2026.",
      tiles: `/v1/tiles/dz2022/${VERSION}/{z}/{x}/{y}.mvt`,
      style: {
        fill: {
          "fill-color": "#6baed6",
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
          "line-opacity": 0.6,
        },
      },
      legend: [{ label: "100", color: "#6baed6" }],
    },
  },
};

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

function placeFixture() {
  return {
    contract: "place_card_v1",
    lat: 55.8609,
    lng: -4.2514,
    place_label: "Glasgow City Centre",
    council_name: "Glasgow City",
    dwellings: 410,
    data_zone: {
      status: "ok",
      code: "S01013482",
      name: "City Centre South",
      vintage: 2022,
    },
    intermediate_zone: { status: "ok", name: "City Centre", code: "S02002645" },
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
}

async function stubMapVisionBackend(page: Page) {
  await page.route("**/backend/v1/tiles/**/*.mvt", async (route) => {
    await route.fulfill({
      status: 200,
      headers: {
        "Content-Type": "application/vnd.mapbox-vector-tile",
        "Cache-Control": "public, max-age=31536000, immutable",
      },
      body: DZ_MVT,
    });
  });
  await page.route(
    "**/backend/v1/tiles/**/values/pop_density.json",
    async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          layer: "dz2022",
          version: VERSION,
          measure: "pop_density",
          values: { S01013482: 500 },
        }),
      });
    },
  );
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/v1\/tiles\//.test(url)) {
      await route.fallback();
      return;
    }
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(placeFixture()),
      });
      return;
    }
    if (/data-zones\/at/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: "S01013482",
          name: "City Centre South",
          vintage: 2022,
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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

test("N-MV1 resolveSeqToken, resolveCatToken, resolveSupportingStrokeStyle positive & negative checks", () => {
  expect(resolveSeqToken("seq-0")).toBe("#BDBDBD");
  expect(resolveSeqToken("seq-1")).toBe("#FDE725");
  expect(resolveSeqToken("seq-6")).toBe("#440154");
  expect(Object.keys(MV_SEQ_TOKENS)).toHaveLength(7);

  expect(resolveCatToken("cat-1")).toBe("#E69F00");
  expect(resolveCatToken("cat-6")).toBe("#CC79A7");
  expect(Object.keys(MV_CAT_TOKENS)).toHaveLength(6);

  const oilStyle = resolveSupportingStrokeStyle("oil-fields");
  expect(oilStyle).toEqual({
    token: "cat-5",
    color: "#D55E00",
    dasharray: [4, 2],
    lineWidth: 1.8,
  });
  expect(Object.keys(MV_SUPPORTING_STROKE_STYLES).length).toBeGreaterThanOrEqual(8);

  for (const bad of [undefined, null, "", "seq-7", 1, 1.5, true, false, [], {}]) {
    expect(() => resolveSeqToken(bad)).toThrow(
      /^MAP-VISION: unknown seq token /,
    );
    expect(() => resolveCatToken(bad)).toThrow(
      /^MAP-VISION: unknown cat token /,
    );
    expect(() => resolveSupportingStrokeStyle(bad)).toThrow(
      /^MAP-VISION: unknown supporting layer /,
    );
  }
});

test("N-MV2 assertSupportingLayerNotFill positive & negative checks", () => {
  expect(() => assertSupportingLayerNotFill("oil-fields", "outline")).not.toThrow();
  expect(() => assertSupportingLayerNotFill("pipelines", "line")).not.toThrow();
  expect(() => assertSupportingLayerNotFill("platforms", "circle")).not.toThrow();

  for (const badId of [undefined, null, "", "   ", 1, true, false, [], {}]) {
    expect(() => assertSupportingLayerNotFill(badId, "line")).toThrow(
      /^MAP-VISION: layerId must be a non-empty string$/,
    );
  }
  for (const badKind of [undefined, null, "", "fill", "polygon", 1, true, false, [], {}]) {
    expect(() => assertSupportingLayerNotFill("oil-fields", badKind)).toThrow(
      /^MAP-VISION: supporting layer 'oil-fields' must not use kind '/,
    );
  }
});

test("N-MV3 buildDzFillOpacityExpression & hasSupportingOverlayActive positive & negative checks", () => {
  const baseExpr = buildDzFillOpacityExpression(false);
  expect(baseExpr).toEqual([
    "interpolate",
    ["linear"],
    ["zoom"],
    4.5,
    0,
    5,
    MV_DZ_FILL_OPACITY_BASE,
    14,
    MV_DZ_FILL_OPACITY_BASE,
    15,
    0.4,
  ]);
  const dimExpr = buildDzFillOpacityExpression(true);
  expect(dimExpr).toEqual([
    "interpolate",
    ["linear"],
    ["zoom"],
    4.5,
    0,
    5,
    MV_DZ_FILL_OPACITY_DIMMED,
    14,
    MV_DZ_FILL_OPACITY_DIMMED,
    15,
    0.24,
  ]);
  expect(MV_DZ_FILL_OPACITY_DIMMED).toBeCloseTo(MV_DZ_FILL_OPACITY_BASE * 0.6, 5);

  for (const bad of [undefined, null, "", 0, 1, 1.5, "true", [], {}]) {
    expect(() => buildDzFillOpacityExpression(bad)).toThrow(
      /^MAP-VISION: supportingActive must be a boolean$/,
    );
  }

  expect(hasSupportingOverlayActive([])).toBe(false);
  expect(hasSupportingOverlayActive(["councils", "data_zones"])).toBe(false);
  expect(hasSupportingOverlayActive(["councils", "9"])).toBe(true);
  expect(hasSupportingOverlayActive(["designations"])).toBe(true);

  for (const bad of [
    undefined,
    null,
    "",
    123,
    true,
    false,
    {},
    [""],
    ["   "],
    ["councils", 123],
    ["councils", null],
  ]) {
    expect(() => hasSupportingOverlayActive(bad)).toThrow(
      /^MAP-VISION: activeLayerIds must be an array of strings$/,
    );
  }
});

test("N-MV4 buildSelectedZonePaint positive & negative checks", () => {
  const none = buildSelectedZonePaint(null, null);
  expect(none.outlinePaint).toEqual({
    "line-color": MV_INK,
    "line-width": 3,
    "line-opacity": 0,
  });
  expect(none.haloPaint).toEqual({
    "line-color": MV_HALO,
    "line-width": 5,
    "line-opacity": 0,
  });
  expect(none.hoverPaint).toEqual({
    "line-color": MV_INK,
    "line-width": 1.5,
    "line-opacity": 0,
  });

  const active = buildSelectedZonePaint("S01013482", "S01013483");
  expect(active.outlinePaint["line-width"]).toBe(3);
  expect(active.outlinePaint["line-color"]).toBe("#1A1A1A");
  expect(active.outlinePaint["line-opacity"]).toBe(1);
  expect(active.haloPaint["line-color"]).toBe("#FFFFFF");
  expect(active.haloPaint["line-opacity"]).toBe(0.95);
  expect(active.hoverPaint["line-width"]).toBe(1.5);
  expect(active.hoverPaint["line-opacity"]).toBe(0.85);

  // Hovering the already-selected zone suppresses duplicate hover stroke
  const sameHover = buildSelectedZonePaint("S01013482", "S01013482");
  expect(sameHover.hoverPaint["line-opacity"]).toBe(0);

  for (const bad of [undefined, "", "   ", 123, 1.5, true, false, [], {}]) {
    expect(() => buildSelectedZonePaint(bad, null)).toThrow(
      /^MAP-VISION: selectedCode must be a non-empty string or null$/,
    );
    expect(() => buildSelectedZonePaint(null, bad)).toThrow(
      /^MAP-VISION: hoveredCode must be a non-empty string or null$/,
    );
  }
});

test("N-MV5 prefersReducedMotion & selectCameraMotionMethod positive & negative checks", () => {
  expect(prefersReducedMotion(null)).toBe(false);
  expect(prefersReducedMotion({})).toBe(false);
  expect(
    prefersReducedMotion({
      matchMedia: (q: string) => ({
        matches: q === "(prefers-reduced-motion: reduce)",
      }),
    }),
  ).toBe(true);
  expect(
    prefersReducedMotion({
      matchMedia: () => ({ matches: false }),
    }),
  ).toBe(false);

  for (const badWin of ["win", 123, 1.5, true, false]) {
    expect(() => prefersReducedMotion(badWin)).toThrow(
      /^MAP-VISION: win must be a Window object or null$/,
    );
  }

  expect(selectCameraMotionMethod(true)).toBe("jumpTo");
  expect(selectCameraMotionMethod(false)).toBe("flyTo");
  for (const bad of [undefined, null, "", 0, 1, "true", [], {}]) {
    expect(() => selectCameraMotionMethod(bad)).toThrow(
      /^MAP-VISION: reducedMotion must be a boolean$/,
    );
  }
});

for (const vp of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`E-MV1 MAP-VISION-1a @ ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: vp });

    test("MV-05 DZ fill dims when supporting layer is on; MV-06 selected zone 3px + halo; MV-20 reduced-motion jumpTo", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      await page.emulateMedia({ reducedMotion: "reduce" });
      const gate = attachConsoleGate(page);
      await stubMapVisionBackend(page);
      await routeManifestOverride(page, (route) =>
        route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(MANIFEST_WITH_DZ),
        }),
      );

      await page.goto("/?lat=55.860900&lng=-4.251400");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await expect(page.getByTestId("place-card")).toBeVisible({
        timeout: 45_000,
      });

      // Wait for tile-dz2022-selected-line and tile-dz2022-fill to be added from manifest
      await expect
        .poll(
          async () =>
            page.evaluate(() => {
              const m = (window as unknown as { __map?: { getLayer(id: string): unknown } }).__map;
              return Boolean(
                m?.getLayer("tile-dz2022-fill") &&
                  m?.getLayer("tile-dz2022-selected-line") &&
                  m?.getLayer("tile-dz2022-selected-halo") &&
                  m?.getLayer("tile-dz2022-hover-line"),
              );
            }),
          { timeout: 20_000 },
        )
        .toBe(true);

      // Verify MV-06 selected zone outline (3 px #1A1A1A + 5 px #FFFFFF halo)
      const selectedPaint = await page.evaluate(() => {
        const m = (
          window as unknown as {
            __map: {
              getPaintProperty(layer: string, prop: string): unknown;
              getFilter(layer: string): unknown;
            };
          }
        ).__map;
        return {
          lineWidth: m.getPaintProperty("tile-dz2022-selected-line", "line-width"),
          lineColor: m.getPaintProperty("tile-dz2022-selected-line", "line-color"),
          lineOpacity: m.getPaintProperty("tile-dz2022-selected-line", "line-opacity"),
          haloWidth: m.getPaintProperty("tile-dz2022-selected-halo", "line-width"),
          haloOpacity: m.getPaintProperty("tile-dz2022-selected-halo", "line-opacity"),
          filter: m.getFilter("tile-dz2022-selected-line"),
        };
      });
      expect(selectedPaint.lineWidth).toBe(3);
      expect(selectedPaint.lineOpacity).toBe(1);
      expect(selectedPaint.haloWidth).toBe(5);
      expect(selectedPaint.haloOpacity).toBe(0.95);
      expect(JSON.stringify(selectedPaint.filter)).toContain("S01013482");

      // Verify MV-05 base fill-opacity expression before any supporting layer is turned on
      const baseOpacity = await page.evaluate(() => {
        const m = (
          window as unknown as {
            __map: { getPaintProperty(layer: string, prop: string): unknown };
          }
        ).__map;
        return m.getPaintProperty("tile-dz2022-fill", "fill-opacity");
      });
      expect(JSON.stringify(baseOpacity)).toContain("0.55");

      // Open Layers and toggle on a supporting layer ("9" Oil and gas in resources group)
      await openLayers(page);
      await ensureLayersGroupOpen(page, "resources");
      await page.getByTestId("layer-toggle-9").click();

      // Verify MV-05 dimmed fill-opacity expression (0.33 = 60% of 0.55)
      await expect
        .poll(
          async () =>
            page.evaluate(() => {
              const m = (
                window as unknown as {
                  __map: { getPaintProperty(layer: string, prop: string): unknown };
                }
              ).__map;
              return JSON.stringify(
                m.getPaintProperty("tile-dz2022-fill", "fill-opacity"),
              );
            }),
          { timeout: 10_000 },
        )
        .toContain("0.33");

      assertConsoleClean(gate);
    });
  });
}
