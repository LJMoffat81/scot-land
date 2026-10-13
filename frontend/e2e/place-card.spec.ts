import { expect, test } from "@playwright/test";

test.describe("place card (standalone)", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("shows AGR purpose, rent ranges, DZ grain, licences — no £ figures", async ({
    page,
  }) => {
    await page.goto("/place-card");
    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible();

    await expect(card.getByText("Annual Ground Rent").first()).toBeVisible();
    await expect(card.getByRole("heading", { name: "Glasgow City" })).toBeVisible();
    await expect(page.getByTestId("place-card-data-zone")).toContainText(
      "Data zone S01010264",
    );

    const ranges = page.getByTestId("place-card-rent-ranges");
    await expect(ranges).toBeVisible();
    await expect(page.getByTestId("place-card-rent-market")).toContainText(
      "market",
    );
    await expect(page.getByTestId("place-card-rent-proxy")).toContainText(
      "proxy",
    );
    await expect(page.getByTestId("place-card-rent-shadow")).toContainText(
      "shadow",
    );
    await expect(page.getByTestId("place-card-data-zone-grain")).toHaveText(
      "For now, figures are published at Data Zone level only, not for individual parcels, plots or addresses.",
    );

    const layers = page.getByTestId("place-card-layers");
    await expect(layers.getByText("ROS INSPIRE parcels")).toBeVisible();
    await expect(layers.getByText("Vacant and derelict land")).toBeVisible();
    await expect(layers.getByText("Public and Crown Estate land")).toBeVisible();
    await expect(layers.getByText("Common Good", { exact: true })).toBeVisible();
    await expect(layers.getByText("Local-authority land holdings")).toBeVisible();

    await expect(page.getByTestId("place-card-licence-boundaries")).toContainText(
      /Open Government Licence/i,
    );
    await expect(page.getByTestId("place-card-licence-vdl")).toContainText(
      /OGL/i,
    );
    await expect(page.getByTestId("place-card-licence-public_crown")).toContainText(
      /unverified/i,
    );
    await expect(page.getByTestId("place-card-licence-common_good")).toBeVisible();
    await expect(page.getByTestId("place-card-licence-la_holdings")).toBeVisible();
    await expect(page.getByTestId("place-card-licence-sasine_private")).toBeVisible();

    const links = page.getByTestId("place-card-links");
    await expect(links.getByRole("link", { name: /ScotLIS/i })).toBeVisible();
    await expect(
      links.getByRole("link", { name: /Sources and method/i }),
    ).toBeVisible();

    await expect(page.getByTestId("place-card-disclaimer")).toContainText(
      /No £ Annual Ground Rent figures/i,
    );
    await expect(card).not.toContainText("/year");
    await expect(card).not.toContainText(/£\d/);
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
    await expect(page.getByTestId("place-card-licence-boundaries")).toBeVisible();
  });
});
