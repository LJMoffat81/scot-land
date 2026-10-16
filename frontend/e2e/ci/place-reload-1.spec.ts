import { expect, test, type Page } from "@playwright/test";

/**
 * PLACE-RELOAD-1 — search EH1 1YZ, then reload with panel=place and dz=.
 * The card must come back as the same Data Zone. The reload address may
 * carry a Highland camera; that centre is not the selection, and the
 * centre button is not used. 1280×800 and 390×844. No skips. No public amounts.
 */

const OLD_CODE = "S01008677";
const OLD_NAME = "Old Town";
const HIGH_CODE = "S01012001";
const HIGH_NAME = "Sutherland South";
const EH1 = { lat: 55.9533, lng: -3.1883 };
const HIGHLAND_VIEW = { lng: -4.5, lat: 58.25 };

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

/** 1×1 PNG — stub raster tiles so MapLibre never depends on live CDN in CI. */
const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

/** Minimal style replacing OpenFreeMap positron (no glyphs → no font CDN). */
const STUB_MAP_STYLE = {
  version: 8,
  name: "e2e-stub",
  sources: {
    stub: {
      type: "raster",
      tiles: ["https://tiles.openfreemap.org/e2e-stub/{z}/{x}/{y}.png"],
      tileSize: 256,
    },
  },
  layers: [
    {
      id: "background",
      type: "background",
      paint: { "background-color": "#e8eef4" },
    },
    { id: "stub-raster", type: "raster", source: "stub" },
  ],
};

async function stubOpenFreeMap(page: Page) {
  await page.route("**/tiles.openfreemap.org/**", async (route) => {
    const url = route.request().url();
    if (/\/styles\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(STUB_MAP_STYLE),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
}

function isOldTownPoint(lat: number, lng: number): boolean {
  return Math.abs(lat - EH1.lat) < 0.02 && Math.abs(lng - EH1.lng) < 0.02;
}

function cardFor(lat: number, lng: number) {
  const old = isOldTownPoint(lat, lng);
  return {
    contract: "place_card_v1",
    lat,
    lng,
    place_label: old ? "Edinburgh Old Town" : HIGH_NAME,
    council_name: old ? "City of Edinburgh" : "Highland",
    data_zone: {
      status: "ok",
      code: old ? OLD_CODE : HIGH_CODE,
      name: old ? OLD_NAME : HIGH_NAME,
      vintage: 2011,
    },
    intermediate_zone: {
      status: "ok",
      name: old ? OLD_NAME : HIGH_NAME,
      code: old ? "S02001607" : "S02002264",
    },
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
}

async function stubMap(page: Page) {
  await stubOpenFreeMap(page);
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
    if (/\/layers\/context\/data-zones\/by-code/i.test(url)) {
      const code = new URL(url).searchParams.get("code")?.trim().toUpperCase();
      if (code === OLD_CODE) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            code: OLD_CODE,
            name: OLD_NAME,
            vintage: 2011,
            lat: EH1.lat,
            lng: EH1.lng,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ detail: { error: "data_zone_not_found" } }),
      });
      return;
    }
    if (/\/layers\/context\/data-zones\/at/i.test(url)) {
      const u = new URL(url);
      const lat = Number(u.searchParams.get("lat"));
      const lng = Number(u.searchParams.get("lng") ?? u.searchParams.get("lon"));
      const old = isOldTownPoint(lat, lng);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: old ? OLD_CODE : HIGH_CODE,
          name: old ? OLD_NAME : HIGH_NAME,
          vintage: 2011,
        }),
      });
      return;
    }
    if (/\/platform\/place/i.test(url)) {
      const u = new URL(url);
      const lat = Number(u.searchParams.get("lat"));
      const lng = Number(u.searchParams.get("lng"));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(cardFor(lat, lng)),
      });
      return;
    }
    if (/\/place\?/i.test(url) && !/platform\/place/i.test(url)) {
      const q = (new URL(url).searchParams.get("q") ?? "").toUpperCase();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          q.includes("EH1")
            ? {
                kind: "places",
                matches: [{ label: "EH1 1YZ", lat: EH1.lat, lng: EH1.lng }],
              }
            : { kind: "places", matches: [] },
        ),
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
}

type ConsoleGate = { consoleErrors: string[]; pageErrors: string[] };

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    pageErrors.push(String(err));
  });
  return { consoleErrors, pageErrors };
}

