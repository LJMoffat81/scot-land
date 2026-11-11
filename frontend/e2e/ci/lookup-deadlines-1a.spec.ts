import { readFileSync } from "node:fs";
import { join } from "node:path";
import { type Locator, type Page, type Route } from "@playwright/test";
import { test, expect } from "./_fixtures";
import {
  DUMMY_ESRI_KEY,
  assertConsoleClean,
  attachConsoleGate,
  fulfillEmptyGlyph,
  injectEsriBasemapKey,
  registerOpenFreeMapFontStub,
  waitForMap,
  type ConsoleGate,
} from "./_mapCardsHelpers";
import {
  DATA_ZONE_AT_TIMEOUT_MS,
  LOOKUP_TIMEOUT_MS,
  POSTCODES_ONLY,
} from "../../lib/api";
import {
  LOOKUP_ERROR_COPY,
  PLACE_CARD_ERROR_LINE,
  PLACE_CARD_NO_MATCH,
  PLACE_CARD_TRY_AGAIN_LABEL,
} from "../../lib/placeCard";

registerOpenFreeMapFontStub();

const LOOKUP_LINE = "We couldn't load this area just now.";
const ERROR_LINE = "Something went wrong. Please try again.";
const TRY_LABEL = "Try again";
const TIMEOUT_WORD = /time(d)?[\s-]?out/i;

const A = {
  q: "EH1 1YZ",
  lat: 55.953251,
  lng: -3.188267,
  name: "Old Town Yard",
  pc: "EH1 1YZ",
};

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

type Counts = {
  place: number;
  postcode: number;
  geocode: number;
  platform: number;
  dz: number;
};

type Shell = {
  unexpected: string[];
  counts: Counts;
  platformMode: "ok" | "hold" | "503" | "524";
  placeMode: "ok" | "503" | "nomatch";
  geocodeMode: "ok" | "503";
  dzMode: "ok" | "hold";
  catalogStatus: number;
  cardHold: Hold;
  dzHold: Hold;
};

function freshCounts(): Counts {
  return { place: 0, postcode: 0, geocode: 0, platform: 0, dz: 0 };
}

function lookupHits(counts: Counts): number {
  return counts.place + counts.postcode + counts.geocode + counts.platform + counts.dz;
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

function dzOk() {
  return { code: "S01006506", name: "Old Town", vintage: 2022 };
}

function postcodeBody() {
  return {
    kind: "postcode",
    postcode: A.pc,
    lat: A.lat,
    lng: A.lng,
    label: A.pc,
  };
}

function pointBody() {
  return {
    postcode: { postcode: A.pc },
    lat: A.lat,
    lng: A.lng,
    square: { lat: A.lat, lng: A.lng },
  };
}

async function fulfillJson(route: Route, status: number, body: unknown) {
  try {
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    if (
      message.includes("already handled") ||
      message.includes("Request context disposed") ||
      message.includes("Target page, context or browser has been closed")
    ) {
      return;
    }
    throw err;
  }
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
  const style = JSON.parse(readFileSync(fixturePath, "utf8")) as { sprite: string };
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

function makeShell(): Shell {
  return {
    unexpected: [],
    counts: freshCounts(),
    platformMode: "ok",
    placeMode: "ok",
    geocodeMode: "ok",
    dzMode: "ok",
    catalogStatus: 200,
    cardHold: new Hold(),
    dzHold: new Hold(),
  };
}

async function routeShell(page: Page, shell: Shell) {
  await page.route("**/backend/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path.endsWith("/health")) {
      await fulfillJson(route, 200, { status: "ok", version: "e2e" });
      return;
    }
    if (path.endsWith("/layers/catalog")) {
      if (shell.catalogStatus !== 200) {
        await route.fulfill({ status: shell.catalogStatus, body: "absent" });
        return;
      }
      await fulfillJson(route, 200, { version: 2, layers: [] });
      return;
    }
    if (path === "/backend/place") {
      shell.counts.place += 1;
      if (shell.placeMode === "503") {
        await fulfillJson(route, 503, { detail: "busy" });
        return;
      }
      if (shell.placeMode === "nomatch") {
        await fulfillJson(route, 200, { kind: "none" });
        return;
      }
      await fulfillJson(route, 200, postcodeBody());
      return;
    }
    if (path.startsWith("/backend/postcode/")) {
      shell.counts.postcode += 1;
      await fulfillJson(route, 200, pointBody());
      return;
    }
    if (path === "/backend/geocode/postcode") {
      shell.counts.geocode += 1;
      if (shell.geocodeMode === "503") {
        await fulfillJson(route, 503, { detail: "busy" });
        return;
      }
      await fulfillJson(route, 200, { postcode: A.pc, lat: A.lat, lng: A.lng });
      return;
    }
    if (path === "/backend/layers/context/data-zones/at") {
      shell.counts.dz += 1;
      if (shell.dzMode === "hold") {
        await shell.dzHold.promise;
      }
      await fulfillJson(route, 200, dzOk());
      return;
    }
    if (path === "/backend/platform/place") {
      shell.counts.platform += 1;
      if (shell.platformMode === "hold") {
        await shell.cardHold.promise;
      }
      if (shell.platformMode === "503") {
        await fulfillJson(route, 503, { detail: "busy" });
        return;
      }
      if (shell.platformMode === "524") {
        await fulfillJson(route, 524, { detail: "origin" });
        return;
      }
      await fulfillJson(route, 200, cardBody(A.lat, A.lng, A.name));
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
        body: path.includes("/v1/tiles/") ? "{}" : EMPTY_FC,
      });
      return;
    }
    shell.unexpected.push(path);
    await fulfillJson(route, 200, {});
  });
}

