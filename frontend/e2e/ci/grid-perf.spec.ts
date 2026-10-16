import { expect, test, type Page, type Route, type CDPSession } from "@playwright/test";
import { ensureLayersGroupOpen } from "./_mapCardsHelpers";

/**
 * GRID-BASE-1 — G10–G12 performance budget (Moto G4, 4× CPU throttle).
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

type MapHandle = {
  jumpTo: (o: { zoom: number; center?: [number, number] }) => void;
  getZoom: () => number;
  getSource: (id: string) => { _data?: GeoJSON.FeatureCollection } | null;
  getBounds: () => {
    getWest: () => number;
    getEast: () => number;
    getSouth: () => number;
    getNorth: () => number;
  };
  on: (e: string, cb: () => void) => void;
  off: (e: string, cb: () => void) => void;
  fire: (e: string) => void;
};

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route: Route) => {
    const url = route.request().url();
    if (/\/health(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
}

async function waitMap(page: Page) {
  await page.waitForFunction(() => {
    const el = document.getElementById("map");
    return Boolean(
      el?.dataset?.zoom &&
        (window as unknown as { __SCOT_LAND_MAP__?: MapHandle })
          .__SCOT_LAND_MAP__,
    );
  });
}

test.describe("GRID-BASE-1 perf", () => {
  test("G10 G11 — ≤1500 vertices at z17; hover update ≤16ms", async ({
    page,
    browserName,
  }) => {
    test.skip(browserName !== "chromium", "CDP CPU throttle is Chromium-only");

    await stubMapBackend(page);
    await page.setViewportSize({ width: 390, height: 844 });

    const client: CDPSession = await page.context().newCDPSession(page);
    await client.send("Emulation.setCPUThrottlingRate", { rate: 4 });

    await page.goto("/?layers=grid3");
    await waitMap(page);
    await page.getByTestId("hud-layers-btn").click();
    await ensureLayersGroupOpen(page, "land");
    const toggle = page.getByTestId("layer-toggle-grid3");
    if ((await toggle.getAttribute("aria-checked")) !== "true") {
      await toggle.click();
    }
    await page.keyboard.press("Escape");

    // Warm the lazy chunk, then measure rebuild via exposed helper.
    await page.evaluate(() => {
      const map = (
        window as unknown as {
          __SCOT_LAND_MAP__: MapHandle & {
            fire: (e: string, data?: { originalEvent?: Event }) => void;
            stop: () => void;
          };
        }
      ).__SCOT_LAND_MAP__;
      const oe = new Event("mousedown");
      map.fire("dragstart", { originalEvent: oe });
      map.fire("zoomstart", { originalEvent: oe });
      map.stop();
      map.jumpTo({ zoom: 17.2, center: [-3.1883, 55.9533] });
    });
    await page.waitForFunction(
      () => {
        const helper = (
          window as unknown as { __SCOT_LAND_GRID3__?: unknown }
        ).__SCOT_LAND_GRID3__;
        const map = (window as unknown as { __SCOT_LAND_MAP__: MapHandle })
          .__SCOT_LAND_MAP__;
        const src = map.getSource("grid3-lines") as unknown as {
          _data?: GeoJSON.FeatureCollection;
          serialize?: () => { data?: GeoJSON.FeatureCollection };
        } | null;
        const n =
          src?._data?.features?.length ??
          src?.serialize?.().data?.features?.length ??
          0;
        return Boolean(helper) && n > 0;
      },
      null,
      { timeout: 20_000 },
    );

    const stats = await page.evaluate(async () => {
      const helper = (
        window as unknown as {
          __SCOT_LAND_GRID3__?: {
            buildGrid3Lines: (
              corners: Array<{ lng: number; lat: number }>,
            ) => { vertexCount: number };
            squareAtWgs: (
              lng: number,
              lat: number,
            ) => { easting: number; northing: number } | null;
            buildGrid3Highlight: (
              e: number,
              n: number,
            ) => GeoJSON.FeatureCollection;
          };
        }
      ).__SCOT_LAND_GRID3__;
      if (!helper) throw new Error("grid3 helper not exposed");
      const map = (window as unknown as { __SCOT_LAND_MAP__: MapHandle })
        .__SCOT_LAND_MAP__;
      const b = map.getBounds();
      const corners = [
        { lng: b.getWest(), lat: b.getSouth() },
        { lng: b.getEast(), lat: b.getSouth() },
        { lng: b.getEast(), lat: b.getNorth() },
        { lng: b.getWest(), lat: b.getNorth() },
      ];
      // Warm + take best of several runs (G10 under 4× throttle).
      helper.buildGrid3Lines(corners);
      let rebuildMs = Infinity;
      let vertexCount = 0;
      for (let i = 0; i < 5; i += 1) {
        const t0 = performance.now();
        const built = helper.buildGrid3Lines(corners);
        rebuildMs = Math.min(rebuildMs, performance.now() - t0);
        vertexCount = built.vertexCount;
      }

      map.jumpTo({ zoom: 18.2, center: [-3.1883, 55.9533] });
      helper.squareAtWgs(-3.1883, 55.9533);
      let hoverMs = Infinity;
      for (let i = 0; i < 5; i += 1) {
        const t1 = performance.now();
        const sq = helper.squareAtWgs(-3.1883, 55.9533);
        if (sq) helper.buildGrid3Highlight(sq.easting, sq.northing);
        hoverMs = Math.min(hoverMs, performance.now() - t1);
      }

      return { vertexCount, rebuildMs, hoverMs };
    });

    expect(stats.vertexCount).toBeLessThanOrEqual(1500);
    expect(stats.rebuildMs).toBeLessThanOrEqual(8);
    expect(stats.hoverMs).toBeLessThanOrEqual(16);

    await client.send("Emulation.setCPUThrottlingRate", { rate: 1 });
  });

  test("G12 — lazy grid chunk transfer ≤ 60KB", async ({ page }) => {
    await stubMapBackend(page);
    await page.setViewportSize({ width: 1280, height: 800 });

    await page.goto("/");
    await waitMap(page);

    // Toggle on + zoom to force lazy import
    await page.getByTestId("hud-layers-btn").click();
    await ensureLayersGroupOpen(page, "land");
    await page.getByTestId("layer-toggle-grid3").click();

    await page.evaluate(() => {
      (
        window as unknown as { __SCOT_LAND_MAP__: MapHandle }
      ).__SCOT_LAND_MAP__.jumpTo({ zoom: 17.2, center: [-3.1883, 55.9533] });
    });
    await page.waitForTimeout(1000);

    const transfer = await page.evaluate(() =>
      performance
        .getEntriesByType("resource")
        .filter((e) => /proj4|bng|grid3/i.test(e.name))
        .map((e) => {
          const r = e as PerformanceResourceTiming;
          return r.transferSize || r.encodedBodySize || 0;
        })
        .reduce((a, b) => a + b, 0),
    );
    expect(transfer).toBeLessThanOrEqual(60 * 1024);
  });
});
