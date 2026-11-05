/**
 * M6 Carbon and land — explainer only, no painted key, no pound, no names.
 * Layer 8 stays coming. Synthetic stubs only. Auto-discovered.
 */
import { expect, test } from "./_fixtures";
import {
  assertConsoleClean,
  attachConsoleGate,
  BANNED_VISIBLE,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import { MAP_VIEW_PRESETS } from "../../lib/mapViews";

registerOpenFreeMapFontStub();

const VIEW = MAP_VIEW_PRESETS.find((v) => v.id === "carbon-and-land");
if (!VIEW) throw new Error("carbon-and-land missing");

test.describe("M6 carbon and land", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("M6-E1 explainer and no pound", async ({ page }) => {
    test.setTimeout(180_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await openMap(page, "/?view=carbon-and-land");
    await waitForMap(page);
    await openLayers(page);
    await expect(page.getByTestId("map-view-detail")).toHaveAttribute(
      "data-view",
      "carbon-and-land",
    );
    await expect(page.getByTestId("map-view-finding")).toHaveText(VIEW.finding);
    await expect(page.getByTestId("map-view-question")).toHaveText(
      "Policy question: Carbon and land",
    );
    await expect(page.getByTestId("map-view-takeaway")).toContainText(
      "What this could mean",
    );
    await expect(page.getByTestId("map-view-takeaway")).toContainText(VIEW.takeaway!);
    await expect(page.getByTestId("map-view-gaps")).toContainText("What we can't see");
    for (const gap of VIEW.gaps ?? []) {
      await expect(page.getByTestId("map-view-gaps")).toContainText(gap);
    }
    await expect(page.getByTestId("map-view-estimate")).toHaveCount(0);
    await expect(page.getByTestId("map-view-idle-land-table")).toHaveCount(0);
    await expect(page.getByTestId("map-view-who-holds-table")).toHaveCount(0);
    await expect(page.getByTestId("layer-toggle-8")).toHaveCount(0);
    const detail = await page.getByTestId("map-view-detail").innerText();
    expect(detail).not.toMatch(/\u00a3/);
    expect(detail).not.toMatch(BANNED_VISIBLE);
    expect(detail).not.toMatch(/neighbou?rhood/i);
    assertConsoleClean(gate);
  });

  test("M6-E2 ?view= boot order includes the explainer then the key", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    await stubMapCardsBackend(page);
    await openMap(page, "/?view=carbon-and-land");
    await waitForMap(page);
    await openLayers(page);
    const ids = await page
      .getByTestId("map-view-detail")
      .locator(":scope > [data-testid]")
      .evaluateAll((els) => els.map((e) => e.getAttribute("data-testid")));
    expect(ids).toEqual([
      "map-view-finding",
      "map-view-question",
      "map-view-takeaway",
      "map-view-gaps",
      "map-view-key",
      "map-view-source",
      "map-view-does-not-show",
      "map-view-share",
      "map-view-close",
    ]);
  });
});
