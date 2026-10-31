
import { test, expect } from "./_fixtures";
import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean, ensureLayersGroupOpen, ensureMapZoomAtLeast, openLayers, openMap, stubMapCardsBackend } from "./_mapCardsHelpers";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * LAYERS-ADD-1 — registry rows default OFF; LDP/HLS on roadmap; no £; banned names.
 * Accordion groups must be expanded before toggles exist in the DOM (MAP-CARDS).
 * Improvement Service rows are omitted when the extract is absent.
 */

const NEW_OFF_BY_GROUP: Record<string, readonly string[]> = {
  land: ["access_services"],
  places: [],
};

/** LAYERS-FIX-1: empty stubs are not switches. */
const HIDDEN_STUBS = [
  "flood",
  "deprivation",
  "conservation",
  "listed",
  "stops",
] as const;

const ABSENT_IS = ["contaminated_land", "green_belt", "school_catchments"] as const;

/** Visible new rows, and the map layer each toggle must draw. */
const DRAWN_ROWS = [
  { toggle: "access_services", layer: "access_services-add-fill" },
] as const;

const PRESENT_IS_ROWS = [
  { toggle: "contaminated_land", layer: "contaminated_land-add-fill" },
  { toggle: "green_belt", layer: "green_belt-add-fill" },
  { toggle: "school_catchments", layer: "school_catchments-add-fill" },
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
          properties: {
            stop_type: "bus",
            category: "A",
            name: "Town centre",
            q: 1,
            topic: "access",
            class: "1",
          },
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
        {
          type: "Feature",
          properties: { stop_type: "bus", category: "A" },
          geometry: {
            type: "Point",
            coordinates: [(west + east) / 2, (south + north) / 2],
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

for (const width of [1280, 390] as const) {
  test.describe(`LAYERS-ADD-1 @ ${width}`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 900 } });

    test("new layers default off; gated ids absent; roadmap waiting rows", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await openLayers(page);

      for (const key of ["land", "places"] as const) {
        await ensureLayersGroupOpen(page, key);
        for (const id of NEW_OFF_BY_GROUP[key]!) {
          const toggle = page.getByTestId(`layer-toggle-${id}`);
          await expect(toggle).toBeVisible();
          await expect(toggle).toHaveAttribute("aria-checked", "false");
        }
      }

      for (const id of HIDDEN_STUBS) {
        await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
      }

      for (const id of ABSENT_IS) {
        await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
      }

      await expect(page.getByTestId("layer-toggle-hla")).toHaveCount(0);
      await expect(page.getByTestId("layer-toggle-ldp")).toHaveCount(0);
      const panel = page.getByTestId("layers-panel");
      await expect(panel).not.toContainText(/£/);
      await expect(panel).not.toContainText(/\bSIMD\b/);
      await expect(panel).not.toContainText(/\bNaPTAN\b/);

      await page.goto("/roadmap#map-layers");
      await expect(page.getByTestId("roadmap-waiting-ldp")).toBeVisible();
      await expect(page.getByTestId("roadmap-waiting-hls")).toBeVisible();
      await expect(page.getByTestId("roadmap-waiting-status-ldp")).toContainText(
        "Waiting for permission to use the data",
      );
      await expect(page.locator("main")).not.toContainText(/£/);
      await expect(page.locator("main")).not.toContainText(/sepa_frm_maps/i);

      assertConsoleClean(gate);
    });
  });
}

test.describe("LAYERS-ADD-1 paint", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("toggling each new row draws; absent IS layers stay off the list", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await stubViewportShapes(page);
    await openMap(page);
    await expect
      .poll(async () => page.locator("#map").getAttribute("data-framed"))
      .toBe("1");
    await ensureMapZoomAtLeast(page, 15);
    await openLayers(page);

    for (const id of ABSENT_IS) {
      await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
    }
    for (const id of HIDDEN_STUBS) {
      await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
    }

    for (const row of DRAWN_ROWS) {
      const group = row.toggle === "access_services" ? "land" : "places";
      await ensureLayersGroupOpen(page, group);
      await page.getByTestId(`layer-toggle-${row.toggle}`).click();
      await expectLayerDrawn(page, row.layer);
    }

    assertConsoleClean(gate);
  });

  test("present Improvement Service rows draw", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page, {
      spatialHubLayerIds: ["vdl", ...PRESENT_IS_ROWS.map((row) => row.toggle)],
    });
    await stubViewportShapes(page);
    await openMap(page);
    await expect
      .poll(async () => page.locator("#map").getAttribute("data-framed"))
      .toBe("1");
    await ensureMapZoomAtLeast(page, 15);
    await openLayers(page);

    for (const row of PRESENT_IS_ROWS) {
      const group =
        row.toggle === "contaminated_land" ? "limits" : "places";
      await ensureLayersGroupOpen(page, group);
      const toggle = page.getByTestId(`layer-toggle-${row.toggle}`);
      await expect(toggle).toBeVisible();
      await toggle.click();
      await expectLayerDrawn(page, row.layer);
    }

    assertConsoleClean(gate);
  });
});
