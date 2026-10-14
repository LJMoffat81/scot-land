import { expect, test, type Page } from "@playwright/test";

const OUT_OF_SCOTLAND_LINE =
  "This spot is outside Scotland's land map. Tap on land to see a place.";

/** SW-019 sample: west of the public bounds check (lng < -8.5). */
const OUTSIDE_LAT = 59.66616;
const OUTSIDE_LNG = -9.196485;
// Exact bug-report URL digits (parseCoordinates must accept these).
const OUTSIDE_URL = "/?lat=59.666160&lng=-9.196485";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const OUTSIDE_DETAIL = "Coordinates appear to be outside Scotland.";

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
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
}

/** Sea / outside-Scotland place APIs — 404 DZ miss, or 400 bounds reject. */
async function stubSeaMissPlaceApis(
  page: Page,
  lat: number,
  lng: number,
  mode: "dz404" | "bounds400",
) {
  if (mode === "dz404") {
    await page.route("**/layers/context/data-zones/at**", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          detail: {
            error: "no_data_zone_at_point",
            lat,
            lon: lng,
          },
        }),
      });
    });
    await page.route("**/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          contract: "place_card_v1",
          lat,
          lng,
          place_label: null,
          council_name: null,
          data_zone: {
            status: "miss",
            code: null,
            name: null,
            vintage: null,
            note: "No Scottish data zone contains this point (e.g. at sea).",
          },
          intermediate_zone: { status: "no_data", name: null, note: null },
          square_reference: "Scot-LAND square reference 0,0",
          agr_rows: [
            {
              id: "surface",
              label: "Land",
              tag: "proxy",
              status: "coming_soon",
              applies: true,
            },
          ],
          constraints: [],
          layers: [],
          links: [],
        }),
      });
    });
    return;
  }

  // SW-019: bounds check 400 from place APIs (and DZ).
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

async function expectOutsideScotlandLine(page: Page, timeoutMs = 3_000) {
  const line = page.getByTestId("place-card-out-of-scotland");
  await expect(line).toBeVisible({ timeout: timeoutMs });
  await expect(line).toHaveText(OUT_OF_SCOTLAND_LINE);
  await expect(page.getByText("Looking up this spot…")).toHaveCount(0);
  await expect(page.locator(".place-card-loading")).toHaveCount(0);
}

async function expectPlainLineOnly(page: Page) {
  const card = page.getByTestId("place-card");
  await expect(card.getByTestId("place-card-value")).toHaveCount(0);
  await expect(card.getByTestId("place-card-limits")).toHaveCount(0);
  await expect(card.getByTestId("place-card-data-zone")).toHaveCount(0);
  await expect(card.getByText("No data")).toHaveCount(0);
  await expect(card.locator(".place-card-field")).toHaveCount(0);
}

test.describe("site-watch D3 sea click", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("click at sea shows one plain line, not No data rows", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);

    const lat = 56.5;
    const lng = -1.5;
    await stubSeaMissPlaceApis(page, lat, lng, "dz404");

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.locator("#place-query").waitFor();

    await page.locator("#place-query").fill(`${lat}, ${lng}`);
    await page.locator(".hud-search-go").click();

    await expectOutsideScotlandLine(page, 30_000);
    await expectPlainLineOnly(page);
    assertConsoleClean(gate);
  });
});

test.describe("site-watch SW-019 outside-Scotland 400", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("URL lat/lng outside Scotland shows plain line within 3s, no spinner", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await stubSeaMissPlaceApis(page, OUTSIDE_LAT, OUTSIDE_LNG, "bounds400");

    await page.goto(OUTSIDE_URL);
    await page.locator(".maplibregl-canvas").waitFor();

    await expectOutsideScotlandLine(page, 3_000);
    await expectPlainLineOnly(page);
    assertConsoleClean(gate);
  });

  test("coordinate search outside Scotland shows plain line within 3s, no spinner", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await stubSeaMissPlaceApis(page, OUTSIDE_LAT, OUTSIDE_LNG, "bounds400");

    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    await page.locator("#place-query").waitFor();

    await page.locator("#place-query").fill("59.666160, -9.196485");
    await page.locator(".hud-search-go").click();

    await expectOutsideScotlandLine(page, 3_000);
    await expectPlainLineOnly(page);
    assertConsoleClean(gate);
  });

  test("map click outside Scotland shows plain line within 3s, no spinner", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    // Any click's lat/lng is mocked to the outside-Scotland 400 path.
    await stubSeaMissPlaceApis(page, OUTSIDE_LAT, OUTSIDE_LNG, "bounds400");

    await page.goto("/");
    const canvas = page.locator(".maplibregl-canvas");
    await canvas.waitFor();
    await page.locator("#place-query").waitFor();

    const box = await canvas.boundingBox();
    expect(box).toBeTruthy();
    await page.mouse.click(
      box!.x + box!.width / 2,
      box!.y + box!.height / 2,
    );

    await expectOutsideScotlandLine(page, 3_000);
    await expectPlainLineOnly(page);
    assertConsoleClean(gate);
  });
});
