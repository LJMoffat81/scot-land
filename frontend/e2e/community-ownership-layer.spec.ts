import { expect, test, type Page } from "@playwright/test";

async function openMap(page: Page) {
  await page.goto("/?community=1");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator(".hud-layers-btn").waitFor();
}

test.describe("community ownership layer", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("community ownership is ownership-context via ledger shell (not LayersPanel)", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await page.locator(".hud-layers-btn").click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("public-agr-withheld")).toBeVisible();
    // No LayersPanel chip for community ownership after ledger retarget
    await expect(panel.getByTestId("layer-community-ownership")).toHaveCount(0);
    await expect(
      panel.getByTestId("layer-community-ownership-credit"),
    ).toBeVisible();
    await expect(
      panel.getByText(/Community Ownership in Scotland 2024/i).first(),
    ).toBeVisible();
    await expect(
      panel.getByText(/Open Government Licence|OGL/i).first(),
    ).toBeVisible();
    await expect(page).toHaveURL(/community=1/);
  });
});
