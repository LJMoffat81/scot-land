import { expect, test } from "@playwright/test";

test.describe("place card (internal preview)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("Designer v3.1 field order, tags, no £ figures", async ({ page }) => {
    await page.goto("/place-card");
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible();

    // Field order: Place → DZ → IZ → Council → Square → AGR → constraints → holder → sources
    await expect(page.getByTestId("place-card-place")).toBeVisible();
    await expect(page.getByTestId("place-card-data-zone")).toContainText(
      "S01010264",
    );
    await expect(page.getByTestId("place-card-intermediate-zone")).toContainText(
      /No data/i,
    );
    await expect(page.getByTestId("place-card-council")).toContainText(
      "Glasgow City",
    );
    await expect(page.getByTestId("place-card-square-reference")).toContainText(
      /Scot-LAND square reference/i,
    );
    await expect(page.getByTestId("place-card-square-reference")).not.toContainText(
      /what3words/i,
    );

    await expect(page.getByTestId("place-card-agr-surface")).toContainText(
      "Surface",
    );
    await expect(page.getByTestId("place-card-agr-resource")).toContainText(
      "Resource",
    );
    await expect(page.getByTestId("place-card-agr-nature")).toContainText(
      "Nature",
    );
    await expect(page.getByTestId("place-card-agr-amount-surface")).toHaveText(
      "figures pending sign-off",
    );
    await expect(page.getByTestId("place-card-of-which-planning_uplift")).toContainText(
      /of which: planning uplift/i,
    );
    await expect(
      page.getByTestId("place-card-of-which-infrastructure_share"),
    ).toContainText(/of which: infrastructure share/i);

    await expect(page.getByTestId("place-tag-market")).toBeVisible();
    await expect(page.getByTestId("place-tag-proxy")).toBeVisible();
    await expect(page.getByTestId("place-tag-shadow")).toBeVisible();

    await expect(page.getByTestId("place-card-data-zone-grain")).toHaveText(
      "For now, figures are published at Data Zone level only, not for individual parcels, plots or addresses.",
    );

    await expect(page.getByTestId("place-card-constraints")).toContainText(
      "Constraint: changes best use, adds no value",
    );
    await expect(page.getByTestId("place-card-holder")).toContainText(
      /private, not shown/i,
    );

    const layers = page.getByTestId("place-card-layers");
    await expect(layers.getByText("ROS INSPIRE parcels")).toBeVisible();
    await expect(page.getByTestId("place-card-licence-boundaries")).toContainText(
      /Open Government Licence/i,
    );
    await expect(page.getByTestId("place-card-licence-vdl")).toContainText(
      /OGL/i,
    );

    await expect(page.getByTestId("place-card-disclaimer")).toContainText(
      /research estimate, not an official valuation or bill/i,
    );
    await expect(card).not.toContainText("/year");
    await expect(card).not.toContainText(/£\d/);
    await expect(card).not.toContainText(/what3words/i);
  });

  test("gap variant still shows licences", async ({ page }) => {
    await page.goto("/place-card?variant=gap");
    await expect(page.getByTestId("place-card-licence-boundaries")).toBeVisible();
    await expect(
      page.locator('[data-layer-id="boundaries"] .place-layer-state'),
    ).toHaveText("No hit");
  });
});
