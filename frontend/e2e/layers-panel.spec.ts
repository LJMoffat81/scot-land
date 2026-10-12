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
      description: "Residual site-value AGR on Scot-LAND squares and notional plots.",
    },
    {
      id: "boundaries",
      group: "spatial",
      status: "live",
      label: "ROS INSPIRE parcels",
      description: "Registered cadastral extents (geometry only — no owners).",
      licence: "OGL / INSPIRE (Crown)",
      source_url: "https://www.ros.gov.uk/open-data",
    },
    {
      id: "cell_grid",
      group: "value",
      status: "live",
      label: "Scot-LAND squares",
      minzoom: 12,
    },
    {
      id: "vdl",
      group: "spatial",
      status: "live",
      label: "Vacant and derelict land",
      licence: "OGL-3.0",
      source_url: "https://www.gov.scot/publications/svdls",
    },
    {
      id: "public_crown",
      group: "ownership",
      status: "live",
      label: "Public and Crown Estate land",
      licence: "OGL-3.0",
      source_url: "https://www.arcgis.com/apps/dashboards/example",
    },
    {
      id: "la_holdings",
      group: "ownership",
      status: "gap",
      label: "Local-authority land holdings",
      description: "Not an open public layer. Shown as a gap, not scraped.",
      source_url: "https://data.spatialhub.scot/dataset/land_ownership-is",
    },
    {
      id: "common_good",
      group: "ownership",
      status: "linked",
      label: "Common Good registers",
      description: "Linked registers. No national open spatial layer.",
    },
  ],
  tools: [],
};

async function openPanel(page: Page) {
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
  await page.goto("/layers-panel");
  await page.getByTestId("layers-panel").waitFor();
}

test.describe("LayersPanel (catalog-driven)", () => {
  test.use({ viewport: { width: 1100, height: 900 } });

  test("every live catalog layer has a toggle with source and licence", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openPanel(page);

    const liveIds = FIXTURE_CATALOG.layers
      .filter((layer) => layer.status === "live")
      .map((layer) => layer.id);

    for (const id of liveIds) {
      await expect(page.getByTestId(`layer-toggle-${id}`)).toBeVisible();
      await expect(page.getByTestId(`layer-source-${id}`)).toBeVisible();
      await expect(page.getByTestId(`layer-licence-${id}`)).toBeVisible();
    }

    await expect(page.getByTestId("layer-toggle-boundaries")).toHaveText(
      /ROS INSPIRE parcels/i,
    );
    await expect(page.getByTestId("layer-licence-boundaries")).toContainText(
      "OGL",
    );
    await expect(page.getByTestId("layer-source-boundaries")).toContainText(
      "Registers of Scotland",
    );
    await expect(page.getByTestId("layer-licence-public_crown")).toContainText(
      "OGL-3.0",
    );
  });

  test("gap and linked rows show honest unavailable copy; no tax / plot AGR £", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openPanel(page);

    await expect(page.getByTestId("layer-toggle-la_holdings")).toHaveCount(0);
    await expect(page.getByTestId("layer-unavailable-la_holdings")).toContainText(
      /gap|unavailable|not scraped/i,
    );
    await expect(
      page.getByTestId("layer-unavailable-common_good"),
    ).toContainText(/linked|no national/i);

    await page.getByTestId("layer-toggle-agr_value").click();
    await expect(page.getByTestId("layer-unavailable-agr_value")).toContainText(
      /not on the public map|yield calibration|tax scenarios/i,
    );

    // No scenario calculator UI — only the honest "not shown" disclaimer may mention tax.
    await expect(page.getByTestId("layers-panel")).not.toContainText(
      /LVT calculator|replace_full_basket|scenario calculators/i,
    );
    await expect(page.getByRole("button", { name: /scenario/i })).toHaveCount(0);
    const body = await page.getByTestId("layers-panel").innerText();
    expect(body).not.toMatch(/£\d/);
  });
});
