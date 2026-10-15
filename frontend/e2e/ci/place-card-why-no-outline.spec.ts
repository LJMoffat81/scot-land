import { expect, test, type Page } from "@playwright/test";

/**
 * Suggestion 31 — place card "Why no outline?":
 * - keep "No registered outline at this point" visible
 * - fold the Sasine explanation behind the button (collapsed by default)
 * - at 1280×800 the first value row is visible without scrolling
 * - button toggles aria-expanded; expanded text unchanged
 * Console / pageerror fail the test (do not loosen).
 */

const NO_OUTLINE_STATUS = "No registered outline at this point";
const WHY_NO_OUTLINE = "Why no outline?";
const NO_OUTLINE_NOTE =
  "We found no Land Register boundary at this point. Its title may still be in " +
  "the older Sasine register, or the land may not be registered at all. We estimate " +
  "it by area and land type, and show no boundaries, titles or owners.";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const PLACE_NO_OUTLINE = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "Glasgow",
  council_name: "Glasgow City",
  square_reference: "Scot-LAND square reference · demo",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre", code: "S02001234" },
  land_register_outline: {
    status: "no_outline",
    note: NO_OUTLINE_NOTE,
  },
  land_outline: {
    status: "no_outline",
    label: "Land outline",
    area_sqm: null,
    note: NO_OUTLINE_NOTE,
  },
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "proxy",
      status: "in_progress",
      applies: true,
    },
    {
      id: "natural_resource",
      label: "Natural resource rents",
      tag: "shadow",
      status: "coming_soon",
      applies: true,
    },
    {
      id: "services_of_nature",
      label: "Services of nature",
      tag: "shadow",
      status: "coming_soon",
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

async function stubMapChrome(page: Page) {
  // Quiet unmatched /backend traffic so the Next proxy never 503s in CI.
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_NO_OUTLINE),
      });
      return;
    }
    if (/\/layers\/context\/data-zones\/at/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "ok",
          code: "S01014567",
          name: "City Centre South",
          vintage: 2022,
        }),
      });
      return;
    }
    if (/\/health/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ version: 2, layers: [] }),
      });
      return;
    }
    if (/\/backend\/place/i.test(url) && !/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
      return;
    }
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

  await page.route("**/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_NO_OUTLINE),
    });
  });
  await page.route("**/api/place.json**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PLACE_NO_OUTLINE),
    });
  });
  await page.route("**/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        status: "ok",
        code: "S01014567",
        name: "City Centre South",
        vintage: 2022,
      }),
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

async function openNoOutlineCard(page: Page) {
  // Full document load so client module state (expand Map) cannot leak across tests.
  await page.goto("about:blank");
  await page.goto("/", { waitUntil: "load" });
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();

  await page.locator("#place-query").fill("55.86090, -4.25140");
  await page.locator(".hud-search-go").click();

  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  await expect(page.getByTestId("place-card-loading")).toHaveCount(0, {
    timeout: 30_000,
  });
  await expect(page.getByTestId("place-card-outline-status")).toHaveText(
    NO_OUTLINE_STATUS,
  );
  await expect(page.getByTestId("place-card-why-no-outline-btn")).toBeVisible();
  return card;
}

