/**
 * M5 Who holds Scotland — explainer, council table, no named points, no pound.
 * Synthetic stubs only. Auto-discovered.
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
import {
  WHO_HOLDS_COL_ASSETS,
  WHO_HOLDS_COL_COUNCIL,
  WHO_HOLDS_COL_HECTARES,
  WHO_HOLDS_TABLE_HEADING,
} from "../../lib/whoHolds";

registerOpenFreeMapFontStub();

const VIEW = MAP_VIEW_PRESETS.find((v) => v.id === "who-holds-scotland");
if (!VIEW) throw new Error("who-holds-scotland missing");

test.describe("M5 who holds Scotland", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("M5-E1 explainer, table and no named point overlay", async ({ page }) => {
    test.setTimeout(180_000);
    const gate = attachConsoleGate(page);
    const pointReqs: string[] = [];
    page.on("request", (req) => {
      if (/community-ownership/.test(req.url())) pointReqs.push(req.url());
    });
    await stubMapCardsBackend(page);
    await openMap(page, "/?view=who-holds-scotland");
    await waitForMap(page);
    await openLayers(page);
    await expect(page.getByTestId("map-view-detail")).toHaveAttribute(
      "data-view",
      "who-holds-scotland",
    );
    await expect(page.getByTestId("map-view-finding")).toHaveText(VIEW.finding);
    await expect(page.getByTestId("map-view-question")).toHaveText(
      "Policy question: Who holds the land",
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
    await expect(page.getByTestId("map-view-who-holds-table")).toBeVisible();
    await expect(page.getByTestId("map-view-who-holds-table")).toContainText(
      WHO_HOLDS_TABLE_HEADING,
    );
    await expect(page.getByTestId("map-view-who-holds-table")).toContainText(
      WHO_HOLDS_COL_COUNCIL,
    );
    await expect(page.getByTestId("map-view-who-holds-table")).toContainText(
      WHO_HOLDS_COL_ASSETS,
    );
    await expect(page.getByTestId("map-view-who-holds-table")).toContainText(
      WHO_HOLDS_COL_HECTARES,
    );
    const detail = await page.getByTestId("map-view-detail").innerText();
    expect(detail).not.toMatch(/\u00a3/);
    expect(detail).not.toMatch(/neighbou?rhood/i);
    expect(pointReqs).toEqual([]);
    assertConsoleClean(gate);
  });

  test("M5-E2 ?view= boot order includes the explainer then the table", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    await stubMapCardsBackend(page);
    await openMap(page, "/?view=who-holds-scotland");
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
      "map-view-who-holds-table",
      "map-view-key",
      "map-view-source",
      "map-view-does-not-show",
      "map-view-share",
      "map-view-close",
    ]);
  });
});
