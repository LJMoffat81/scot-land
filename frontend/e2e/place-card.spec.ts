import { expect, test } from "@playwright/test";

test.describe("place card (internal preview)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("UX10-1 skeleton: AGR, pre-£, parts, no £", async ({ page }) => {
    await page.goto("/place-card");
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible();

    await expect(page.getByTestId("place-card-place")).toBeVisible();
    await expect(page.getByTestId("place-card-council")).toContainText(
      "Glasgow City",
    );
    await expect(page.getByTestId("place-card-figure")).toContainText(
      "We're not showing amounts yet while we check our method.",
    );
    await expect(page.getByTestId("place-card-agr-label")).toHaveText(
      "Annual Ground Rent",
    );
    await expect(page.getByTestId("place-card-covers-homes")).toHaveText(
      "Covers land under homes only.",
    );
    await expect(page.getByTestId("place-card-typical-home")).toContainText(
      "For a typical home in this neighbourhood, not your home.",
    );
    await expect(page.getByTestId("place-card-fact")).toBeVisible();

    const parts = page.getByTestId("place-card-parts");
    await expect(parts.locator("summary")).toHaveText(
      "Natural resource rents & services of nature",
    );
    await parts.locator("summary").click();
    await expect(page.getByTestId("place-card-agr-surface")).toContainText(
      /Land/i,
    );
    await expect(page.getByTestId("place-card-map-reference")).toContainText(
      "Map reference",
    );
    await expect(page.getByTestId("place-card-figure-why")).toHaveAttribute(
      "href",
      "/methodology#how-sure",
    );
    await expect(page.getByTestId("place-card-of-which-planning_uplift")).toContainText(
      /of which: planning uplift/i,
    );
    await expect(page.getByTestId("place-card-range-surface")).toHaveText(
      "not yet estimated",
    );
    await expect(page.getByTestId("place-tag-estimate")).toHaveText("Estimate");
    await expect(page.getByTestId("place-card-parts-note")).toContainText(
      "These are worked out differently, so we don't add them up.",
    );

    const howLink = page.getByTestId("place-card-methodology-link");
    await expect(howLink).toHaveText("How we work this out");
    await expect(howLink).toHaveAttribute("href", "/methodology");
    await expect(page.getByTestId("place-card-how-homes-only")).toContainText(
      "Shops, offices and industrial land aren't included yet.",
    );

    await expect(card).not.toContainText("£0");
    await expect(card).not.toContainText(/£\d/);
    await expect(card).not.toContainText(/what3words/i);
    await expect(card).not.toContainText(/Estimate \(no market price\)/);
    await expect(card).not.toContainText(/ECONOMIC_RULES|NESTED|REPORTED/i);
    expect(await card.innerHTML()).not.toMatch(/\bshadow\b/i);
  });
});