async function openMapReady(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await page.locator("#place-query").waitFor();
  await waitForMap(page);
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => {
          requestAnimationFrame(() => resolve());
        });
      }),
  );
  await page.clock.install();
}

async function submit(page: Page, q: string) {
  const input = page.locator("#place-query");
  await input.fill(q);
  await input.press("Enter");
}

async function realWait(ms: number) {
  await new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function advanceUntil(
  page: Page,
  locator: Locator,
  opts: { stepMs: number; maxSteps: number },
) {
  for (let step = 1; step <= opts.maxSteps; step += 1) {
    await page.clock.runFor(opts.stepMs);
    try {
      await expect(locator).toBeVisible({ timeout: 100 });
      return;
    } catch (err) {
      if (step === opts.maxSteps) {
        throw new Error(`advanceUntil: not visible after ${opts.maxSteps} steps`, {
          cause: err,
        });
      }
    }
  }
}

async function settle(page: Page) {
  await page.clock.runFor(LOOKUP_TIMEOUT_MS + 1_000);
  await realWait(300);
}

function intersects(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
): boolean {
  return a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;
}

async function assertNoTimeoutWord(page: Page) {
  const text = await page.evaluate(() => {
    const chunks: string[] = [];
    const take = (el: Element | null) => {
      if (!el) return;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return;
      if (el instanceof HTMLInputElement) chunks.push(el.value);
      chunks.push((el as HTMLElement).innerText || "");
    };
    take(document.querySelector("#place-query"));
    take(document.querySelector("#place-suggestions"));
    take(document.querySelector("[data-testid='search-retry-state']"));
    take(document.querySelector("[data-testid='place-card-error']"));
    take(document.querySelector("[data-testid='search-no-match']"));
    return chunks.join("\n");
  });
  expect(text).not.toMatch(TIMEOUT_WORD);
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
  await expect(
    page.getByText(ERROR_LINE, { exact: true }).filter({ visible: true }),
  ).toHaveCount(0);
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
  await assertNoTimeoutWord(page);
}

async function installRetryObserver(page: Page) {
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
}

async function retryInserts(page: Page): Promise<number> {
  return page.evaluate(() => {
    const holder = window as Window & { __lookupRetryInserts?: number };
    return holder.__lookupRetryInserts ?? 0;
  });
}

async function alertAncestors(locator: Locator): Promise<number> {
  return locator.evaluate((el) => {
    let count = 0;
    let node: HTMLElement | null = el.parentElement;
    while (node) {
      if (node.getAttribute("role") === "alert") count += 1;
      node = node.parentElement;
    }
    return count;
  });
}

async function prepare(page: Page, shell: Shell) {
  await stubMapBasemap(page);
  await routeShell(page, shell);
}

async function clickMap(page: Page) {
  const canvas = page.locator(".maplibregl-canvas");
  const box = await canvas.boundingBox();
  if (!box) throw new Error("map canvas missing");
  await canvas.click({
    position: {
      x: Math.max(8, Math.floor(box.width / 2)),
      y: Math.max(8, Math.floor(box.height * 0.62)),
    },
  });
}

function platformRequest(page: Page) {
  return page.waitForRequest(
    (req) => new URL(req.url()).pathname === "/backend/platform/place",
    { timeout: 10_000 },
  );
}

function placeRequest(page: Page) {
  return page.waitForRequest(
    (req) => new URL(req.url()).pathname === "/backend/place",
    { timeout: 10_000 },
  );
}

async function finish(gate: ConsoleGate, shell: Shell) {
  expect(shell.unexpected).toEqual([]);
  assertConsoleClean(gate);
}

test("N0 helper self-check", async ({ page }) => {
  const gate = attachConsoleGate(page);
  const box = { x: 0, y: 0, width: 10, height: 10 };
  expect(intersects(box, box)).toBe(true);
  await page.clock.install();
  await expect(
    advanceUntil(page, page.locator("#lookup-deadlines-n0-absent"), {
      stepMs: 250,
      maxSteps: 2,
    }),
  ).rejects.toThrow(/2/);
  assertConsoleClean(gate);
});

for (const viewport of WIDTHS) {
  test.describe(`lookup deadlines ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("N1 stalled place card shows the lookup line at the time limit", async ({ page }) => {
      test.setTimeout(120_000);
      assertLockedCopy();
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.platformMode = "hold";
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seen = platformRequest(page);
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
        expect(shell.counts.platform).toBe(1);
        await finish(gate, shell);
      } finally {
        shell.cardHold.release();
        await realWait(40);
      }
    });

    test("N2a prime a 524 is one http error", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/platform/place", status: 524, count: 1 });
      const shell = makeShell();
      shell.platformMode = "524";
      await prepare(page, shell);
      await openMapReady(page);
      const seen = platformRequest(page);
      await submit(page, A.q);
      await seen;
      await advanceUntil(page, page.getByTestId("place-card-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      await settle(page);
      expect(shell.counts.platform).toBe(1);
      await assertLookupError(page, "place-card");
      await expect(page.getByTestId("place-card-retry-state")).toHaveAttribute(
        "data-error-kind",
        "http",
      );
      await finish(gate, shell);
    });

    test("N2b repeated 503 keeps three tries and an http kind", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/platform/place", status: 503, count: 3 });
      const shell = makeShell();
      shell.platformMode = "503";
      await prepare(page, shell);
      await openMapReady(page);
      const seen = platformRequest(page);
      await submit(page, A.q);
      await seen;
      await advanceUntil(page, page.getByTestId("place-card-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      await settle(page);
      expect(shell.counts.platform).toBe(3);
      await assertLookupError(page, "place-card");
      await expect(page.getByTestId("place-card-retry-state")).toHaveAttribute(
        "data-error-kind",
        "http",
      );
      await finish(gate, shell);
    });

    test("N3 a five second success never shows an error", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.platformMode = "hold";
      await installRetryObserver(page);
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seen = platformRequest(page);
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(5000);
        shell.cardHold.release();
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        expect(await retryInserts(page)).toBe(0);
        await expect(page.getByTestId("place-card-loading")).toHaveCount(0);
        await finish(gate, shell);
      } finally {
        shell.cardHold.release();
        await realWait(40);
      }
    });

    test("N4 prime a stalled data zone still opens the card", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.dzMode = "hold";
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seenDz = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/layers/context/data-zones/at",
          { timeout: 10_000 },
        );
        await submit(page, A.q);
        await seenDz;
        await page.clock.runFor(DATA_ZONE_AT_TIMEOUT_MS - 500);
        expect(shell.counts.platform).toBe(0);
        const seenCard = platformRequest(page);
        await page.clock.runFor(1000);
        await seenCard;
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        await expect(page.locator("[data-testid$='-retry-state']")).toHaveCount(0);
        expect(shell.counts.platform).toBe(1);
        await finish(gate, shell);
      } finally {
        shell.dzHold.release();
        await realWait(40);
      }
    });

    test("N6 Try again sends one request and recovers", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.platformMode = "hold";
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seen = platformRequest(page);
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS - 1000);
        await page.clock.runFor(2000);
        await assertLookupError(page, "place-card");
        shell.platformMode = "ok";
        const again = platformRequest(page);
        await page.getByTestId("place-card-try-again").evaluate((el) => {
          const button = el as HTMLButtonElement;
          button.click();
          button.click();
        });
        await again;
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        await expect(page.locator("[data-testid$='-retry-state']")).toHaveCount(0);
        expect(shell.counts.platform).toBe(2);
        await expect(page.getByTestId("place-card-error")).toHaveCount(0);
        await finish(gate, shell);
      } finally {
        shell.cardHold.release();
        await realWait(40);
      }
    });

    test("N8 a blank or short query sends no lookup", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      await prepare(page, shell);
      await openMapReady(page);
      await submit(page, "");
      await expect(page.getByText(POSTCODES_ONLY, { exact: true })).toBeVisible();
      await submit(page, "   ");
      await expect(page.getByText(POSTCODES_ONLY, { exact: true })).toBeVisible();
      const input = page.locator("#place-query");
      await input.fill("E");
      await input.fill("EH");
      await page.clock.runFor(1000);
      expect(lookupHits(shell.counts)).toBe(0);
      await finish(gate, shell);
    });

    test("N13 a map click focuses Try again and Enter retries once", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.platformMode = "hold";
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seenDz = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/layers/context/data-zones/at",
          { timeout: 10_000 },
        );
        const seenCard = platformRequest(page);
        await clickMap(page);
        await page.clock.runFor(200);
        await seenDz;
        await seenCard;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS - 1000);
        await page.clock.runFor(2000);
        await expect
          .poll(() =>
            page.evaluate(() => document.activeElement?.getAttribute("data-testid") ?? ""),
          )
          .toBe("place-card-try-again");
        shell.platformMode = "ok";
        const again = platformRequest(page);
        await page.keyboard.press("Enter");
        await again;
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        expect(shell.counts.platform).toBe(2);
        await finish(gate, shell);
      } finally {
        shell.cardHold.release();
        await realWait(40);
      }
    });

    test("N14 the card line is a polite status", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.platformMode = "hold";
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seen = platformRequest(page);
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS + 1000);
        const line = page.getByText(LOOKUP_ERROR_COPY, { exact: true });
        await expect(line).toHaveCount(1);
        await expect(line).toHaveAttribute("role", "status");
        await expect(line).toHaveAttribute("aria-live", "polite");
        await expect(line).toHaveClass(/retry-state-line/);
        expect(await alertAncestors(line)).toBe(0);
        await finish(gate, shell);
      } finally {
        shell.cardHold.release();
        await realWait(40);
      }
    });

    test("N14 the search line is a polite status", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/place", status: 503, count: 3 });
      const shell = makeShell();
      shell.placeMode = "503";
      await prepare(page, shell);
      await openMapReady(page);
      const seen = placeRequest(page);
      await submit(page, "Leith Walk");
      await seen;
      await advanceUntil(page, page.getByTestId("search-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      const line = page.getByText(LOOKUP_ERROR_COPY, { exact: true });
      await expect(line).toHaveCount(1);
      await expect(line).toHaveAttribute("role", "status");
      await expect(line).toHaveAttribute("aria-live", "polite");
      await expect(line).toHaveClass(/retry-state-line/);
      expect(await alertAncestors(line)).toBe(0);
      await expect(page.locator("#place-suggestions .search-suggest-note")).toHaveCount(0);
      await finish(gate, shell);
    });

    test("N15 editing the query clears the search error", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/place", status: 503, count: 6 });
      const shell = makeShell();
      shell.placeMode = "503";
      await prepare(page, shell);
      await openMapReady(page);
      const input = page.locator("#place-query");
      const first = placeRequest(page);
      await submit(page, "Leith Walk");
      await first;
      await advanceUntil(page, page.getByTestId("search-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      const beforeType = lookupHits(shell.counts);
      await input.click();
      await page.keyboard.press("Control+A");
      await page.keyboard.type("E");
      await expect(page.getByTestId("search-retry-state")).toHaveCount(0);
      await page.clock.runFor(1000);
      expect(lookupHits(shell.counts) - beforeType).toBe(0);
      const second = placeRequest(page);
      await submit(page, "Leith Walk");
      await second;
      await advanceUntil(page, page.getByTestId("search-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      const beforeClear = lookupHits(shell.counts);
      await input.click();
      await page.keyboard.press("Control+A");
      await page.keyboard.press("Backspace");
      await expect(page.getByTestId("search-retry-state")).toHaveCount(0);
      await page.clock.runFor(1000);
      expect(lookupHits(shell.counts) - beforeClear).toBe(0);
      await finish(gate, shell);
    });

    test("N17 a search failure does not keep the old suggestion note", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/place", status: 503, count: 3 });
      const shell = makeShell();
      shell.placeMode = "503";
      await prepare(page, shell);
      await openMapReady(page);
      const seen = placeRequest(page);
      await submit(page, "Leith Walk");
      await seen;
      await advanceUntil(page, page.getByTestId("search-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      await expect(page.locator(".retry-state-line:visible")).toBeVisible();
      await expect(page.locator("#place-suggestions li.search-suggest-note")).toHaveCount(0);
      await expect(page.getByTestId("search-retry-state").locator("button")).toHaveText(TRY_LABEL);
      await finish(gate, shell);
    });

    test("N18 a loaded card stays loaded after the per-attempt limit", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.platformMode = "hold";
      await installRetryObserver(page);
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seen = platformRequest(page);
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(5000);
        shell.cardHold.release();
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        await page.clock.runFor(LOOKUP_TIMEOUT_MS * 2);
        await expect(page.locator("[data-testid$='-retry-state']")).toHaveCount(0);
        expect(await retryInserts(page)).toBe(0);
        expect(shell.counts.platform).toBe(1);
        await expect(page.getByTestId("place-card-place")).toHaveText(A.name);
        await finish(gate, shell);
      } finally {
        shell.cardHold.release();
        await realWait(40);
      }
    });

    test("N19 a postcode-only 5xx shows the search line", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/layers/catalog", status: 404, count: 2 });
      gate.expectError({ urlPath: "/backend/geocode/postcode", status: 503, count: 3 });
      const shell = makeShell();
      shell.catalogStatus = 404;
      shell.geocodeMode = "503";
      await prepare(page, shell);
      await openMapReady(page);
      const seen = page.waitForRequest(
        (req) => new URL(req.url()).pathname === "/backend/geocode/postcode",
        { timeout: 10_000 },
      );
      await submit(page, A.q);
      await seen;
      await advanceUntil(page, page.getByTestId("search-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      await settle(page);
      expect(shell.counts.geocode).toBe(3);
      expect(shell.counts.place).toBe(0);
      await assertLookupError(page, "search");
      const body = await page.locator("body").innerText();
      expect(body).not.toContain("Click the map instead");
      await finish(gate, shell);
    });

    test("N20a a search error leaves focus in the search box", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      gate.expectError({ urlPath: "/backend/place", status: 503, count: 3 });
      const shell = makeShell();
      shell.placeMode = "503";
      await prepare(page, shell);
      await openMapReady(page);
      const seen = placeRequest(page);
      await submit(page, "Leith Walk");
      await seen;
      await advanceUntil(page, page.getByTestId("search-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      await expect(page.locator("#place-query")).toBeFocused();
      let reached = false;
      for (let i = 0; i < 3; i += 1) {
        await page.keyboard.press("Tab");
        reached = await page.evaluate(() =>
          Boolean(document.activeElement?.classList.contains("retry-state-button")),
        );
        if (reached) break;
      }
      expect(reached).toBe(true);
      await finish(gate, shell);
    });

    test("N20b a typed search card error leaves focus in the search box", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.platformMode = "hold";
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seen = platformRequest(page);
        await submit(page, A.q);
        await seen;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS + 1000);
        await expect(page.getByTestId("place-card-retry-state")).toBeVisible();
        await expect(page.locator("#place-query")).toBeFocused();
        const buttonFocused = await page.evaluate(() =>
          Boolean(document.activeElement?.classList.contains("retry-state-button")),
        );
        expect(buttonFocused).toBe(false);
        await finish(gate, shell);
      } finally {
        shell.cardHold.release();
        await realWait(40);
      }
    });

    test("N20c a map click card error focuses Try again", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.platformMode = "hold";
      await prepare(page, shell);
      try {
        await openMapReady(page);
        const seenDz = page.waitForRequest(
          (req) => new URL(req.url()).pathname === "/backend/layers/context/data-zones/at",
          { timeout: 10_000 },
        );
        const seenCard = platformRequest(page);
        await clickMap(page);
        await page.clock.runFor(200);
        await seenDz;
        await seenCard;
        await page.clock.runFor(LOOKUP_TIMEOUT_MS + 1000);
        await expect(page.getByTestId("place-card-retry-state")).toBeVisible();
        await expect
          .poll(() =>
            page.evaluate(() =>
              Boolean(document.activeElement?.classList.contains("retry-state-button")),
            ),
          )
          .toBe(true);
        await finish(gate, shell);
      } finally {
        shell.cardHold.release();
        await realWait(40);
      }
    });

    test("N21 no-match is a polite status", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      const shell = makeShell();
      shell.placeMode = "nomatch";
      await prepare(page, shell);
      await openMapReady(page);
      const seen = placeRequest(page);
      await submit(page, "ZZZQQQ999");
      await seen;
      const line = page.getByTestId("search-no-match");
      await expect(line).toHaveText(PLACE_CARD_NO_MATCH);
      await expect(line).toHaveAttribute("role", "status");
      await expect(line).toHaveAttribute("aria-live", "polite");
      expect(await alertAncestors(line)).toBe(0);
      await finish(gate, shell);
    });
  });
}

test.describe("N16 390px error does not cover map controls", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("search and card errors stay off Layers, 3D and Aerial", async ({ page }) => {
    test.setTimeout(180_000);
    const gate = attachConsoleGate(page);
    gate.expectError({ urlPath: "/backend/place", status: 503, count: 3 });
    const shell = makeShell();
    shell.placeMode = "503";
    shell.platformMode = "hold";
    await injectEsriBasemapKey(page, DUMMY_ESRI_KEY);
    await stubMapBasemap(page);
    await stubEsriStyle(page);
    await routeShell(page, shell);
    try {
      await openMapReady(page);
      const controls = [
        page.getByTestId("hud-layers-btn"),
        page.getByTestId("view-3d-toggle"),
        page.getByTestId("basemap-switcher"),
      ];
      const seenSearch = placeRequest(page);
      await submit(page, "Leith Walk");
      await seenSearch;
      await advanceUntil(page, page.getByTestId("search-retry-state"), {
        stepMs: 250,
        maxSteps: 200,
      });
      await assertNoOverlap(page.getByTestId("search-retry-state"), controls);
      shell.placeMode = "ok";
      const seenCard = platformRequest(page);
      await submit(page, A.q);
      await seenCard;
      await page.clock.runFor(LOOKUP_TIMEOUT_MS + 1000);
      const cardRegion = page.getByTestId("place-card-retry-state");
      await expect(cardRegion).toBeVisible();
      await assertNoOverlap(cardRegion, controls);
      await finish(gate, shell);
    } finally {
      shell.cardHold.release();
      await realWait(40);
    }
  });
});

async function assertNoOverlap(region: Locator, controls: Locator[]) {
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
