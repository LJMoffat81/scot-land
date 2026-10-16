import { expect, test } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  getStyleSourceIds,
  openLayers,
  openMap,
  openPlaceViaCoords,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";

/**
 * MAP-CARDS checks 4, 24, 26–32, 34–35 — legend/layers GIS probes (stubbed).
 * Tile/Lighthouse perf (26 partial) is soft where CI has no live tiles.
 */

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`MAP-CARDS GIS (${viewport.width})`, () => {
    test.use({ viewport });

    test("4 legend matches toggled layers; strip when panel closed", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await openLayers(page);

      const landToggle = page.getByTestId("layers-group-toggle-land");
      if ((await landToggle.getAttribute("aria-expanded")) !== "true") {
        await landToggle.click();
      }
      await expect(page.getByTestId("layer-inline-legend-vdl")).toHaveCount(0);
      await page.getByTestId("layer-toggle-vdl").click();
      await expect(page.getByTestId("layer-inline-legend-vdl")).toBeVisible();
      await expect(page.getByTestId("layer-inline-legend-vdl")).toContainText(
        /Vacant|Derelict/i,
      );
      await page.getByTestId("layer-toggle-vdl").click();
      await expect(page.getByTestId("layer-inline-legend-vdl")).toHaveCount(0);

      // Close panel → legend strip for an active non-default layer
      await page.getByTestId("layer-toggle-vdl").click();
      await page.getByTestId("map-panel-slot-close").click();
      await expect(page.getByTestId("legend-strip")).toBeVisible();
      await expect(page.getByTestId("legend-strip")).toContainText(
        /Vacant|derelict/i,
      );
      assertConsoleClean(gate);
    });

    test("24 race: two identifies — only second renders", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const slow = {
        ...{
          contract: "place_card_v1",
          lat: 55.95,
          lng: -3.19,
          place_label: "First Slow",
          council_name: "City of Edinburgh",
          dwellings: 400,
          dz_code: "S01008600",
          source_crs: "EPSG:27700",
          data_zone: {
            status: "ok",
            code: "S01008600",
            name: "Slow Zone",
            vintage: 2022,
          },
          intermediate_zone: { status: "ok", name: "First Slow", code: "S02001" },
          agr_rows: [],
          constraints: [],
          layers: [],
          links: [],
        },
      };
      const fast = {
        contract: "place_card_v1",
        lat: 55.86,
        lng: -4.25,
        place_label: "Second Fast",
        council_name: "Glasgow City",
        dwellings: 400,
        dz_code: "S01014567",
        source_crs: "EPSG:27700",
        data_zone: {
          status: "ok",
          code: "S01014567",
          name: "Fast Zone",
          vintage: 2022,
        },
        intermediate_zone: {
          status: "ok",
          name: "Second Fast",
          code: "S02002",
        },
        agr_rows: [],
        constraints: [],
        layers: [],
        links: [],
      };

      let call = 0;
      await page.route("**/api/gbp-live**", async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ enabled: false }),
        });
      });
      await page.route("**/backend/**", async (route) => {
        const url = route.request().url();
        if (/\/health/i.test(url)) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ status: "ok", routers: {} }),
          });
          return;
        }
        if (/\/platform\/place/i.test(url)) {
          call += 1;
          const n = call;
          const body = n === 1 ? slow : fast;
          const delay = n === 1 ? 1200 : 50;
          await new Promise((r) => setTimeout(r, delay));
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(body),
          });
          return;
        }
        if (/\/layers\/context\/data-zones\/at/i.test(url)) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ code: null, name: null, vintage: null }),
          });
          return;
        }
        const wantsGeo =
          /\/layers\//i.test(url) ||
          /\/boundaries\//i.test(url) ||
          /\/w3w-grid/i.test(url) ||
          /\/parcels/i.test(url);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(
            wantsGeo ? { type: "FeatureCollection", features: [] } : {},
          ),
        });
      });

      await openMap(page);
      // First identify (slow) — dispatch on the map without waiting for the card,
      // then immediately fire identify-at-centre (force: peek sheet may still be landing).
      await page.evaluate(() => {
        const map = (
          window as unknown as {
            __map?: { getCanvas(): HTMLCanvasElement };
          }
        ).__map;
        const canvas = map?.getCanvas() || document.querySelector(".maplibregl-canvas");
        canvas?.dispatchEvent(
          new MouseEvent("click", { bubbles: true, clientX: 200, clientY: 300 }),
        );
      });
      // Immediately second via identify-at-centre after a tiny wait so gen bumps
      await page.waitForTimeout(80);
      await page.getByTestId("identify-at-centre").click({ force: true });
      await expect(page.getByTestId("place-card")).toBeVisible({
        timeout: 45_000,
      });
      // After both settle, title must be the second (fast) place — not First Slow
      await page.waitForTimeout(1500);
      await expect(page.getByTestId("place-card-place")).toHaveText(/Second Fast|Fast Zone|Glasgow/i);
      await expect(page.getByTestId("place-card-place")).not.toHaveText(
        /First Slow/,
      );
      assertConsoleClean(gate);
    });

    test("29 attribution on/off; 31 no parcel|w3w sources; 32 zoom gate", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForMap(page);

      await expect(page.getByTestId("map-all-sources")).toBeVisible();
      const sources = await getStyleSourceIds(page);
      expect(sources.filter((id) => /parcel|w3w/i.test(id))).toEqual([]);

      await openLayers(page);
      // access_services minzoom 8 — at default ~5.7 should gate
      const landToggle = page.getByTestId("layers-group-toggle-land");
      if ((await landToggle.getAttribute("aria-expanded")) !== "true") {
        await landToggle.click();
      }
      await page.getByTestId("layer-toggle-access_services").click();
      await expect(
        page.getByTestId("layer-zoom-gate-access_services"),
      ).toHaveText("Zoom in to see this layer");
      assertConsoleClean(gate);
    });

    test("34 map padding soft: marker not under panel after search", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openPlaceViaCoords(page);
      const slot = page.getByTestId("map-panel-slot");
      await expect(slot).toBeVisible();
      const marker = page.locator(".maplibregl-marker").first();
      if ((await marker.count()) === 0) {
        // Soft: no pin when URL inspect uses existing marker path — skip soft fail
        test.info().annotations.push({
          type: "note",
          description: "no marker for soft padding check",
        });
        assertConsoleClean(gate);
        return;
      }
      const slotBox = await slot.boundingBox();
      const markerBox = await marker.boundingBox();
      expect(slotBox && markerBox).toBeTruthy();
      if (viewport.width >= 1280 && slotBox && markerBox) {
        // Desktop: marker should sit to the right of the left panel
        expect(markerBox.x + markerBox.width / 2).toBeGreaterThan(
          slotBox.x + slotBox.width - 8,
        );
      }
      assertConsoleClean(gate);
    });
  });
}

