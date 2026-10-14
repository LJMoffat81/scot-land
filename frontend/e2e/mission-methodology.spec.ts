import { expect, test } from "@playwright/test";

test.describe("about and how-it-works pages", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("about follows rewrite section B copy", async ({ page }) => {
    await page.goto("/about");
    const root = page.getByTestId("mission-page");
    await expect(root).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "About Scot-LAND" }),
    ).toBeVisible();
    for (const heading of [
      "What Scot-LAND is not",
      "Why I am building this",
      "Contact",
    ]) {
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
    await expect(page.getByTestId("research-banner")).toContainText(
      "Research estimate.",
    );
    await expect(root).toContainText("I am Laurie Moffat");
    await expect(root).toContainText("Scottish Land Commission");
    await expect(root).toContainText("Open data only at launch");
    await expect(root).not.toContainText(/£\s*[\d,]+/);
    await expect(page).toHaveTitle(/About \| Scot-LAND/);
  });

  test("how it works covers valuation, roll-up, glossary, gaps", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(String(err));
    });

    await page.goto("/methodology");
    const root = page.getByTestId("methodology-page");
    await expect(root).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "How it works" }),
    ).toBeVisible();
    for (const heading of [
      "How an area is valued",
      "Small areas, added up honestly",
      "Words we use",
      "How sure are these numbers?",
      "What's missing",
    ]) {
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
    }
    await expect(page.getByTestId("glossary-box")).toBeVisible();
    await expect(root).toContainText("Constraint: changes best use, adds no value");
    await expect(root).toContainText("different labels are never added");
    await expect(root).not.toContainText(/\bchips?\b/i);
    await expect(root).toContainText("2011 Data Zones");
    await expect(root).toContainText("Market = taken from real prices");
    await expect(root).not.toContainText("£0");
    await expect(root).not.toContainText(/£\s*[\d,]+/);
    await expect(root).not.toContainText(/PostGIS|ECONOMIC_RULES|503 when/i);
    await expect(page).toHaveTitle(/How it works \| Scot-LAND/);
    expect(consoleErrors, `console errors: ${consoleErrors.join("; ")}`).toEqual(
      [],
    );
  });
});
