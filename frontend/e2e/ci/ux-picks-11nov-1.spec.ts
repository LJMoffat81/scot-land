import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import type { Page, Route, TestInfo } from "@playwright/test";
import {
  expect,
  test,
  routeManifestOverride,
  TILES_MANIFEST_PATHNAME,
} from "./_fixtures";
import {
  injectEsriBasemapKey,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";
import {
  LAYERS_FAIL_COPY,
  LAYERS_LOADING_COPY,
  MAP_LOAD_FAIL_COPY,
  MAP_LOAD_TIMEOUT_MS,
  MAP_LOADING_COPY,
} from "../../lib/mapBasemap";
import { PLACE_CARD_TRY_AGAIN_LABEL } from "../../lib/placeCard";
import {
  DEFAULT_3D_PITCH_DESKTOP,
  DEFAULT_3D_PITCH_MOBILE,
} from "../../lib/default3dView";
import { VIEW_CLOSE_LABEL, VIEW_SHARE_LABEL } from "../../lib/mapViews";

const T0 = new Date("2026-06-01T12:00:00.000Z");
const STYLE_BODY = readFileSync(
  join(process.cwd(), "e2e", "fixtures", "ofm-style-min.json"),
  "utf8",
);
const EMPTY_MANIFEST = readFileSync(
  join(process.cwd(), "e2e", "ci", "fixtures", "tiles-manifest-empty.json"),
  "utf8",
);
const ARTIFACTS = "/opt/cursor/artifacts";

const WIDTHS = [
  { width: 1280, height: 800, pitch: DEFAULT_3D_PITCH_DESKTOP },
  { width: 390, height: 844, pitch: DEFAULT_3D_PITCH_MOBILE },
] as const;

type StyleCtl = { mode: "hang" | "ok"; hits: number; held: Route | null };
type ManifestCtl = {
  mode: "hold" | "empty" | "error" | "error-once";
  hits: number;
  held: Route[];
};

function boxesIntersect(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
): boolean {
  return (
    a.x < b.x + b.width &&
    b.x < a.x + a.width &&
    a.y < b.y + b.height &&
    b.y < a.y + a.height
  );
}

async function saveShot(
  testInfo: TestInfo,
  name: string,
  png: Buffer,
): Promise<void> {
  await testInfo.attach(name, { body: png, contentType: "image/png" });
  mkdirSync(ARTIFACTS, { recursive: true });
  writeFileSync(join(ARTIFACTS, `${name}.png`), png);
}

async function routeStyle(page: Page, ctl: StyleCtl): Promise<void> {
  await page.route("**/tiles.openfreemap.org/styles/positron**", async (route) => {
    ctl.hits += 1;
    if (ctl.mode === "hang") {
      ctl.held = route;
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: STYLE_BODY,
    });
  });
}

async function routeManifest(page: Page, ctl: ManifestCtl): Promise<void> {
  await routeManifestOverride(page, async (route) => {
    ctl.hits += 1;
    if (ctl.mode === "hold") {
      ctl.held.push(route);
      return;
    }
    if (ctl.mode === "error" || (ctl.mode === "error-once" && ctl.hits === 1)) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: "{}",
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: EMPTY_MANIFEST,
    });
  });
}

async function pauseClock(page: Page): Promise<void> {
  await page.clock.install({ time: T0 });
  await page.clock.pauseAt(new Date(T0.getTime() + 500));
}

async function armMap(page: Page): Promise<void> {
  await expect(page.getByTestId("map-loading")).toHaveText(MAP_LOADING_COPY);
  await expect(page.locator(".maplibregl-canvas")).toBeAttached({
    timeout: 20_000,
  });
}

async function focusByTab(page: Page, selector: string): Promise<void> {
  for (let step = 0; step < 40; step += 1) {
    const focused = await page.evaluate(
      (sel) => document.activeElement === document.querySelector(sel),
      selector,
    );
    if (focused) return;
    await page.keyboard.press("Tab");
  }
  await expect(page.locator(selector)).toBeFocused();
}

async function focusState(page: Page, containerTestId: string) {
  return page.evaluate((testId) => {
    const region = document.querySelector(`[data-testid="${testId}"]`);
    const active = document.activeElement;
    return {
      notBody: active !== document.body && active !== null,
      contained: Boolean(region && active && region.contains(active)),
      isRegion: active === region,
    };
  }, containerTestId);
}

