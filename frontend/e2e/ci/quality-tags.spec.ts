import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";

registerOpenFreeMapFontStub();


test.describe("quality-tag colours", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("developers page reuses quality-tag chips", async ({ page }) => {
    await page.goto("/developers");
    const tags = page.getByTestId("quality-tag-inline").getByTestId("quality-tag");
    await expect(tags).toHaveCount(4);
    await expect(tags.nth(0)).toHaveAttribute("data-quality", "live");
    await expect(tags.nth(1)).toHaveAttribute("data-quality", "derived");
    await expect(tags.nth(2)).toHaveAttribute("data-quality", "modelled");
    await expect(tags.nth(3)).toHaveAttribute("data-quality", "placeholder");
    const colors = await tags.evaluateAll((nodes) =>
      nodes.map((n) => getComputedStyle(n).color),
    );
    assertDistinct(colors);
    // SW-025: map-label line after the input quality tags.
    await expect(page.getByTestId("quality-tag-inline")).toContainText(
      "These describe where the input data comes from. On the map, figures are labelled Market, Modelled or Estimate.",
    );
  });
});

function assertDistinct(colors: string[]) {
  const unique = new Set(colors);
  expect(unique.size).toBeGreaterThanOrEqual(3);
}
