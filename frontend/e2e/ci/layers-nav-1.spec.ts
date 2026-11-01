import { test, expect } from "./_fixtures";
import {
  registerOpenFreeMapFontStub,
  attachConsoleGate,
  assertConsoleClean,
  ensureLayersGroupOpen,
  LIVE_LAYER_IDS,
  openLayers,
  openMap,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";
import { LIMITS_ON_USE_NOTE } from "../../components/MapLayersDrawer";

registerOpenFreeMapFontStub();

/**
 * LAYERS-NAV-1 — LAND / Limits / Places; no planned-row placeholders.
 * CARD-CLARITY-31OCT-1B item 7.
 */

const HEADER_ORDER = [
  "LAND",
  "Sites",
  "Natural resources",
  "Limits on use",
  "PLACES AND BOUNDARIES",
] as const;

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`LAYERS-NAV-1 (${viewport.width})`, () => {
    test.use({ viewport });

    test("headers, sub-groups, live switches; no aim placeholders", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);

      await openMap(page);
      await openLayers(page);
      for (const key of ["land", "resources", "limits", "places"] as const) {
        await ensureLayersGroupOpen(page, key);
      }

      const panel = page.getByTestId("layers-panel");
      const order = await page
        .locator(
          "[data-testid='layers-nav-header'], [data-testid='layers-nav-subgroup']",
        )
        .allInnerTexts();
      expect(order.map((line) => line.trim())).toEqual([...HEADER_ORDER]);
      await expect(page.getByTestId("layers-nav-header")).toHaveCount(2);
      await expect(page.getByTestId("layers-nav-subgroup")).toHaveCount(3);
      await expect(page.getByTestId("layers-nav-land-subtitle")).toHaveText(
        "Everything nature provides and no one made",
      );
      await expect(page.getByTestId("layers-nature-note")).toHaveCount(0);
      await expect(page.getByTestId("layers-group-note-tenure")).toHaveCount(0);
      await expect(page.getByTestId("layers-group-note-limits")).toHaveText(
        LIMITS_ON_USE_NOTE,
      );
      await expect(
        page.getByTestId("map-layers-limits-explainer"),
      ).toHaveCount(0);

      const placesText = await page.getByTestId("layers-nav-places").innerText();
      expect(placesText).not.toContain("£");
      expect(placesText.toLowerCase()).not.toContain("rent");
      await expect(
        panel.getByRole("switch", {
          name: "Local areas (data zones)",
          exact: true,
        }),
      ).toHaveCount(1);
      await expect(
        panel.getByRole("switch", { name: "Area boundaries", exact: true }),
      ).toHaveCount(0);
      await expect(panel.getByText("Services of nature", { exact: true })).toHaveCount(
        0,
      );

      const switchIds = (
        await panel.locator("[data-testid^='layer-toggle-']").evaluateAll((els) =>
          els.map((el) =>
            (el.getAttribute("data-testid") ?? "").replace(/^layer-toggle-/, ""),
          ),
        )
      ).sort();
      expect(switchIds).toEqual([...LIVE_LAYER_IDS].sort());

      await expect(panel.locator("[data-testid^='layers-aim-']")).toHaveCount(0);
      await expect(
        page.getByTestId("map-layers-roadmap-link").getByRole("link", {
          name: "What's coming next →",
          exact: true,
        }),
      ).toHaveCount(1);

      assertConsoleClean(gate);
    });
  });
}
