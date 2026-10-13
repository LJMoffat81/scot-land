import { expect, test, type Page } from "@playwright/test";

import { LEDGER_FIXTURE } from "../lib/ledger";

const FIXTURE = {
  ...LEDGER_FIXTURE,
  source: "api" as const,
};

async function mockLedger(page: Page) {
  await page.route("**/ledger", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE),
    });
  });
  await page.route("**/backend/ledger", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(FIXTURE),
    });
  });
}

async function openPreview(page: Page) {
  await mockLedger(page);
  await page.goto("/ledger-panel");
  await page.getByTestId("ledger-panel").waitFor();
}

async function openOnMap(page: Page) {
  await mockLedger(page);
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByRole("button", { name: "Ledger", exact: true }).click();
  await page.getByTestId("ledger-panel").waitFor();
}

test.describe("LedgerPanel (Natural capital ledger)", () => {
  test.use({ viewport: { width: 1100, height: 900 } });

  test("lists rows 1–10 + nested 1a with one toggle each", async ({ page }) => {
    test.setTimeout(90_000);
    await openPreview(page);

    for (const row of FIXTURE.rows) {
      await expect(page.getByTestId(`ledger-row-${row.id}`)).toBeVisible();
      await expect(page.getByTestId(`ledger-toggle-${row.id}`)).toBeVisible();
      await expect(page.getByTestId(`ledger-amount-${row.id}`)).toHaveText("—");
    }

    await expect(page.getByTestId("ledger-row-1a")).toHaveAttribute(
      "data-nested",
      "true",
    );
    await expect(page.getByTestId("ledger-outside-9")).toContainText(
      /Outside Scottish total/i,
    );

    const body = await page.getByTestId("ledger-panel").innerText();
    // Constraints may say "£0"; rent figures / AGR plot £ must not appear.
    expect(body).not.toMatch(/£\d{2,}/);
    expect(body).not.toMatch(/annual_ground_rent|site_rental_per_sqm/i);
    for (const row of FIXTURE.rows) {
      await expect(page.getByTestId(`ledger-amount-${row.id}`)).not.toHaveText(
        /£/,
      );
    }
  });

  test("Constraints group is £0, changes best use", async ({ page }) => {
    test.setTimeout(90_000);
    await openPreview(page);

    await expect(page.getByTestId("ledger-constraints")).toBeVisible();
    await expect(page.getByTestId("ledger-constraints-rule")).toHaveText(
      /£0, changes best use/i,
    );
    for (const id of ["designations", "flood", "crofting", "lca"]) {
      await expect(
        page.getByTestId(`ledger-constraint-toggle-${id}`),
      ).toBeVisible();
      await expect(
        page.getByTestId(`ledger-constraint-rule-${id}`),
      ).toContainText(/£0, changes best use/i);
    }

    // No GIS layer checklist chrome on the ledger panel.
    await expect(page.getByTestId("layers-panel")).toHaveCount(0);
    await expect(page.getByText("The charge")).toHaveCount(0);
    await expect(page.getByText("Around the land")).toHaveCount(0);
  });

  test("Ledger button on the main map embeds the ledger panel", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openOnMap(page);

    const tools = page.locator("aside.hud-tools");
    await expect(tools.getByTestId("ledger-panel")).toBeVisible();
    await expect(tools.getByTestId("ledger-toggle-1")).toBeVisible();
    await expect(tools.getByTestId("ledger-toggle-1a")).toBeVisible();
    await expect(
      tools.getByTestId("ledger-constraint-toggle-flood"),
    ).toBeVisible();
    await expect(tools.getByTestId("layers-panel")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Layers", exact: true })).toHaveCount(
      0,
    );
  });
});
