import { expect, test } from "@playwright/test";

test.describe("place card (internal preview)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("redesign IA: DZ2022, value/limits, legend, no £", async ({ page }) => {
    await page.goto("/place-card");
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible();

    await expect(page.getByTestId("place-card-place")).toBeVisible();
    await expect(page.getByTestId("place-card-data-zone-label")).toHaveText(
      "Data zone (2022)",
    );
    await expect(page.getByTestId("place-card-data-zone")).toContainText(
      "S01014567",
    );
    await expect(page.getByTestId("place-card-dz-vintage")).toContainText(
      "DZ2022",
    );
    await expect(page.getByTestId("place-card-intermediate-zone")).toContainText(
      /City Centre/i,
    );
    await expect(page.getByTestId("place-card-council")).toContainText(
      "Glasgow City",
    );
    await expect(page.getByText("Map reference", { exact: true })).toBeVisible();
    await expect(page.getByTestId("place-card-map-reference")).toContainText(
      /Scot-LAND square reference/i,
    );
    await expect(page.getByTestId("place-card-square-reference")).toContainText(
      /Scot-LAND square reference/i,
    );
    await expect(page.getByTestId("place-card-map-reference-copy")).toBeVisible();

    await expect(page.getByTestId("place-card-value")).toContainText(
      /What gives this land value/i,
    );
    await expect(page.getByTestId("place-card-agr-surface")).toContainText(
      /Land/i,
    );
    await expect(page.getByTestId("place-card-agr-resource")).toContainText(
      "Natural resource rents",
    );
    await expect(page.getByTestId("place-card-agr-nature")).toContainText(
      "Services of nature",
    );
    await expect(page.getByTestId("place-card-of-which-planning_uplift")).toContainText(
      /of which: planning uplift/i,
    );
    await expect(page.getByTestId("place-value-status-in_progress")).toHaveText(
      "Figure not published yet",
    );
    await expect(page.getByTestId("place-value-status-coming_soon").first()).toHaveText(
      "Figure not published yet",
    );
    await expect(page.getByTestId("place-card-figure-why").first()).toHaveText(
      "Why?",
    );
    await expect(
      page.getByTestId("place-card-figure-why-text").first(),
    ).toHaveText("Figures will appear once the valuation rules are signed off.");

    await expect(page.getByTestId("evidence-tag-legend")).toBeVisible();
    await expect(page.getByTestId("evidence-tag-legend-market")).toContainText(
      /real prices people paid/i,
    );
    await expect(page.getByTestId("evidence-tag-legend-proxy")).toContainText(
      /related prices/i,
    );
    await expect(page.getByTestId("evidence-tag-legend-shadow")).toContainText(
      /no market price/i,
    );

    await expect(page.getByTestId("place-card-limits")).toContainText("Limits");
    await expect(page.getByTestId("place-card-constraint-banner")).toContainText(
      "Constraint: changes best use, adds no value",
    );
    // Fixture rows apply=false — all three must still list (not filtered out).
    await expect(page.getByTestId("place-card-constraint-flood")).toContainText(
      "Does not apply",
    );
    await expect(page.getByTestId("place-card-constraint-sssi")).toContainText(
      "Does not apply",
    );
    await expect(page.getByTestId("place-card-constraint-crofting")).toContainText(
      "Does not apply",
    );
    await expect(page.getByTestId("place-card-holder-copy")).toHaveText(
      "Public records only. Private owners are not shown.",
    );
    await expect(page.getByTestId("place-card-scotlis")).toContainText(
      "Check the official title record on ScotLIS",
    );
    await expect(page.getByTestId("place-card-how-we-value")).toHaveAttribute(
      "href",
      "/methodology#glossary",
    );
    await expect(page.getByTestId("place-card-sources")).toContainText(
      "Where this comes from",
    );

    await expect(card).not.toContainText("£0");
    await expect(card).not.toContainText(/£\d/);
    await expect(card).not.toContainText(/ECONOMIC_RULES|NESTED|REPORTED/i);
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
