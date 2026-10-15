import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * SW-023: basemap switcher at bottom-right; Locate removed.
 * Console errors fail the test (site-nav-banner pattern).
 */

const consoleErrors: string[] = [];
const resourceFails: Array<{ url: string; status: number }> = [];

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

const KNOWN_OPTIONAL_FAIL_URL = [
  /\/favicon\.ico(?:\?|$)/i,
  /\/apple-touch-icon/i,
];

function isKnownOptionalFailUrl(url: string): boolean {
  return KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(url));
}

/** 1×1 PNG — stub ArcGIS imagery so toggle tests do not depend on live tiles. */
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  resourceFails.length = 0;
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
    if (status === 404 || status === 503) {
      resourceFails.push({ url: response.url(), status });
    }
  });

  // Keep the same Esri World Imagery host as ScotlandMap; fulfill locally.
  await page.route("**/ArcGIS/rest/services/World_Imagery/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });

  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
      }),
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
      body: JSON.stringify({ layers: [] }),
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
      body: JSON.stringify({ code: null, name: null, vintage: null }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_STUB),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
});

test.afterEach(() => {
  const unknownResourceFails = resourceFails.filter(
    (fail) => !isKnownOptionalFailUrl(fail.url),
  );
  expect(
    unknownResourceFails,
    `unexpected HTTP 404/503:\n${unknownResourceFails
      .map((f) => `${f.status} ${f.url}`)
      .join("\n")}`,
  ).toEqual([]);

  const meaningful = consoleErrors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    if (
      /Failed to load resource: the server responded with a status of (404|503)/i.test(
        text,
      )
    ) {
      if (KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(text))) return false;
      if (!/https?:\/\//i.test(text) && unknownResourceFails.length === 0) {
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
});

async function openMap(page: Page) {
  await page.goto("/");
  // React chrome (basemap tile) is independent of MapLibre tile load.
  await page.getByTestId("basemap-switcher").waitFor({ state: "attached" });
  await page.locator(".maplibregl-canvas").waitFor();
  // App collapses MapLibre compact-show; <details> without open is not
  // Playwright-visible (same as site-nav-banner 390×844). Wait for (i).
  const attrib = page.locator(".maplibregl-ctrl-attrib");
  await attrib.waitFor({ state: "attached" });
  await expect(attrib).toHaveClass(/maplibregl-compact/);
  await expect(page.locator(".maplibregl-ctrl-attrib-button")).toBeVisible();
  await expect(page.locator(".maplibregl-ctrl-zoom-in")).toBeVisible();
  await expect(page.locator(".maplibregl-ctrl-zoom-out")).toBeVisible();
  await expect(page.getByTestId("basemap-switcher")).toBeVisible();
}

async function openPlaceCard(page: Page) {
  const search = page.locator("#place-query");
  await search.fill("55.86090, -4.25140");
  await page.locator(".hud-search-go").click();
  const card = page.locator("aside.place-card-stub, aside.place-card").first();
  await expect(card).toBeVisible({ timeout: 45_000 });
  // Wait for place-open layout (desktop bottom clearance / mobile right gutter).
  await expect(page.locator(".app-shell.place-open")).toBeVisible();
  await expect
    .poll(async () => {
      const box = await card.boundingBox();
      return box ? Math.round(box.height) : 0;
    })
    .toBeGreaterThan(40);
  return card;
}

async function openAttributionIfCollapsed(page: Page) {
  const attrib = page.locator(".maplibregl-ctrl-attrib");
  const collapsed = await attrib.evaluate((el) => {
    const compact = el.classList.contains("maplibregl-compact");
    const shown = el.classList.contains("maplibregl-compact-show");
    const inner = el.querySelector(".maplibregl-ctrl-attrib-inner");
    if (!inner) return false;
    const style = getComputedStyle(inner);
    const hidden = style.display === "none" || style.visibility === "hidden";
    return (compact && !shown) || hidden;
  });
  if (!collapsed) return;
  await page.locator(".maplibregl-ctrl-attrib-button").click({ timeout: 10_000 });
}

/** Resting chrome: collapse expanded (i) so zoom returns to the bottom-right stack. */
async function collapseAttribution(page: Page) {
  const attrib = page.locator(".maplibregl-ctrl-attrib");
  // Match ScotlandMap.collapseCompactAttribution — click can race MapLibre.
  await attrib.evaluate((el) => {
    el.classList.remove("maplibregl-compact-show");
    el.removeAttribute("open");
  });
  await expect(attrib).not.toHaveClass(/maplibregl-compact-show/);
  // Zoom must settle back into the lower viewport (expanded attrib shoves it up).
  const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
  await expect
    .poll(async () => {
      const box = await zoomIn.boundingBox();
      if (!box) return 0;
      return box.y / (await page.evaluate(() => window.innerHeight));
    })
    .toBeGreaterThan(0.5);
}

async function attributionText(page: Page) {
  await openAttributionIfCollapsed(page);
  return (await page.locator(".maplibregl-ctrl-attrib").innerText()) || "";
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

async function assertNoBoxOverlap(
  a: Locator,
  b: Locator,
  label: string,
) {
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

async function expectStreetsState(page: Page, switcher: Locator) {
  await expect(switcher).toHaveAccessibleName("Switch to satellite view");
  await expect(switcher).toContainText("Satellite");
  await expect(switcher).toHaveAttribute("aria-pressed", "false");
  await expect
    .poll(async () => attributionText(page), { timeout: 15_000 })
    .not.toMatch(/Esri/i);
}

async function expectSatelliteState(page: Page, switcher: Locator) {
  await expect(switcher).toHaveAccessibleName("Switch to map view");
  await expect(switcher).toContainText("Map");
  await expect(switcher).toHaveAttribute("aria-pressed", "true");
  await expect
    .poll(async () => attributionText(page), { timeout: 15_000 })
    .toMatch(/Esri/i);
}

async function runBasemapChecks(page: Page) {
  await openMap(page);

  await expect(page.getByRole("button", { name: "Locate" })).toHaveCount(0);

  const switcher = page.getByTestId("basemap-switcher");
  await expect(switcher).toBeVisible();
  await expect(switcher).toHaveAttribute("type", "button");
  // SW-023 tile is ~64×64 (small device-pixel tolerance; do not loosen further).
  const tileBox = await switcher.boundingBox();
  expect(tileBox, "basemap tile box").toBeTruthy();
  expect(
    Math.abs(tileBox!.width - 64),
    `basemap tile width ≈ 64 (got ${tileBox!.width})`,
  ).toBeLessThanOrEqual(4);
  expect(
    Math.abs(tileBox!.height - 64),
    `basemap tile height ≈ 64 (got ${tileBox!.height})`,
  ).toBeLessThanOrEqual(4);
  await expectStreetsState(page, switcher);

  // Click toggles streets → satellite.
  await switcher.click();
  await expectSatelliteState(page, switcher);

  // Click toggles satellite → streets.
  await switcher.click();
  await expectStreetsState(page, switcher);

  // Keyboard: Tab to control, Enter / Space toggle.
  await page.evaluate(() => {
    const active = document.activeElement;
    if (active instanceof HTMLElement) active.blur();
  });
  for (let step = 0; step < 40; step += 1) {
    if (await switcher.evaluate((el) => el === document.activeElement)) break;
    await page.keyboard.press("Tab");
  }
  await expect(switcher).toBeFocused();

  await page.keyboard.press("Enter");
  await expectSatelliteState(page, switcher);
  // Attribution poll can move focus off the tile — re-focus before Space.
  await switcher.focus();
  await expect(switcher).toBeFocused();
  await switcher.press("Space");
  await expectStreetsState(page, switcher);

  // Geometry checks use resting collapsed-(i) chrome (expanded attrib shoves zoom up).
  await collapseAttribution(page);

  const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
  const zoomOut = page.locator(".maplibregl-ctrl-zoom-out");
  const attribBtn = page.locator(".maplibregl-ctrl-attrib-button");
  await expect(attribBtn).toBeVisible();

  await assertNoBoxOverlap(switcher, zoomIn, "basemap vs zoom-in");
  await assertNoBoxOverlap(switcher, zoomOut, "basemap vs zoom-out");
  await assertNoBoxOverlap(switcher, attribBtn, "basemap vs attribution (i)");

  const card = await openPlaceCard(page);
  await collapseAttribution(page);
  await assertNoBoxOverlap(switcher, card, "basemap vs place card");
  await assertNoBoxOverlap(switcher, zoomIn, "basemap vs zoom-in (place open)");
  await assertNoBoxOverlap(switcher, attribBtn, "basemap vs (i) (place open)");

  // Still no Locate after place opens.
  await expect(page.getByRole("button", { name: "Locate" })).toHaveCount(0);
}

test.describe("1280 desktop", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("basemap tile toggles; clear of zoom, (i), place card; no Locate", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await runBasemapChecks(page);
  });
});

test.describe("390x844 mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("basemap tile above zoom; clear of place card and (i); no Locate", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await runBasemapChecks(page);

    // Mobile layout: tile stacked above the zoom column (same right edge band).
    // Resting collapsed-(i) state — same as product chrome after openMap.
    await collapseAttribution(page);
    const switcher = page.getByTestId("basemap-switcher");
    const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
    const switchBox = await switcher.boundingBox();
    const zoomBox = await zoomIn.boundingBox();
    expect(switchBox).toBeTruthy();
    expect(zoomBox).toBeTruthy();
    expect(switchBox!.y + switchBox!.height, "tile should sit above zoom").toBeLessThanOrEqual(
      zoomBox!.y + 1,
    );
    expect(
      Math.abs(switchBox!.x + switchBox!.width - (zoomBox!.x + zoomBox!.width)),
      "tile should share the zoom right column",
    ).toBeLessThanOrEqual(24);
  });
});
