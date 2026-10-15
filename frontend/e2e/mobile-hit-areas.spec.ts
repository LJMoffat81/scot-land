import {
  expect,
  test,
  type Locator,
  type Page,
  type Route,
} from "@playwright/test";

/**
 * UX-01 — mobile tap targets ≥44×44 at 390×844.
 * Covered: zoom +/-, layer chips, banner More, Show legend, nav links,
 * card × (incl. sea stub), Search, footer Sources.
 * Console / pageerror fail the test (never loosen).
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
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
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
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    if (
      /Failed to load resource: the server responded with a status of (400|404|503)/i.test(
        text,
      )
    ) {
      if (!/https?:\/\//i.test(text) && unexpectedResourceFails.length === 0) {
        return false;
      }
      return true;
    }
    return true;
  });
  expect(
    meaningful,
    `console errors:\n${meaningful.join("\n")}`,
  ).toEqual([]);
}

function boxesOverlap(a: Box, b: Box) {
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
  expect(box, `${label}: missing box`).toBeTruthy();
  expect(
    box!.width,
    `${label}: width ${box!.width} < ${MIN_HIT}`,
  ).toBeGreaterThanOrEqual(MIN_HIT);
  expect(
    box!.height,
    `${label}: height ${box!.height} < ${MIN_HIT}`,
  ).toBeGreaterThanOrEqual(MIN_HIT);
  return box!;
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

async function assertNoPairwiseOverlaps(
  named: Array<{ label: string; locator: Locator }>,
) {
  for (let i = 0; i < named.length; i += 1) {
    for (let j = i + 1; j < named.length; j += 1) {
      await assertNoBoxOverlap(
        named[i].locator,
        named[j].locator,
        `${named[i].label} vs ${named[j].label}`,
      );
    }
  }
}

async function stubMapChrome(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    const wantsGeo =
      /\/layers\//i.test(url) ||
      /\/w3w-grid/i.test(url) ||
      /\/parcels/i.test(url);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(wantsGeo ? EMPTY_FC : {}),
    });
  });

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
  await page.route("**/backend/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/backend/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: "S01014567",
        name: "City Centre South",
        vintage: 2022,
      }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
    });
  });
  await page.route("**/api/place.json**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
    });
  });
  await page.route("**/api/catalog.json**", async (route) => {
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
  await page.locator(".maplibregl-ctrl-zoom-out").waitFor();
  await page.locator(".hud-search-go").waitFor();
  await page.getByTestId("map-footer-line").waitFor();
}

test.describe("UX-01 mobile hit areas 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("resting chrome + nav + layers + place/sea × meet 44px with no overlaps", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openMap(page);

    const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
    const zoomOut = page.locator(".maplibregl-ctrl-zoom-out");
    const searchGo = page.locator(".hud-search-go");
    const legend = page.locator("button.hud-scotland-fold");
    const bannerMore = page.getByTestId("research-banner-toggle");
    const sources = page
      .getByTestId("map-footer-line")
      .getByRole("link", { name: "Sources and licences" });

    await expect(legend).toBeVisible();
    await expect(bannerMore).toBeVisible({ timeout: 15_000 });
    await expect(sources).toBeVisible();

    await assertMinHit(zoomIn, "zoom-in");
    await assertMinHit(zoomOut, "zoom-out");
    await assertMinHit(searchGo, "Search");
    await assertMinHit(legend, "Show legend");
    await assertMinHit(bannerMore, "banner More");
    await assertMinHit(sources, "footer Sources");

    await assertNoPairwiseOverlaps([
      { label: "zoom-in", locator: zoomIn },
      { label: "zoom-out", locator: zoomOut },
      { label: "Search", locator: searchGo },
      { label: "Show legend", locator: legend },
      { label: "banner More", locator: bannerMore },
      { label: "footer Sources", locator: sources },
    ]);

    // Nav links (burger panel)
    await page.getByTestId("site-nav-menu-btn").click();
    const panel = page.getByTestId("site-nav-panel");
    await expect(panel).toBeVisible();
    const navLinks = panel.getByRole("link");
    const navCount = await navLinks.count();
    expect(navCount, "nav link count").toBeGreaterThanOrEqual(2);
    const navNamed: Array<{ label: string; locator: Locator }> = [];
    for (let i = 0; i < navCount; i += 1) {
      const link = navLinks.nth(i);
      const name = (await link.innerText()).trim() || `nav-${i}`;
      await assertMinHit(link, `nav link ${name}`);
      navNamed.push({ label: `nav ${name}`, locator: link });
    }
    await assertNoPairwiseOverlaps(navNamed);
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();

    // Layer chips
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    const layersPanel = page.getByTestId("layers-panel");
    await expect(layersPanel).toBeVisible();
    const chips = layersPanel.locator("button.chip");
    const chipCount = await chips.count();
    expect(chipCount, "layer chip count").toBeGreaterThanOrEqual(1);
    const chipNamed: Array<{ label: string; locator: Locator }> = [];
    for (let i = 0; i < chipCount; i += 1) {
      const chip = chips.nth(i);
      const name = (await chip.innerText()).trim() || `chip-${i}`;
      await assertMinHit(chip, `layer chip ${name}`);
      chipNamed.push({ label: `chip ${name}`, locator: chip });
    }
    await assertNoPairwiseOverlaps(chipNamed);
    // Chips must not cover zoom controls
    for (const chip of chipNamed) {
      await assertNoBoxOverlap(chip.locator, zoomIn, `${chip.label} vs zoom-in`);
      await assertNoBoxOverlap(chip.locator, zoomOut, `${chip.label} vs zoom-out`);
    }
    await page.getByRole("button", { name: "Layers", exact: true }).click();
    await expect(layersPanel).toBeHidden();

    // Place card ×
    await page.locator("#place-query").fill("Glasgow");
    await searchGo.click();
    const placeClose = page.getByRole("button", { name: "Close place card" });
    await expect(placeClose).toBeVisible({ timeout: 30_000 });
    await assertMinHit(placeClose, "place card ×");
    await assertNoBoxOverlap(placeClose, zoomIn, "place × vs zoom-in");
    await assertNoBoxOverlap(placeClose, zoomOut, "place × vs zoom-out");
    await assertNoBoxOverlap(placeClose, searchGo, "place × vs Search");
    await placeClose.click();
    await expect(placeClose).toBeHidden();

    // Sea stub ×
    await stubSeaMiss(page);
    await page.locator("#place-query").fill(`${OUTSIDE_LAT}, ${OUTSIDE_LNG}`);
    await searchGo.click();
    const seaLine = page.getByTestId("place-card-out-of-scotland");
    await expect(seaLine).toBeVisible({ timeout: 30_000 });
    const seaClose = page.getByRole("button", { name: "Close place card" });
    await expect(seaClose).toBeVisible();
    await assertMinHit(seaClose, "sea stub ×");
    await assertNoBoxOverlap(seaClose, zoomIn, "sea × vs zoom-in");
    await assertNoBoxOverlap(seaClose, zoomOut, "sea × vs zoom-out");
    await assertNoBoxOverlap(seaClose, searchGo, "sea × vs Search");

    assertConsoleClean(gate);
  });
});
