import { registerOpenFreeMapFontStub, stubLayersCouncilsQuiet, CI_OPTIONAL_FAIL_URL, isCiOptionalFailUrl, stubCiTileDataQuiet } from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test, type Locator, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * SW-026 — research banner must not overlap the open place card at
 * desktop widths 1280×800 and 1024×768. Console / pageerror fail the test.
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

const KNOWN_OPTIONAL_FAIL_URL = CI_OPTIONAL_FAIL_URL;

function isKnownOptionalFailUrl(url: string): boolean {
  return isCiOptionalFailUrl(url);
}

type Box = { x: number; y: number; width: number; height: number };

function boxesOverlap(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

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
  expect(
    meaningful,
    `console errors:\n${meaningful.join("\n")}`,
  ).toEqual([]);
});

const VIEWPORTS = [
  { name: "1280×800", width: 1280, height: 800 },
  { name: "1024×768", width: 1024, height: 768 },
] as const;

for (const vp of VIEWPORTS) {
  test.describe(`${vp.name}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("place card hides research banner (MAP-CARDS say-it-once)", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      await openMap(page);

      // MAP-HINTS-OFF-1: banner never mounts on the map.
      await expect(page.getByTestId("research-banner")).toHaveCount(0);

      const card = await openPlaceCard(page);
      await expect(page.locator(".app-shell.place-open")).toBeVisible();
      await expect(page.getByTestId("research-banner")).toHaveCount(0);
      const cardBox = await card.boundingBox();
      expect(cardBox, "place card box").toBeTruthy();
      expect(cardBox!.height).toBeGreaterThan(40);
    });
  });
}

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

async function openPlaceCard(page: Page) {
  const search = page.locator("#place-query");
  await search.fill("55.86090, -4.25140");
  await page.locator(".hud-search-go").click();
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".app-shell.place-open")).toBeVisible();
  await expect
    .poll(async () => {
      const box = await card.boundingBox();
      return box ? Math.round(box.height) : 0;
    })
    .toBeGreaterThan(40);
  return card;
}

async function assertFullyVisible(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const result = await locator.evaluate((el) => {
    const style = getComputedStyle(el);
    const box = el.getBoundingClientRect();
    return {
      visibility: style.visibility,
      opacity: Number(style.opacity),
      display: style.display,
      left: box.left,
      top: box.top,
      right: box.right,
      bottom: box.bottom,
      width: box.width,
      height: box.height,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
    };
  });
  expect(result.visibility, label).not.toBe("hidden");
  expect(result.opacity, label).toBeGreaterThan(0);
  expect(result.display, label).not.toBe("none");
  expect(result.width, `${label} has no area`).toBeGreaterThan(0);
  expect(result.height, `${label} has no area`).toBeGreaterThan(0);
  expect(result.left, `${label} left outside viewport`).toBeGreaterThanOrEqual(
    -0.5,
  );
  expect(result.top, `${label} top outside viewport`).toBeGreaterThanOrEqual(
    -0.5,
  );
  expect(
    result.right,
    `${label} right outside viewport`,
  ).toBeLessThanOrEqual(result.innerWidth + 0.5);
  expect(
    result.bottom,
    `${label} bottom outside viewport`,
  ).toBeLessThanOrEqual(result.innerHeight + 0.5);
}

async function assertCenterTappable(locator: Locator, label: string) {
  const box = await locator.boundingBox();
  expect(box, `${label} box`).toBeTruthy();
  const mid = {
    x: box!.x + box!.width / 2,
    y: box!.y + box!.height / 2,
  };
  const hit = await pageEvaluateHit(locator, mid);
  expect(hit, `${label} center covered by ${hit}`).toBe(true);
}

async function pageEvaluateHit(
  locator: Locator,
  point: { x: number; y: number },
): Promise<boolean> {
  return locator.evaluate((el, p) => {
    const hit = document.elementFromPoint(p.x, p.y);
    return Boolean(hit && (hit === el || el.contains(hit)));
  }, point);
}
