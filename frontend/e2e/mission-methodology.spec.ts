import { expect, test } from "@playwright/test";

const DZ_GRAIN =
  "For now, figures are published at Data Zone level only, not for individual parcels, plots or addresses.";

test.describe("mission and methodology pages", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("mission follows Designer brief sections", async ({ page }) => {
    await page.goto("/mission");
    const root = page.getByTestId("mission-page");
    await expect(root).toBeVisible();
    await expect(page.getByRole("heading", { name: "Mission" })).toBeVisible();
    for (const heading of [
      "Why",
      "Goal",
      "Who it's for",
      "What it isn't",
      "What done looks like",
      "Get involved",
    ]) {
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
    await expect(root).toContainText("Annual Ground Rent");
    await expect(page.getByTestId("experimental-not-official")).toContainText(
      "Research estimate, not an official valuation or bill",
    );
    await expect(page.getByTestId("experimental-not-official")).toContainText(
      "Figures pending sign-off",
    );
    await expect(page.getByTestId("experimental-not-official")).toContainText(
      DZ_GRAIN,
    );
    await expect(root).toContainText(
      "Open data only at launch; paid sources may be added later",
    );
    await expect(root).toContainText("Scot-LAND square reference");
    await expect(root).not.toContainText(/£\s*[\d,]+/);
  });

  test("methodology covers roll-up, tags, sources, gaps", async ({ page }) => {
    await page.goto("/methodology");
    const root = page.getByTestId("methodology-page");
    await expect(root).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Methodology" }),
    ).toBeVisible();
    for (const heading of [
      "What AGR is",
      "The roll-up",
      "The three tags",
      "Rents kept separate; constraints add no value",
      "Sources",
      "Gaps",
      "Validation",
      "Changelog",
    ]) {
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
    await expect(root).toContainText(
      "Constraint: changes best use, adds no value",
    );
    await expect(root).toContainText("Roll-up figures stay unpublished");
    await expect(root).toContainText("2011-to-2022");
    await expect(page.getByTestId("confidence-tag-list")).toBeVisible();
    await expect(
      page.getByTestId("confidence-tag").filter({ hasText: "Market" }),
    ).toHaveAttribute("data-confidence", "market");
    await expect(
      page.getByTestId("confidence-tag").filter({ hasText: "Proxy" }),
    ).toHaveAttribute("data-confidence", "proxy");
    await expect(
      page.getByTestId("confidence-tag").filter({ hasText: "Shadow" }),
    ).toHaveAttribute("data-confidence", "shadow");
    const table = page.getByTestId("sources-table");
    await expect(table).toBeVisible();
    expect(await table.locator("tbody tr").count()).toBeGreaterThan(20);
    await expect(root).not.toContainText(/£\s*[\d,]+/);
  });
});
