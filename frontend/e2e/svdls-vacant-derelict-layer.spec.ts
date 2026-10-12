import { expect, test, type Page } from "@playwright/test";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator(".hud-layers-btn").waitFor();
}

test.describe("SVDLS vacant and derelict layer", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("vacant and derelict sits in ownership with legend and credits", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await page.locator(".hud-layers-btn").click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByText("Ownership and cadastre")).toBeVisible();
    await expect(panel.getByTestId("layer-vdl")).toBeVisible();
    await expect(panel.getByTestId("layer-vdl")).toHaveText(
      "Vacant and derelict",
    );

    // Promoted: ownership section precedes the charge controls; VDL is not under Around the land
    const ownershipBeforeCharge = await panel.evaluate((el) => {
      const ownership = el.querySelector(".layer-ownership");
      const labels = Array.from(el.querySelectorAll(".layer-select-label"));
      const charge = labels.find((node) =>
        node.textContent?.includes("The charge"),
      );
      if (!ownership || !charge) return false;
      return Boolean(
        ownership.compareDocumentPosition(charge) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      );
    });
    expect(ownershipBeforeCharge).toBe(true);

    const aroundFold = panel.locator("details.layer-fold").filter({
      hasText: "Around the land",
    });
    await expect(aroundFold.getByTestId("layer-vdl")).toHaveCount(0);

    await panel.getByTestId("layer-vdl").click();
    await expect(
      panel.getByLabel("Vacant and derelict legend"),
    ).toBeVisible();
    await expect(panel.getByText("Vacant Land", { exact: true })).toBeVisible();
    await expect(panel.getByText("Derelict", { exact: true })).toBeVisible();
    await expect(
      panel.getByText(/Scottish Vacant and Derelict Land Survey/i).first(),
    ).toBeVisible();
    await expect(
      panel.getByText(/Improvement Service|Open Government Licence|OGL/i).first(),
    ).toBeVisible();
  });
});
