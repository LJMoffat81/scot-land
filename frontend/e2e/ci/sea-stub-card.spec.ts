import { injectEsriBasemapKey, registerOpenFreeMapFontStub, stubLayersCouncilsQuiet, stubCiTileDataQuiet, attachConsoleGate, assertConsoleClean } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Locator, type Page } from "@playwright/test";
import { stubLayersAddQuiet } from "./_layersAddStub";

registerOpenFreeMapFontStub();


/**
 * SW-028 + suggestion 25 — sea stub card:
 * - desktop (≥1024) height hugs content (no empty panel under the line)
 * - "Show me Scotland" link closes card + national view
 * - 1280 and 390; card clear of basemap tile and zoom controls
 * Console / pageerror fail the test (do not loosen).
 */

/** MAP-CARDS §5.2 — exact sea / outside-Scotland line. */
const OUT_OF_SCOTLAND_LINE =
  "We only cover land so far. Scotland's sea rents (offshore wind, oil and gas, fish farms and seabed) will come later as their own map layer.";
const SHOW_SCOTLAND = "Show me Scotland";

/** SW-019 sample: west of the public bounds check (lng < -8.5). */
const OUTSIDE_LAT = 59.66616;
const OUTSIDE_LNG = -9.196485;

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const OUTSIDE_DETAIL = "Coordinates appear to be outside Scotland.";






async function stubMapChrome(page: Page) {
  await page.route("**/backend/boundaries/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await stubLayersCouncilsQuiet(page);
  await stubCiTileDataQuiet(page);

  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ version: 2, layers: [] }),
    });
  });
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
    });
  });
  await page.route("**/backend/layers/open/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await stubLayersAddQuiet(page);
}

async function stubSeaMissPlaceApis(page: Page, lat: number, lng: number) {
  await page.route("**/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: OUTSIDE_DETAIL }),
    });
  });
  await page.route("**/platform/place**", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: OUTSIDE_DETAIL }),
    });
  });
  await page.route("**/api/place.json**", async (route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: OUTSIDE_DETAIL }),
    });
  });
}

function boxesOverlap(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
) {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function assertNoBoxOverlap(a: Locator, b: Locator, label: string) {
  await expect(a, label).toBeVisible();
  await expect(b, label).toBeVisible();
  const boxA = await a.boundingBox();
  const boxB = await b.boundingBox();
  expect(boxA, `${label}: missing A`).toBeTruthy();
  expect(boxB, `${label}: missing B`).toBeTruthy();
  expect(
    boxesOverlap(boxA!, boxB!),
    `${label}: overlap A=${JSON.stringify(boxA)} B=${JSON.stringify(boxB)}`,
  ).toBe(false);
}

/** Card outer height within 24px of in-flow content + vertical padding. */
async function assertSeaCardHeightFitsContent(card: Locator) {
  const metrics = await card.evaluate((el) => {
    const style = getComputedStyle(el);
    const padY =
      parseFloat(style.paddingTop || "0") +
      parseFloat(style.paddingBottom || "0");
    const gap = parseFloat(style.rowGap || style.gap || "0") || 0;
    const kids = Array.from(el.children).filter((child) => {
      const cs = getComputedStyle(child);
      return (
        cs.position !== "absolute" &&
        cs.position !== "fixed" &&
        cs.display !== "none"
      );
    });
    const contentH = kids.reduce((sum, child, i) => {
      return sum + child.getBoundingClientRect().height + (i > 0 ? gap : 0);
    }, 0);
    return {
      boxH: el.getBoundingClientRect().height,
      contentH: contentH + padY,
    };
  });
  expect(
    Math.abs(metrics.boxH - metrics.contentH),
    `sea card height ${metrics.boxH} vs content ${metrics.contentH}`,
  ).toBeLessThanOrEqual(24);
}

async function openSeaStub(page: Page) {
  // Prefer deep-link boot (avoids search chrome races in CI).
  await injectEsriBasemapKey(page);
  await page.goto(`/?lat=${OUTSIDE_LAT}&lng=${OUTSIDE_LNG}`);
  await page.locator(".maplibregl-canvas").waitFor();

  const line = page.getByTestId("place-card-out-of-scotland");
  if ((await line.count()) === 0) {
    await page.locator("#place-query").waitFor();
    await page.locator("#place-query").fill(`${OUTSIDE_LAT}, ${OUTSIDE_LNG}`);
    await page.locator(".hud-search-go").click();
  }

  await expect(line).toBeVisible({ timeout: 30_000 });
  await expect(line).toHaveText(OUT_OF_SCOTLAND_LINE);

  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible();
  await expect(card).toHaveClass(/place-card-sea-miss/);
  return card;
}

async function runSeaStubChecks(page: Page) {
  const gate = attachConsoleGate(page);
  await stubMapChrome(page);
  await stubSeaMissPlaceApis(page, OUTSIDE_LAT, OUTSIDE_LNG);

  const card = await openSeaStub(page);
  const showLink = page.getByTestId("place-card-show-scotland");
  await expect(showLink).toBeVisible();
  await expect(showLink).toHaveText(SHOW_SCOTLAND);

  await assertSeaCardHeightFitsContent(card);

  const basemap = page.getByTestId("basemap-switcher");
  const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
  await expect(basemap).toBeVisible();
  await expect(zoomIn).toBeVisible();
  await assertNoBoxOverlap(card, basemap, "sea card vs basemap tile");
  await assertNoBoxOverlap(card, zoomIn, "sea card vs zoom-in");

  // Capture zoom while sea point is framed, then reset.
  const zoomBefore = await page.locator("#map").evaluate((el) =>
    Number((el as HTMLElement).dataset.zoom || "0"),
  );

  await showLink.click();
  await expect(page.getByTestId("place-card")).toHaveCount(0);
  await expect(page.locator(".app-shell")).not.toHaveClass(/place-open/);

  await expect(async () => {
    const cam = await page.locator("#map").evaluate((el) => {
      const node = el as HTMLElement;
      return {
        zoom: Number(node.dataset.zoom || "0"),
        lat: Number(node.dataset.lat || "0"),
        lng: Number(node.dataset.lng || "0"),
      };
    });
    expect(cam.zoom, "national maxZoom 7.4").toBeLessThanOrEqual(7.4);
    expect(cam.lat).toBeGreaterThan(54);
    expect(cam.lat).toBeLessThan(61);
    expect(cam.lng).toBeGreaterThan(-9);
    expect(cam.lng).toBeLessThan(0);
    // After a sea fly-to, national fit should move the camera.
    if (zoomBefore > 8) {
      expect(cam.zoom).toBeLessThan(zoomBefore);
    }
  }).toPass({ timeout: 15_000 });

  assertConsoleClean(gate);
}

test.describe("SW-028 sea stub card 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("height hugs content; Show me Scotland resets national view", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await runSeaStubChecks(page);
  });
});

test.describe("SW-028 sea stub card 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  // QUARANTINE CI-DEDUP-1 Q3: flaky on unrelated PRs, runs 39504926402; owner Eng Lead; exit = 10 consecutive green quarantine runs then remove tag, or fix by 2026-11-21.
  test("compact height; Show me Scotland resets national view @quarantine", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await runSeaStubChecks(page);
  });
});
