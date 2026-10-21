import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";
import { execFileSync } from "child_process";
import path from "path";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  ensureMapZoomAtLeast,
  HIDDEN_LAYER_IDS,
  LIVE_LAYER_IDS,
  openLayers,
  openMap,
  openPlaceViaCoords,
  PLACE_FIXTURE,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();


/**
 * MAP-CARDS ADDENDUM A1–A6.
 */

const registryScript = path.join(
  process.cwd(),
  "scripts/test-map-layer-registry.mjs",
);

test.describe("MAP-CARDS addendum A1 registry unit", () => {
  test("scripts/test-map-layer-registry.mjs stays green", () => {
    const out = execFileSync(
      process.execPath,
      ["--experimental-strip-types", registryScript],
      { encoding: "utf8" },
    );
    expect(out).toMatch(/test-map-layer-registry: ok/);
  });
});

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`MAP-CARDS addendum (${viewport.width})`, () => {
    test.use({ viewport });

    test("A1 layers-panel lists registry live ids only", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await openLayers(page);

      // Expand every group so all switches exist in the DOM.
      for (const key of ["land", "resources", "nature", "places"]) {
        await ensureLayersGroupOpen(page, key);
      }

      for (const id of LIVE_LAYER_IDS) {
        await expect(page.getByTestId(`layer-toggle-${id}`)).toBeVisible();
      }
      // Removed / coming-later ids must not appear
      for (const id of [
        "1a",
        "2",
        "5",
        "6",
        "7",
        "10",
        "lca",
        "builtup_mask",
        "settlements",
        "localities",
        "boundaries",
        ...HIDDEN_LAYER_IDS,
      ]) {
        await expect(page.getByTestId(`layer-toggle-${id}`)).toHaveCount(0);
      }
      assertConsoleClean(gate);
    });

    test("A2 unknown URL param foo=bar preserved after panel + pan", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await page.goto("/?foo=bar&place=S01014567&lat=55.8609&lng=-4.2514");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await expect(page.getByTestId("place-card")).toBeVisible({
        timeout: 45_000,
      });
      expect(page.url()).toMatch(/foo=bar/);

      await openLayers(page);
      expect(page.url()).toMatch(/foo=bar/);

      await waitForMap(page);
      await page.evaluate(() => {
        const map = (
          window as unknown as {
            __map?: { panBy(offset: [number, number]): void };
          }
        ).__map;
        map?.panBy([40, 20]);
      });
      await page.waitForTimeout(500);
      expect(page.url()).toMatch(/foo=bar/);
      assertConsoleClean(gate);
    });

    test("A3 maxZoom 20 (GRID-BASE-1 supersedes addendum 19)", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForMap(page);
      const maxZoom = await page.evaluate(() => {
        const map = (
          window as unknown as {
            __map?: { getMaxZoom(): number; zoomTo(z: number): void; getZoom(): number };
          }
        ).__map;
        if (!map) throw new Error("no map");
        map.zoomTo(30);
        return { max: map.getMaxZoom(), zoom: map.getZoom() };
      });
      expect(maxZoom.max).toBe(20);
      expect(maxZoom.zoom).toBeLessThanOrEqual(20);
      assertConsoleClean(gate);
    });

    test("A4 row6 slot hidden empty; A5 registry legend on toggle 1", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openPlaceViaCoords(page);

      const row6 = page.getByTestId("place-card-row6-slot");
      await expect(row6).toBeAttached();
      await expect(row6).toBeHidden();
      await expect(row6).toBeEmpty();

      // Check 8 counts still hold with row6 present but hidden
      const body = await page.locator("body").innerText();
      expect(body).not.toMatch(/coming soon/i);

      await ensureMapZoomAtLeast(page, 11);
      await openLayers(page);
      await ensureLayersGroupOpen(page, "land");
      await page.getByTestId("layer-toggle-1").click();
      const legend = page.getByTestId("layer-inline-legend-1");
      await expect(legend).toContainText("Lower");
      await expect(legend).toContainText("Higher");
      await expect(legend).toContainText("Striped = less sure");
      await expect(legend).toContainText("No figure here");
      await expect(page.getByTestId("layer-source-caption-1")).toContainText(
        /Scot-LAND model/,
      );
      assertConsoleClean(gate);
    });

    test("A6 identify response includes dz_code and source_crs", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      let sawDz = false;
      let sawCrs = false;
      await stubMapCardsBackend(page, {
        place: {
          ...PLACE_FIXTURE,
          dz_code: "S01014567",
          source_crs: "EPSG:27700",
        },
      });
      await page.route("**/platform/place**", async (route) => {
        const json = {
          ...PLACE_FIXTURE,
          dz_code: "S01014567",
          source_crs: "EPSG:27700",
        };
        sawDz = json.dz_code === "S01014567";
        sawCrs = json.source_crs === "EPSG:27700";
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(json),
        });
      });

      const responsePromise = page.waitForResponse(
        (r) => /platform\/place/i.test(r.url()) && r.ok(),
      );
      await openPlaceViaCoords(page);
      const res = await responsePromise;
      const body = (await res.json()) as {
        dz_code?: string;
        source_crs?: string;
      };
      expect(body.dz_code).toBe("S01014567");
      expect(body.source_crs).toBe("EPSG:27700");
      expect(sawDz && sawCrs).toBe(true);
      await expect(page.getByTestId("place-card")).toBeVisible();
      // Zone codes must not appear as visitor text
      await expect(page.getByTestId("place-card")).not.toContainText("S01014567");
      assertConsoleClean(gate);
    });
  });
}