async function assertFirstValueRowVisibleWithoutScroll(page: Page) {
  const card = page.getByTestId("place-card");
  const firstRow = page.getByTestId("place-card-agr-surface");
  await expect(firstRow).toBeVisible();

  const metrics = await page.evaluate(() => {
    const cardEl = document.querySelector(
      '[data-testid="place-card"]',
    ) as HTMLElement | null;
    const rowEl = document.querySelector(
      '[data-testid="place-card-agr-surface"]',
    ) as HTMLElement | null;
    if (!cardEl || !rowEl) {
      return null;
    }
    const cardRect = cardEl.getBoundingClientRect();
    const rowRect = rowEl.getBoundingClientRect();
    const visibleTop = Math.max(rowRect.top, cardRect.top);
    const visibleBottom = Math.min(rowRect.bottom, cardRect.bottom);
    const visibleH = Math.max(0, visibleBottom - visibleTop);
    return {
      scrollTop: cardEl.scrollTop,
      rowH: rowRect.height,
      visibleH,
      rowTop: rowRect.top,
      cardTop: cardRect.top,
      cardBottom: cardRect.bottom,
    };
  });
  expect(metrics, "card/row metrics").toBeTruthy();
  expect(
    metrics!.scrollTop,
    "card must not need scrolling for first value row",
  ).toBe(0);
  expect(
    metrics!.rowTop,
    "first value row top must sit inside the card",
  ).toBeGreaterThanOrEqual(metrics!.cardTop - 1);
  expect(
    metrics!.rowTop,
    "first value row must start above the card clip edge",
  ).toBeLessThan(metrics!.cardBottom);
  // Majority of the row is in the card scrollport — user can read it without scrolling.
  expect(
    metrics!.rowH,
    "first value row must have height",
  ).toBeGreaterThan(0);
  expect(
    metrics!.visibleH / metrics!.rowH,
    `first value row visible fraction ${metrics!.visibleH}/${metrics!.rowH}`,
  ).toBeGreaterThanOrEqual(0.5);
}

async function clickWhyNoOutline(page: Page) {
  const toggle = page.getByTestId("place-card-why-no-outline-btn");
  await expect(toggle).toBeVisible();
  await toggle.evaluate((el) => (el as HTMLButtonElement).click());
}

async function expectExpanded(page: Page, open: boolean) {
  const toggle = page.getByTestId("place-card-why-no-outline-btn");
  const detail = page.getByTestId("place-card-why-no-outline-detail");
  await expect(toggle).toHaveAttribute("aria-expanded", open ? "true" : "false");
  if (open) {
    await expect(detail).toBeVisible();
    await expect(detail).toHaveText(NO_OUTLINE_NOTE);
  } else {
    await expect(detail).toHaveCount(0);
  }
}

async function runWhyNoOutlineChecks(page: Page, opts: { checkScroll: boolean }) {
  const gate = attachConsoleGate(page);
  await stubMapChrome(page);

  const card = await openNoOutlineCard(page);

  const status = page.getByTestId("place-card-outline-status");
  await expect(status).toHaveText(NO_OUTLINE_STATUS);
  await expect(status).toBeVisible();

  const toggle = page.getByTestId("place-card-why-no-outline-btn");
  await expect(toggle).toBeVisible();
  await expect(toggle).toHaveText(WHY_NO_OUTLINE);
  await expectExpanded(page, false);
  await expect(card).not.toContainText(NO_OUTLINE_NOTE);

  if (opts.checkScroll) {
    await assertFirstValueRowVisibleWithoutScroll(page);
  }

  await expect(async () => {
    const expanded =
      (await toggle.getAttribute("aria-expanded")) === "true";
    if (!expanded) {
      await clickWhyNoOutline(page);
    }
    await expectExpanded(page, true);
  }).toPass({ timeout: 15_000 });

  await expect(async () => {
    const expanded =
      (await page
        .getByTestId("place-card-why-no-outline-btn")
        .getAttribute("aria-expanded")) === "true";
    if (expanded) {
      await clickWhyNoOutline(page);
    }
    await expectExpanded(page, false);
  }).toPass({ timeout: 15_000 });

  await expect(status).toHaveText(NO_OUTLINE_STATUS);
  await expect(card).not.toContainText(NO_OUTLINE_NOTE);

  assertConsoleClean(gate);
}

test.describe("Suggestion 31 why no outline 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("first value row visible; Why no outline? toggles aria-expanded", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await runWhyNoOutlineChecks(page, { checkScroll: true });
  });
});

test.describe("Suggestion 31 why no outline 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("Why no outline? toggles aria-expanded; expanded text unchanged", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await runWhyNoOutlineChecks(page, { checkScroll: false });
  });
});
