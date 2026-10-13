import { expect, test } from "@playwright/test";

/**
 * Public builds omit NEXT_PUBLIC_ENABLE_INTERNAL_UI=1, so the tax-scenario
 * panel must 404 (same gate as /ledger-panel).
 */
test.describe("Internal tax scenario gate", () => {
  test("public site cannot reach /tax-scenario-panel", async ({ page }) => {
    test.setTimeout(60_000);
    const res = await page.goto("/tax-scenario-panel", {
      waitUntil: "domcontentloaded",
    });
    expect(res).not.toBeNull();
    expect(res!.status()).toBe(404);
    await expect(page.getByTestId("internal-tax-scenario")).toHaveCount(0);
  });

  test("legacy /internal/tax-scenario path is not a public route", async ({
    page,
  }) => {
    test.setTimeout(60_000);
    const res = await page.goto("/internal/tax-scenario", {
      waitUntil: "domcontentloaded",
    });
    expect(res).not.toBeNull();
    expect(res!.status()).toBe(404);
    await expect(page.getByTestId("internal-tax-scenario")).toHaveCount(0);
  });
});
