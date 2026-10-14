import { expect, test, type Page } from "@playwright/test";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByRole("button", { name: "Layers", exact: true }).waitFor();
}

test.describe("cadastral and public land layers", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("map HUD opens Layers drawer (not Ledger)", async ({ page }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await expect(
      page.getByRole("button", { name: "Ledger", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("layers-panel")).toBeVisible();
    await expect(panel.getByTestId("layer-toggle-boundaries")).toBeVisible();
    await expect(panel.getByTestId("ledger-panel")).toHaveCount(0);
    await expect(panel.getByTestId("layer-toggle-public_crown")).toHaveCount(0);
    await expect(panel.getByText("The charge")).toHaveCount(0);
    await expect(panel.getByText("Rent per square metre")).toHaveCount(0);
    const body = await panel.innerText();
    expect(body).not.toContain("£0");
  });
});
