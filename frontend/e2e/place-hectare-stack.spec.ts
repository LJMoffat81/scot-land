import { expect, test } from "@playwright/test";

test.describe("place per-hectare stack", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("headline stacks to total; 1a nested; shadow separate; no AGR £", async ({
    page,
  }) => {
    await page.goto("/place?fixture=1");
    const stack = page.getByTestId("place-hectare-stack");
    await expect(stack).toBeVisible();

    await expect(page.getByTestId("place-stack-zone")).toContainText(
      "S01010264",
    );

    const headline = page.getByTestId("place-stack-headline");
    await expect(headline).toBeVisible();
    await expect(page.getByTestId("place-stack-row-1")).toBeVisible();
    const nested = page.getByTestId("place-stack-row-1a");
    await expect(nested).toHaveAttribute("data-nested", "true");
    await expect(nested).toHaveAttribute("data-in-total", "false");
    await expect(page.getByTestId("place-stack-1a-note")).toContainText(
      /not added/i,
    );

    const headlineTotal = page.getByTestId("place-stack-headline-total");
    await expect(headlineTotal).toHaveAttribute(
      "data-sum-ids",
      "1,2,3,4",
    );
    await expect(headlineTotal).toContainText("1 + 2 + 3 + 4");
    await expect(headlineTotal).not.toContainText("1a");

    const shadow = page.getByTestId("place-stack-shadow");
    await expect(shadow).toBeVisible();
    await expect(page.getByTestId("place-stack-row-5")).toBeVisible();
    await expect(page.getByTestId("place-stack-shadow-total")).toHaveAttribute(
      "data-sum-ids",
      "5,6,7,8,10",
    );

    const outside = page.getByTestId("place-stack-outside");
    await expect(outside).toContainText(/Outside Scottish total/i);
    await expect(page.getByTestId("place-stack-row-9")).toBeVisible();
    await expect(page.getByTestId("place-stack-benchmark-label")).toContainText(
      /benchmark only, not inputs/i,
    );
    await expect(page.getByTestId("place-stack-benchmarks")).toContainText(
      "Wightman",
    );

    await expect(page.getByTestId("place-stack-constraints")).toContainText(
      /£0, change best/i,
    );

    await expect(page.getByTestId("place-stack-disclaimer")).toContainText(
      /No modelled Annual Ground Rent/i,
    );
    await expect(stack).not.toContainText(/£\d/);
    await expect(stack).not.toContainText("/year");
    // Placeholders are em-dash, never £0 for not-yet rows.
    await expect(page.getByTestId("place-stack-amount-1")).toHaveText("—");
    await expect(page.getByTestId("place-stack-amount-1a")).toHaveText("—");
  });

  test("blocked zone publishes nothing", async ({ page }) => {
    await page.goto("/place?fixture=blocked");
    await expect(page.getByTestId("place-stack-blocked")).toBeVisible();
    await expect(page.getByTestId("place-stack-blocked")).toContainText(
      /nothing published for blocked zones/i,
    );
    await expect(page.getByTestId("place-stack-headline")).toHaveCount(0);
    await expect(page.getByTestId("place-stack-shadow")).toHaveCount(0);
  });

  test("place card links to hectare stack for a zone", async ({ page }) => {
    await page.goto("/place-card");
    const link = page.getByTestId("place-card-hectare-stack-link");
    await expect(link).toBeVisible();
    await expect(link).toHaveAttribute("href", "/place?zone=S01010264");
  });
});
