import { expect, test, type Page } from "@playwright/test";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator(".hud-layers-btn").waitFor();
}

test.describe("cadastral and public land layers", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("ownership layers appear at the top of the layer control", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await page.locator(".hud-layers-btn").click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByText("Ownership and cadastre")).toBeVisible();
    await expect(panel.getByTestId("layer-cadastral")).toBeVisible();
    await expect(panel.getByTestId("layer-cadastral")).toHaveText(
      "Cadastral parcels",
    );
    await expect(panel.getByTestId("layer-public-land")).toBeVisible();
    await expect(panel.getByTestId("layer-public-land")).toHaveText(
      "Public land",
    );

    // Prominent: ownership section precedes the charge controls
    const ownershipBeforeCharge = await panel.evaluate((el) => {
      const ownership = el.querySelector(".layer-ownership");
      const labels = Array.from(el.querySelectorAll(".layer-select-label"));
      const charge = labels.find((node) => node.textContent?.includes("The charge"));
      if (!ownership || !charge) return false;
      return Boolean(
        ownership.compareDocumentPosition(charge) & Node.DOCUMENT_POSITION_FOLLOWING,
      );
    });
    expect(ownershipBeforeCharge).toBe(true);

    await panel.getByTestId("layer-public-land").click();
    await expect(panel.getByLabel("Public land legend")).toBeVisible();
    await expect(panel.getByText("Forestry and Land Scotland")).toBeVisible();
    await expect(
      panel.getByText(/Registers of Scotland|Scottish Public and Crown/i).first(),
    ).toBeVisible();
  });
});
