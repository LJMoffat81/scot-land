import { expect, test } from "@playwright/test";

/**
 * WEALTH-ENGINE-NAME-1 — three verbatim lines at 1280 and 390.
 * The roadmap line is the last roadmap row.
 */

const ROADMAP_LINE =
  "Scotland National Wealth Engine: land value for every parcel, ready to support fair land taxation";
const BUILT_LINE =
  "The map runs on the Scotland National Wealth Engine, which we are building step by step.";
const API_LINE =
  "The API and bulk data will come from the Scotland National Wealth Engine.";

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`WEALTH-ENGINE-NAME-1 ${viewport.width}`, () => {
    test.use({ viewport });

    test("three lines sit where the spec puts them", async ({ page }) => {
      await page.goto("/roadmap");
      const names = page.locator(".roadmap-layer-name");
      await expect(names.last()).toHaveText(ROADMAP_LINE);
      await expect(page.getByTestId("roadmap-final-row")).toContainText(ROADMAP_LINE);

      await page.goto("/how-we-built-this");
      const copy = page.getByTestId("how-we-built-copy");
      await expect(copy).toContainText("led by Laurie Moffat");
      await expect(copy).toContainText(BUILT_LINE);
      const builtText = await copy.innerText();
      const ledAt = builtText.indexOf("led by Laurie Moffat");
      const engineAt = builtText.indexOf(BUILT_LINE);
      expect(ledAt).toBeGreaterThanOrEqual(0);
      expect(engineAt).toBeGreaterThan(ledAt);

      await page.goto("/developers/api");
      const teaser = page.getByTestId("api-teaser");
      await expect(teaser).toContainText(API_LINE);
      const teaserText = await teaser.innerText();
      const headingAt = teaserText.indexOf("Developer API and bulk data: coming");
      const lineAt = teaserText.indexOf(API_LINE);
      const registerAt = teaserText.indexOf("Register interest");
      expect(lineAt).toBeGreaterThan(headingAt);
      expect(registerAt).toBeGreaterThan(lineAt);
    });
  });
}
