/**
 * UX-POLISH-28OCT-1 — 28 Oct 2026 UX & Wording batch:
 * 1. CREDIT-BAR-MOBILE-DESKTOP-1: mobile credit bar stays left of 48px control column (h <= 48px, nowrap);
 *    desktop credit bar shows short names + ⓘ ("Map credits") sheet without repeating full OGL paragraphs inline.
 * 2. LAYERS-DRAWER-CONTROLS-SHIFT-1: desktop Layers drawer shifts 2D/3D, Basemap, and Zoom +/- left of the 380px drawer;
 *    mobile .tools-open rules apply without relying on .map-narrow.
 * 3. MOBILE-CONTROLS-ORDER-HALF-1: mobile Place Card half-sheet keeps top-to-bottom order (2D/3D -> Basemap -> Zoom +/-).
 * 4. COUNCIL-DENSITY-KEY-TITLE-1: POP_DENSITY_RANGE_LEGEND_TITLE === "People per km²".
 * 5. WORDING-POLISH-BATCH-1 / SEARCH-PLACEHOLDER-1:
 *    - Search placeholder: "Search a postcode, or tap the map"
 *    - POSTCODES_ONLY: "Search finds full UK postcodes only (e.g. G2 1DU). Or tap or click the map."
 *    - PLACE_CARD_ESTIMATE_LINE: "Research estimate, not a bill or an official valuation."
 * 6. r30 note: direct load of /?b=aerial produces zero React #418 hydration warnings.
 */
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { type Page } from "@playwright/test";
import { expect, test } from "./_fixtures";
import {
  CI_TINY_PNG,
  EMPTY_GLYPH_PBF,
  assertConsoleClean,
  attachConsoleGate,
  injectEsriBasemapKey,
  openLayers,
  openMap,
  openPlaceViaCoords,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import { POSTCODES_ONLY } from "../../lib/api";
import {
  DEFAULT_VIEW_METRIC_ID,
  POP_DENSITY_RANGE_LEGEND_TITLE,
  metricById,
  rangeLegendTitle,
} from "../../lib/mapColourRamps";
import { PLACE_CARD_ESTIMATE_LINE } from "../../lib/siteNav";

registerOpenFreeMapFontStub();

const ESRI_STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

const ESRI_FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

async function routeEsriFixture(page: Page) {
  if (!existsSync(ESRI_FIXTURE_PATH)) {
    throw new Error("fixture missing: esri-imagery-style.json");
  }
  const style = JSON.parse(readFileSync(ESRI_FIXTURE_PATH, "utf8")) as {
    sprite: string;
  };
  await page.route(`${ESRI_STYLE_URL}**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(style),
    });
  });
  await page.route(`${style.sprite}.json`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ image: "root.png", width: 1, height: 1 }),
    });
  });
  await page.route(`${style.sprite}.png`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  await page.route("**/basemaps-api.arcgis.com/**/*.pbf**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/x-protobuf",
      body: EMPTY_GLYPH_PBF,
    });
  });
  await page.route("**/ibasemaps-api.arcgis.com/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
}

const COUNCIL_FC = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: { name: "Glasgow City", population_density_per_km2: 3520 },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-4.32, 55.82],
            [-4.18, 55.82],
            [-4.18, 55.9],
            [-4.32, 55.9],
            [-4.32, 55.82],
          ],
        ],
      },
    },
  ],
};

async function stubCouncilsOk(page: Page) {
  await page.route("**/layers/councils**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(COUNCIL_FC),
    });
  });
}

async function hitCheck(page: Page, selector: string) {
  return page.evaluate((sel) => {
    const el = document.querySelector(sel);
    if (!el) return { exists: false, hitSelf: false, rect: null };
    const r = el.getBoundingClientRect();
    const cx = Math.round(r.left + r.width / 2);
    const cy = Math.round(r.top + r.height / 2);
    const topEl = document.elementFromPoint(cx, cy);
    const hitSelf = topEl ? el === topEl || el.contains(topEl) : false;
    return {
      exists: true,
      hitSelf,
      rect: {
        x: r.x,
        y: r.y,
        width: r.width,
        height: r.height,
        right: r.right,
        bottom: r.bottom,
      },
    };
  }, selector);
}

test("N-UX-28OCT-1 locked wording constants and density legend title", () => {
  expect(POP_DENSITY_RANGE_LEGEND_TITLE).toBe("People per km²");
  expect(rangeLegendTitle(metricById(DEFAULT_VIEW_METRIC_ID)!)).toBe(
    "People per km²",
  );
  expect(POSTCODES_ONLY).toBe(
    "Search finds full UK postcodes only (e.g. G2 1DU). Or tap or click the map.",
  );
  expect(PLACE_CARD_ESTIMATE_LINE).toBe(
    "Research estimate, not a bill or an official valuation.",
  );
});

test.describe("E-UX-28OCT-1 desktop 1280x800", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("desktop credit bar uses short names + ⓘ sheet, Layers shifts controls left of drawer, and placeholder/density title match", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await injectEsriBasemapKey(page);
    await stubMapCardsBackend(page);
    await stubCouncilsOk(page);
    await openMap(page, "/?layers=councils,vdl&z=12&c=-4.25,55.86");
    await waitForMap(page);

    await expect(page.locator("#place-query")).toHaveAttribute(
      "placeholder",
      "Search a postcode, or tap the map",
    );
    await expect(page.locator("#place-query")).not.toHaveAttribute(
      "placeholder",
      "Search a postcode, e.g. G2 1DU",
    );

    // Pick 1 superseded (CARD-CLARITY-31OCT-1A): short names are sheet-only;
    // bar shows Sources (N) without short name; ⓘ still opens long licence text.
    const credit = page.getByTestId("map-credit-line");
    await expect(credit).toBeVisible();
    const visibleCredit = await credit.innerText();
    expect(visibleCredit).not.toContain("Vacant land: SVDLS");
    expect(visibleCredit).toMatch(/Sources \(\d+\)/);
    expect(visibleCredit).not.toContain("Scottish Vacant and Derelict Land Survey");

    const infoBtn = page.getByTestId("map-credit-info");
    await expect(infoBtn).toBeVisible();
    const infoBox = await infoBtn.boundingBox();
    expect(infoBox).toBeTruthy();
    expect(infoBox!.width).toBeGreaterThanOrEqual(44);
    expect(infoBox!.height).toBeGreaterThanOrEqual(44);

    await infoBtn.click();
    const sheet = page.getByTestId("map-credit-sheet");
    await expect(sheet).toBeVisible();
    await expect(sheet).toContainText("Vacant land: SVDLS");
    await expect(sheet).toContainText("Scottish Vacant and Derelict Land Survey");
    await page.getByTestId("map-credit-sheet-close").click();
    await expect(sheet).toHaveCount(0);

    // Pick 2 & Pick 4: Opening Layers shifts 2D/3D, Basemap, and Zoom +/- left of the 380px Layers drawer,
    // and Council areas density key title reads "People per km²".
    await page.evaluate(() => {
      const m = (window as unknown as { __map?: { jumpTo(o: { zoom: number }): void } }).__map;
      m?.jumpTo({ zoom: 6 });
    });
    await openLayers(page);
    const layersCol = page.locator(".map-panel-slot--layers");
    await expect(layersCol).toBeVisible();
    await expect(page.getByTestId("map-range-legend-title")).toHaveText(
      "People per km²",
    );
    const layersBox = await layersCol.boundingBox();
    expect(layersBox).toBeTruthy();

    for (const sel of [
      '[data-testid="view-3d-toggle"]',
      '[data-testid="basemap-switcher"]',
      ".maplibregl-ctrl-zoom-in",
      ".maplibregl-ctrl-zoom-out",
    ]) {
      const check = await hitCheck(page, sel);
      expect(check.exists, sel).toBe(true);
      expect(check.hitSelf, `${sel} hitSelf when Layers open`).toBe(true);
      expect(
        check.rect!.right,
        `${sel} right edge clears layers drawer`,
      ).toBeLessThanOrEqual(layersBox!.x);
    }

    assertConsoleClean(gate);
  });

  test("direct /?b=aerial load produces zero React #418 hydration warnings", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await injectEsriBasemapKey(page);
    await stubMapCardsBackend(page);
    await routeEsriFixture(page);
    await openMap(page, "/?b=aerial&z=6&c=-4.2,56.8");
    await waitForMap(page);

    const switcher = page.getByTestId("basemap-switcher");
    await expect(switcher).toBeVisible();
    await expect(switcher).toHaveAttribute("aria-pressed", "true", {
      timeout: 30_000,
    });
    expect(page.url()).toContain("b=aerial");
    assertConsoleClean(gate);
  });
});

test.describe("E-UX-28OCT-1 mobile 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("mobile credit bar stays <=48px tall and left of controls, and half-sheet keeps 2D/3D -> Basemap -> Zoom order", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await injectEsriBasemapKey(page);
    await stubMapCardsBackend(page);
    await openMap(page, "/?layers=vdl&z=12&c=-4.25,55.86");
    await waitForMap(page);

    // Pick 1 on mobile at rest: credit bar <= 48px tall and left of right-hand controls.
    const creditBox = await page.getByTestId("map-credit-line").boundingBox();
    expect(creditBox).toBeTruthy();
    expect(creditBox!.height).toBeLessThanOrEqual(48);

    for (const sel of [
      '[data-testid="view-3d-toggle"]',
      '[data-testid="basemap-switcher"]',
      ".maplibregl-ctrl-zoom-in",
      ".maplibregl-ctrl-zoom-out",
      '[data-testid="map-credit-info"]',
    ]) {
      const check = await hitCheck(page, sel);
      expect(check.exists, sel).toBe(true);
      expect(check.hitSelf, `${sel} hitSelf at mobile opening`).toBe(true);
    }

    const zoomInRest = await hitCheck(page, ".maplibregl-ctrl-zoom-in");
    expect(creditBox!.x + creditBox!.width).toBeLessThanOrEqual(
      zoomInRest.rect!.x,
    );

    // Pick 3: Open Place Card and step to half detent -> verify 2D/3D -> Basemap -> Zoom +/- order.
    await openPlaceViaCoords(page);
    const slot = page.getByTestId("map-panel-slot");
    await expect(slot).toBeVisible();
    const handle = page.getByTestId("map-panel-handle");
    for (let i = 0; i < 3; i += 1) {
      if ((await slot.getAttribute("data-detent")) === "half") break;
      await handle.click();
    }
    await expect(slot).toHaveAttribute("data-detent", "half");

    const v3dHalf = await hitCheck(page, '[data-testid="view-3d-toggle"]');
    const bmHalf = await hitCheck(page, '[data-testid="basemap-switcher"]');
    const zInHalf = await hitCheck(page, ".maplibregl-ctrl-zoom-in");
    const zOutHalf = await hitCheck(page, ".maplibregl-ctrl-zoom-out");

    expect(v3dHalf.hitSelf, "2D/3D hitSelf at half detent").toBe(true);
    expect(bmHalf.hitSelf, "Basemap hitSelf at half detent").toBe(true);
    expect(zInHalf.hitSelf, "Zoom in hitSelf at half detent").toBe(true);
    expect(zOutHalf.hitSelf, "Zoom out hitSelf at half detent").toBe(true);

    expect(v3dHalf.rect!.y).toBeLessThan(bmHalf.rect!.y);
    expect(bmHalf.rect!.y).toBeLessThan(zInHalf.rect!.y);
    expect(zInHalf.rect!.y).toBeLessThan(zOutHalf.rect!.y);

    const creditHalfBox = await page
      .getByTestId("map-credit-line")
      .boundingBox();
    expect(creditHalfBox).toBeTruthy();
    expect(creditHalfBox!.height).toBeLessThanOrEqual(48);
    expect(creditHalfBox!.x + creditHalfBox!.width).toBeLessThanOrEqual(
      zOutHalf.rect!.x,
    );

    assertConsoleClean(gate);
  });
});
