/**
 * M4 story-view framework — explainer rows (policy question, "What this could mean",
 * "What we can't see"). M4 ships the framework only: no shipped view sets
 * them, so none of the three blocks may render. Rules are unit-tested on
 * synthetic presets in scripts/test-map-views.mjs (T10–T13). Auto-discovered.
 */
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import { MAP_VIEW_PRESETS } from "../../lib/mapViews";

registerOpenFreeMapFontStub();

test.describe("M4 story views", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("M4-E1 no shipped view renders an explainer block", async ({ page }) => {
    test.setTimeout(180_000);
    const gate = attachConsoleGate(page);
    expect(MAP_VIEW_PRESETS.length).toBeGreaterThan(0);
    await stubMapCardsBackend(page);
    await openMap(page, "/");
    await waitForMap(page);
    await openLayers(page);
    for (const v of MAP_VIEW_PRESETS) {
      await page.getByTestId(`map-view-${v.id}`).click();
      await expect(page.getByTestId("map-view-detail")).toHaveAttribute("data-view", v.id);
      await expect(page.getByTestId("map-view-finding")).toHaveText(v.finding);
      await expect(page.getByTestId("map-view-question")).toHaveCount(0);
      await expect(page.getByTestId("map-view-takeaway")).toHaveCount(0);
      await expect(page.getByTestId("map-view-gaps")).toHaveCount(0);
      const detail = await page.getByTestId("map-view-detail").innerText();
      expect(detail).not.toMatch(/Policy question|What this could mean|What we can't see|\u00a3/);
    }
    assertConsoleClean(gate);
  });

  test("M4-E2 ?view= boot keeps the VIEWS-1a detail order", async ({ page }) => {
    test.setTimeout(180_000);
    await stubMapCardsBackend(page);
    await openMap(page, "/?view=access-to-services");
    await waitForMap(page);
    await openLayers(page);
    const ids = await page
      .getByTestId("map-view-detail")
      .locator(":scope > [data-testid]")
      .evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")));
    expect(ids).toEqual([
      "map-view-finding",
      "map-view-key",
      "map-view-source",
      "map-view-does-not-show",
      "map-view-share",
      "map-view-close",
    ]);
  });
});
