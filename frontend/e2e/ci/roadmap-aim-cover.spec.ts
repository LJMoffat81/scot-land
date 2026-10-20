import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * ROADMAP-VISION-1 coverage list — three groups and one status on every row.
 * Auto-discovered by playwright.ci.config.ts (its own spec; not a shared list).
 */

const SECTION_HEADING = "What we aim to cover";

const AIM_ROWS: ReadonlyArray<readonly [string, string, string]> = [
  ["Land (Annual Ground Rent)", "Site rent: homes", "In progress"],
  ["Land (Annual Ground Rent)", "Site rent: business", "Later"],
  ["Land (Annual Ground Rent)", "Rural and farmland values", "Later"],
  ["Land (Annual Ground Rent)", "Planning uplift", "Not started"],
  ["Land (Annual Ground Rent)", "Infrastructure commons uplift", "Later"],
  ["Land (Annual Ground Rent)", "Licences and franchises", "Later"],
  [
    "Land (Annual Ground Rent)",
    "Monopoly and other artificial privileges",
    "Later",
  ],
  ["Natural resource rents", "Minerals and aggregates", "Not started"],
  ["Natural resource rents", "Oil and gas", "Later"],
  ["Natural resource rents", "Water abstraction", "Not started"],
  ["Natural resource rents", "Fishing quota", "Later"],
  ["Natural resource rents", "Fish-farm seabed leases", "Later"],
  ["Natural resource rents", "Onshore wind and hydro sites", "In progress"],
  ["Natural resource rents", "Offshore wind and seabed", "Later"],
  ["Natural resource rents", "Timber", "Not started"],
  ["Natural resource rents", "Radio spectrum", "Later"],
  ["Natural resource rents", "Orbits and airspace", "Later"],
  ["Services of nature", "Carbon in peat and soils", "Not started"],
  [
    "Services of nature",
    "Flood regulation, pollination, clean water, recreation",
    "Not started",
  ],
];

const GROUP_HEADINGS = [
  "Land (Annual Ground Rent)",
  "Natural resource rents",
  "Services of nature",
] as const;

async function assertAimCoverVisible(page: Page) {
  await page.goto("/roadmap");
  const section = page.getByTestId("roadmap-aim");
  await expect(
    section.getByRole("heading", { name: SECTION_HEADING, exact: true }),
  ).toBeVisible();

  for (const heading of GROUP_HEADINGS) {
    await expect(
      section.getByRole("heading", { name: heading, exact: true }),
    ).toBeVisible();
  }

  const rows = section.getByTestId("roadmap-aim-row");
  await expect(rows).toHaveCount(AIM_ROWS.length);

  for (const [, name, status] of AIM_ROWS) {
    const row = rows.filter({
      has: page.getByText(name, { exact: true }),
    });
    await expect(row).toHaveCount(1);
    const statusEl = row.getByTestId("roadmap-aim-status");
    await expect(statusEl).toBeVisible();
    await expect(statusEl).toHaveText(status);
  }
}

test.describe("ROADMAP-VISION-1 coverage at 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("group headings and a status on every row are visible", async ({
    page,
  }) => {
    await assertAimCoverVisible(page);
  });
});

test.describe("ROADMAP-VISION-1 coverage at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("group headings and a status on every row are visible", async ({
    page,
  }) => {
    await assertAimCoverVisible(page);
  });
});
