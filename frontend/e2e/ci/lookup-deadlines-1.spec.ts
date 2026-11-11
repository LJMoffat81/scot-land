import { readFileSync } from "node:fs";
import { join } from "node:path";
import { type Page, type Route } from "@playwright/test";
import { test, expect } from "./_fixtures";
import {
  DUMMY_ESRI_KEY,
  assertConsoleClean,
  attachConsoleGate,
  fulfillEmptyGlyph,
  injectEsriBasemapKey,
  registerOpenFreeMapFontStub,
} from "./_mapCardsHelpers";
import {
  DATA_ZONE_AT_TIMEOUT_MS,
  LOOKUP_TIMEOUT_MS,
  POSTCODES_ONLY,
} from "../../lib/api";
import {
  LOOKUP_ERROR_COPY,
  PLACE_CARD_ERROR_LINE,
  PLACE_CARD_TRY_AGAIN_LABEL,
} from "../../lib/placeCard";

registerOpenFreeMapFontStub();

const LOOKUP_LINE = "We couldn't load this area just now.";
const ERROR_LINE = "Something went wrong. Please try again.";
const TRY_LABEL = "Try again";

const A = { q: "EH1 1YZ", lat: 55.953251, lng: -3.188267, name: "Old Town Yard", pc: "EH1 1YZ" };
const B = { q: "G2 1DU", lat: 55.861114, lng: -4.251203, name: "Glasgow Cross", pc: "G2 1DU" };

const WIDTHS = [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const;

const TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

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
    { id: "background", type: "background", paint: { "background-color": "#e8eef4" } },
    { id: "stub-raster", type: "raster", source: "stub" },
  ],
};

const EMPTY_FC = JSON.stringify({ type: "FeatureCollection", features: [] });
const MANIFEST = JSON.stringify({ schema: 1, tilesets: {} });

class Hold {
  private releaseFn: () => void = () => {};
  readonly promise: Promise<void>;
  constructor() {
    this.promise = new Promise((resolve) => {
      this.releaseFn = resolve;
    });
  }
  release(): void {
    this.releaseFn();
  }
}

function assertLockedCopy(): void {
  expect(LOOKUP_ERROR_COPY).toBe(LOOKUP_LINE);
  expect(PLACE_CARD_ERROR_LINE).toBe(ERROR_LINE);
  expect(PLACE_CARD_TRY_AGAIN_LABEL).toBe(TRY_LABEL);
}

function cardBody(lat: number, lng: number, name: string) {
  return {
    contract: "place_card_v1",
    lat,
    lng,
    place_label: name,
    council_name: "City of Edinburgh",
    data_zone: { status: "ok", code: "S01006506", name: "Old Town", vintage: 2022 },
    intermediate_zone: { status: "no_data", name: null },
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
  };
}

function placeByQuery(q: string) {
  const text = q.toUpperCase();
  if (text.includes("G2")) return B;
  return A;
}

async function fulfillJson(route: Route, status: number, body: unknown) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

/** Stub basemap style/tiles so CDN flakes cannot throw a bare pageerror. */
async function stubMapBasemap(page: Page) {
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
    if (/\/fonts\//i.test(url)) {
      await fulfillEmptyGlyph(route);
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/ArcGIS/rest/services/World_Imagery/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/api/parcels/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/api/context/**/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
}

async function stubEsriStyle(page: Page) {
  const fixturePath = join(process.cwd(), "e2e", "fixtures", "esri-imagery-style.json");
  const style = JSON.parse(readFileSync(fixturePath, "utf8")) as {
    sprite: string;
  };
  await page.route("**/basemapstyles-api.arcgis.com/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(style),
    });
  });
  await page.route(`${style.sprite}.json`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ image: "root.png", width: 1, height: 1 }),
    });
  });
  await page.route(`${style.sprite}.png`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
  await page.route("**/basemaps-api.arcgis.com/**/*.pbf**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/x-protobuf",
      body: Buffer.from("ChoKEU9wZW4gU2FucyBSZWd1bGFyEgUwLTI1NQ==", "base64"),
    });
  });
  await page.route("**/ibasemaps-api.arcgis.com/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: TINY_PNG,
    });
  });
}

