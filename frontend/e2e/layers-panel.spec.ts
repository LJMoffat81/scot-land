import { expect, test, type Page } from "@playwright/test";

const FIXTURE_CATALOG = {
  version: 1,
  layers: [
    {
      id: "agr_value",
      group: "value",
      status: "live",
      label: "AGR value",
      description: "Modelled plot AGR",
      licence: "Research estimate",
    },
    {
      id: "boundaries",
      group: "spatial",
      status: "live",
      label: "ROS INSPIRE parcels",
      description: "Registered extents",
      licence: "Open Government Licence v3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      source_url: "https://www.ros.gov.uk/open-data",
      attribution:
        "Reproduced with the permission of Registers of Scotland. Contains OS data © Crown copyright and database right 2026",
    },
    {
      id: "cell_grid",
      group: "value",
      status: "live",
      label: "Scot-LAND squares",
      licence: "Not published",
    },
    {
      id: "data_zones",
      group: "spatial",
      status: "live",
      label: "Data zones",
      licence: "OGL-3.0",
    },
    {
      id: "vdl",
      group: "spatial",
      status: "live",
      label: "Vacant and derelict land",
      licence: "OGL-3.0",
    },
    {
      id: "hydro_sites",
      group: "value",
      status: "live",
      label: "Hydropower sites",
      licence: "OGL-3.0",
    },
    {
      id: "sepa_car",
      group: "value",
      status: "live",
      label: "SEPA CAR",
      licence: "OGL-3.0",
    },
    {
      id: "public_crown",
      group: "ownership",
      status: "gap",
      label: "Public and Crown Estate land",
      licence: "unverified/not open",
      description: "Licence unverified — gap shown",
    },
    {
      id: "la_holdings",
      group: "ownership",
      status: "gap",
      label: "Local-authority land holdings",
      licence: "Not openly licensed for this portal",
      description: "National LA ownership layer is a gap / unavailable",
    },
    {
      id: "common_good",
      group: "ownership",
      status: "linked",
      label: "Common Good",
      licence: "Linked registers; Highland licence unconfirmed",
      description: "Linked registers; no national open layer",
    },
    {
      id: "crofting_register",
      group: "ownership",
      status: "linked",
      label: "Crofting register",
      licence: "OGL-3.0",
      description: "OGL lists; RoS register map for extents",
    },
    {
      id: "common_grazings",
      group: "ownership",
      status: "linked",
      label: "Common grazings",
      licence: "OGL-3.0",
      description: "OGL grazings list; no national polygon",
    },
    {
      id: "scotwind_intog",
      group: "value",
      status: "live",
      label: "ScotWind / INTOG",
      licence: "OGL-3.0",
      ledger_role: "ledger-row",
      ui_surface: "ledger",
    },
  ],
};

async function mockCatalog(page: Page) {
  await page.route("**/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE_CATALOG),
    });
  });
}

async function openPanel(page: Page) {
  await mockCatalog(page);
  await page.goto("/layers-panel");
  await page.getByTestId("layers-panel").waitFor();
}

test.describe("LayersPanel (catalog-driven, Dev/QA /layers-panel)", () => {
  test.use({ viewport: { width: 1100, height: 900 } });

  test("every live catalog layer has a toggle with source and licence", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openPanel(page);

    const liveIds = FIXTURE_CATALOG.layers
      .filter((layer) => layer.status === "live")
      .filter(
        (layer) =>
          !(
            "ledger_role" in layer && layer.ledger_role
          ) &&
          !(
            "ui_surface" in layer && layer.ui_surface === "ledger"
          ),
      )
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
      "Open Government Licence v3.0",
    );
    await expect(page.getByTestId("layer-source-boundaries")).toContainText(
      "Registers of Scotland",
    );
    await expect(page.getByTestId("layer-toggle-public_crown")).toHaveCount(0);
    await expect(page.getByTestId("layer-licence-public_crown")).toContainText(
      "unverified/not open",
    );
  });

  test("gap and linked rows show honest unavailable copy; no tax / plot AGR £", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openPanel(page);

    await expect(page.getByTestId("layer-toggle-public_crown")).toHaveCount(0);
    await expect(page.getByTestId("layer-toggle-la_holdings")).toHaveCount(0);
    await expect(page.getByTestId("layer-unavailable-la_holdings")).toContainText(
      /gap|unavailable|not scraped/i,
    );
    await expect(page.getByTestId("layer-toggle-common_good")).toHaveCount(0);
    await expect(
      page.getByTestId("layer-unavailable-common_good"),
    ).toContainText(/linked|unconfirmed|Highland|no national/i);

    await page.getByTestId("layer-toggle-agr_value").click();
    await expect(page.getByTestId("layer-unavailable-agr_value")).toContainText(
      /not on the public map|yield calibration|tax scenarios/i,
    );

    await expect(page.getByTestId("layers-panel")).not.toContainText(
      /LVT calculator|replace_full_basket|scenario calculators/i,
    );
    await expect(page.getByRole("button", { name: /scenario/i })).toHaveCount(0);
    const body = await page.getByTestId("layers-panel").innerText();
    expect(body).not.toMatch(/£\d/);
  });

  test("main map HUD uses Layers drawer with redesign groups", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await expect(
      page.getByRole("button", { name: "Ledger", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const tools = page.locator("aside.hud-tools");
    await expect(tools.getByTestId("layers-panel")).toBeVisible();
    await expect(tools.getByTestId("layers-group-land")).toBeVisible();
    await expect(tools.getByTestId("layers-group-boundaries")).toBeVisible();
    await expect(tools.getByTestId("ledger-panel")).toHaveCount(0);
  });
});
