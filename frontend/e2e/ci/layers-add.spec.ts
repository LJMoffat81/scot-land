import { expect, test } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  openMap,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";

/**
 * LAYERS-ADD-1 — registry rows default OFF; LDP/HLS on roadmap; no £; banned names.
 * Accordion groups must be expanded before toggles exist in the DOM (MAP-CARDS).
 */

const NEW_OFF_BY_GROUP: Record<string, readonly string[]> = {
  land: ["flood", "contaminated_land"],
  places: [
    "deprivation",
    "conservation",
    "listed",
    "stops",
    "green_belt",
    "school_catchments",
  ],
};

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
