import { expect, test, type Page } from "@playwright/test";

/**
 * F2 — country-zoom place pick gate.
 * Zoom < 9: tap flies to 11 + hint; no /platform/place or data-zones/at.
 * Zoom ≥ 9: place card opens. Postcode search still opens a card from zoom 6.
 */

const PLACE_PICK_HINT = "Zoom in to pick a place.";
const POSTCODE = "EH1 1YZ";
const EDINBURGH = { lat: 55.952, lng: -3.189 };

const EMPTY_FC = {
  type: "FeatureCollection",
  features: [],
};

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const PLACE_CARD = {
  contract: "place_card_v1",
  lat: EDINBURGH.lat,
  lng: EDINBURGH.lng,
  place_label: "Edinburgh Old Town",
  council_name: "City of Edinburgh",
  data_zone: {
    status: "ok",
    code: "S01008677",
    name: "Old Town",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "Old Town and Canongate" },
  square_reference: "Scot-LAND square reference 0,0",
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

function attachConsoleTraps(page: Page): string[] {
  const consoleErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    const text = msg.text();
    // Intentional stubbed HTTP errors still log in Chromium.
    if (
      /Failed to load resource: the server responded with a status of \d+/i.test(
        text,
      )
    ) {
      return;
    }
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return;
    }
    consoleErrors.push(text);
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  return consoleErrors;
}

function expectNoConsoleErrors(consoleErrors: string[]) {
  expect(
    consoleErrors,
    `console errors:\n${consoleErrors.join("\n")}`,
  ).toEqual([]);
}

function isBlockedPlaceRequest(url: string): boolean {
  return (
    /\/platform\/place(?:\?|$)/i.test(url) ||
    /\/layers\/context\/data-zones\/at(?:\?|$)/i.test(url)
  );
}

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;

    if (path.includes("/health")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(HEALTH_OK),
      });
      return;
    }

    if (path.includes("/postcode/") || path.includes("/geocode/postcode")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          postcode: { postcode: POSTCODE },
          lat: EDINBURGH.lat,
          lng: EDINBURGH.lng,
          square: { lat: EDINBURGH.lat, lng: EDINBURGH.lng },
        }),
      });
      return;
    }

    if (path.includes("/platform/place")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_CARD),
      });
      return;
    }

    if (path.includes("/layers/context/data-zones/at")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: "S01008677",
          name: "Old Town",
          vintage: 2022,
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

    if (path.includes("/place") && !path.includes("/platform/place")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          kind: "places",
          matches: [
            {
              label: POSTCODE,
              postcode: POSTCODE,
              lat: EDINBURGH.lat,
              lng: EDINBURGH.lng,
            },
          ],
        }),
      });
      return;
    }

    const wantsGeo =
      /\/layers\//i.test(path) ||
      /\/w3w-grid/i.test(path) ||
      /\/parcels/i.test(path);
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(wantsGeo ? EMPTY_FC : {}),
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

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
  await page.locator("#map[data-framed='1']").waitFor({ timeout: 30_000 });
}

async function readZoom(page: Page): Promise<number> {
  return page.locator("#map").evaluate((el) =>
    Number((el as HTMLElement).dataset.zoom),
  );
}

async function zoomToAtLeast(page: Page, target: number) {
  const zoomIn = page.locator(".maplibregl-ctrl-zoom-in");
  for (let step = 0; step < 30; step += 1) {
    const zoom = await readZoom(page);
    if (zoom >= target) return;
    await zoomIn.click({ timeout: 10_000 });
    await page.waitForTimeout(400);
  }
  await expect
    .poll(async () => readZoom(page), { timeout: 20_000 })
    .toBeGreaterThanOrEqual(target);
}

async function clickMapCentre(page: Page) {
  const canvas = page.locator(".maplibregl-canvas");
  const box = await canvas.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
}

test.describe("F2 country-zoom place pick", () => {
  test.use({ viewport: { width: 1440, height: 900 } });

  test("zoom 6 tap shows hint, flies in, and skips place APIs", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page);

    const blockedHits: string[] = [];
    page.on("request", (req) => {
      if (isBlockedPlaceRequest(req.url())) blockedHits.push(req.url());
    });

    await openMap(page);
    const startZoom = await readZoom(page);
    expect(startZoom).toBeLessThan(9);
    // Framed Scotland is typically ~6; keep the stated case honest.
    expect(startZoom).toBeLessThanOrEqual(7.4);

    await clickMapCentre(page);

    const hint = page.getByTestId("place-pick-zoom-hint");
    await expect(hint).toBeVisible({ timeout: 10_000 });
    await expect(hint).toHaveText(PLACE_PICK_HINT);

    await expect
      .poll(async () => readZoom(page), { timeout: 15_000 })
      .toBeGreaterThanOrEqual(10.5);
    await expect
      .poll(async () => readZoom(page), { timeout: 5_000 })
      .toBeCloseTo(11, 0);

    expect(
      blockedHits,
      `unexpected place/DZ-at requests:\n${blockedHits.join("\n")}`,
    ).toEqual([]);
    await expect(page.getByTestId("place-card")).toHaveCount(0);
    await expect(page.locator("aside.place-card-stub")).toHaveCount(0);

    await expect(hint).toBeHidden({ timeout: 6_000 });
    expectNoConsoleErrors(consoleErrors);
  });

  test("zoom 12 tap opens place card", async ({ page }) => {
    test.setTimeout(120_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page);
    await openMap(page);

    await zoomToAtLeast(page, 12);
    expect(await readZoom(page)).toBeGreaterThanOrEqual(12);

    await clickMapCentre(page);

    await expect(page.getByTestId("place-card")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("place-pick-zoom-hint")).toHaveCount(0);
    expectNoConsoleErrors(consoleErrors);
  });

  test("EH1 1YZ search opens place card from zoom 6", async ({ page }) => {
    test.setTimeout(90_000);
    const consoleErrors = attachConsoleTraps(page);
    await stubMapBackend(page);
    await openMap(page);

    const startZoom = await readZoom(page);
    expect(startZoom).toBeLessThan(9);

    const search = page.locator("#place-query");
    await search.fill(POSTCODE);
    await page.locator(".hud-search-go").click();

    await expect(page.getByTestId("place-card")).toBeVisible({
      timeout: 30_000,
    });
    await expect(page.getByTestId("place-pick-zoom-hint")).toHaveCount(0);
    await expect(page.getByTestId("place-card")).not.toContainText(/£\d/);
    expectNoConsoleErrors(consoleErrors);
  });
});