function assertConsoleClean(gate: ConsoleGate) {
  const meaningful = gate.consoleErrors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    if (
      /Failed to load resource: the server responded with a status of (400|404|503)/i.test(
        text,
      )
    ) {
      return false;
    }
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
  expect(gate.pageErrors, `pageerrors:\n${gate.pageErrors.join("\n")}`).toEqual([]);
}

async function zoneOnCard(page: Page) {
  const card = page.getByTestId("place-card");
  await expect(card).toBeVisible({ timeout: 30_000 });
  const code = await card.getAttribute("data-zone-code");
  const name = await card.getAttribute("data-zone-name");
  const title = (await page.getByTestId("place-card-place").innerText()).trim();
  return { code, name, title };
}

async function searchEh1ThenReload(page: Page) {
  const gate = attachConsoleGate(page);
  await page.addInitScript(() => {
    document.addEventListener(
      "click",
      (event) => {
        const target = event.target;
        if (
          target instanceof Element &&
          target.closest("[data-testid='identify-at-centre']")
        ) {
          (window as unknown as { __centreClicked?: boolean }).__centreClicked =
            true;
        }
      },
      true,
    );
  });
  await stubMap(page);
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await page.locator("#place-query").fill("EH1 1YZ");
  await page.locator(".hud-search-go").click();

  const before = await zoneOnCard(page);
  expect(before.code).toBe(OLD_CODE);
  expect(before.name).toBe(OLD_NAME);
  expect(before.title).toBe(OLD_NAME);
  await expect(page.getByTestId("place-card-council")).toHaveText("City of Edinburgh");
  await expect
    .poll(() => new URL(page.url()).searchParams.get("dz"))
    .toBe(OLD_CODE);

  // Reload the selected zone with a Highland camera already in the address.
  // The card must come from dz=, not from that centre and not from the
  // centre button.
  const reloadUrl = new URL(page.url());
  reloadUrl.searchParams.set("panel", "place");
  reloadUrl.searchParams.set(
    "c",
    `${HIGHLAND_VIEW.lng.toFixed(5)},${HIGHLAND_VIEW.lat.toFixed(5)}`,
  );
  expect(reloadUrl.searchParams.get("dz")).toBe(OLD_CODE);
  const [reloadLng, reloadLat] = (reloadUrl.searchParams.get("c") ?? "")
    .split(",")
    .map(Number);
  expect(isOldTownPoint(reloadLat, reloadLng)).toBe(false);

  const placeCalls: string[] = [];
  const onRequest = (request: { url: () => string }) => {
    if (/\/platform\/place\?/.test(request.url())) placeCalls.push(request.url());
  };
  page.on("request", onRequest);
  const byCode = page.waitForRequest(
    (request) =>
      request.url().includes("/layers/context/data-zones/by-code") &&
      request.url().includes(`code=${OLD_CODE}`),
  );
  await page.goto(`${reloadUrl.pathname}${reloadUrl.search}`);
  await byCode;
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const after = await zoneOnCard(page);
  page.off("request", onRequest);
  expect(after.code).toBe(before.code);
  expect(after.name).toBe(before.name);
  expect(after.title).toBe(before.title);
  expect(after.code).not.toBe(HIGH_CODE);
  expect(after.name).not.toBe(HIGH_NAME);
  await expect(page.getByTestId("place-card-council")).toHaveText("City of Edinburgh");
  await expect(page.getByTestId("place-card-place")).not.toContainText(HIGH_NAME);
  expect(new URL(page.url()).searchParams.get("dz")).toBe(OLD_CODE);
  expect(page.url()).toContain("panel=place");
  expect(page.url()).not.toMatch(/EH1/i);
  expect(placeCalls.length).toBeGreaterThan(0);
  for (const url of placeCalls) {
    const parsed = new URL(url);
    const lat = Number(parsed.searchParams.get("lat"));
    const lng = Number(parsed.searchParams.get("lng"));
    expect(isOldTownPoint(lat, lng)).toBe(true);
  }
  expect(
    await page.evaluate(
      () =>
        (window as unknown as { __centreClicked?: boolean }).__centreClicked ===
        true,
    ),
  ).toBe(false);
  assertConsoleClean(gate);
}

test.describe("PLACE-RELOAD-1 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("EH1 1YZ reload keeps the same zone code and name", async ({ page }) => {
    test.setTimeout(90_000);
    await searchEh1ThenReload(page);
  });
});

test.describe("PLACE-RELOAD-1 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("EH1 1YZ reload keeps the same zone code and name", async ({ page }) => {
    test.setTimeout(90_000);
    await searchEh1ThenReload(page);
  });
});
