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
      status: "gap",
      label: "Public and Crown Estate land",
      description:
        "SG 2024 dashboard only — licence unverified/not open. Hidden from the public map.",
      licence: "unverified/not open",
      source_url: "https://www.arcgis.com/apps/dashboards/example",
    },
    {
      id: "hydro_sites",
      group: "spatial",
      status: "live",
      label: "Hydropower sites (SEPA CAR)",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      source_url:
        "https://www.data.gov.uk/dataset/5750f8e5-d51b-4e75-a8d6-403a0d1ded81/hydropower_sites",
      value_tier: "proxy",
      publication_status: "ok",
    },
    {
      id: "sepa_car",
      group: "spatial",
      status: "live",
      label: "SEPA CAR licences",
      licence: "OGL-3.0",
      licence_url:
        "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
      source_url: "https://www.sepa.org.uk/environment/environmental-data/",
      value_tier: "market",
      publication_status: "ok",
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
      description:
        "Linked registers. Highland FeatureServers licence unconfirmed (link-only). Fife OS INSPIRE EUL linked only. No national open spatial layer.",
      licence:
        "unconfirmed (Highland linked only); OS Public Sector End User Licence - INSPIRE (Fife)",
      source_url:
        "https://www.highland.gov.uk/community-support-development/common-good-asset-register",
      ledger_role: "ownership-context",
      ledger_row: null,
      ui_surface: "ledger",
    },
    {
      id: "crofting_register",
      group: "ownership",
      status: "linked",
      label: "Crofting Register (RoC)",
      description:
        "OGL Register of Crofts tables. Map extents on RoS Crofting Register.",
      licence: "OGL-3.0",
      source_url: "https://www.crofting.scotland.gov.uk/open-data/",
    },
    {
      id: "common_grazings",
      group: "ownership",
      status: "linked",
      label: "Common grazings",
      description:
        "OGL List of Grazings. No national open polygon overlay.",
      licence: "OGL-3.0",
      source_url: "https://www.crofting.scotland.gov.uk/open-data/",
    },
  ],
  tools: [],
};

async function mockCatalog(page: Page) {
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
      "OGL",
    );
    await expect(page.getByTestId("layer-source-boundaries")).toContainText(
      "Registers of Scotland",
    );
    await expect(page.getByTestId("layer-toggle-public_crown")).toHaveCount(0);
    await expect(page.getByTestId("layer-licence-public_crown")).toContainText(
      "unverified/not open",
    );
    // ScotWind/INTOG is ledger row 4 (ui_surface=ledger) — not a LayersPanel toggle.
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
    await expect(
      page.getByTestId("layer-unavailable-crofting_register"),
    ).toContainText(/OGL|RoS|Register|extents/i);
    await expect(
      page.getByTestId("layer-licence-crofting_register"),
    ).toContainText("OGL-3.0");
    await expect(
      page.getByTestId("layer-unavailable-common_grazings"),
    ).toContainText(/grazing|polygon|OGL|national/i);
    await expect(
      page.getByTestId("layer-licence-common_grazings"),
    ).toContainText("OGL-3.0");

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

  test("main map HUD uses ledger, not the catalog LayersPanel", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await expect(
      page.getByRole("button", { name: "Layers", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Ledger", exact: true }).click();
    const tools = page.locator("aside.hud-tools");
    await expect(tools.getByTestId("ledger-panel")).toBeVisible();
    await expect(tools.getByTestId("layers-panel")).toHaveCount(0);
  });
});