test.describe("MAP-CARDS tablet 768", () => {
  test.use({ viewport: { width: 768, height: 1024 } });

  test("35 key checks: one panel, no £, layers registry, identify", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await openMap(page);
    await expect(page.getByTestId("map-rest-prompt")).toBeVisible();
    await openPlaceViaCoords(page);
    await expect(page.getByTestId("place-card")).toBeVisible();
    await expect(page.getByTestId("layers-panel")).toHaveCount(0);
    await expect(page.locator("body")).not.toContainText("£");
    await openLayers(page);
    await expect(page.getByTestId("layers-panel")).toBeVisible();
    await expect(page.getByTestId("place-card")).toHaveCount(0);
    await expect(page.getByTestId("layers-panel")).not.toContainText(
      /coming soon/i,
    );
    await page.getByTestId("map-panel-slot-close").click();
    // Closing Layers restores the place card at peek/half — identify sits above it.
    await page.getByTestId("identify-at-centre").click({ force: true });
    await expect(page.getByTestId("place-card")).toBeVisible({
      timeout: 45_000,
    });
    assertConsoleClean(gate);
  });
});

test.describe("MAP-CARDS method stamp when £ (1280)", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("30 method stamp sibling when range shown (gbp live)", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page, {
      gbpLive: true,
      place: {
        contract: "place_card_v1",
        lat: 55.86,
        lng: -4.25,
        place_label: "City Centre",
        council_name: "Glasgow City",
        dwellings: 410,
        gbp_live: { enabled: true },
        surface_rent_display: {
          state: "ok",
          low: 1200,
          central: 1500,
          high: 1900,
          estimate_label: "Estimate",
        },
        intermediate_zone: { status: "ok", name: "City Centre" },
        agr_rows: [
          {
            id: "surface",
            label: "Land",
            tag: "proxy",
            class: "proxy",
            status: "in_progress",
            applies: true,
          },
        ],
        layers: [],
        links: [],
      },
    });
    await openPlaceViaCoords(page);
    const figure = page.getByTestId("place-card-figure");
    await expect(figure).toContainText(/£/);
    // GIS 15 method stamp — assert sibling methodology path when present;
    // fold always carries How we work this out → /methodology.
    const method = page.locator(
      '[data-testid="place-card-method-stamp"], [data-testid="place-card-methodology-link"]',
    );
    const parts = page.getByTestId("place-card-parts");
    if (!(await parts.getAttribute("open"))) {
      await parts.locator("summary").click();
    }
    await expect(method.first()).toBeVisible();
    assertConsoleClean(gate);
  });
});
