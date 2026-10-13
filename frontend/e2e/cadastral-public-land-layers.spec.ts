import { expect, test, type Page } from "@playwright/test";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByRole("button", { name: "Ledger", exact: true }).waitFor();
}

test.describe("cadastral and public land layers", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("map HUD opens Natural capital ledger (not GIS layer checklist)", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    // Old Layers GIS pop-out must stay gone (#52); HUD is Natural capital ledger (#53).
    await expect(
      page.getByRole("button", { name: "Layers", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Ledger", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("ledger-panel")).toBeVisible();
    await expect(panel.getByTestId("ledger-toggle-1")).toBeVisible();
    await expect(panel.getByTestId("layers-panel")).toHaveCount(0);
    // SG 2024 public/Crown dashboard stays off the public map (gap / unverified).
    await expect(panel.getByTestId("layer-toggle-public_crown")).toHaveCount(0);
    await expect(panel.getByTestId("layer-public-land")).toHaveCount(0);

    // Public shell withholds council AGR charge / rent £/m² controls (#50).
    await expect(panel.getByTestId("public-agr-withheld")).toBeVisible();
    await expect(panel.getByText("The charge")).toHaveCount(0);
    await expect(panel.getByText("Rent per square metre")).toHaveCount(0);
  });
});
