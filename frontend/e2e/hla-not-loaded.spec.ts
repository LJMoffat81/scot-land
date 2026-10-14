import { expect, test, type Page } from "@playwright/test";

const HLA_NOT_LOADED =
  "Housing land audit isn't loaded yet. We don't fill gaps with guesses.";

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.getByRole("button", { name: "Layers", exact: true }).waitFor();
}

test.describe("Housing land audit 503 notice", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("map shows exact HLA unload line — not Service busy", async ({
    page,
  }) => {
    test.setTimeout(90_000);

    await page.route("**/layers/open/hla**", async (route) => {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: HLA_NOT_LOADED }),
      });
    });

    await openMap(page);
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel.getByTestId("layer-toggle-hla")).toBeVisible();
    await panel.getByTestId("layer-toggle-hla").click();

    const notice = page.getByTestId("layer-notice");
    await expect(notice).toBeVisible({ timeout: 15_000 });
    await expect(notice).toHaveText(HLA_NOT_LOADED);
    await expect(notice).not.toContainText(/Service busy/i);
    await expect(notice).not.toContainText(/overlay/i);
    await expect(notice).not.toContainText(/\.env/);
  });
});
