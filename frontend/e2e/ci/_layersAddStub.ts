import type { Page } from "@playwright/test";

const EMPTY_FC = { type: "FeatureCollection", features: [] };

/**
 * Quiet LAYERS-ADD responses for map chrome specs.
 * Vacant land stays listed (it already paints). New Improvement Service
 * extracts stay absent. Viewport shapes are empty until a spec supplies them.
 * Registered last so it wins over a backend catch-all 404.
 */
export async function stubLayersAddQuiet(
  page: Page,
  spatialHubLayerIds: readonly string[] = ["vdl"],
) {
  await page.route("**/layers/add/tiles-manifest**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 1,
        sources: spatialHubLayerIds.map((id) => ({
          layer_id: id,
          display_id: id,
        })),
      }),
    });
  });
  await page.route("**/layers/add/viewport/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
}
