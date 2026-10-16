import { expect, test } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureMapZoomAtLeast,
  openMap,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";

/**
 * VDL-DZ-1 — a Data Zone place with vacant land must not show a site code.
 * The overlay stub still carries a site code (the leak on main). The card
 * and the map popup must not render it.
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
        .poll(
          async () =>
            page.evaluate(() => {
              const map = (
                window as unknown as {
                  __map?: {
                    getLayer(id: string): unknown;
                    queryRenderedFeatures(
                      point: { x: number; y: number },
                      opts: { layers: string[] },
                    ): unknown[];
                  };
                }
              ).__map;
              if (!map?.getLayer("vdl-fill")) return 0;
              const canvas = document.querySelector(".maplibregl-canvas");
              if (!(canvas instanceof HTMLCanvasElement)) return 0;
              const rect = canvas.getBoundingClientRect();
              return map.queryRenderedFeatures(
                { x: rect.width / 2, y: rect.height / 2 },
                { layers: ["vdl-fill"] },
              ).length;
            }),
          { timeout: 20_000 },
        )
        .toBeGreaterThan(0);

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

      const popup = page.locator(".maplibregl-popup");
      await expect(popup).toBeVisible({ timeout: 10_000 });
      await expect(popup).toContainText("Scottish Vacant and Derelict Land Survey");
      await expect(popup).not.toContainText(SITE_CODE);
      await expect(popup).not.toContainText("Site code");
      await expect(popup).not.toContainText("1 High Street");
      await expect(popup).not.toContainText("Former works");

      assertConsoleClean(gate);
    });
  });
}