async function openLayersPanel(page: Page): Promise<void> {
  const panel = page.getByTestId("layers-panel");
  if ((await panel.count()) === 0) {
    await page.getByTestId("hud-layers-btn").click();
  }
  await expect(panel).toBeVisible();
}

async function openStory(page: Page, viewId: string): Promise<void> {
  await openLayersPanel(page);
  await page.getByTestId(`map-view-${viewId}`).click();
  await expect(page.getByTestId("map-view-detail")).toBeVisible();
  await expect(page.locator(".map-view-detail tbody tr")).toHaveCount(32);
}

async function searchRing(page: Page) {
  return page.evaluate(() => {
    const input = document.querySelector("#place-query");
    const pill = document.querySelector(".hud-search");
    if (!(input instanceof HTMLElement) || !(pill instanceof HTMLElement)) {
      throw new Error("search field missing");
    }
    const ic = getComputedStyle(input);
    const pc = getComputedStyle(pill);
    return {
      inputOutline: ic.outlineStyle,
      inputShadow: ic.boxShadow,
      pillOutline: pc.outlineStyle,
      pillWidth: pc.outlineWidth,
      pillColor: pc.outlineColor,
      pillOffset: pc.outlineOffset,
      pillShadow: pc.boxShadow,
    };
  });
}

function expectFocusedRing(ring: Awaited<ReturnType<typeof searchRing>>): void {
  expect(ring.inputOutline).toBe("none");
  expect(ring.inputShadow).toBe("none");
  expect(ring.pillOutline).toBe("solid");
  expect(ring.pillWidth).toBe("3px");
  expect(ring.pillColor).toBe("rgb(255, 221, 0)");
  expect(ring.pillOffset).toBe("2px");
  expect(ring.pillShadow).toContain("rgb(11, 30, 58) 0px 0px 0px 1px");
}

