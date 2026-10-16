import { expect, test, type Page } from "@playwright/test";
import { isScotlandViewCenter } from "../../lib/mapUrlState";
import {
  assertConsoleClean,
  attachConsoleGate,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";

/**
 * HOTFIX-VIEW-1 — fresh visitors frame Scotland.
 * Empty storage, 1280x800 and 390x844. Must be able to fail:
 * null-island c=, c= written before the first view, zoom > 8, or a
 * 2 d.p. centre that reopens more than 5 m away.
 */

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const;

const FRESH_PATHS = ["/", "/map", "/?layers=grid3"] as const;

const NULL_ISLAND = /^0(?:\.0+)?,0(?:\.0+)?$/;
const FIVE_DP = /^-?\d+\.\d{5},-?\d+\.\d{5}$/;

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

/**
 * z=19 loads live glyph ranges. A failed font response is logged as a
 * one-character console error (the missing glyph), which the console gate
 * keeps. Serve a glyph-free style instead, same as the other map specs.
 */
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

function centerFromSearch(search: string): string | null {
  const q = search.includes("?") ? search.slice(search.indexOf("?") + 1) : search.replace(/^\?/, "");
  return new URLSearchParams(q).get("c");
}

type UrlWrite = { search: string; framed: boolean };

function metresBetween(
  a: { lng: number; lat: number },
  b: { lng: number; lat: number },
): number {
  const toRad = (deg: number) => (deg * Math.PI) / 180;
  const earth = 6_371_000;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const s =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.sin(dLng / 2) ** 2;
  return 2 * earth * Math.asin(Math.sqrt(s));
}

async function installEmptyStorage(page: Page) {
  await page.addInitScript(() => {
    localStorage.clear();
    sessionStorage.clear();
    const bucket = window as unknown as { __mapUrlWrites?: UrlWrite[] };
    bucket.__mapUrlWrites = [];
    const note = () => {
      const framed = document.getElementById("map")?.dataset.framed === "1";
      bucket.__mapUrlWrites?.push({
        search: window.location.search,
        framed: framed === true,
      });
    };
    const replace = history.replaceState.bind(history);
    const push = history.pushState.bind(history);
    history.replaceState = (data, unused, url) => {
      replace(data, unused, url);
      note();
    };
    history.pushState = (data, unused, url) => {
      push(data, unused, url);
      note();
    };
  });
}

async function readCamera(page: Page) {
  const raw = await page.locator("#map").evaluate((el) => {
    const node = el as HTMLElement;
    return {
      framed: node.dataset.framed === "1",
      lng: Number(node.dataset.lng),
      lat: Number(node.dataset.lat),
      zoom: Number(node.dataset.zoom),
    };
  });
  expect(raw.framed).toBe(true);
  expect(Number.isFinite(raw.lng)).toBe(true);
  expect(Number.isFinite(raw.lat)).toBe(true);
  expect(Number.isFinite(raw.zoom)).toBe(true);
  return raw;
}

async function urlWrites(page: Page): Promise<UrlWrite[]> {
  return page.evaluate(() => {
    const bucket = window as unknown as { __mapUrlWrites?: UrlWrite[] };
    return bucket.__mapUrlWrites ?? [];
  });
}

function scotlandCenterWrite(write: { search: string; framed: boolean }): boolean {
  if (!write.framed) return false;
  const c = centerFromSearch(write.search);
  if (!c || !FIVE_DP.test(c)) return false;
  const [lng, lat] = c.split(",").map(Number);
  return isScotlandViewCenter(lng, lat);
}

function assertNoNullIsland(searches: string[]) {
  for (const search of searches) {
    const c = centerFromSearch(search);
    expect(c ?? "", search).not.toMatch(NULL_ISLAND);
  }
}

for (const viewport of VIEWPORTS) {
  test.describe(`HOTFIX-VIEW-1 ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("empty storage frames Scotland and never writes null island", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await stubOpenFreeMap(page);
      await stubMapCardsBackend(page);
      await installEmptyStorage(page);

      for (const path of FRESH_PATHS) {
        await page.goto(path);
        await page.locator("#map[data-framed='1']").waitFor({ timeout: 45_000 });
        await page.waitForFunction(() => {
          const el = document.getElementById("map");
          if (!el || el.dataset.framed !== "1") return false;
          const zoom = Number(el.dataset.zoom);
          const lng = Number(el.dataset.lng);
          const lat = Number(el.dataset.lat);
          if (
            !(
              zoom <= 8 &&
              lng <= -0.5 &&
              lng >= -9.5 &&
              lat >= 54.5 &&
              lat <= 61
            )
          ) {
            return false;
          }
          const writes =
            (
              window as unknown as {
                __mapUrlWrites?: { search: string; framed: boolean }[];
              }
            ).__mapUrlWrites ?? [];
          return writes.some((write) => {
            if (!write.framed) return false;
            const c = new URLSearchParams(write.search.replace(/^\?/, "")).get(
              "c",
            );
            if (!c || !/^-?\d+\.\d{5},-?\d+\.\d{5}$/.test(c)) return false;
            const [wLng, wLat] = c.split(",").map(Number);
            return wLng <= -0.5 && wLng >= -9.5 && wLat >= 54.5 && wLat <= 61;
          });
        });

        const stored = await page.evaluate(() => ({
          local: localStorage.length,
          session: sessionStorage.length,
        }));
        expect(stored.local).toBe(0);
        expect(stored.session).toBe(0);

        const camera = await readCamera(page);
        expect(camera.zoom).toBeLessThanOrEqual(8);
        expect(isScotlandViewCenter(camera.lng, camera.lat)).toBe(true);

        const writes = await urlWrites(page);
        const searches = [page.url(), ...writes.map((write) => write.search)];
        assertNoNullIsland(searches);
        for (const write of writes) {
          const c = centerFromSearch(write.search);
          if (!c) continue;
          expect(
            write.framed,
            `c= written before the first view: ${write.search}`,
          ).toBe(true);
          expect(c, write.search).toMatch(FIVE_DP);
          const [lng, lat] = c.split(",").map(Number);
          expect(isScotlandViewCenter(lng, lat)).toBe(true);
        }
      }

      assertConsoleClean(gate);
    });

    test("c outside Scotland is ignored, including a high z", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubOpenFreeMap(page);
      await stubMapCardsBackend(page);
      await installEmptyStorage(page);

      for (const path of [
        "/?c=0.00,0.00&z=12",
        "/?c=0,0&z=19",
        "/?lat=0&lng=0",
      ]) {
        await page.goto(path);
        await page.locator("#map[data-framed='1']").waitFor({ timeout: 45_000 });
        await page.waitForFunction(() => {
          const el = document.getElementById("map");
          if (!el || el.dataset.framed !== "1" || Number(el.dataset.zoom) > 8) {
            return false;
          }
          const writes =
            (
              window as unknown as {
                __mapUrlWrites?: { search: string; framed: boolean }[];
              }
            ).__mapUrlWrites ?? [];
          return writes.some((write) => {
            if (!write.framed) return false;
            const c = new URLSearchParams(write.search.replace(/^\?/, "")).get(
              "c",
            );
            if (!c || !/^-?\d+\.\d{5},-?\d+\.\d{5}$/.test(c)) return false;
            const [wLng, wLat] = c.split(",").map(Number);
            return wLng <= -0.5 && wLng >= -9.5 && wLat >= 54.5 && wLat <= 61;
          });
        });
        const camera = await readCamera(page);
        expect(camera.zoom).toBeLessThanOrEqual(8);
        expect(isScotlandViewCenter(camera.lng, camera.lat)).toBe(true);
        expect(camera.zoom).toBeGreaterThan(2);
        const writes = await urlWrites(page);
        const opened = centerFromSearch(path);
        for (const write of writes) {
          const c = centerFromSearch(write.search);
          if (!c || !NULL_ISLAND.test(c)) continue;
          // The address the visitor opened may be echoed once before the
          // map replaces it. It must not be the applied view.
          expect(write.framed, write.search).toBe(false);
          expect(c, write.search).toBe(opened);
        }
        expect(centerFromSearch(page.url()) ?? "", page.url()).not.toMatch(
          NULL_ISLAND,
        );
        expect(writes.some((write) => scotlandCenterWrite(write))).toBe(true);
      }

      assertConsoleClean(gate);
    });

    test("shared link and z19 centre reopen within 5 m at 5 d.p.", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubOpenFreeMap(page);
      await stubMapCardsBackend(page);
      await installEmptyStorage(page);

      const shared = { lng: -3.19, lat: 55.95 };
      await page.goto("/?c=-3.19000,55.95000&z=12");
      await page.locator("#map[data-framed='1']").waitFor({ timeout: 45_000 });
      await page.waitForFunction(() => {
        const el = document.getElementById("map");
        return Boolean(el && Math.abs(Number(el.dataset.zoom) - 12) < 0.05);
      });
      const sharedCam = await readCamera(page);
      expect(Math.abs(sharedCam.zoom - 12)).toBeLessThan(0.05);
      expect(metresBetween(shared, sharedCam)).toBeLessThan(5);
      expect(isScotlandViewCenter(sharedCam.lng, sharedCam.lat)).toBe(true);

      // Not exact at 2 d.p. — a 2 d.p. write reopens hundreds of metres away.
      const precise = { lng: -3.18827, lat: 55.95331 };
      await page.goto("/?c=-3.18827,55.95331&z=19");
      await page.locator("#map[data-framed='1']").waitFor({ timeout: 45_000 });
      await page.waitForFunction(() => {
        const el = document.getElementById("map");
        return Boolean(el && Number(el.dataset.zoom) >= 15);
      });
      const first = await readCamera(page);
      expect(first.zoom).toBeGreaterThanOrEqual(15);
      expect(metresBetween(precise, first)).toBeLessThan(5);

      const c = new URL(page.url()).searchParams.get("c");
      expect(c).toMatch(FIVE_DP);
      await page.goto(`/?c=${c}&z=19`);
      await page.locator("#map[data-framed='1']").waitFor({ timeout: 45_000 });
      await page.waitForFunction(() => {
        const el = document.getElementById("map");
        return Boolean(el && Number(el.dataset.zoom) >= 15);
      });
      const reopened = await readCamera(page);
      expect(metresBetween(precise, reopened)).toBeLessThan(5);
      expect(new URL(page.url()).searchParams.get("c")).toMatch(FIVE_DP);
      assertNoNullIsland([page.url()]);

      assertConsoleClean(gate);
    });
  });
}
