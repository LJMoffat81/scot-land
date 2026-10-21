import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";
import { assertConsoleClean, attachConsoleGate, ensureLayersGroupOpen, ensureMapZoomAtLeast, openLayers, openMap, registerOpenFreeMapFontStub, stubMapCardsBackend } from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

/**
 * SEPA-FLOOD-1 — Data Zone choropleth.
 * Empty table: the flood switch is absent (LAYERS-FIX-1).
 * Loaded fixture: the switch draws at a lowland view.
 */

const LEGEND =
  "Share of this area in SEPA's medium-likelihood flood extent (today's climate)";
const CREDIT =
  "©SEPA 2025; this SEPA product is licensed under the Open Government Licence version 3.0.";

function floodBody(url: string): string {
  const parsed = new URL(url);
  const bbox = (parsed.searchParams.get("bbox") || "-4.30,55.84,-4.22,55.88")
    .split(",")
    .map(Number);
  const [west, south, east, north] = bbox;
  const lngPad = ((east ?? -4.2) - (west ?? -4.3)) * 0.15;
  const latPad = ((north ?? 55.88) - (south ?? 55.84)) * 0.15;
  return JSON.stringify({
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {
          data_zone: "S01014567",
          pct_area_river: 50,
          pct_area_coastal: 0,
          pct_area_surface: 12,
          source_version: "v3.0",
        },
        geometry: {
          type: "Polygon",
          coordinates: [
            [
              [(west ?? -4.3) + lngPad, (south ?? 55.84) + latPad],
              [(east ?? -4.2) - lngPad, (south ?? 55.84) + latPad],
              [(east ?? -4.2) - lngPad, (north ?? 55.88) - latPad],
              [(west ?? -4.3) + lngPad, (north ?? 55.88) - latPad],
              [(west ?? -4.3) + lngPad, (south ?? 55.84) + latPad],
            ],
          ],
        },
      },
    ],
    meta: { loaded: true, ok: true },
  });
}

async function stubFloodLoaded(page: Page) {
  await page.route("**/layers/open/flood-dz**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: floodBody(route.request().url()),
    });
  });
}

for (const width of [1280, 390] as const) {
  test.describe(`SEPA-FLOOD-1 @ ${width}`, () => {
    test.use({ viewport: { width, height: width === 390 ? 844 : 900 } });

    test("empty table hides the flood switch", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await openLayers(page);
      await ensureLayersGroupOpen(page, "land");
      await expect(page.getByTestId("layer-toggle-flood")).toHaveCount(0);
      await expect(page.getByTestId("layers-panel")).not.toContainText(/£/);
      assertConsoleClean(gate);
    });

    test("loaded fixture draws at a lowland view", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { floodDzLoaded: true });
      await stubFloodLoaded(page);
      await openMap(page, "/?lat=55.86&lng=-4.25");
      await expect
        .poll(async () => page.locator("#map").getAttribute("data-framed"))
        .toBe("1");
      await ensureMapZoomAtLeast(page, 11);
      await openLayers(page);
      await ensureLayersGroupOpen(page, "land");
      const toggle = page.getByTestId("layer-toggle-flood");
      await expect(toggle).toBeVisible();
      await expect(toggle).toContainText("Flood risk (SEPA)");
      await expect(page.getByTestId("flood-kind-river")).toBeVisible();
      await expect(page.getByTestId("flood-kind-coastal")).toBeVisible();
      await expect(page.getByTestId("flood-kind-surface")).toBeVisible();
      await toggle.click();
      await expect(page.getByTestId("layer-flood-extent-legend")).toHaveText(
        LEGEND,
      );
      await expect(page.getByTestId("layer-source-caption-flood")).toHaveText(
        CREDIT,
      );
      await expect
        .poll(
          async () =>
            page.evaluate(() => {
              const map = (
                window as unknown as {
                  __map?: {
                    getLayer(id: string): unknown;
                    queryRenderedFeatures(opts: { layers: string[] }): unknown[];
                  };
                }
              ).__map;
              if (!map?.getLayer("sepa_nfra_grid-add-fill")) return 0;
              return map.queryRenderedFeatures({
                layers: ["sepa_nfra_grid-add-fill"],
              }).length;
            }),
          { timeout: 20_000 },
        )
        .toBeGreaterThan(0);
      await expect(page.getByTestId("layers-panel")).not.toContainText(/£/);
      assertConsoleClean(gate);
    });
  });
}
