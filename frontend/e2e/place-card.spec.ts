import { expect, test } from "@playwright/test";

test.describe("place card (standalone)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("shows council, data zone, layers, and links without AGR £", async ({
    page,
  }) => {
    await page.goto("/place-card");
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible();

    await expect(card.getByRole("heading", { name: "Glasgow City" })).toBeVisible();
    await expect(page.getByTestId("place-card-data-zone")).toContainText(
      "Data zone S01010264",
    );

    const layers = page.getByTestId("place-card-layers");
    await expect(layers.getByText("ROS INSPIRE parcels")).toBeVisible();
    await expect(layers.getByText("Vacant and derelict land")).toBeVisible();
    await expect(layers.getByText("Public and Crown Estate land")).toBeVisible();
    await expect(layers.getByText("Common Good")).toBeVisible();
    await expect(layers.getByText("Local-authority land holdings")).toBeVisible();

    const links = page.getByTestId("place-card-links");
    await expect(links.getByRole("link", { name: /ScotLIS/i })).toBeVisible();
    await expect(
      links.getByRole("link", { name: /Sources and method/i }),
    ).toBeVisible();

    await expect(card).toContainText(/No modelled plot AGR/i);
    await expect(card).not.toContainText("£");
    await expect(card).not.toContainText("/year");
  });

  test("gap variant marks parcel miss and gaps honestly", async ({ page }) => {
    await page.goto("/place-card?variant=gap");
    const layers = page.getByTestId("place-card-layers");
    await expect(
      layers.locator('[data-layer-id="boundaries"] .place-layer-state'),
    ).toHaveText("No hit");
    await expect(
      layers.locator('[data-layer-id="la_holdings"] .place-layer-state'),
    ).toHaveText("Gap");
  });
});
