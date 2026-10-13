import { expect, test, type Page } from "@playwright/test";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByRole("button", { name: "Ledger", exact: true }).waitFor();
}

test.describe("SVDLS vacant and derelict layer", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("map HUD ledger replaces vacant GIS checklist controls", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await expect(
      page.getByRole("button", { name: "Layers", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Ledger", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("ledger-panel")).toBeVisible();
    await expect(panel.getByTestId("layer-toggle-vdl")).toHaveCount(0);
    await expect(panel.getByText("Around the land")).toHaveCount(0);
    await expect(panel.getByTestId("ledger-constraints-rule")).toContainText(
      /£0, changes best use/i,
    );
    // Public shell withholds council AGR charge controls (#50).
    await expect(panel.getByTestId("public-agr-withheld")).toBeVisible();
    await expect(panel.getByText("The charge")).toHaveCount(0);
  });
});
