import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";
import { type Locator, type Page, type Route } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * UX-01 — mobile tap targets ≥44×44 at 390×844 (MAP-CARDS aligned).
 * Covered: zoom +/-, Layers, banner More, nav links, panel ×, Search, All sources.
 */

const MIN_HIT = 44;

const OUTSIDE_LAT = 59.66616;
const OUTSIDE_LNG = -9.196485;
const OUTSIDE_DETAIL = "Coordinates appear to be outside Scotland.";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const PLACE_STUB = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "Glasgow",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre" },
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
};

type ConsoleGate = {
  consoleErrors: string[];
  resourceFails: Array<{ url: string; status: number }>;
};

type Box = { x: number; y: number; width: number; height: number };

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const resourceFails: Array<{ url: string; status: number }> = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
  page.on("response", (response) => {
    const status = response.status();
    if (status === 404 || status === 400 || status === 503) {
      resourceFails.push({ url: response.url(), status });
    }
  });
  return { consoleErrors, resourceFails };
}

function assertConsoleClean(gate: ConsoleGate) {
  const unexpectedResourceFails = gate.resourceFails.filter((fail) => {
    if (
      (fail.status === 404 || fail.status === 400) &&
      /data-zones\/at|platform\/place|api\/place\.json/i.test(fail.url)
    ) {
      return false;
    }
    if (/\/favicon\.ico(?:\?|$)|\/apple-touch-icon/i.test(fail.url)) {
      return false;
    }
    return true;
  });
  expect(
    unexpectedResourceFails,
    `unexpected HTTP 400/404/503:\n${unexpectedResourceFails
      .map((f) => `${f.status} ${f.url}`)
      .join("\n")}`,
  ).toEqual([]);

  const meaningful = gate.consoleErrors.filter((text) => {
    if (/\bAbortError\b|aborted/i.test(text)) return false;
        return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
}

function boxesOverlap(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function assertMinHit(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, `${label} box`).toBeTruthy();
  expect(box!.width, `${label} width`).toBeGreaterThanOrEqual(MIN_HIT);
  expect(box!.height, `${label} height`).toBeGreaterThanOrEqual(MIN_HIT);
}

async function assertNoBoxOverlap(a: Locator, b: Locator, label: string) {
  const boxA = await a.boundingBox();
  const boxB = await b.boundingBox();
  expect(boxA && boxB, label).toBeTruthy();
  expect(boxesOverlap(boxA!, boxB!), label).toBe(false);
}

async function assertNoPairwiseOverlaps(
  items: Array<{ label: string; locator: Locator }>,
) {
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      await assertNoBoxOverlap(
        items[i]!.locator,
        items[j]!.locator,
        `${items[i]!.label} vs ${items[j]!.label}`,
      );
    }
  }
}

async function stubMapChrome(page: Page) {
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
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_STUB),
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
      body: JSON.stringify(wantsGeo ? EMPTY_FC : {}),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
}

async function stubSeaMiss(page: Page) {
  const reject = async (route: Route) => {
    await route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ detail: OUTSIDE_DETAIL }),
    });
  };
  await page.route("**/backend/platform/place**", reject);
  await page.route("**/api/place.json**", reject);
  await page.route("**/backend/layers/context/data-zones/at**", reject);
}

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator(".maplibregl-ctrl-zoom-in").waitFor();
  await page.locator(".hud-search-go").waitFor();
}

test.describe("UX-01 mobile hit areas 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("resting chrome + nav + layers + place/sea × meet 44px", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openMap(page);

    const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
    const zoomOut = page.locator(".maplibregl-ctrl-zoom-out");
    const searchGo = page.locator(".hud-search-go");
    const layersBtn = page.getByTestId("hud-layers-btn");
    const bannerMore = page.getByTestId("research-banner-toggle");
    const allSources = page.getByTestId("map-all-sources");

    await expect(layersBtn).toBeVisible();
    await expect(allSources).toBeVisible();

    await assertMinHit(zoomIn, "zoom-in");
    await assertMinHit(zoomOut, "zoom-out");
    await assertMinHit(searchGo, "Search");
    await assertMinHit(layersBtn, "Layers");
    if (await bannerMore.isVisible().catch(() => false)) {
      await assertMinHit(bannerMore, "banner More");
    }
    await assertMinHit(allSources, "All sources");
    const creditInfo = page.getByTestId("map-credit-info");
    if (await creditInfo.isVisible().catch(() => false)) {
      await assertMinHit(creditInfo, "Map credits");
    }

    await expect(page.getByRole("button", { name: "Show legend" })).toHaveCount(
      0,
    );

    // Nav links (burger panel)
    await page.getByTestId("site-nav-menu-btn").click();
    const panel = page.getByTestId("site-nav-panel");
    await expect(panel).toBeVisible();
    const navLinks = panel.getByRole("link");
    const navCount = await navLinks.count();
    expect(navCount, "nav link count").toBeGreaterThanOrEqual(2);
    for (let i = 0; i < navCount; i += 1) {
      const link = navLinks.nth(i);
      const name = (await link.innerText()).trim() || `nav-${i}`;
      await assertMinHit(link, `nav link ${name}`);
    }
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();

    // Layer switches
    await layersBtn.click();
    const layersPanel = page.getByTestId("layers-panel");
    await expect(layersPanel).toBeVisible();
    const placesToggle = page.getByTestId("layers-group-toggle-places");
    if ((await placesToggle.getAttribute("aria-expanded")) !== "true") {
      await placesToggle.click();
    }
    const sw = page.getByTestId("layer-toggle-councils");
    await assertMinHit(sw, "council switch");
    await page.getByTestId("map-panel-slot-close").click();
    await expect(layersPanel).toHaveCount(0);

    // Place card ×
    await page.locator("#place-query").fill("55.86090, -4.25140");
    await searchGo.click();
    const placeClose = page.getByRole("button", { name: "Close place card" });
    await expect(placeClose).toBeVisible({ timeout: 30_000 });
    await assertMinHit(placeClose, "place panel ×");
    await placeClose.click();
    for (let i = 0; i < 3; i += 1) {
      if ((await page.getByTestId("place-card").count()) === 0) break;
      await page.keyboard.press("Escape");
    }

    // Sea stub ×
    await stubSeaMiss(page);
    await page.locator("#place-query").fill(`${OUTSIDE_LAT}, ${OUTSIDE_LNG}`);
    await searchGo.click();
    const seaLine = page.getByTestId("place-card-out-of-scotland");
    await expect(seaLine).toBeVisible({ timeout: 30_000 });
    const seaClose = page.getByRole("button", { name: "Close place card" });
    await expect(seaClose).toBeVisible();
    await assertMinHit(seaClose, "sea panel ×");

    assertConsoleClean(gate);
  });
});
