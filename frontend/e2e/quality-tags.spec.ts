import { expect, test } from "@playwright/test";

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
  });
});

function assertDistinct(colors: string[]) {
  const unique = new Set(colors);
  expect(unique.size).toBeGreaterThanOrEqual(3);
}
