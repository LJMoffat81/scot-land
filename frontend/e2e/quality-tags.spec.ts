import { expect, test } from "@playwright/test";

test.describe("quality-tag colours", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("methodology lists four coloured data-state quality tags", async ({
    page,
  }) => {
    await page.goto("/methodology");
    const list = page.getByTestId("quality-tag-list");
    await expect(list).toBeVisible();
    const tags = list.getByTestId("quality-tag");
    await expect(tags).toHaveCount(4);
    await expect(tags.nth(0)).toHaveAttribute("data-quality", "live");
    await expect(tags.nth(1)).toHaveAttribute("data-quality", "derived");
    await expect(tags.nth(2)).toHaveAttribute("data-quality", "modelled");
    await expect(tags.nth(3)).toHaveAttribute("data-quality", "placeholder");
    // Distinct CSS colour tokens (not the same muted grey for every tag).
    const colors = await tags.evaluateAll((nodes) =>
      nodes.map((n) => getComputedStyle(n).color),
    );
    assertDistinct(colors);
  });

  test("downloads and open-api reuse quality-tag chips", async ({ page }) => {
    await page.goto("/downloads");
    await expect(page.getByTestId("quality-tag-inline").getByTestId("quality-tag")).toHaveCount(
      4,
    );
    await page.goto("/open-api");
    await expect(page.getByTestId("quality-tag-inline").getByTestId("quality-tag")).toHaveCount(
      4,
    );
  });
});

function assertDistinct(colors: string[]) {
  const unique = new Set(colors);
  expect(unique.size).toBeGreaterThanOrEqual(3);
}
