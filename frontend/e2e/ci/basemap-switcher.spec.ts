import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test, type Locator, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * MAP-CARDS basemap — Simple ↔ Detailed (open tiles). Locate removed.
 * Desktop uses radios. Narrow uses the icon toggle. Console errors fail the test.
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

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  resourceFails.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
  page.on("response", (response) => {
    const status = response.status();
    if (status === 404 || status === 503) {
      resourceFails.push({ url: response.url(), status });
    }
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
  await page.route("**/backend/boundaries/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await stubLayersAddQuiet(page);
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
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
});

async function openMap(page: Page) {
  await page.goto("/");
  await page.getByTestId("basemap-switcher").waitFor({ state: "attached" });
  await page.locator(".maplibregl-canvas").waitFor();
  const attrib = page.locator(".maplibregl-ctrl-attrib");
  await attrib.waitFor({ state: "attached" });
  await expect(page.locator(".maplibregl-ctrl-zoom-in")).toBeVisible();
  await expect(page.getByTestId("basemap-switcher")).toBeVisible();
}

async function openPlaceCard(page: Page) {
  const search = page.locator("#place-query");
  await search.fill("55.86090, -4.25140");
  await page.locator(".hud-search-go").click();
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 45_000 });
  return card;
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

async function runBasemapChecks(page: Page) {
  await openMap(page);
  const narrow = (page.viewportSize()?.width ?? 1280) <= 900;

  await expect(page.getByRole("button", { name: "Locate" })).toHaveCount(0);
  const switcher = page.getByTestId("basemap-switcher");
  await expect(switcher).toBeVisible();
  await expect(switcher).not.toContainText(/Satellite/i);
  await expect(switcher).not.toContainText("Light");

  const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
  const zoomOut = page.locator(".maplibregl-ctrl-zoom-out");

  if (narrow) {
    await expect(page.locator(".basemap-switcher-wide")).toBeHidden();
    const toggle = page.getByTestId("basemap-toggle-narrow");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAccessibleName("Detailed");
    await expect(toggle).toHaveText("Detailed");
    await expect(toggle.locator("svg")).toHaveCount(0);
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    await expect(toggle).toHaveAccessibleName("Simple");
    await expect(toggle).toHaveText("Simple");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(toggle).toHaveText("Detailed");
  } else {
    await expect(page.getByTestId("basemap-toggle-narrow")).toBeHidden();
    const group = page.getByRole("radiogroup", { name: "Map style" });
    await expect(group).toBeVisible();
    const simple = page.getByTestId("basemap-option-light");
    const detailed = page.getByTestId("basemap-option-detailed");
    await expect(simple).toHaveAttribute("aria-checked", "true");
    await expect(simple).toHaveText("Simple");
    await expect(detailed).toHaveAttribute("aria-checked", "false");
    await expect(detailed).toHaveText("Detailed");
    await detailed.click();
    await expect(detailed).toHaveAttribute("aria-checked", "true");
    await simple.click();
    await expect(simple).toHaveAttribute("aria-checked", "true");
  }

  await assertNoBoxOverlap(switcher, zoomIn, "basemap vs zoom-in");
  await assertNoBoxOverlap(switcher, zoomOut, "basemap vs zoom-out");

  const card = await openPlaceCard(page);
  await assertNoBoxOverlap(switcher, card, "basemap vs place card");
  await expect(page.getByRole("button", { name: "Locate" })).toHaveCount(0);
}

test.describe("1280 desktop", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("basemap radios Simple/Detailed; clear of zoom and place card", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await runBasemapChecks(page);
  });
});

test.describe("390x844 mobile", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("basemap narrow toggle; clear of place card; no Locate", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await runBasemapChecks(page);
  });
});
