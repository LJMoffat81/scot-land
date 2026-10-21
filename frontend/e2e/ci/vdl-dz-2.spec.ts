import { expect, test } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import { VDL_ZONE_TOTALS_ATTRIBUTION } from "../../lib/mapAttributionLine";

registerOpenFreeMapFontStub();


/**
 * VDL-DZ-2 — no site-polygon overlay and no site-type legend classes.
 * Attribution describes Data Zone totals. Fails on main before this change:
 * the map added source vdl-overlay and credited "Survey sites, not a title".
 */

const STALE = [
  "Survey sites, not a title",
  "Owner class is a survey field",
  "Survey polygons are indicative",
] as const;

const SITE_LEGEND = ["Vacant Land", "Vacant Land and Buildings", "Derelict"] as const;

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`VDL zone totals map (${viewport.width})`, () => {
    test.use({ viewport });

    test("no site overlay, site legend, or stale attribution", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page, "/?layers=vdl&z=12&c=-4.25,55.86");
      await waitForMap(page);

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
            if (
              map.getSource("vdl-overlay") ||
              map.getLayer("vdl-fill") ||
              map.getLayer("vdl-line")
            ) {
              return "overlay-present";
            }
            return "clear";
          }),
        )
        .toBe("clear");

      await expect(page.getByTestId("layer-inline-legend-vdl")).toHaveCount(0);
      for (const label of SITE_LEGEND) {
        await expect(page.getByText(label, { exact: true })).toHaveCount(0);
      }

      const credit = page.getByTestId("map-credit-line");
      await expect(credit).toBeVisible();
      await expect(credit).toContainText("OpenFreeMap");
      await expect(page.locator(".maplibregl-ctrl-attrib")).toHaveCount(0);
      await expect(page.getByTestId("map-attribution-line")).toHaveCount(0);
      for (const phrase of STALE) {
        await expect(credit).not.toContainText(phrase);
        await expect(page.locator("body")).not.toContainText(phrase);
      }
      // Approved VDL zone-totals credit is reached via Sources (MAP-FOOTER-1).
      const sources = page.getByTestId("map-credit-sources");
      if ((await sources.count()) > 0) {
        await sources.click();
      } else {
        await page.getByTestId("map-credit-info").click();
        await expect(page.getByTestId("map-credit-sheet")).toBeVisible();
        await page
          .getByTestId("map-credit-sheet")
          .getByTestId("map-credit-sources")
          .click();
      }
      await expect(page).toHaveURL(/\/data#licences/);
      await expect(page.getByText(/Vacant and Derelict/i).first()).toBeVisible({
        timeout: 30_000,
      });
      expect(VDL_ZONE_TOTALS_ATTRIBUTION).toContain(
        "Zones with one or two sites show no area.",
      );
      for (const phrase of STALE) {
        await expect(page.locator("body")).not.toContainText(phrase);
        expect(VDL_ZONE_TOTALS_ATTRIBUTION).not.toContain(phrase);
      }

      assertConsoleClean(gate);
    });
  });
}
