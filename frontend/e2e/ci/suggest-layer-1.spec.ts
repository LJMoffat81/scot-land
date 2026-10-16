import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * SUGGEST-LAYER-1 and the roadmap lines that sit with it.
 * The suggest section is before Coming to the map. The link uses the issue form.
 */

const SUGGEST_COPY =
  "Know a dataset that would make this map better? Tell us what the layer is, where the data comes from (a link), and why it matters for land value. We check every suggestion against its licence and our method before adding it.";

const SUGGEST_HREF =
  "https://github.com/LJMoffat81/scot-land/issues/new?template=suggest-layer.yml";

async function assertRoadmapAdditions(page: Page) {
  await page.goto("/roadmap");

  const order = await page.evaluate(() => {
    const headings = [...document.querySelectorAll("h2")].map((el) =>
      (el.textContent || "").trim(),
    );
    return {
      suggest: headings.indexOf("Suggest a layer"),
      coming: headings.indexOf("Coming to the map"),
    };
  });
  expect(order.suggest).toBeGreaterThanOrEqual(0);
  expect(order.coming).toBeGreaterThan(order.suggest);

  const suggest = page.getByTestId("roadmap-suggest-layer");
  await expect(suggest).toContainText(SUGGEST_COPY);
  const link = suggest.getByRole("link", { name: "Suggest a layer", exact: true });
  await expect(link).toHaveAttribute("href", SUGGEST_HREF);
  expect(SUGGEST_HREF).toContain("template=suggest-layer.yml");

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

  test("suggest section, vision line, and vacant land status", async ({ page }) => {
    await assertRoadmapAdditions(page);
  });
});

test.describe("SUGGEST-LAYER-1 at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("suggest section, vision line, and vacant land status", async ({ page }) => {
    await assertRoadmapAdditions(page);
  });
});
