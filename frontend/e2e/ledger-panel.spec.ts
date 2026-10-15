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

test.describe("LedgerPanel (internal preview only)", () => {
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
      /outside the Scottish land total/i,
    );

    const body = await page.getByTestId("ledger-panel").innerText();
    expect(body).not.toMatch(/£\d/);
    expect(body).not.toContain("£0");
    expect(body).not.toMatch(/ECONOMIC_RULES|Placeholders are not/i);
    for (const row of FIXTURE.rows) {
      await expect(page.getByTestId(`ledger-amount-${row.id}`)).not.toHaveText(
        /£/,
      );
    }
  });

  test("Constraints group uses public constraint wording", async ({ page }) => {
    test.setTimeout(90_000);
    await openPreview(page);

    await expect(page.getByTestId("ledger-constraints")).toBeVisible();
    await expect(page.getByTestId("ledger-constraints-rule")).toHaveText(
      /Constraint: changes best use, adds no value/i,
    );
    for (const id of ["designations", "flood", "crofting", "lca"]) {
      await expect(
        page.getByTestId(`ledger-constraint-toggle-${id}`),
      ).toBeVisible();
    }
  });

  test("main map no longer embeds LedgerPanel", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await expect(
      page.getByRole("button", { name: "Ledger", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const tools = page.locator("aside.hud-tools");
    await expect(tools.getByTestId("layers-panel")).toBeVisible();
    await expect(tools.getByTestId("ledger-panel")).toHaveCount(0);
    // SW-044: chip key is in the left legend, not the Layers drawer.
    await expect(tools.getByTestId("evidence-tag-legend")).toHaveCount(0);
  });
});
