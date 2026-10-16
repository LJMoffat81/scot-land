import { expect, test, type Page } from "@playwright/test";

/**
 * LAYERS-ADD-1a — Housing land supply / HLA is licence-gated OFF.
 * No live Layers row; visitor status is on /roadmap#map-layers.
 */

async function stubQuietBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ version: 2, layers: [] }),
      });
      return;
    }
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ status: "ok" }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ type: "FeatureCollection", features: [] }),
    });
  });
}

test.describe("Housing land audit gated (LAYERS-ADD-1a)", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("no HLA Layers toggle; roadmap shows Waiting for permission", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await stubQuietBackend(page);

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const panel = page.locator("aside.hud-tools");
    await expect(panel.getByTestId("layer-toggle-hla")).toHaveCount(0);
    await expect(panel).not.toContainText("Housing land audit");

    await page.goto("/roadmap#map-layers");
    await expect(page.getByTestId("roadmap-waiting-hls")).toBeVisible();
    await expect(page.getByTestId("roadmap-waiting-status-hls")).toContainText(
      "Waiting for permission to use the data",
    );
  });
});
