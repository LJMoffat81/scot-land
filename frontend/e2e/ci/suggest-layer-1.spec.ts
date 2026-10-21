import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";
import { SUGGEST_LAYER_COPY } from "../../components/SuggestLayerSection";

registerOpenFreeMapFontStub();

/**
 * SUGGEST-LAYER-1 — flag-off: section omitted (SW-082 / FRONTEND-BATCH-3).
 * Flag-on order + link assertions live in frontend-batch-3.spec.ts T-R2.
 */

async function assertNoMailtoOrEmail(page: Page) {
  await expect(page.locator('a[href^="mailto:"]')).toHaveCount(0);
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/);
}

async function assertRoadmapAdditions(page: Page) {
  await page.goto("/roadmap");

  // Flag off (default): whole #suggest-a-layer section is out of the DOM.
  await expect(page.locator("#suggest-a-layer")).toHaveCount(0);
  await expect(page.getByTestId("roadmap-suggest-layer")).toHaveCount(0);
  await expect(page.getByText("Suggest a layer")).toHaveCount(0);
  await expect(page.getByText(SUGGEST_LAYER_COPY)).toHaveCount(0);
  await assertNoMailtoOrEmail(page);

  const vision = page.getByTestId("roadmap-vision");
  await expect(vision).toContainText(
    "Today the map shows estimates for Data Zones only.",
  );
  await expect(
    vision.getByRole("link", { name: "Back to map", exact: true }),
  ).toHaveAttribute("href", "/");

  const vacant = page.getByTestId("roadmap-waiting-vdl");
  await expect(vacant).toContainText("Vacant and derelict land");
  await expect(vacant.getByTestId("roadmap-waiting-status-vdl")).toHaveText(
    "In progress",
  );
}

test.describe("SUGGEST-LAYER-1 at 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("flag off: no suggest section; vision line and vacant status", async ({
    page,
  }) => {
    await assertRoadmapAdditions(page);
  });
});

test.describe("SUGGEST-LAYER-1 at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("flag off: no suggest section; vision line and vacant status", async ({
    page,
  }) => {
    await assertRoadmapAdditions(page);
  });
});
