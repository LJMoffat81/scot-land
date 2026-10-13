import { expect, test } from "@playwright/test";

/**
 * Public builds omit NEXT_PUBLIC_ENABLE_INTERNAL_UI=1, so /internal/* must 404.
 * Playwright webServer does not enable that flag (see playwright.config.ts).
 */
test.describe("Internal tax scenario gate", () => {
  test("public site cannot reach /internal/tax-scenario", async ({ page }) => {
    test.setTimeout(60_000);
    const res = await page.goto("/internal/tax-scenario", {
      waitUntil: "domcontentloaded",
    });
    expect(res).not.toBeNull();
    expect(res!.status()).toBe(404);
    await expect(page.getByTestId("internal-tax-scenario")).toHaveCount(0);
  });
});
