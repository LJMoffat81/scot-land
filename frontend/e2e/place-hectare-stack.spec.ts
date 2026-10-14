import { expect, test } from "@playwright/test";

test.describe("place per-hectare stack", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("headline stacks to total; planning uplift under surface; no £0", async ({
    page,
  }) => {
    await page.goto("/place?fixture=1");
    const stack = page.getByTestId("place-hectare-stack");
    await expect(stack).toBeVisible();

    await expect(page.getByTestId("place-stack-zone")).toContainText(
      "S01014567",
    );

    const headline = page.getByTestId("place-stack-headline");
    await expect(headline).toBeVisible();
    await expect(page.getByTestId("place-stack-row-1")).toBeVisible();
    const nested = page.getByTestId("place-stack-row-1a");
    await expect(nested).toHaveAttribute("data-nested", "true");
    await expect(nested).toHaveAttribute("data-in-total", "false");
    await expect(page.getByTestId("place-stack-1a-note")).toContainText(
      /of which under surface/i,
    );

    const headlineTotal = page.getByTestId("place-stack-headline-total");
    await expect(headlineTotal).toHaveAttribute("data-sum-ids", "1,2,3,4");
    await expect(headlineTotal).not.toContainText("1a");

    const shadow = page.getByTestId("place-stack-shadow");
    await expect(shadow).toBeVisible();
    await expect(page.getByTestId("place-stack-row-5")).toBeVisible();

    const outside = page.getByTestId("place-stack-outside");
    await expect(outside).toContainText(/outside the Scottish land total/i);
    await expect(page.getByTestId("place-stack-row-9")).toBeVisible();

    await expect(page.getByTestId("place-stack-constraints")).toContainText(
      /Constraint: changes best use, adds no value/i,
    );
    await expect(page.getByTestId("place-stack-disclaimer")).toContainText(
      /Figures are being checked/i,
    );
    await expect(stack).not.toContainText("£0");
    await expect(stack).not.toContainText(/£\d/);
    await expect(stack).not.toContainText(/ECONOMIC_RULES|NESTED|REPORTED/i);
    await expect(page.getByTestId("place-stack-amount-1")).toHaveText("—");
  });

  test("blocked zone publishes nothing", async ({ page }) => {
    await page.goto("/place?fixture=blocked");
    await expect(page.getByTestId("place-stack-blocked")).toBeVisible();
    await expect(page.getByTestId("place-stack-blocked")).toContainText(
      /nothing published for blocked zones/i,
    );
    await expect(page.getByTestId("place-stack-headline")).toHaveCount(0);
  });
});
