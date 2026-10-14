import { expect, test } from "@playwright/test";

/**
 * Site-watch PR B item 7 — /data must load and expand every sources group
 * without console errors.
 */
test.describe("/data sources page", () => {
  test("loads and expands every section without console errors", async ({
    page,
  }) => {
    const consoleErrors: string[] = [];
    page.on("console", (msg) => {
      if (msg.type() === "error") {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      consoleErrors.push(String(err));
    });

    await page.route("**/api/catalog.json", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          layers: [
            {
              id: "vdl",
              label: "Vacant and derelict land",
              description: "Survey sites of vacant and derelict land.",
              licence: "OGL-3.0",
              licence_url:
                "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
              source_url: "https://www.gov.scot/",
              group: "spatial",
            },
            {
              id: "repd_onshore_wind",
              label: "Onshore wind",
              description: "Onshore wind planning sites.",
              licence: "OGL-3.0",
              licence_url:
                "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
              source_url: "https://www.gov.uk/",
              ledger_row: "3",
            },
            {
              id: "nfi",
              label: "National Forest Inventory",
              description: "Woodland of half a hectare or more.",
              licence: "OGL-3.0",
              licence_url:
                "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
              source_url: "https://www.forestresearch.gov.uk/",
              ledger_row: "1",
            },
            {
              id: "sssi",
              label: "SSSI",
              description: "Sites of Special Scientific Interest.",
              licence: "OGL-3.0",
              licence_url:
                "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
              source_url: "https://opendata.nature.scot/",
              ledger_role: "constraint",
            },
          ],
        }),
      });
    });

    await page.goto("/data");
    await expect(page.getByRole("heading", { name: "Data & sources" })).toBeVisible();
    await expect(page.getByTestId("data-sources-groups")).toBeVisible();

    const groups = page.locator("[data-testid^='data-sources-group-']");
    const count = await groups.count();
    expect(count).toBeGreaterThan(0);

    for (let i = 0; i < count; i += 1) {
      const group = groups.nth(i);
      await group.locator("summary").click();
      await expect(group).toHaveAttribute("open", "");
      await expect(group.locator("table tbody tr").first()).toBeVisible();
    }

    expect(
      consoleErrors,
      `console errors on /data:\n${consoleErrors.join("\n")}`,
    ).toEqual([]);
  });
});