type LookupHit = { path: string };

function isCountedLookup(pathname: string): boolean {
  return (
    pathname === "/backend/place" ||
    pathname.startsWith("/backend/postcode/") ||
    pathname === "/backend/geocode/postcode" ||
    pathname === "/backend/platform/place"
  );
}

async function routeShell(
  page: Page,
  unexpected: string[],
  hits: LookupHit[],
  onLookup: (route: Route, url: URL) => Promise<void>,
) {
  await page.route("**/backend/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/health")) {
      await fulfillJson(route, 200, { status: "ok", version: "e2e" });
      return;
    }
    if (path.endsWith("/layers/catalog")) {
      await fulfillJson(route, 200, { version: 2, layers: [] });
      return;
    }
    if (path.endsWith("/v1/tiles/manifest.json")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: MANIFEST,
      });
      return;
    }
    if (
      path === "/backend/place" ||
      path.startsWith("/backend/postcode/") ||
      path === "/backend/geocode/postcode" ||
      path === "/backend/platform/place" ||
      path === "/backend/layers/context/data-zones/at"
    ) {
      if (isCountedLookup(path)) hits.push({ path });
      await onLookup(route, url);
      return;
    }
    if (
      path.includes("/layers/") ||
      path.includes("/boundaries/") ||
      path.includes("/v1/tiles/")
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: path.includes("/v1/tiles/") ? MANIFEST : EMPTY_FC,
      });
      return;
    }
    unexpected.push(path);
    await fulfillJson(route, 200, {});
  });
}

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await page.locator("#place-query").waitFor();
  await page.clock.install();
}

async function submit(page: Page, q: string) {
  const input = page.locator("#place-query");
  await input.fill(q);
  await input.press("Enter");
}

async function nodePause() {
  await new Promise((resolve) => {
    setTimeout(resolve, 40);
  });
}

async function assertLookupError(page: Page, prefix: "place-card" | "search") {
  assertLockedCopy();
  await expect(page.getByText("Looking up…", { exact: true })).toHaveCount(0);
  await expect(page.getByTestId("place-card-loading")).toHaveCount(0);
  const region = page.getByTestId(`${prefix}-retry-state`);
  await expect(region).toBeVisible();
  const line = page.locator(".retry-state-line:visible");
  await expect(line).toHaveCount(1);
  await expect(line).toHaveText(LOOKUP_LINE);
  await expect(page.getByText(ERROR_LINE, { exact: true })).toHaveCount(0);
  const button = region.locator("button.retry-state-button");
  await expect(button).toBeVisible();
  await expect(button).toHaveText(TRY_LABEL);
  const box = await button.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.width).toBeGreaterThanOrEqual(44);
  expect(box!.height).toBeGreaterThanOrEqual(44);
  const wording = await region.innerText();
  expect(wording).not.toMatch(/\d/);
  expect(wording).not.toMatch(/server/i);
  expect(wording).not.toMatch(/cloudflare/i);
}

function dzOk() {
  return { code: "S01006506", name: "Old Town", vintage: 2022 };
}

async function countRetryInserts(page: Page): Promise<number> {
  return page.evaluate(() => {
    const holder = window as Window & { __lookupRetryInserts?: number };
    return holder.__lookupRetryInserts ?? 0;
  });
}

