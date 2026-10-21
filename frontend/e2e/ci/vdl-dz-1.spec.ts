
import { test, expect } from "./_fixtures";
import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean, ensureMapZoomAtLeast, openMap, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

/**
 * VDL-DZ-1 — a Data Zone place with vacant land must not show a site code.
 * The route stub still carries a site code. The card must not render it.
 * VDL-DZ-2 removes the site polygon, so the map must not draw vdl-fill.
 */

const SITE_CODE = "GLA-SITE-CODE-LEAK";

const VDL_LEAK = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-8.4, 54.6],
            [-0.6, 54.6],
            [-0.6, 60.8],
            [-8.4, 60.8],
            [-8.4, 54.6],
          ],
        ],
      },
      properties: {
        name: "Former works",
        site_code: SITE_CODE,
        site_type: "Derelict",
        size_ha: 1.25,
        address: "1 High Street",
        source: "Scottish Vacant and Derelict Land Survey.",
      },
    },
  ],
};

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`VDL data zone place card (${viewport.width})`, () => {
    test.use({ viewport });

    test("place card shows no site code", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await page.route("**/layers/open/vdl**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(VDL_LEAK),
        });
      });

      await openMap(page, "/?layers=vdl&z=12&c=-4.25,55.86");
      await waitForMap(page);
      await ensureMapZoomAtLeast(page, 8);

      await expect
        .poll(async () =>
          page.evaluate(() => {
            const map = (
              window as unknown as {
                __map?: {
                  getLayer(id: string): unknown;
                  getSource(id: string): unknown;
                };
              }
            ).__map;
            if (!map) return "missing-map";
            if (map.getSource("vdl-overlay") || map.getLayer("vdl-fill") || map.getLayer("vdl-line")) {
              return "overlay-present";
            }
            return "clear";
          }),
        )
        .toBe("clear");

      const canvas = page.locator(".maplibregl-canvas");
      const box = await canvas.boundingBox();
      if (!box) throw new Error("map canvas missing");
      await canvas.click({
        position: { x: box.width / 2, y: box.height / 2 },
      });

      const card = page.getByTestId("place-card");
      await expect(card).toBeVisible({ timeout: 20_000 });
      await expect(card).not.toContainText(SITE_CODE);
      await expect(card).not.toContainText("Site code");

      await expect(page.locator(".maplibregl-popup")).toHaveCount(0);
      await expect(page.locator("body")).not.toContainText(SITE_CODE);
      await expect(page.locator("body")).not.toContainText("1 High Street");
      await expect(page.locator("body")).not.toContainText("Former works");

      assertConsoleClean(gate);
    });
  });
}
