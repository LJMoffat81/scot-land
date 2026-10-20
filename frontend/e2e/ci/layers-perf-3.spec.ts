import { expect, test, type Page } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  ensureLayersGroupOpen,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

/**
 * LAYERS-PERF-3 — a size-capped oil and gas body shows the zoom hint
 * and is not kept for the rest of the page.
 */

const HIDDEN_OIL = JSON.stringify({
  type: "FeatureCollection",
  features: [],
  meta: {
    ok: true,
    hidden_below_zoom: true,
    hint: "Zoom in to see oil and gas",
  },
});

const OUTLINE = {
  type: "Feature",
  properties: { name: "Highland site" },
  geometry: {
    type: "Polygon",
    coordinates: [
      [
        [-5.4, 56.8],
        [-4.1, 57.05],
        [-4.6, 57.7],
        [-5.6, 57.35],
        [-5.4, 56.8],
      ],
    ],
  },
};

async function jump(page: Page, zoom: number) {
  await page.evaluate((z) => {
    const map = (
      window as unknown as {
        __map?: { jumpTo(opts: { center: [number, number]; zoom: number }): void };
      }
    ).__map;
    map?.jumpTo({ center: [-4.5, 57.2], zoom: z });
  }, zoom);
}

test.describe("LAYERS-PERF-3", () => {
  test.use({ viewport: { width: 1280, height: 900 } });

  test("size-capped oil and gas shows the hint and is fetched again", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    let fetches = 0;
    await stubMapCardsBackend(page);
    await page.route("**/layers/context/oil-fields**", async (route) => {
      fetches += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: HIDDEN_OIL,
      });
    });

    await openMap(page);
    await waitForMap(page);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "resources");
    const toggle = page.getByTestId("layer-toggle-9");
    const hint = page.getByTestId("oil-gas-zoom-hint");

    await toggle.click();
    await expect(hint).toHaveText("Zoom in to see oil and gas", {
      timeout: 20_000,
    });
    expect(fetches).toBe(1);

    await toggle.click();
    await expect(hint).toBeHidden();
    await toggle.click();
    await expect(hint).toHaveText("Zoom in to see oil and gas", {
      timeout: 20_000,
    });
    expect(fetches).toBe(2);
    assertConsoleClean(gate);
  });

  test("simplified outlines chip is shown at z6 and hidden at z10", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    const body = JSON.stringify({
      type: "FeatureCollection",
      features: [OUTLINE],
    });
    await stubMapCardsBackend(page);
    await page.route("**/layers/open/naturescot-designations**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body,
      });
    });
    await page.route("**/layers/open/sssi**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body,
      });
    });

    await openMap(page);
    await waitForMap(page);
    await jump(page, 6);
    // FRONTEND-BATCH-1 diagnosis: people/km² adds /layers/councils; wait for
    // zoom ≥6 before the chip assert (test timing, not a product bug).
    await expect
      .poll(async () =>
        page.evaluate(() => {
          const map = (window as unknown as { __map?: { getZoom(): number } })
            .__map;
          return map?.getZoom() ?? 0;
        }),
      )
      .toBeGreaterThanOrEqual(6);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "nature");
    await page.getByTestId("layer-toggle-designations").click();

    const chip = page.getByTestId("simplified-outlines-chip");
    await expect(chip).toHaveText(
      "Simplified outlines at this zoom. Zoom in for detail.",
      { timeout: 20_000 },
    );

    await jump(page, 10);
    await expect(chip).toBeHidden({ timeout: 20_000 });
    assertConsoleClean(gate);
  });

  test("oil and gas hint stacks under the protected-sites hint", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    const hiddenSites = JSON.stringify({
      type: "FeatureCollection",
      features: [],
      meta: { hidden_below_zoom: true },
    });
    await stubMapCardsBackend(page);
    await page.route("**/layers/context/oil-fields**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: HIDDEN_OIL,
      });
    });
    await page.route("**/layers/open/naturescot-designations**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: hiddenSites,
      });
    });
    await page.route("**/layers/open/sssi**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: hiddenSites,
      });
    });

    await openMap(page);
    await waitForMap(page);
    await jump(page, 6);
    await openLayers(page);
    await ensureLayersGroupOpen(page, "nature");
    await page.getByTestId("layer-toggle-designations").click();
    await ensureLayersGroupOpen(page, "resources");
    await page.getByTestId("layer-toggle-9").click();

    const sites = page.getByTestId("protected-sites-zoom-hint");
    const oil = page.getByTestId("oil-gas-zoom-hint");
    await expect(sites).toBeVisible({ timeout: 20_000 });
    await expect(oil).toBeVisible();
    const sitesBox = await sites.boundingBox();
    const oilBox = await oil.boundingBox();
    expect(sitesBox).not.toBeNull();
    expect(oilBox).not.toBeNull();
    expect(oilBox!.y).toBeGreaterThanOrEqual(sitesBox!.y + sitesBox!.height);
    assertConsoleClean(gate);
  });
});