function intersects(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

for (const viewport of WIDTHS) {
  test.describe(`lookup deadlines ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("N1 stalled place card shows the lookup line at the time limit", async ({ page }) => {
      test.setTimeout(120_000);
      assertLockedCopy();
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const cardHold = new Hold();
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          const place = placeByQuery(url.searchParams.get("q") ?? "");
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: place.pc,
            lat: place.lat,
            lng: place.lng,
            label: place.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          await cardHold.promise;
          await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const seen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/platform/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS - 1000);
        await expect(page.getByTestId("place-card-loading")).toBeVisible();
        await page.clock.runFor(2000);
        await assertLookupError(page, "place-card");
        await expect(page.getByTestId("place-card-retry-state")).toHaveAttribute(
          "data-error-kind",
          "timeout",
        );
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        cardHold.release();
        await nodePause();
      }
    });

    test("N2a repeated 524 shows origin timeout after one retry", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/platform/place", status: 524, count: 2 });
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      let platformPlaceHits = 0;
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          platformPlaceHits += 1;
          await fulfillJson(route, 524, { detail: "origin" });
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      await openMap(page);
      const seen = page.waitForRequest(
        (req) => new URL(req.url()).pathname === "/backend/platform/place",
        { timeout: 10_000 },
      );
      await submit(page, A.q);
      await seen;
      await page.clock.runFor(3000);
      expect(platformPlaceHits).toBe(2);
      await assertLookupError(page, "place-card");
      await expect(page.getByTestId("place-card-retry-state")).toHaveAttribute(
        "data-error-kind",
        "origin_timeout",
      );
      expect(unexpected).toEqual([]);
      assertConsoleClean(gate);
    });

    test("N2b repeated 503 keeps three tries and an http kind", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/platform/place", status: 503, count: 3 });
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      let platformPlaceHits = 0;
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          platformPlaceHits += 1;
          await fulfillJson(route, 503, { detail: "busy" });
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      await openMap(page);
      const seen = page.waitForRequest(
        (req) => new URL(req.url()).pathname === "/backend/platform/place",
        { timeout: 10_000 },
      );
      await submit(page, A.q);
      await seen;
      await page.clock.runFor(3000);
      expect(platformPlaceHits).toBe(3);
      await assertLookupError(page, "place-card");
      await expect(page.getByTestId("place-card-retry-state")).toHaveAttribute(
        "data-error-kind",
        "http",
      );
      expect(unexpected).toEqual([]);
      assertConsoleClean(gate);
    });

    test("N3 a five second success never shows an error", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const cardHold = new Hold();
      await stubMapBasemap(page);
      await page.addInitScript(() => {
        const holder = window as Window & { __lookupRetryInserts?: number };
        holder.__lookupRetryInserts = 0;
        const watch = () => {
          const obs = new MutationObserver((records) => {
            for (const record of records) {
              for (const node of record.addedNodes) {
                if (!(node instanceof Element)) continue;
                if (
                  node.matches("[data-testid$='-retry-state']") ||
                  node.querySelector("[data-testid$='-retry-state']")
                ) {
                  holder.__lookupRetryInserts = (holder.__lookupRetryInserts ?? 0) + 1;
                }
              }
            }
          });
          obs.observe(document.documentElement, { childList: true, subtree: true });
        };
        if (document.documentElement) watch();
        else document.addEventListener("DOMContentLoaded", watch, { once: true });
      });
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          await cardHold.promise;
          await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const seen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/platform/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(5000);
        cardHold.release();
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        expect(await countRetryInserts(page)).toBe(0);
        await expect(page.getByTestId("place-card-loading")).toHaveCount(0);
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        cardHold.release();
        await nodePause();
      }
    });

    test("a rendered card is not replaced when the chain deadline passes", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const cardHold = new Hold();
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          await cardHold.promise;
          await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const seen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/platform/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(5000);
        cardHold.release();
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        await page.clock.runFor(26_000);
        await expect(page.locator("[data-testid$='-retry-state']")).toHaveCount(0);
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        cardHold.release();
        await nodePause();
      }
    });

    test("N4 a stalled data zone does not block the card", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const log: string[] = [];
      const dzHold = new Hold();
      page.on("request", (req) => {
        const path = new URL(req.url()).pathname;
        if (path === "/backend/platform/place") log.push("platform/place");
        if (path === "/backend/layers/context/data-zones/at") log.push("dz-request");
      });
      page.on("response", (res) => {
        if (new URL(res.url()).pathname === "/backend/layers/context/data-zones/at") {
          log.push("dz-response");
        }
      });
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          log.push("dz-request");
          await dzHold.promise;
          log.push("dz-response");
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          log.push("platform/place");
          await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const seen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/platform/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await seen;
        expect(log.indexOf("platform/place")).toBeGreaterThanOrEqual(0);
        expect(log.includes("dz-response")).toBe(false);
        await page.clock.runFor(DATA_ZONE_AT_TIMEOUT_MS + 500);
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        await expect(page.locator("[data-testid$='-retry-state']")).toHaveCount(0);
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        dzHold.release();
        await nodePause();
      }
    });

    test("N5 a superseded search cannot overwrite the newer card", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const failures: { url: string; errorText: string }[] = [];
      const aHold = new Hold();
      page.on("requestfailed", (req) => {
        failures.push({
          url: req.url(),
          errorText: req.failure()?.errorText ?? "",
        });
      });
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          const place = placeByQuery(url.searchParams.get("q") ?? "");
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: place.pc,
            lat: place.lat,
            lng: place.lng,
            label: place.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          const raw = decodeURIComponent(path.split("/").pop() ?? "");
          const place = placeByQuery(raw);
          await fulfillJson(route, 200, {
            postcode: { postcode: place.pc },
            lat: place.lat,
            lng: place.lng,
            square: { lat: place.lat, lng: place.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          const lat = url.searchParams.get("lat");
          if (lat === String(A.lat)) {
            await aHold.promise;
            await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
            return;
          }
          await fulfillJson(route, 200, cardBody(B.lat, B.lng, B.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const seenA = page.waitForRequest((req) => {
          const url = new URL(req.url());
          return url.pathname === "/backend/platform/place" && url.searchParams.get("lat") === String(A.lat);
        }, { timeout: 10_000 });
        await submit(page, A.q);
        await seenA;
        const seenB = page.waitForRequest((req) => {
          const url = new URL(req.url());
          return url.pathname === "/backend/platform/place" && url.searchParams.get("lat") === String(B.lat);
        }, { timeout: 10_000 });
        await submit(page, B.q);
        await seenB;
        await expect(page.getByTestId("place-card-place")).toHaveText(B.name);
        aHold.release();
        await page.clock.runFor(2000);
        await expect(page.getByTestId("place-card-place")).toHaveText(B.name);
        await expect(page.locator("[data-testid$='-retry-state']")).toHaveCount(0);
        const aFails = failures.filter((item) => {
          const url = new URL(item.url);
          return (
            url.pathname === "/backend/platform/place" &&
            url.searchParams.get("lat") === String(A.lat) &&
            url.searchParams.get("lng") === String(A.lng)
          );
        });
        expect(aFails).toHaveLength(1);
        expect(aFails[0]?.errorText).toBe("net::ERR_ABORTED");
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        aHold.release();
        await nodePause();
      }
    });

    test("N6 Try again sends one request and recovers", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const firstHold = new Hold();
      let mode: "hold" | "ok" = "hold";
      let platformPlaceHits = 0;
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          platformPlaceHits += 1;
          if (mode === "hold") {
            await firstHold.promise;
          }
          await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const seen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/platform/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS - 1000);
        await page.clock.runFor(2000);
        await assertLookupError(page, "place-card");
        mode = "ok";
        const button = page.getByTestId("place-card-try-again");
        await button.evaluate((el) => {
          (el as HTMLButtonElement).click();
          (el as HTMLButtonElement).click();
        });
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        expect(platformPlaceHits).toBe(2);
        await expect(page.locator("[data-testid$='-retry-state']")).toHaveCount(0);
        await expect(page.getByTestId("place-card")).toBeVisible();
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        firstHold.release();
        await nodePause();
      }
    });

    test("N8 a blank or short query sends no lookup", async ({ page }) => {
      test.setTimeout(120_000);
      assertLockedCopy();
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        unexpected.push(url.pathname);
        await fulfillJson(route, 200, {});
      });
      await openMap(page);
      const input = page.locator("#place-query");
      await input.fill("");
      await input.press("Enter");
      await expect(page.locator(".search-suggest-note")).toHaveText(POSTCODES_ONLY);
      await input.fill("   ");
      await input.press("Enter");
      await expect(page.locator(".search-suggest-note")).toHaveText(POSTCODES_ONLY);
      await input.fill("");
      await input.pressSequentially("E");
      await input.pressSequentially("H");
      await page.clock.runFor(1000);
      const lookupHits = hits.filter((hit) => isCountedLookup(hit.path));
      expect(lookupHits).toEqual([]);
      expect(unexpected).toEqual([]);
      assertConsoleClean(gate);
    });

    test("N12a the chain deadline stops a card whose steps each fit", async ({ page }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const placeHold = new Hold();
      const postcodeHold = new Hold();
      const cardHold = new Hold();
      const failures: string[] = [];
      page.on("requestfailed", (req) => {
        failures.push(req.url());
      });
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await placeHold.promise;
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await postcodeHold.promise;
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          await cardHold.promise;
          await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const placeSeen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await placeSeen;
        await page.clock.runFor(15_000);
        placeHold.release();
        const postcodeSeen = page.waitForRequest(
          (req) => new URL(req.url()).pathname.startsWith("/backend/postcode/"),
          { timeout: 10_000 },
        );
        await postcodeSeen;
        await page.clock.runFor(5_000);
        postcodeHold.release();
        const cardSeen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/platform/place",
          { timeout: 10_000 },
        );
        await cardSeen;
        await page.clock.runFor(9_000);
        await expect(page.locator("[data-testid$='-retry-state']")).toHaveCount(0);
        await page.clock.runFor(2_000);
        await assertLookupError(page, "place-card");
        await expect(page.getByTestId("place-card-retry-state")).toHaveAttribute(
          "data-error-kind",
          "timeout",
        );
        const aborted = failures.filter(
          (url) => new URL(url).pathname === "/backend/platform/place",
        );
        expect(aborted.length).toBeGreaterThanOrEqual(1);
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        placeHold.release();
        postcodeHold.release();
        cardHold.release();
        await nodePause();
      }
    });

    test("N12b the chain deadline stops a slow search before a card", async ({ page }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const placeHold = new Hold();
      const postcodeHold = new Hold();
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await placeHold.promise;
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await postcodeHold.promise;
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/platform/place" || path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, path.endsWith("/at") ? dzOk() : cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const placeSeen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await placeSeen;
        await page.clock.runFor(15_000);
        placeHold.release();
        const postcodeSeen = page.waitForRequest(
          (req) => new URL(req.url()).pathname.startsWith("/backend/postcode/"),
          { timeout: 10_000 },
        );
        await postcodeSeen;
        await page.clock.runFor(16_000);
        await assertLookupError(page, "search");
        await expect(page.getByTestId("place-card")).toHaveCount(0);
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        placeHold.release();
        postcodeHold.release();
        await nodePause();
      }
    });

    test("N13 focus moves to Try again and Enter retries once", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const cardHold = new Hold();
      let mode: "hold" | "ok" = "hold";
      let platformPlaceHits = 0;
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          platformPlaceHits += 1;
          if (mode === "hold") await cardHold.promise;
          await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const seen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/platform/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS + 1000);
        await assertLookupError(page, "place-card");
        const active = await page.evaluate(
          () => document.activeElement?.getAttribute("data-testid") ?? "",
        );
        expect(active).toBe("place-card-try-again");
        mode = "ok";
        const before = platformPlaceHits;
        await page.keyboard.press("Enter");
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        expect(platformPlaceHits).toBe(before + 1);
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        cardHold.release();
        await nodePause();
      }
    });

    test("N14 the card line is a polite status", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      const cardHold = new Hold();
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        const path = url.pathname;
        if (path === "/backend/place") {
          await fulfillJson(route, 200, {
            kind: "postcode",
            postcode: A.pc,
            lat: A.lat,
            lng: A.lng,
            label: A.pc,
          });
          return;
        }
        if (path.startsWith("/backend/postcode/")) {
          await fulfillJson(route, 200, {
            postcode: { postcode: A.pc },
            lat: A.lat,
            lng: A.lng,
            square: { lat: A.lat, lng: A.lng },
          });
          return;
        }
        if (path === "/backend/layers/context/data-zones/at") {
          await fulfillJson(route, 200, dzOk());
          return;
        }
        if (path === "/backend/platform/place") {
          await cardHold.promise;
          await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
          return;
        }
        unexpected.push(path);
        await fulfillJson(route, 200, {});
      });
      try {
        await openMap(page);
        const seen = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/platform/place",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS + 1000);
        const line = page.getByText(LOOKUP_LINE, { exact: true });
        await expect(line).toHaveCount(1);
        await expect(line).toHaveAttribute("role", "status");
        await expect(line).toHaveAttribute("aria-live", "polite");
        expect(await line.evaluate((el) => el.classList.contains("retry-state-line"))).toBe(true);
        expect(await line.evaluate((el) => !!el.closest('[role="alert"]'))).toBe(false);
        expect(unexpected).toEqual([]);
        assertConsoleClean(gate);
      } finally {
        cardHold.release();
        await nodePause();
      }
    });

    test("N14 the search line is a polite status", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/place", status: 503, count: 3 });
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        if (url.pathname === "/backend/place") {
          await fulfillJson(route, 503, { detail: "busy" });
          return;
        }
        unexpected.push(url.pathname);
        await fulfillJson(route, 200, {});
      });
      await openMap(page);
      const seen = page.waitForRequest(
        (req) => new URL(req.url()).pathname === "/backend/place",
        { timeout: 10_000 },
      );
      await submit(page, "Leith Walk");
      await seen;
      await page.clock.runFor(3000);
      const line = page.getByText(LOOKUP_LINE, { exact: true });
      await expect(line).toHaveCount(1);
      await expect(line).toHaveAttribute("role", "status");
      await expect(line).toHaveAttribute("aria-live", "polite");
      expect(await line.evaluate((el) => el.classList.contains("retry-state-line"))).toBe(true);
      expect(await line.evaluate((el) => !!el.closest('[role="alert"]'))).toBe(false);
      await expect(page.locator("#place-suggestions .search-suggest-note")).toHaveCount(0);
      expect(unexpected).toEqual([]);
      assertConsoleClean(gate);
    });

    test("N15 editing the query clears the search error", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/place", status: 503, count: 3 });
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        if (url.pathname === "/backend/place") {
          await fulfillJson(route, 503, { detail: "busy" });
          return;
        }
        unexpected.push(url.pathname);
        await fulfillJson(route, 200, {});
      });
      await openMap(page);
      const seen = page.waitForRequest(
        (req) => new URL(req.url()).pathname === "/backend/place",
        { timeout: 10_000 },
      );
      await submit(page, "Leith Walk");
      await seen;
      await page.clock.runFor(3000);
      await expect(page.getByTestId("search-retry-state")).toBeVisible();
      const before = hits.length;
      const input = page.locator("#place-query");
      await input.focus();
      await input.evaluate((el) => {
        const field = el as HTMLInputElement;
        field.setSelectionRange(0, field.value.length);
      });
      await page.keyboard.type("E");
      await expect(page.getByTestId("search-retry-state")).toHaveCount(0);
      await page.clock.runFor(1000);
      expect(hits.length - before).toBe(0);
      await input.evaluate((el) => {
        const field = el as HTMLInputElement;
        field.setSelectionRange(0, field.value.length);
      });
      const beforeBlank = hits.length;
      await page.keyboard.press("Backspace");
      await expect(page.getByTestId("search-retry-state")).toHaveCount(0);
      await page.clock.runFor(1000);
      expect(hits.length - beforeBlank).toBe(0);
      expect(unexpected).toEqual([]);
      assertConsoleClean(gate);
    });

    test("N17 a search failure does not keep the old suggestion note", async ({ page }) => {
      test.setTimeout(120_000);
      assertLockedCopy();
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/place", status: 503, count: 3 });
      const unexpected: string[] = [];
      const hits: LookupHit[] = [];
      await stubMapBasemap(page);
      await routeShell(page, unexpected, hits, async (route, url) => {
        if (url.pathname === "/backend/place") {
          await fulfillJson(route, 503, { detail: "busy" });
          return;
        }
        await fulfillJson(route, 200, {});
      });
      await openMap(page);
      const seen = page.waitForRequest(
        (req) => new URL(req.url()).pathname === "/backend/place",
        { timeout: 10_000 },
      );
      await submit(page, "Leith Walk");
      await seen;
      await page.clock.runFor(3000);
      await expect(page.getByText(LOOKUP_LINE, { exact: true })).toBeVisible();
      await expect(page.getByTestId("search-retry-state")).toBeVisible();
      await expect(page.locator("#place-suggestions li.search-suggest-note")).toHaveCount(0);
      await expect(page.getByTestId("search-retry-state").locator("button.retry-state-button")).toHaveText(
        TRY_LABEL,
      );
      expect(PLACE_CARD_TRY_AGAIN_LABEL).toBe(TRY_LABEL);
      expect(unexpected).toEqual([]);
      assertConsoleClean(gate);
    });
  });
}

test.describe("N16 390px error does not cover map controls", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("search and card errors stay off Layers, 3D and Aerial", async ({ page }) => {
    test.setTimeout(180_000);
    const gate = attachConsoleGate(page);
    gate.expectError({ urlPath: "/backend/place", status: 503, count: 3 });
    const unexpected: string[] = [];
    const hits: LookupHit[] = [];
    const cardHold = new Hold();
    let placeMode: "fail" | "ok" = "fail";
    await injectEsriBasemapKey(page, DUMMY_ESRI_KEY);
    await stubMapBasemap(page);
    await stubEsriStyle(page);
    await routeShell(page, unexpected, hits, async (route, url) => {
      const path = url.pathname;
      if (path === "/backend/place") {
        if (placeMode === "fail") {
          await fulfillJson(route, 503, { detail: "busy" });
          return;
        }
        await fulfillJson(route, 200, {
          kind: "postcode",
          postcode: A.pc,
          lat: A.lat,
          lng: A.lng,
          label: A.pc,
        });
        return;
      }
      if (path.startsWith("/backend/postcode/")) {
        await fulfillJson(route, 200, {
          postcode: { postcode: A.pc },
          lat: A.lat,
          lng: A.lng,
          square: { lat: A.lat, lng: A.lng },
        });
        return;
      }
      if (path === "/backend/layers/context/data-zones/at") {
        await fulfillJson(route, 200, dzOk());
        return;
      }
      if (path === "/backend/platform/place") {
        await cardHold.promise;
        await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
        return;
      }
      unexpected.push(path);
      await fulfillJson(route, 200, {});
    });
    try {
      await openMap(page);
      const controls = [
        page.getByTestId("hud-layers-btn"),
        page.getByTestId("view-3d-toggle"),
        page.getByTestId("basemap-switcher"),
      ];
      const seenSearch = page.waitForRequest(
        (req) => new URL(req.url()).pathname === "/backend/place",
        { timeout: 10_000 },
      );
      await submit(page, "Leith Walk");
      await seenSearch;
      await page.clock.runFor(3000);
      const searchRegion = page.getByTestId("search-retry-state");
      await expect(searchRegion).toBeVisible();
      await assertNoOverlap(page, searchRegion, controls);
      placeMode = "ok";
      const seenCard = page.waitForRequest(
        (req) => new URL(req.url()).pathname === "/backend/platform/place",
        { timeout: 10_000 },
      );
      await submit(page, A.q);
      await seenCard;
      await page.clock.runFor(LOOKUP_TIMEOUT_MS + 1000);
      const cardRegion = page.getByTestId("place-card-retry-state");
      await expect(cardRegion).toBeVisible();
      await assertNoOverlap(page, cardRegion, controls);
      expect(unexpected).toEqual([]);
      assertConsoleClean(gate);
    } finally {
      cardHold.release();
      await nodePause();
    }
  });
});

async function assertNoOverlap(
  page: Page,
  region: ReturnType<Page["getByTestId"]>,
  controls: ReturnType<Page["getByTestId"]>[],
) {
  const regionBox = await region.boundingBox();
  expect(regionBox).not.toBeNull();
  expect(intersects(regionBox!, regionBox!)).toBe(true);
  for (const control of controls) {
    const box = await control.boundingBox();
    expect(box).not.toBeNull();
    expect(intersects(regionBox!, box!)).toBe(false);
    await control.click({ trial: true, timeout: 5_000 });
  }
}
