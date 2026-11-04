/**
 * UX picks – 4 Nov 2026 (Visual Designer; Project Lead gate: IN SCOPE).
 *  1. NOTICE-STACK         — map notices + "Try again" banner share one column;
 *                            Retry stays clickable; search row clear on phones.
 *  2. SEARCH-HINT-SPACING  — placeholder uses normal word spacing; typed text
 *                            keeps the wide postcode gap (T-P3 unchanged).
 *  3. OPENING-3D-FRAMING   — Scotland fits the padded view with the tilt on;
 *                            DEFAULT-3D-VIEW pitch/bearing unchanged.
 * Synthetic stubs only; no money values, no backend, no real data.
 */
import { expect, test } from "./_fixtures";
import {
  injectEsriBasemapKey,
  openMap,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import { DEFAULT_3D_PITCH_DESKTOP, DEFAULT_3D_PITCH_MOBILE } from "../../lib/default3dView";
import {
  SCOTLAND_FIT_BOUNDS,
  fitBoundsPitched,
  validateFitBox,
  validateFitPadding,
  type PitchedFitMap,
} from "../../lib/pitchedFit";
import { BASEMAP_LOAD_NOTICE } from "../../lib/mapBasemap";
import { TRY_AGAIN } from "../../lib/api";

const PAD = { top: 10, bottom: 10, left: 10, right: 10 };

/** Spy map: records camera calls so a refusal can prove nothing moved. */
function spyMap(): PitchedFitMap & { calls: string[] } {
  const calls: string[] = [];
  return {
    calls,
    fitBounds: () => calls.push("fitBounds"),
    jumpTo: () => calls.push("jumpTo"),
    project: () => ({ x: 0, y: 0 }),
    unproject: () => ({ lng: 0, lat: 0 }),
    getZoom: () => 5,
    getCenter: () => ({ lng: 0, lat: 0 }),
    getContainer: () => ({ clientWidth: 400, clientHeight: 400 }),
  };
}

test("U-4N-1 validateFitBox accepts Scotland and refuses bad boxes", () => {
  expect(validateFitBox(SCOTLAND_FIT_BOUNDS)).toEqual([
    [-8.05, 54.48],
    [-0.55, 60.88],
  ]);
  for (const bad of [
    undefined,
    null,
    [],
    [[-8, 54]],
    [[-8, 54], [-0.5]],
    [[-0.5, 54], [-8, 60]], // west >= east
    [[-8, 60], [-0.5, 54]], // south >= north
    [[-8, 54], [-8, 60]], // zero width
    [[Number.NaN, 54], [-0.5, 60]],
    [[-8, 54], [-0.5, Number.POSITIVE_INFINITY]],
    [[-181, 54], [-0.5, 60]],
    [[-8, 54], [-0.5, 86]],
    [["-8", 54], [-0.5, 60]],
  ]) {
    expect(() => validateFitBox(bad), JSON.stringify(bad)).toThrow(/^OPENING-3D-FRAMING: /);
  }
});

test("U-4N-2 validateFitPadding refuses missing, negative or non-finite sides", () => {
  expect(validateFitPadding(PAD)).toEqual(PAD);
  for (const bad of [
    null,
    5,
    { top: 1, bottom: 1, left: 1 },
    { ...PAD, top: -1 },
    { ...PAD, left: Number.NaN },
    { ...PAD, right: "4" },
  ]) {
    expect(() => validateFitPadding(bad), JSON.stringify(bad)).toThrow(
      /^OPENING-3D-FRAMING: padding/,
    );
  }
});

test("U-4N-3 fitBoundsPitched refuses before moving the camera", () => {
  const good = { padding: PAD, maxZoom: 7.4, pitch: 60, bearing: 0 };
  const cases: Array<[string, unknown, Record<string, unknown>, RegExp]> = [
    ["pitch > 60", SCOTLAND_FIT_BOUNDS, { ...good, pitch: 61 }, /^DEFAULT-3D: pitch/],
    ["pitch NaN", SCOTLAND_FIT_BOUNDS, { ...good, pitch: Number.NaN }, /^DEFAULT-3D: pitch/],
    ["bearing > 180", SCOTLAND_FIT_BOUNDS, { ...good, bearing: 181 }, /^DEFAULT-3D: bearing/],
    ["maxZoom NaN", SCOTLAND_FIT_BOUNDS, { ...good, maxZoom: Number.NaN }, /maxZoom/],
    ["maxZoom string", SCOTLAND_FIT_BOUNDS, { ...good, maxZoom: "7" }, /maxZoom/],
    ["no room", SCOTLAND_FIT_BOUNDS, { ...good, padding: { ...PAD, left: 200, right: 200 } }, /no room/],
    ["bad box", [[0, 0], [0, 0]], good, /bounds/],
    ["minZoom NaN", SCOTLAND_FIT_BOUNDS, { ...good, minZoom: Number.NaN }, /minZoom/],
    ["minZoom > maxZoom", SCOTLAND_FIT_BOUNDS, { ...good, minZoom: 8 }, /minZoom/],
    ["bad padding", SCOTLAND_FIT_BOUNDS, { ...good, padding: { ...PAD, top: -5 } }, /padding\.top/],
  ];
  for (const [name, box, opts, re] of cases) {
    const m = spyMap();
    expect(
      () => fitBoundsPitched(m, box, opts as Parameters<typeof fitBoundsPitched>[2]),
      name,
    ).toThrow(re);
    expect(m.calls, name).toEqual([]);
  }
});

const VIEWPORTS = [
  { name: "desktop", width: 1280, height: 800, pitch: DEFAULT_3D_PITCH_DESKTOP, pad: { top: 96, bottom: 36, left: 24, right: 28 } },
  { name: "mobile", width: 390, height: 844, pitch: DEFAULT_3D_PITCH_MOBILE, pad: { top: 132, bottom: 72, left: 12, right: 16 } },
] as const;

// Short, wide window: here the tilted box is limited by height, not width.
const SHORT_WIDE = { name: "short-wide", width: 1280, height: 500, pitch: DEFAULT_3D_PITCH_DESKTOP, pad: { top: 96, bottom: 36, left: 24, right: 28 } } as const;

type Box = { x: number; y: number; width: number; height: number };
const overlaps = (a: Box, b: Box) =>
  a.x < b.x + b.width && b.x < a.x + a.width && a.y < b.y + b.height && b.y < a.y + a.height;

for (const vp of [...VIEWPORTS, SHORT_WIDE]) {
  test.describe(`UX picks 4 Nov @ ${vp.name} ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test(`E-4N-1 opening 3D view fits Scotland with the tilt applied (pitch ${vp.pitch})`, async ({ page }) => {
      test.setTimeout(120_000);
      await injectEsriBasemapKey(page);
      await stubMapCardsBackend(page);
      await openMap(page, "/");
      await waitForMap(page);
      await page.locator("#map[data-framed='1']").waitFor({ timeout: 30_000 });
      const cam = await page.evaluate((box) => {
        const m = (window as unknown as {
          __map: {
            getPitch(): number;
            getBearing(): number;
            getZoom(): number;
            project(p: [number, number]): { x: number; y: number };
            getContainer(): HTMLElement;
          };
        }).__map;
        const [[w, s], [e, n]] = box;
        const c = m.getContainer();
        return {
          pitch: m.getPitch(),
          bearing: m.getBearing(),
          zoom: m.getZoom(),
          cw: c.clientWidth,
          ch: c.clientHeight,
          sw: m.project([w, s]),
          se: m.project([e, s]),
          ne: m.project([e, n]),
          nw: m.project([w, n]),
        };
      }, SCOTLAND_FIT_BOUNDS);
      // DEFAULT-3D-VIEW unchanged.
      expect(cam.pitch).toBeCloseTo(vp.pitch, 1);
      expect(cam.bearing).toBeCloseTo(0, 1);
      const pts = [cam.sw, cam.se, cam.ne, cam.nw];
      const left = Math.min(...pts.map((p) => p.x));
      const right = Math.max(...pts.map((p) => p.x));
      const top = Math.min(...pts.map((p) => p.y));
      const bottom = Math.max(...pts.map((p) => p.y));
      const TOL = 2;
      // Opening never goes below the z5 layer band.
      expect(cam.zoom).toBeGreaterThanOrEqual(5 - 0.001);
      if (vp.name === "mobile") {
        // Phone: tilted Scotland needs < z5, so the fit stops at the z5 floor,
        // centred in the padded view.
        expect(cam.zoom).toBeCloseTo(5, 3);
        const availW = cam.cw - vp.pad.left - vp.pad.right;
        const availH = cam.ch - vp.pad.top - vp.pad.bottom;
        const xs = [cam.sw, cam.se, cam.ne, cam.nw].map((p) => p.x);
        const ys = [cam.sw, cam.se, cam.ne, cam.nw].map((p) => p.y);
        expect(Math.abs((Math.min(...xs) + Math.max(...xs)) / 2 - (vp.pad.left + availW / 2))).toBeLessThanOrEqual(TOL);
        expect(Math.abs((Math.min(...ys) + Math.max(...ys)) / 2 - (vp.pad.top + availH / 2))).toBeLessThanOrEqual(TOL);
        expect(cam.nw.y).toBeLessThan(cam.sw.y);
        return;
      }
      // Whole box inside the padded view (fails with the flat fit at 55-60°).
      expect(left).toBeGreaterThanOrEqual(vp.pad.left - TOL);
      expect(right).toBeLessThanOrEqual(cam.cw - vp.pad.right + TOL);
      expect(top).toBeGreaterThanOrEqual(vp.pad.top - TOL);
      expect(bottom).toBeLessThanOrEqual(cam.ch - vp.pad.bottom + TOL);
      // ...and tight: one axis fills the padded view (not just zoomed far out).
      const availW = cam.cw - vp.pad.left - vp.pad.right;
      const availH = cam.ch - vp.pad.top - vp.pad.bottom;
      const fill = Math.max((right - left) / availW, (bottom - top) / availH);
      // (Unless the fit is capped by maxZoom 7.4, as before.)
      if (cam.zoom < 7.4 - 0.01) expect(fill).toBeGreaterThanOrEqual(0.97);
      else expect(fill).toBeLessThanOrEqual(1 + TOL / Math.min(availW, availH));
      // North is up: Shetland edge above the Solway edge.
      expect(cam.nw.y).toBeLessThan(cam.sw.y);
      // Record which axis limits the fit, so each viewport proves one.
      const limit = (right - left) / availW > (bottom - top) / availH ? "width" : "height";
      expect(limit).toBe(vp.name === "short-wide" ? "height" : "width"); // desktop: width
    });
  });
}

for (const vp of VIEWPORTS) {
  test.describe(`UX picks 4 Nov @ ${vp.name} ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("E-4N-2 notices stack in one column; Retry and Reload stay clickable; search row clear", async ({
      page,
      gate,
    }) => {
      test.setTimeout(120_000);
      gate.expectError({
        text: "Error: AJAXError: Internal Server Error (500): https://tiles.openfreemap.org/styles/positron https://tiles.openfreemap.org/styles/positron",
        count: 1,
      });
      await stubMapCardsBackend(page);
      let healthCalls = 0;
      // Registered after the stubs, so it wins: API reports not ok (no HTTP error).
      await page.route("**/health**", async (route) => {
        healthCalls += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ status: "down" }),
        });
      });
      await page.route("**/tiles.openfreemap.org/styles/positron**", async (route) => {
        await route.fulfill({
          status: 500,
          contentType: "application/json",
          body: JSON.stringify({ error: "style failed" }),
        });
      });
      await page.goto("/");
      await page.locator("#place-query").waitFor({ timeout: 60_000 });

      const column = page.getByTestId("map-notices");
      const banner = column.locator(".hud-banner");
      const notice = column.getByTestId("basemap-notice");
      await expect(banner).toBeVisible({ timeout: 30_000 });
      await expect(banner).toContainText(TRY_AGAIN);
      await expect(notice).toBeVisible({ timeout: 30_000 });
      await expect(notice).toContainText(BASEMAP_LOAD_NOTICE);
      // Exactly one column; no notice rendered outside it.
      await expect(page.getByTestId("map-notices")).toHaveCount(1);
      await expect(page.locator(".basemap-notice:not([data-testid='map-notices'] *)")).toHaveCount(0);
      await expect(page.locator(".hud-banner:not([data-testid='map-notices'] *)")).toHaveCount(0);

      const bannerBox = (await banner.boundingBox())!;
      const noticeBox = (await notice.boundingBox())!;
      const searchBox = (await page.locator(".hud-search").first().boundingBox())!;
      expect(overlaps(bannerBox, noticeBox), "banner vs notice").toBe(false);
      expect(overlaps(bannerBox, searchBox), "banner vs search").toBe(false);
      expect(overlaps(noticeBox, searchBox), "notice vs search").toBe(false);

      // Hit-test: the topmost element at each button centre is that button.
      const retry = banner.getByRole("button", { name: "Retry" });
      const reload = notice.getByRole("button", { name: "Reload" });
      for (const [label, btn] of [["Retry", retry], ["Reload", reload]] as const) {
        const b = (await btn.boundingBox())!;
        const hit = await page.evaluate(
          ([x, y]) => document.elementFromPoint(x, y)?.closest("button")?.textContent?.trim() ?? null,
          [b.x + b.width / 2, b.y + b.height / 2],
        );
        expect(hit, `${label} hit-test`).toBe(label);
      }
      // The column itself is click-through: beside the (narrower) banner and
      // in the gap between notices, taps reach the map, not the column.
      const colBox = (await column.boundingBox())!;
      const through = await page.evaluate(
        (pts) =>
          pts.map(([x, y]) =>
            Boolean(document.elementFromPoint(x, y)?.closest("[data-testid='map-notices']")),
          ),
        [
          [colBox.x + 2, bannerBox.y + bannerBox.height / 2],
          [colBox.x + colBox.width / 2, (bannerBox.y + bannerBox.height + noticeBox.y) / 2],
        ] as Array<[number, number]>,
      );
      expect(bannerBox.x).toBeGreaterThan(colBox.x + 2);
      expect(noticeBox.y).toBeGreaterThan(bannerBox.y + bannerBox.height + 1);
      expect(through).toEqual([false, false]);
      // In flow: the notice sits one 0.5rem gap under the banner, at the
      // column's left edge and full column width.
      expect(Math.abs(noticeBox.y - (bannerBox.y + bannerBox.height) - 8)).toBeLessThanOrEqual(1);
      expect(Math.abs(noticeBox.x - colBox.x)).toBeLessThanOrEqual(1);
      expect(Math.abs(noticeBox.width - colBox.width)).toBeLessThanOrEqual(1);
      // Search input is reachable at its centre (column is click-through).
      const inputHit = await page.evaluate(() => {
        const el = document.querySelector("#place-query")!;
        const r = el.getBoundingClientRect();
        return document.elementFromPoint(r.x + r.width / 2, r.y + r.height / 2)?.id ?? null;
      });
      expect(inputHit).toBe("place-query");

      // A real click on Retry re-checks the API.
      const before = healthCalls;
      await retry.click({ trial: false });
      await expect.poll(() => healthCalls).toBeGreaterThan(before);
    });

    test("E-4N-3 search hint uses normal word spacing; typed text keeps the postcode gap", async ({ page }) => {
      test.setTimeout(90_000);
      await stubMapCardsBackend(page);
      await openMap(page, "/");
      const s = await page.locator("#place-query").evaluate((el) => ({
        input: getComputedStyle(el).wordSpacing,
        hint: getComputedStyle(el, "::placeholder").wordSpacing,
        fontSize: getComputedStyle(el).fontSize,
      }));
      expect(s.hint).toBe("0px");
      const px = Number.parseFloat(s.input);
      expect(px).toBeGreaterThanOrEqual(3 * (Number.parseFloat(s.fontSize) / 14) - 0.01);
    });
  });
}
