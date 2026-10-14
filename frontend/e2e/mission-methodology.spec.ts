import { expect, test } from "@playwright/test";

const DZ_GRAIN =
  "For now, figures are published at Data Zone level only, not for individual parcels, plots or addresses.";

test.describe("about and how-it-works pages", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("about follows Designer brief sections", async ({ page }) => {
    await page.goto("/about");
    const root = page.getByTestId("mission-page");
    await expect(root).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "About Scot-LAND" }),
    ).toBeVisible();
    for (const heading of [
      "Why I am building this",
      "Goal",
      "Who it's for",
      "What it isn't",
      "What done looks like",
      "Get involved",
    ]) {
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
    await expect(root).toContainText("Annual Ground Rent");
    await expect(page.getByTestId("research-banner")).toContainText(
      "Research estimate.",
    );
    await expect(page.getByTestId("experimental-not-official")).toHaveCount(0);
    await expect(root).toContainText(DZ_GRAIN);
    await expect(root).toContainText(
      "Open data only at launch; paid sources may be added later",
    );
    await expect(root).toContainText("Scot-LAND square reference");
    await expect(root).not.toContainText(/£\s*[\d,]+/);
  });

  test("how it works covers roll-up, tags, sources, gaps", async ({ page }) => {
    await page.goto("/methodology");
    const root = page.getByTestId("methodology-page");
    await expect(root).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "How it works" }),
    ).toBeVisible();
    for (const heading of [
      "What AGR is",
      "The roll-up",
      "The three tags",
      "Rents kept separate; constraints add no value",
      "Natural capital ledger",
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
    await expect(page.getByTestId("methodology-ledger-table")).toBeVisible();
    await expect(page.getByTestId("methodology-oil-gas-footnote")).toContainText(
      /offshore, outside the Scottish land total/i,
    );
    await expect(
      page.getByTestId("confidence-tag").filter({ hasText: "Market" }),
    ).toHaveAttribute("data-confidence", "market");
    await expect(root).toContainText(/based on real sales or prices/i);
    const table = page.getByTestId("sources-table");
    await expect(table).toBeVisible();
    expect(await table.locator("tbody tr").count()).toBeGreaterThan(20);
    await expect(root).not.toContainText("£0");
    await expect(root).not.toContainText(/£\s*[\d,]+/);
    await expect(page).toHaveTitle(/How it works \| Scot-LAND/);
  });
});
