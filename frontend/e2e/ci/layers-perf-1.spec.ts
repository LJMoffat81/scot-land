import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  openMap,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();


/**
 * LAYERS-PERF-1 — protected sites draw inside the payload budget, and
 * Oil and gas is fetched once per session.
 */

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
    let oilHits = 0;
    await stubMapCardsBackend(page);
    await page.route("**/layers/context/oil-fields**", async (route) => {
      oilHits += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: featureCollection([NORTH_SEA_POLYGON]),
      });
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
        .poll(async () => renderedCount(page, ["oil-fields-fill"]), {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-checked", "false");
      await toggle.click();
      await expect
        .poll(async () => renderedCount(page, ["oil-fields-fill"]), {
          timeout: 20_000,
        })
        .toBeGreaterThan(0);
    }
    expect(oilHits).toBe(1);
    assertConsoleClean(gate);
  });
});