for (const vp of WIDTHS) {
  test.describe(`UX-PICKS-11NOV-1 @ ${vp.width}x${vp.height}`, () => {
    test.use({ viewport: { width: vp.width, height: vp.height } });

    test("M1 map loading then fail at the timeout", async ({ page }) => {
      test.setTimeout(90_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await expect(page.getByTestId("map-loading")).toHaveAttribute("role", "status");
      await expect(page.getByTestId("map-loading")).toHaveAttribute(
        "aria-live",
        "polite",
      );
      await expect(page.getByText(MAP_LOADING_COPY, { exact: true })).toHaveCount(1);
      await expect(page.locator("#map")).toHaveAttribute("aria-busy", "true");
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS - 1);
      await expect(page.getByTestId("map-load-retry-state")).toHaveCount(0);
      await page.clock.runFor(1);
      const line = page.locator(".map-load-fail .retry-state-line");
      await expect(line).toHaveText(MAP_LOAD_FAIL_COPY);
      await expect(page.getByText(MAP_LOAD_FAIL_COPY, { exact: true })).toHaveCount(1);
      await expect(page.getByTestId("map-load-try-again")).toHaveText(
        PLACE_CARD_TRY_AGAIN_LABEL,
      );
      await expect(page.getByTestId("map-loading")).toHaveCount(0);
      await expect(page.locator("#map")).toHaveAttribute("aria-busy", "false");
      const box = await page.getByTestId("map-load-try-again").boundingBox();
      expect(box).toBeTruthy();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);
      expect(style.hits).toBe(1);
    });

    test("M2 Try again does not loop", async ({ page }) => {
      test.setTimeout(90_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      await expect(page.getByTestId("map-load-retry-state")).toBeVisible();
      await page.getByTestId("map-load-try-again").click();
      await expect(page.getByTestId("map-load-retry-state")).toHaveCount(0);
      expect(style.hits).toBe(2);
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      await expect(page.getByTestId("map-load-retry-state")).toBeVisible();
      await page.getByTestId("map-load-try-again").click();
      expect(style.hits).toBe(3);
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      await expect(page.getByTestId("map-load-retry-state")).toBeVisible();
      await page.clock.runFor(4 * MAP_LOAD_TIMEOUT_MS);
      expect(style.hits).toBe(3);
      await expect(page.getByTestId("map-load-retry-state")).toBeVisible();
    });

    test("M3 Try again remounts and keeps defaults", async ({ page }) => {
      test.setTimeout(120_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      await expect(page.getByTestId("map-load-retry-state")).toBeVisible();
      style.mode = "ok";
      await page.getByTestId("map-load-try-again").click();
      await page.clock.resume();
      await waitForMap(page);
      await expect(page.getByTestId("map-load-retry-state")).toHaveCount(0);
      await expect(page.getByTestId("map-loading")).toHaveCount(0);
      expect(style.hits).toBe(2);
      await expect(page.locator("#map")).toHaveAttribute("aria-busy", "false");
      const pitch = await page.evaluate(() => {
        const map = (window as unknown as { __map?: { getPitch(): number } }).__map;
        if (!map) throw new Error("map missing");
        return map.getPitch();
      });
      expect(pitch).toBeCloseTo(vp.pitch, 0);
      await openLayersPanel(page);
      const places = page.getByTestId("layers-group-toggle-places");
      if ((await places.getAttribute("aria-expanded")) !== "true") {
        await places.click();
      }
      await expect(page.getByTestId("layer-toggle-data_zones")).toHaveAttribute(
        "aria-checked",
        "true",
      );
      await expect(page.getByTestId("layer-toggle-councils")).toHaveAttribute(
        "aria-checked",
        "false",
      );
    });

    test("M4 late load clears the fail state without a click", async ({ page }) => {
      test.setTimeout(120_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      await expect(page.getByTestId("map-load-retry-state")).toBeVisible();
      expect(style.hits).toBe(1);
      const held = style.held;
      if (!held) throw new Error("M4 held style request missing");
      await held.fulfill({
        status: 200,
        contentType: "application/json",
        body: STYLE_BODY,
      });
      await page.clock.resume();
      await expect(page.getByTestId("map-load-retry-state")).toHaveCount(0);
      await expect(page.getByTestId("map-loading")).toHaveCount(0);
      expect(style.hits).toBe(1);
    });

    test("M5 a normal load clears the timer", async ({ page }) => {
      test.setTimeout(120_000);
      const style: StyleCtl = { mode: "ok", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await page.goto("/");
      await waitForMap(page);
      await expect(page.getByTestId("map-load-retry-state")).toHaveCount(0);
      await expect(page.getByTestId("map-loading")).toHaveCount(0);
      await page.clock.install({ time: T0 });
      await page.clock.runFor(2 * MAP_LOAD_TIMEOUT_MS);
      await expect(page.getByTestId("map-load-retry-state")).toHaveCount(0);
      await expect(page.getByTestId("map-loading")).toHaveCount(0);
    });

    test("M6 fail state is the only notice", async ({ page }) => {
      test.setTimeout(90_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      await expect(page.getByTestId("map-load-retry-state")).toBeVisible();
      await expect(page.getByTestId("basemap-notice")).toHaveCount(0);
      const text = await page.locator("body").innerText();
      const hits = text.split(MAP_LOAD_FAIL_COPY).length - 1;
      expect(hits).toBe(1);
    });

    test("M7 fail card does not cover map controls", async ({ page }, testInfo) => {
      test.setTimeout(90_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await injectEsriBasemapKey(page);
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      const card = page.getByTestId("map-load-retry-state");
      await expect(card).toBeVisible();
      const cardBox = await card.boundingBox();
      expect(cardBox).toBeTruthy();
      for (const sel of [
        '[data-testid="hud-layers-btn"]',
        '[data-testid="view-3d-toggle"]',
        '[data-testid="basemap-switcher"]',
        "#place-query",
      ]) {
        const target = page.locator(sel);
        const box = await target.boundingBox();
        expect(box, sel).toBeTruthy();
        expect(boxesIntersect(cardBox!, box!), sel).toBe(false);
        await target.click({ trial: true, timeout: 5000 });
      }
      await saveShot(
        testInfo,
        `map-fail-${vp.width}`,
        await page.screenshot(),
      );
    });

    test("M8 keyboard focus stays in the map region", async ({ page }) => {
      test.setTimeout(90_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await page.locator("#place-query").focus();
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      await expect(page.locator("#place-query")).toBeFocused();
      const line = page.locator(".map-load-fail .retry-state-line");
      await expect(line).toHaveAttribute("role", "status");
      await expect(line).toHaveAttribute("aria-live", "polite");
      const alert = await line.evaluate(
        (el) => Boolean(el.closest('[role="alert"]')),
      );
      expect(alert).toBe(false);
      await focusByTab(page, '[data-testid="map-load-try-again"]');
      await page.keyboard.press("Enter");
      await expect(page.getByTestId("map-load-retry-state")).toHaveCount(0);
      const focus = await focusState(page, "map-region");
      expect(focus.notBody).toBe(true);
      expect(focus.contained).toBe(true);
      expect(focus.isRegion).toBe(true);
    });

    test("M8 mouse focus stays in the map region", async ({ page }) => {
      test.setTimeout(90_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await page.locator("#place-query").focus();
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      await expect(page.locator("#place-query")).toBeFocused();
      await page.getByTestId("map-load-try-again").click();
      await expect(page.getByTestId("map-load-retry-state")).toHaveCount(0);
      const focus = await focusState(page, "map-region");
      expect(focus.notBody).toBe(true);
      expect(focus.contained).toBe(true);
      expect(focus.isRegion).toBe(true);
    });

    test("L0 layers open with a loading line then fail", async ({ page }, testInfo) => {
      test.setTimeout(90_000);
      const style: StyleCtl = { mode: "hang", hits: 0, held: null };
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await pauseClock(page);
      await page.goto("/");
      await armMap(page);
      await page.getByTestId("hud-layers-btn").click();
      await expect(page.getByTestId("layers-panel")).toBeVisible();
      await expect(page.getByTestId("layers-status-loading")).toHaveText(
        LAYERS_LOADING_COPY,
      );
      await expect(page.getByText(LAYERS_LOADING_COPY, { exact: true })).toHaveCount(1);
      await saveShot(
        testInfo,
        `layers-loading-${vp.width}`,
        await page.screenshot(),
      );
      await page.clock.runFor(MAP_LOAD_TIMEOUT_MS);
      const line = page.locator('[data-testid="layers-retry-state"] .retry-state-line');
      await expect(line).toHaveText(LAYERS_FAIL_COPY);
      await expect(page.getByText(LAYERS_FAIL_COPY, { exact: true })).toHaveCount(1);
      const box = await page.getByTestId("layers-try-again").boundingBox();
      expect(box).toBeTruthy();
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);
      await saveShot(
        testInfo,
        `layers-fail-${vp.width}`,
        await page.screenshot(),
      );
    });

    test("L1 a held manifest resolves to ready", async ({ page }) => {
      test.setTimeout(120_000);
      const manifest: ManifestCtl = { mode: "hold", hits: 0, held: [] };
      await stubMapCardsBackend(page);
      await routeManifest(page, manifest);
      await page.goto("/");
      await waitForMap(page);
      await openLayersPanel(page);
      await expect(page.getByTestId("layers-status-loading")).toHaveText(
        LAYERS_LOADING_COPY,
      );
      await expect(page.getByTestId("layers-retry-state")).toHaveCount(0);
      manifest.mode = "empty";
      const held = manifest.held[0];
      if (!held) throw new Error("L1 held manifest request missing");
      await held.fulfill({
        status: 200,
        contentType: "application/json",
        body: EMPTY_MANIFEST,
      });
      await expect(page.getByTestId("layers-status-loading")).toHaveCount(0);
      await expect(page.getByTestId("layers-retry-state")).toHaveCount(0);
      expect(manifest.hits).toBe(1);
    });

    test("L2 an empty manifest is not an error", async ({ page }) => {
      test.setTimeout(120_000);
      await stubMapCardsBackend(page);
      await page.goto("/");
      await waitForMap(page);
      await openLayersPanel(page);
      await expect(page.getByTestId("layers-status-loading")).toHaveCount(0);
      await expect(page.getByTestId("layers-retry-state")).toHaveCount(0);
      await expect(page.getByTestId("layer-toggle-data_zones")).toBeVisible();
    });

    test("L3 a manifest error does not retry by itself", async ({ page, gate }) => {
      test.setTimeout(120_000);
      const style: StyleCtl = { mode: "ok", hits: 0, held: null };
      const manifest: ManifestCtl = { mode: "error", hits: 0, held: [] };
      gate.expectError({
        urlPath: TILES_MANIFEST_PATHNAME,
        status: 503,
        count: 2,
      });
      await stubMapCardsBackend(page);
      await routeStyle(page, style);
      await routeManifest(page, manifest);
      await page.goto("/");
      await waitForMap(page);
      await openLayersPanel(page);
      await expect(
        page.locator('[data-testid="layers-retry-state"] .retry-state-line'),
      ).toHaveText(LAYERS_FAIL_COPY);
      expect(manifest.hits).toBe(1);
      const styleBefore = style.hits;
      await page.getByTestId("layers-try-again").click();
      await expect(
        page.locator('[data-testid="layers-retry-state"] .retry-state-line'),
      ).toHaveText(LAYERS_FAIL_COPY, { timeout: 20_000 });
      expect(manifest.hits).toBe(2);
      expect(style.hits - styleBefore).toBe(1);
      await page.clock.install({ time: T0 });
      await page.clock.runFor(4 * MAP_LOAD_TIMEOUT_MS);
      expect(manifest.hits).toBe(2);
    });

    test("L4 Try again keeps the camera", async ({ page, gate }) => {
      test.setTimeout(120_000);
      const manifest: ManifestCtl = { mode: "error-once", hits: 0, held: [] };
      gate.expectError({
        urlPath: TILES_MANIFEST_PATHNAME,
        status: 503,
        count: 1,
      });
      await stubMapCardsBackend(page);
      await routeManifest(page, manifest);
      await page.goto("/");
      await waitForMap(page);
      await openLayersPanel(page);
      await expect(page.getByTestId("layers-retry-state")).toBeVisible();
      const before = await page.evaluate(() => {
        const map = (
          window as unknown as {
            __map: {
              getCenter(): { lng: number; lat: number };
              getZoom(): number;
              getPitch(): number;
            };
          }
        ).__map;
        const center = map.getCenter();
        return {
          lng: center.lng,
          lat: center.lat,
          zoom: map.getZoom(),
          pitch: map.getPitch(),
        };
      });
      await page.getByTestId("layers-try-again").click();
      await expect(page.getByTestId("layers-retry-state")).toHaveCount(0);
      await expect(page.getByTestId("layers-status-loading")).toHaveCount(0);
      expect(manifest.hits).toBe(2);
      const after = await page.evaluate(() => {
        const map = (
          window as unknown as {
            __map: {
              getCenter(): { lng: number; lat: number };
              getZoom(): number;
              getPitch(): number;
            };
          }
        ).__map;
        const center = map.getCenter();
        return {
          lng: center.lng,
          lat: center.lat,
          zoom: map.getZoom(),
          pitch: map.getPitch(),
        };
      });
      expect(Math.abs(after.lng - before.lng)).toBeLessThanOrEqual(1e-6);
      expect(Math.abs(after.lat - before.lat)).toBeLessThanOrEqual(1e-6);
      expect(Math.abs(after.zoom - before.zoom)).toBeLessThanOrEqual(1e-6);
      expect(Math.abs(after.pitch - before.pitch)).toBeLessThanOrEqual(1e-6);
    });

    test("L5 the layers preview has no status line", async ({ page, gate }) => {
      test.setTimeout(60_000);
      // The CI build does not enable the internal preview, so the route 404s.
      // The new status nodes must still be absent.
      gate.expectError({
        text: "Failed to load resource: the server responded with a status of 404 (Not Found)",
        count: 1,
      });
      await stubMapCardsBackend(page);
      await page.goto("/layers-panel");
      await expect(page.getByTestId("layers-status-loading")).toHaveCount(0);
      await expect(page.getByTestId("layers-retry-state")).toHaveCount(0);
    });

    test("L6 keyboard focus stays in the layers panel", async ({ page, gate }) => {
      test.setTimeout(120_000);
      await assertLayersFocus(page, gate, "keyboard");
    });

    test("L6 mouse focus stays in the layers panel", async ({ page, gate }) => {
      test.setTimeout(120_000);
      await assertLayersFocus(page, gate, "mouse");
    });

    test("D1-D8 story tables stick and clear the last row", async ({ page }, testInfo) => {
      test.setTimeout(180_000);
      await stubMapCardsBackend(page);
      await page.goto("/");
      await waitForMap(page);
      for (const viewId of ["idle-land", "who-holds-scotland"] as const) {
        await openStory(page, viewId);
        const table =
          viewId === "idle-land"
            ? page.locator("table.map-view-idle-land")
            : page.locator("table.map-view-who-holds");
        const scroll = page.getByTestId("map-panel-scroll");
        const head = table.locator("thead th").first();
        const sticky = await head.evaluate((el) => {
          const cs = getComputedStyle(el);
          return { position: cs.position, top: cs.top };
        });
        expect(sticky.position, `${viewId} D1`).toBe("sticky");
        expect(sticky.top, `${viewId} D1`).toBe("0px");
        await table.locator("tbody tr:nth-child(20)").scrollIntoViewIfNeeded();
        const headBox = await head.boundingBox();
        const scrollBox = await scroll.boundingBox();
        expect(headBox, `${viewId} D1`).toBeTruthy();
        expect(scrollBox, `${viewId} D1`).toBeTruthy();
        expect(Math.abs(headBox!.y - scrollBox!.y), `${viewId} D1`).toBeLessThanOrEqual(1);

        const align = await table.evaluate((el) => {
          const cell = (sel: string) => {
            const node = el.querySelector(sel);
            if (!(node instanceof HTMLElement)) throw new Error(sel);
            const cs = getComputedStyle(node);
            return { align: cs.textAlign, nums: cs.fontVariantNumeric };
          };
          const border = getComputedStyle(el.querySelector("thead th") as Element);
          return {
            td2: cell("tbody td:nth-child(2)"),
            td3: cell("tbody td:nth-child(3)"),
            th2: cell("thead th:nth-child(2)"),
            th3: cell("thead th:nth-child(3)"),
            td1: cell("tbody td:nth-child(1)"),
            borderWidth: border.borderBottomWidth,
            borderStyle: border.borderBottomStyle,
          };
        });
        for (const cell of [align.td2, align.td3, align.th2, align.th3]) {
          expect(cell.align, `${viewId} D2`).toBe("right");
          expect(cell.nums, `${viewId} D2`).toBe("tabular-nums");
        }
        expect(["start", "left"], `${viewId} D2`).toContain(align.td1.align);
        expect(align.borderWidth, `${viewId} D3`).toBe("1px");
        expect(align.borderStyle, `${viewId} D3`).toBe("solid");

        const share = page.getByTestId("map-view-share");
        const close = page.getByTestId("map-view-close");
        for (const button of [share, close]) {
          const stuck = await button.evaluate((el) => {
            const cs = getComputedStyle(el);
            return { position: cs.position, bottom: cs.bottom, shadow: cs.boxShadow };
          });
          expect(stuck.position, `${viewId} D4`).toBe("sticky");
          expect(stuck.bottom, `${viewId} D4`).toBe("8px");
          expect(stuck.shadow, `${viewId} D7`).toContain("rgb(255, 255, 255)");
          expect(stuck.shadow, `${viewId} D7`).toContain("0px -12px");
        }
        const scrollNow = await scroll.boundingBox();
        expect(scrollNow).toBeTruthy();
        for (const button of [share, close]) {
          const box = await button.boundingBox();
          expect(box, `${viewId} D4`).toBeTruthy();
          expect(box!.y, `${viewId} D4`).toBeGreaterThanOrEqual(scrollNow!.y);
          expect(box!.y + box!.height, `${viewId} D4`).toBeLessThanOrEqual(
            scrollNow!.y + scrollNow!.height + 1,
          );
          await button.click({ trial: true });
        }

        const ids = await page
          .getByTestId("map-view-detail")
          .locator(":scope > [data-testid]")
          .evaluateAll((els) => els.map((el) => el.getAttribute("data-testid")));
        expect(ids.at(-2), `${viewId} D5`).toBe("map-view-share");
        expect(ids.at(-1), `${viewId} D5`).toBe("map-view-close");
        await expect(share).toHaveText(VIEW_SHARE_LABEL);
        await expect(close).toHaveText(VIEW_CLOSE_LABEL);

        const pad = await scroll.evaluate(
          (el) => getComputedStyle(el).paddingBottom,
        );
        expect(Number.parseFloat(pad), `${viewId} D6`).toBeGreaterThanOrEqual(24);

        await page.evaluate(() => {
          const scroller = document.querySelector(
            '[data-testid="map-panel-scroll"]',
          );
          const detail = document.querySelector(".map-view-detail");
          if (!(scroller instanceof HTMLElement) || !(detail instanceof HTMLElement)) {
            return;
          }
          const delta =
            detail.getBoundingClientRect().bottom -
            scroller.getBoundingClientRect().bottom;
          scroller.scrollTop += delta;
        });
        const last = table.locator("tbody tr").last();
        const lastBox = await last.boundingBox();
        const endScroll = await scroll.boundingBox();
        const shareBox = await share.boundingBox();
        const closeBox = await close.boundingBox();
        expect(lastBox, `${viewId} D8`).toBeTruthy();
        expect(endScroll, `${viewId} D8`).toBeTruthy();
        expect(shareBox, `${viewId} D8`).toBeTruthy();
        expect(closeBox, `${viewId} D8`).toBeTruthy();
        expect(lastBox!.y, `${viewId} D8`).toBeGreaterThanOrEqual(endScroll!.y);
        expect(lastBox!.y + lastBox!.height, `${viewId} D8`).toBeLessThanOrEqual(
          endScroll!.y + endScroll!.height,
        );
        expect(lastBox!.y + lastBox!.height, `${viewId} D8`).toBeLessThanOrEqual(
          Math.min(shareBox!.y, closeBox!.y),
        );
        for (const button of [share, close]) {
          await expect(button).toBeVisible();
          const box = await button.boundingBox();
          expect(box!.width, `${viewId} D8`).toBeGreaterThanOrEqual(44);
          expect(box!.height, `${viewId} D8`).toBeGreaterThanOrEqual(44);
        }
        if (viewId === "idle-land") {
          await saveShot(
            testInfo,
            `story-sticky-${vp.width}`,
            await page.screenshot(),
          );
        }
        await close.click();
        await expect(page.getByTestId("map-view-detail")).toHaveCount(0);
      }
    });

    test("T1-T3 story controls are 44px", async ({ page }) => {
      test.setTimeout(120_000);
      await stubMapCardsBackend(page);
      await page.goto("/");
      await waitForMap(page);
      await openStory(page, "idle-land");
      const buttons = page.locator(".map-view-button");
      await expect(buttons).toHaveCount(4);
      const count = await buttons.count();
      for (let i = 0; i < count; i += 1) {
        const box = await buttons.nth(i).boundingBox();
        expect(box, `T1 button ${i}`).toBeTruthy();
        expect(box!.width).toBeGreaterThanOrEqual(44);
        expect(box!.height).toBeGreaterThanOrEqual(44);
      }
      for (const id of ["map-view-share", "map-view-close"]) {
        const box = await page.getByTestId(id).boundingBox();
        expect(box, `T1 ${id}`).toBeTruthy();
        expect(box!.width).toBeGreaterThanOrEqual(44);
        expect(box!.height).toBeGreaterThanOrEqual(44);
      }
      await page.evaluate(() => {
        const scroller = document.querySelector('[data-testid="map-panel-scroll"]');
        if (scroller instanceof HTMLElement) scroller.scrollTop = scroller.scrollHeight;
      });
      const actions = page.locator(".map-view-detail > .map-view-action");
      await expect(actions).toHaveCount(2);
      for (let i = 0; i < 2; i += 1) {
        const box = await actions.nth(i).boundingBox();
        expect(box, `T2 ${i}`).toBeTruthy();
        expect(box!.width).toBeGreaterThanOrEqual(44);
        expect(box!.height).toBeGreaterThanOrEqual(44);
      }
      const link = page.getByTestId("map-layers-labels-link").locator("a");
      await link.scrollIntoViewIfNeeded();
      await expect(link).toHaveText("What the labels mean");
      await expect(link).toHaveAttribute("href", "/methodology#glossary-tags");
      const linkBox = await link.boundingBox();
      expect(linkBox, "T3").toBeTruthy();
      expect(linkBox!.width).toBeGreaterThanOrEqual(44);
      expect(linkBox!.height).toBeGreaterThanOrEqual(44);
    });

    test("F1 mouse focus ring sits on the search pill", async ({ page }, testInfo) => {
      test.setTimeout(120_000);
      await stubMapCardsBackend(page);
      await page.goto("/");
      await waitForMap(page);
      await page.locator("#place-query").click();
      expectFocusedRing(await searchRing(page));
      await saveShot(
        testInfo,
        `search-focus-mouse-${vp.width}`,
        await page.locator(".hud-search").screenshot(),
      );
    });

    test("F2 keyboard focus ring matches the mouse ring", async ({ page }, testInfo) => {
      test.setTimeout(120_000);
      await stubMapCardsBackend(page);
      await page.goto("/");
      await waitForMap(page);
      await page.getByTestId("hud-layers-btn").focus();
      await focusByTab(page, "#place-query");
      await expect(page.locator("#place-query")).toBeFocused();
      expectFocusedRing(await searchRing(page));
      await saveShot(
        testInfo,
        `search-focus-keyboard-${vp.width}`,
        await page.locator(".hud-search").screenshot(),
      );
    });

    test("F3 the pill ring is present while the input is focused", async ({ page }) => {
      test.setTimeout(120_000);
      await stubMapCardsBackend(page);
      await page.goto("/");
      await waitForMap(page);
      await page.locator("#place-query").click();
      const ring = await searchRing(page);
      expectFocusedRing(ring);
      expect(ring.pillOutline).not.toBe("none");
    });

    test("F4 the pill ring clears on blur", async ({ page }) => {
      test.setTimeout(120_000);
      await stubMapCardsBackend(page);
      await page.goto("/");
      await waitForMap(page);
      await page.locator("#place-query").click();
      await page.locator("#place-query").blur();
      const ring = await searchRing(page);
      expect(ring.pillOutline).toBe("none");
    });

    test("F5 focused search screenshots", async ({ page }, testInfo) => {
      test.setTimeout(120_000);
      await stubMapCardsBackend(page);
      await page.goto("/");
      await waitForMap(page);
      await page.locator("#place-query").click();
      await saveShot(
        testInfo,
        `f5-mouse-${vp.width}`,
        await page.locator(".hud-search").screenshot(),
      );
      await page.getByTestId("hud-layers-btn").focus();
      await focusByTab(page, "#place-query");
      await expect(page.locator("#place-query")).toBeFocused();
      await saveShot(
        testInfo,
        `f5-keyboard-${vp.width}`,
        await page.locator(".hud-search").screenshot(),
      );
    });
  });
}

async function assertLayersFocus(
  page: Page,
  gate: { expectError: (spec: { urlPath: string; status: number; count: number }) => void },
  kind: "keyboard" | "mouse",
): Promise<void> {
  const manifest: ManifestCtl = { mode: "hold", hits: 0, held: [] };
  gate.expectError({
    urlPath: TILES_MANIFEST_PATHNAME,
    status: 503,
    count: 2,
  });
  await stubMapCardsBackend(page);
  await routeManifest(page, manifest);
  await page.goto("/");
  await waitForMap(page);
  await openLayersPanel(page);
  await page.getByTestId("map-panel-slot-close").focus();
  const before = await page.evaluate(
    () =>
      document.activeElement ===
      document.querySelector('[data-testid="map-panel-slot-close"]'),
  );
  expect(before).toBe(true);
  manifest.mode = "error";
  const held = manifest.held[0];
  if (!held) throw new Error("L6 held manifest request missing");
  await held.fulfill({
    status: 503,
    contentType: "application/json",
    body: "{}",
  });
  await expect(page.getByTestId("layers-retry-state")).toBeVisible();
  await expect(page.getByTestId("map-panel-slot-close")).toBeFocused();
  const line = page.locator('[data-testid="layers-retry-state"] .retry-state-line');
  await expect(line).toHaveAttribute("role", "status");
  await expect(line).toHaveAttribute("aria-live", "polite");
  if (kind === "keyboard") {
    await focusByTab(page, '[data-testid="layers-try-again"]');
    await page.keyboard.press("Enter");
  } else {
    await page.getByTestId("layers-try-again").click();
  }
  const immediate = await focusState(page, "layers-panel");
  expect(immediate.notBody).toBe(true);
  expect(immediate.contained).toBe(true);
  expect(immediate.isRegion).toBe(true);
  await expect(page.getByTestId("layers-retry-state")).toBeVisible();
  const after = await focusState(page, "layers-panel");
  expect(after.notBody).toBe(true);
  expect(after.contained).toBe(true);
}
