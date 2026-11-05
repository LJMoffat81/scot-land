/**
 * M2 Idle land — explainer, council table, no named sites, no pound.
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
  IDLE_LAND_COL_COUNCIL,
  IDLE_LAND_COL_HECTARES,
  IDLE_LAND_COL_SITES,
  IDLE_LAND_TABLE_HEADING,
} from "../../lib/idleLand";

registerOpenFreeMapFontStub();

const VIEW = MAP_VIEW_PRESETS.find((v) => v.id === "idle-land");
if (!VIEW) throw new Error("idle-land missing");

test.describe("M2 idle land", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("M2-E1 explainer, table and no named site overlay", async ({ page }) => {
    test.setTimeout(180_000);
    const gate = attachConsoleGate(page);
    const pointReqs: string[] = [];
    page.on("request", (req) => {
      if (/\/layers\/open\/vdl|community-ownership|vdl-councils/.test(req.url())) pointReqs.push(req.url());
    });
    await stubMapCardsBackend(page);
    await openMap(page, "/?view=idle-land");
    await waitForMap(page);
    await openLayers(page);
    await expect(page.getByTestId("map-view-detail")).toHaveAttribute(
      "data-view",
      "idle-land",
    );
    await expect(page.getByTestId("map-view-finding")).toHaveText(VIEW.finding);
    await expect(page.getByTestId("map-view-question")).toHaveText(
      "Policy question: Vacant and derelict land",
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
    await expect(page.getByTestId("map-view-idle-land-table")).toBeVisible();
    await expect(page.getByTestId("map-view-idle-land-table")).toContainText(
      IDLE_LAND_TABLE_HEADING,
    );
    await expect(page.getByTestId("map-view-idle-land-table")).toContainText(
      IDLE_LAND_COL_COUNCIL,
    );
    await expect(page.getByTestId("map-view-idle-land-table")).toContainText(
      IDLE_LAND_COL_SITES,
    );
    await expect(page.getByTestId("map-view-idle-land-table")).toContainText(
      IDLE_LAND_COL_HECTARES,
    );
    const detail = await page.getByTestId("map-view-detail").innerText();
    expect(detail).not.toMatch(/\u00a3/);
    expect(detail).not.toMatch(/neighbou?rhood/i);
    expect(pointReqs).toEqual([]);
    assertConsoleClean(gate);
  });

  test("M2-E2 ?view= boot order includes the explainer then the table", async ({
    page,
  }) => {
    test.setTimeout(180_000);
    await stubMapCardsBackend(page);
    await openMap(page, "/?view=idle-land");
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
      "map-view-idle-land-table",
      "map-view-key",
      "map-view-source",
      "map-view-does-not-show",
      "map-view-share",
      "map-view-close",
    ]);
  });
});
