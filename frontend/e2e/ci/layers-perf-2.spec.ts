import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";
import { assertConsoleClean, attachConsoleGate, ensureLayersGroupOpen, openLayers, openMap, registerOpenFreeMapFontStub, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

/**
 * LAYERS-PERF-2 — at z6 the map shows real outlines or the zoom hint.
 * A 5-point bounding box is never drawn.
 */

const IRREGULAR = {
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

type Mode = "outline" | "hidden";

function bodyFor(mode: Mode): string {
  if (mode === "hidden") {
    return JSON.stringify({
      type: "FeatureCollection",
      features: [],
      meta: { hidden_below_zoom: true },
    });
  }
  return JSON.stringify({ type: "FeatureCollection", features: [IRREGULAR] });
}

async function rectangleCount(page: Page): Promise<number> {
  return page.evaluate(() => {
    const map = (
      window as unknown as {
        __map?: {
          getSource(id: string): { _data?: GeoJSON.FeatureCollection } | undefined;
          queryRenderedFeatures(opts: { layers: string[] }): Array<{
            geometry?: GeoJSON.Geometry;
          }>;
          getLayer(id: string): unknown;
        };
      }
    ).__map;
    if (!map) return 0;

    const isRect = (geometry: GeoJSON.Geometry | undefined): boolean => {
      if (!geometry || geometry.type !== "Polygon") return false;
      const ring = geometry.coordinates[0];
      if (!ring || ring.length !== 5) return false;
      const corners = ring.slice(0, 4);
      const xs = corners.map((point) => point[0]);
      const ys = corners.map((point) => point[1]);
      return new Set(xs).size === 2 && new Set(ys).size === 2;
    };

    const source = map.getSource("designations-overlay");
    const fromSource = (source?._data?.features ?? []).filter((feature) =>
      isRect(feature.geometry),
    ).length;
    const layers = ["designations-fill", "designations-line"].filter((id) =>
      map.getLayer(id),
    );
    const fromPaint = layers.length
      ? map.queryRenderedFeatures({ layers }).filter((feature) => isRect(feature.geometry))
          .length
      : 0;
    return fromSource + fromPaint;
  });
}

async function renderedCount(page: Page): Promise<number> {
  return page.evaluate(() => {
    const map = (
      window as unknown as {
        __map?: {
          getLayer(id: string): unknown;
          queryRenderedFeatures(opts: { layers: string[] }): unknown[];
        };
      }
    ).__map;
    if (!map?.getLayer("designations-fill")) return 0;
    return map.queryRenderedFeatures({ layers: ["designations-fill"] }).length;
  });
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

test.describe("LAYERS-PERF-2", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("z6 shows outlines or the zoom hint and never a rectangle", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    let mode: Mode = "outline";
    await stubMapCardsBackend(page);
    await page.route("**/layers/open/naturescot-designations**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: bodyFor(mode),
      });
    });
    await page.route("**/layers/open/sssi**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: bodyFor(mode),
      });
    });

    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "limits");
    await jump(page, 6);
    const toggle = page.getByTestId("layer-toggle-designations");
    await toggle.click();

    const hint = page.getByTestId("protected-sites-zoom-hint");
    await expect
      .poll(async () => {
        const outlines = await renderedCount(page);
        const hintVisible = await hint.isVisible().catch(() => false);
        return outlines > 0 || hintVisible;
      }, { timeout: 20_000 })
      .toBe(true);
    await expect.poll(async () => renderedCount(page), { timeout: 20_000 }).toBeGreaterThan(0);
    await expect(hint).toBeHidden();
    expect(await rectangleCount(page)).toBe(0);

    mode = "hidden";
    await jump(page, 6.4);
    await expect(hint).toHaveText("Zoom in to see protected sites", { timeout: 20_000 });
    await expect.poll(async () => renderedCount(page), { timeout: 20_000 }).toBe(0);
    expect(await rectangleCount(page)).toBe(0);
    assertConsoleClean(gate);
  });
});
