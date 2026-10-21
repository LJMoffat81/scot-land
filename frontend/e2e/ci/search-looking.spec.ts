import {
  attachConsoleGate,
  assertConsoleClean,
  fulfillEmptyGlyph,
  registerOpenFreeMapFontStub,
} from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


const POSTCODE = "EH1 1YZ";
const LOOKING = "Looking…";
/** Delay place stubs so Looking… stays painted before the response lands. */
const PLACE_DELAY_MS = 700;

async function expectLookingVisible(page: Page) {
  await expect(page.locator(".search-suggest-note", { hasText: LOOKING })).toBeVisible({
    timeout: 15_000,
  });
}

const EMPTY_FC = JSON.stringify({
  type: "FeatureCollection",
  features: [],
});

/** 1×1 PNG — stub raster tiles so MapLibre never depends on live CDN in CI. */
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

/** Minimal style replacing OpenFreeMap positron (no glyphs → no font CDN). */
const STUB_MAP_STYLE = {
  version: 8,
  name: "e2e-stub",
  sources: {
    stub: {
      type: "raster",
      tiles: ["https://tiles.openfreemap.org/e2e-stub/{z}/{x}/{y}.png"],
      tileSize: 256,
    },
  },
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#e8eef4" },
    },
    { id: "stub-raster", type: "raster", source: "stub" },
  ],
};

/** Stub basemap style/tiles so CDN flakes cannot throw bare pageerror "Error". */
async function stubMapBasemap(page: Page) {
  // One host handler: style JSON vs raster (LIFO would otherwise serve PNG for
  // https://tiles.openfreemap.org/styles/positron).
  await page.route("**/tiles.openfreemap.org/**", async (route) => {
    const url = route.request().url();
    if (/\/styles\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(STUB_MAP_STYLE),
      });
      return;
    }
    if (/\/fonts\//i.test(url)) {
      await fulfillEmptyGlyph(route);
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/ArcGIS/rest/services/World_Imagery/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/api/parcels/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/api/context/**/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
}

async function stubMapBackend(
  page: Page,
  place: "success" | "error",
) {
  await stubMapBasemap(page);
  await page.route("**/backend/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.endsWith("/health") || path.includes("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          routers: {
            "api.agr_routes": { loaded: true },
            "api.platform_routes": { loaded: true },
          },
        }),
      });
      return;
    }

    if (path.includes("/place") && !path.includes("/platform/place")) {
      await new Promise((r) => setTimeout(r, PLACE_DELAY_MS));
      if (place === "error") {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ detail: "stubbed place failure" }),
        });
        return;
      }
      const q = (url.searchParams.get("q") || "")
        .toUpperCase()
        .replace(/\s+/g, " ");
      if (q.includes("EH1")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            kind: "postcode",
            postcode: POSTCODE,
            lat: 55.952,
            lng: -3.189,
            label: POSTCODE,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "none", note: "No matches" }),
      });
      return;
    }

    if (path.includes("/postcode/")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          postcode: { postcode: POSTCODE },
          lat: 55.952,
          lng: -3.189,
          square: { lat: 55.952, lng: -3.189 },
        }),
      });
      return;
    }

    if (path.includes("/platform/place")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat: 55.952,
          lng: -3.189,
          place_label: "Edinburgh Old Town",
          council_name: "City of Edinburgh",
          data_zone: {
            status: "ok",
            code: "S01008677",
            name: "Old Town",
            vintage: 2022,
          },
          intermediate_zone: { status: "ok", name: "Old Town and Canongate" },
          agr_rows: [
            {
              id: "surface",
              label: "Land",
              tag: "proxy",
              status: "in_progress",
              applies: true,
            },
          ],
          constraints: [],
          layers: [],
          links: [],
        }),
      });
      return;
    }

    if (path.includes("/layers/catalog") || path.endsWith("/catalog")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
      return;
    }

    // Quiet other map layer / context probes so the proxy does not 503.
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: EMPTY_FC,
    });
  });
}

async function openMapSearch(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  const search = page.locator("#place-query");
  await search.waitFor();
  // MAP-HINTS-OFF-1: no research banner on the map to dismiss.
  await expect(page.getByTestId("research-banner")).toHaveCount(0);
  return search;
}

test.describe("search dropdown Looking…", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("selecting a postcode clears Looking… within 1s", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page, "success");

    const search = await openMapSearch(page);
    await search.fill(POSTCODE);
    await expectLookingVisible(page);
    await expect(page.getByRole("option", { name: POSTCODE })).toBeVisible({
      timeout: 10_000,
    });
    // Keyboard select (active option is index 0) — avoids banner pointer intercept.
    await search.press("Enter");

    await page.waitForTimeout(1000);
    await expect(page.getByText(LOOKING)).toHaveCount(0);
    await expect(page.locator(".search-suggest")).toHaveCount(0);
    assertConsoleClean(gate);
  });

  test("empty results show No matches and clear Looking…", async ({ page }) => {
    test.setTimeout(60_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page, "success");

    const search = await openMapSearch(page);
    await search.fill("zzznowhere");
    await expectLookingVisible(page);
    await expect(page.getByText("No matches")).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(LOOKING)).toHaveCount(0);
    assertConsoleClean(gate);
  });

  test("Escape clears Looking… after it appears", async ({ page }) => {
    test.setTimeout(60_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page, "success");

    const search = await openMapSearch(page);
    await search.fill("EH1");
    await expectLookingVisible(page);
    await search.press("Escape");
    await expect(page.getByText(LOOKING)).toHaveCount(0);
    await expect(page.locator(".search-suggest")).toHaveCount(0);
    assertConsoleClean(gate);
  });

  test("place 500 clears Looking…", async ({ page }) => {
    test.setTimeout(60_000);
    const gate = attachConsoleGate(page);
    // Intentional place 500 fixture.
    gate.expectError({
      urlPath: "/backend/place",
      status: 500,
      count: 1,
    });
    await stubMapBackend(page, "error");

    const search = await openMapSearch(page);
    await search.fill(POSTCODE);
    await expectLookingVisible(page);
    await expect(page.getByText(LOOKING)).toHaveCount(0, { timeout: 15_000 });
    assertConsoleClean(gate);
  });

  test("blur clears Looking…", async ({ page }) => {
    test.setTimeout(60_000);
    const gate = attachConsoleGate(page);
    await stubMapBackend(page, "success");

    const search = await openMapSearch(page);
    await search.fill(POSTCODE);
    await expectLookingVisible(page);
    await search.blur();
    // onBlur clears after 180ms; allow debounce/abort to settle.
    await expect(page.getByText(LOOKING)).toHaveCount(0, { timeout: 10_000 });
    await expect(page.locator(".search-suggest")).toHaveCount(0);
    assertConsoleClean(gate);
  });
});
