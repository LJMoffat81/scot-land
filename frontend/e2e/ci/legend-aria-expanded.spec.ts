import { expect, test, type Page } from "@playwright/test";

/**
 * UX-02 — legend fold aria-expanded must match #hud-scotland-body visibility.
 * At 1280 with a place card open the fold is toggleable; click it 5 times.
 * Console / pageerror fail the test (do not loosen).
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
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
  await page.locator("button.hud-scotland-fold").waitFor({ state: "attached" });
  await page.locator("#hud-scotland-body").waitFor({ state: "attached" });
}

async function openPlaceCard(page: Page) {
  const search = page.locator("#place-query");
  await search.fill("55.86090, -4.25140");
  await page.locator(".hud-search-go").click();
  const card = page.locator("aside.place-card-stub, aside.place-card").first();
  await expect(card).toBeVisible({ timeout: 45_000 });
  await expect(page.locator(".app-shell.place-open")).toBeVisible();
  return card;
}

async function expectAriaMatchesBody(page: Page, label: string) {
  const toggle = page.locator("button.hud-scotland-fold");
  const body = page.locator("#hud-scotland-body");
  const bodyVisible = await body.isVisible();
  await expect(
    toggle,
    `${label}: aria-expanded must match #hud-scotland-body visible=${bodyVisible}`,
  ).toHaveAttribute("aria-expanded", bodyVisible ? "true" : "false");
  await expect(toggle).toHaveAttribute("aria-controls", "hud-scotland-body");
}

test.describe("UX-02 legend aria-expanded at 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("fold aria-expanded tracks body visibility across 5 toggles", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await openMap(page);

    // Desktop: body is shown while the fold is still hidden — aria must agree.
    await expect(page.locator("#hud-scotland-body")).toBeVisible();
    await expect(page.locator("button.hud-scotland-fold")).toBeHidden();
    await expectAriaMatchesBody(page, "before place card");

    await openPlaceCard(page);

    const toggle = page.locator("button.hud-scotland-fold");
    await expect(toggle).toBeVisible();
    await expectAriaMatchesBody(page, "after place card opens");

    for (let step = 1; step <= 5; step += 1) {
      await toggle.click();
      await expectAriaMatchesBody(page, `after toggle ${step}`);
    }

    await expect(page.getByText(/£\d/)).toHaveCount(0);
  });
});
