import { expect, test, type Page } from "@playwright/test";

/**
 * LAYERS-ADD-1 — registry rows default OFF; LDP/HLS on roadmap; no £; banned names.
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};
const EMPTY_FC = { type: "FeatureCollection", features: [] };

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ version: 2, layers: [] }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
}

const NEW_OFF_IDS = [
  "flood",
  "contaminated_land",
  "deprivation",
  "conservation",
  "listed",
  "stops",
  "green_belt",
  "school_catchments",
] as const;

for (const width of [1280, 390] as const) {
  test.describe(`LAYERS-ADD-1 @ ${width}`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 900 } });

    test("new layers default off; gated ids absent; roadmap waiting rows", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const consoleErrors: string[] = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });
      page.on("pageerror", (err) => consoleErrors.push(String(err)));

      await stubMapBackend(page);
      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor();
      await page.getByRole("button", { name: "Layers", exact: true }).click();
      const panel = page.locator("aside.hud-tools");

      for (const id of NEW_OFF_IDS) {
        const toggle = panel.getByTestId(`layer-toggle-${id}`);
        await expect(toggle).toBeVisible();
        await expect(toggle).toHaveAttribute("aria-checked", "false");
      }
      await expect(panel.getByTestId("layer-toggle-hla")).toHaveCount(0);
      await expect(panel.getByTestId("layer-toggle-ldp")).toHaveCount(0);
      await expect(panel).not.toContainText(/£/);
      await expect(panel).not.toContainText(/\bSIMD\b/);
      await expect(panel).not.toContainText(/\bNaPTAN\b/);

      await page.goto("/roadmap#map-layers");
      await expect(page.getByTestId("roadmap-waiting-ldp")).toBeVisible();
      await expect(page.getByTestId("roadmap-waiting-hls")).toBeVisible();
      await expect(page.getByTestId("roadmap-waiting-status-ldp")).toContainText(
        "Waiting for permission to use the data",
      );
      await expect(page.locator("main")).not.toContainText(/£/);
      await expect(page.locator("main")).not.toContainText(/sepa_frm_maps/i);

      expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
    });
  });
}
