import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean } from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * API-TEASER-1 — /developers/api is a short coming note.
 * Widths 1280 and 390. No skips. Console errors fail.
 */

const TEASER_H1 = "Developer API and bulk data: later";
// Case-insensitive months/years; May excludes modal "may be" (paid-services line).
const DATE_RE =
  /\b(?:19|20)\d{2}\b|\b(?:January|February|March|April|June|July|August|September|October|November|December)\b|\bMay\b(?!\s+be\b)/i;

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};





async function stubQuiet(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(/\/health/i.test(url) ? HEALTH_OK : {}),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await stubLayersAddQuiet(page);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`API-TEASER-1 ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("teaser has register interest and no paths, prices, or dates", async ({
      page,
    }) => {
      const gate = attachConsoleGate(page);
      await stubQuiet(page);
      await page.goto("/developers/api");

      const teaser = page.getByTestId("api-teaser");
      await expect(teaser).toBeVisible();
      await expect(teaser.getByRole("heading", { level: 1 })).toHaveText(
        TEASER_H1,
      );
      await expect(teaser).toContainText(
        "We plan to offer a developer API and bulk downloads. They will cover:",
      );
      await expect(teaser).toContainText(
        "Land rent estimates for each Data Zone, with ranges and quality labels",
      );
      await expect(teaser).toContainText(
        "Map layers we use, where licences allow",
      );
      await expect(teaser).toContainText(
        "Sources and method notes for every figure",
      );
      await expect(teaser).toContainText(
        "The map stays free to use. Bulk data and the API may be paid services later.",
      );
      await expect(page.getByTestId("api-register-interest")).toHaveCount(0);
      await expect(page.getByRole("link", { name: "Register interest" })).toHaveCount(0);
      await expect(page.locator('a[href="/about#contact"]')).toHaveCount(0);

      const html = await teaser.innerHTML();
      expect(html, "no /api/ paths").not.toContain("/api/");
      expect(html, "no £").not.toContain("£");
      expect(html, "no free tier").not.toMatch(/free tier/i);
      const text = await teaser.innerText();
      expect(text, "no year or month dates").not.toMatch(DATE_RE);

      const apiLinks = page.locator('a[href*="/api/"]');
      await expect(apiLinks).toHaveCount(0);
    assertConsoleClean(gate);
    });
  });
}
