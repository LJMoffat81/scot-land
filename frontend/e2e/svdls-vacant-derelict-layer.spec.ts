import { expect, test, type Page } from "@playwright/test";

const FIXTURE_CATALOG = {
  version: 2,
  brief: "docs/PLATFORM.md",
  principle: "AGR first",
  layers: [
    {
      id: "agr_value",
      group: "value",
      status: "live",
      label: "Annual Ground Rent",
    },
    {
      id: "boundaries",
      group: "spatial",
      status: "live",
      label: "ROS INSPIRE parcels",
    },
    {
      id: "cell_grid",
      group: "value",
      status: "live",
      label: "W3W cell grid",
    },
    {
      id: "vdl",
      group: "spatial",
      status: "live",
      label: "Vacant and derelict land",
      licence: "OGL-3.0",
      source_url:
        "https://www.gov.scot/publications/the-scottish-vacant-and-derelict-land-survey-site-register/",
    },
    {
      id: "public_crown",
      group: "ownership",
      status: "live",
      label: "Public and Crown Estate land",
    },
  ],
  tools: [],
};

async function openMap(page: Page) {
  await page.route("**/layers/catalog", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_CATALOG),
    });
  });
  await page.route("**/backend/layers/catalog", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_CATALOG),
    });
  });
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByRole("button", { name: "Layers", exact: true }).waitFor();
}

test.describe("SVDLS vacant and derelict layer", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("vacant and derelict sits in catalog with legend and credits", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("layers-panel")).toBeVisible();
    await expect(panel.getByTestId("layer-toggle-vdl")).toBeVisible();

    // Catalog panel precedes the charge controls; VDL is not under Around the land
    const catalogBeforeCharge = await panel.evaluate((el) => {
      const catalog = el.querySelector("[data-testid='layers-panel']");
      const labels = Array.from(el.querySelectorAll(".layer-select-label"));
      const charge = labels.find((node) =>
        node.textContent?.includes("The charge"),
      );
      if (!catalog || !charge) return false;
      return Boolean(
        catalog.compareDocumentPosition(charge) &
          Node.DOCUMENT_POSITION_FOLLOWING,
      );
    });
    expect(catalogBeforeCharge).toBe(true);

    const aroundFold = panel.locator("details.layer-fold").filter({
      hasText: "Around the land",
    });
    await expect(aroundFold.getByTestId("layer-toggle-vdl")).toHaveCount(0);

    await panel.getByTestId("layer-toggle-vdl").click();
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
