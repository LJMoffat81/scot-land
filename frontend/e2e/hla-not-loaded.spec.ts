import { expect, test, type Page } from "@playwright/test";

/**
 * SHARE-FIX — Housing land audit tiles 503 → Coming soon / disabled,
 * not a raw "Service busy" / unload banner.
 */

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByRole("button", { name: "Layers", exact: true }).waitFor();
}

test.describe("Housing land audit 503 Coming soon", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("map shows Coming soon / disabled — not Service busy", async ({
    page,
  }) => {
    test.setTimeout(90_000);

    await page.route("**/layers/open/hla**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({
          detail:
            "Housing land audit isn't loaded yet. We don't fill gaps with guesses.",
        }),
      });
    });

    await openMap(page);
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    const toggle = panel.getByTestId("layer-toggle-hla");
    await expect(toggle).toBeVisible();
    await toggle.click();

    await expect(page.getByTestId("layer-coming-soon-hla")).toHaveText(
      "Coming soon",
      { timeout: 15_000 },
    );
    await expect(toggle).toBeDisabled();
    await expect(page.getByTestId("map-layer-hla")).toHaveAttribute(
      "data-coming-soon",
      "true",
    );
    await expect(page.getByTestId("layer-notice")).toHaveCount(0);
    await expect(panel).not.toContainText(/Service busy/i);
  });
});
