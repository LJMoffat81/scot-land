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
      group: "ownership",
      status: "live",
      label: "ROS INSPIRE parcels",
      licence: "OGL / INSPIRE (Crown)",
      source_url: "https://www.ros.gov.uk/open-data",
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
    },
    {
      id: "public_crown",
      group: "ownership",
      status: "gap",
      label: "Public and Crown Estate land",
      licence: "unverified/not open",
      source_url: "https://www.arcgis.com/apps/dashboards/example",
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

test.describe("cadastral and public land layers", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("ownership layers appear at the top of the layer control", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel).toBeVisible();
    await expect(panel.getByTestId("layers-panel")).toBeVisible();
    await expect(panel.getByTestId("layers-group-ownership")).toBeVisible();
    await expect(panel.getByTestId("layer-toggle-boundaries")).toBeVisible();
    // SG 2024 public/Crown dashboard: licence unverified/not open — no public toggle
    await expect(panel.getByTestId("layer-toggle-public_crown")).toHaveCount(0);
    await expect(panel.getByTestId("layer-public-land")).toHaveCount(0);

    // Catalog panel precedes the charge controls
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

    await expect(panel.getByText(/Registers of Scotland/i).first()).toBeVisible();
  });
});
