import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import {
  expect,
  test,
  type Locator,
  type Page,
} from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * UI-FIX-1 + ADDENDUM-1 (SW-056) — 390×844.
 * U1 tap targets ≥44×44; U2 legend vs research banner; U3 no partial wordmark;
 * SW-056: picking a place collapses the Layers sheet on mobile.
 * Tests compare real measured boxes (0 px intersection tolerance) and can fail.
 */

const MIN_HIT = 44;

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
  lat: 55.9533,
  lng: -3.1883,
  place_label: "Edinburgh",
  council_name: "City of Edinburgh",
  data_zone: {
    status: "ok",
    code: "S01008677",
    name: "Old Town",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "Old Town", code: "S02001607" },
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

type ConsoleGate = {
  consoleErrors: string[];
  resourceFails: Array<{ url: string; status: number }>;
};

type Box = { x: number; y: number; width: number; height: number };

function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const resourceFails: Array<{ url: string; status: number }> = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => consoleErrors.push(String(err)));
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
    if (/\/favicon\.ico(?:\?|$)|\/apple-touch-icon/i.test(fail.url)) {
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
    if (/\bAbortError\b|aborted/i.test(text)) return false;
    if (/Failed to load resource:.*(?:400|404|503)/i.test(text)) return false;
    if (/Download the React DevTools/i.test(text)) return false;
    return true;
  });
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
}

function boxesOverlap(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function assertMinHit(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, `${label} box`).toBeTruthy();
  expect(box!.width, `${label} width`).toBeGreaterThanOrEqual(MIN_HIT);
  expect(box!.height, `${label} height`).toBeGreaterThanOrEqual(MIN_HIT);
}

async function assertNoBoxOverlap(a: Locator, b: Locator, label: string) {
  const boxA = await a.boundingBox();
  const boxB = await b.boundingBox();
  expect(boxA && boxB, `${label}: both boxes`).toBeTruthy();
  expect(
    boxesOverlap(boxA!, boxB!),
    `${label}: overlap a=${JSON.stringify(boxA)} b=${JSON.stringify(boxB)}`,
  ).toBe(false);
}

async function stubMapChrome(page: Page) {
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
    if (/\/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_STUB),
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
  // /downloads/manifest.json is a static public file — leave it unstubbed.
}

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator(".maplibregl-ctrl-zoom-in").waitFor();
  await page.locator(".hud-search-go").waitFor();
}

async function openPlaceCard(page: Page) {
  await page.locator("#place-query").fill("55.95330, -3.18830");
  await page.locator(".hud-search-go").click();
  await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });
}

test.describe("UI-FIX-1 + SW-056 @ 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("U1 home + layers + card-open tap targets ≥44×44", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openMap(page);

    const attrib = page.locator(".maplibregl-ctrl-attrib-button");
    await expect(attrib).toBeVisible({ timeout: 30_000 });
    await assertMinHit(attrib, "Toggle attribution");

    await page.locator("#place-query").fill("EH1");
    const clear = page.getByRole("button", { name: "Clear search" });
    await assertMinHit(clear, "Clear search");

    const layersBtn = page.getByTestId("hud-layers-btn");
    await assertMinHit(layersBtn, "Layers");

    const menu = page.getByTestId("site-nav-menu-btn");
    await assertMinHit(menu, "Menu");

    const logo = page.locator(".hud-wordmark");
    await assertMinHit(logo, "Scot-LAND home");

    // U1 listed Copy Map reference, but MAP-CARDS / SW-052 removed that control —
    // assert absence so a silent reintroduction without a 44×44 hit still fails CI.
    await expect(
      page.getByRole("button", { name: /Copy Map reference/i }),
    ).toHaveCount(0);

    await layersBtn.click();
    await expect(page.getByTestId("layers-panel")).toBeVisible();
    // MAP-CARDS hides Layers at full mobile detent; half keeps it a ≥44 tap target.
    const layersSlot = page.getByTestId("map-panel-slot");
    await expect(layersSlot).toHaveAttribute("data-detent", "full");
    await page.getByTestId("map-panel-handle").click();
    await expect(layersSlot).toHaveAttribute("data-detent", "half");
    await expect(layersBtn).toBeVisible();
    await assertMinHit(layersBtn, "Layers (open)");
    await page.getByTestId("map-panel-slot-close").click();
    await expect(page.getByTestId("layers-panel")).toHaveCount(0);

    await openPlaceCard(page);
    await assertMinHit(layersBtn, "Layers (card open)");
    await assertMinHit(logo, "Scot-LAND home (card open)");
    await assertMinHit(menu, "Menu (card open)");

    assertConsoleClean(gate);
  });

  test("U1 /developers Download and JSON buttons ≥44×44", async ({ page }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await page.goto("/developers");
    await expect(page.getByTestId("developers-downloads")).toBeVisible({
      timeout: 30_000,
    });

    const downloadBtns = page.locator("a.download-card-action");
    await expect(downloadBtns.first()).toBeVisible({ timeout: 30_000 });
    const n = await downloadBtns.count();
    expect(n, "download/json action count").toBeGreaterThanOrEqual(1);
    for (let i = 0; i < n; i += 1) {
      const el = downloadBtns.nth(i);
      await expect(el).toBeVisible();
      const text = ((await el.innerText()) || "").trim();
      expect(
        /^(Download|JSON \(for developers\))$/.test(text),
        `unexpected action label: ${text}`,
      ).toBe(true);
      await assertMinHit(el, `${text} #${i}`);
    }

    // /downloads redirects into the same surface — re-check after navigation.
    await page.goto("/downloads");
    await expect(page.getByTestId("developers-downloads")).toBeVisible({
      timeout: 30_000,
    });
    const after = page.locator("a.download-card-action");
    const m = await after.count();
    expect(m).toBeGreaterThanOrEqual(1);
    for (let i = 0; i < m; i += 1) {
      await assertMinHit(after.nth(i), `downloads action #${i}`);
    }

    assertConsoleClean(gate);
  });

  test("U2 legend pill and research banner do not intersect with card open", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openMap(page);
    await openPlaceCard(page);

    // MAP-CARDS §3.6: research banner collapses (height 0) while a place card
    // is open. U2 still requires 0 px intersection with any visible legend UI.
    const banner = page.locator(".research-banner-map");
    await expect(banner).toBeAttached();
    const bannerHeight = await banner.evaluate(
      (el) => el.getBoundingClientRect().height,
    );
    const bannerVisible = bannerHeight > 0.5;

    const legendCandidates = [
      page.getByRole("button", { name: "Show legend" }),
      page.locator(".legend-compact"),
      page.locator(".hud-scotland-fold"),
      page.getByTestId("legend-strip"),
    ];
    let visibleLegend = 0;
    for (const loc of legendCandidates) {
      const count = await loc.count();
      for (let i = 0; i < count; i += 1) {
        const el = loc.nth(i);
        if (!(await el.isVisible().catch(() => false))) continue;
        visibleLegend += 1;
        if (bannerVisible) {
          await assertNoBoxOverlap(
            el,
            banner,
            "legend vs research-banner-map (0px tolerance)",
          );
        }
      }
    }
    if (bannerVisible) {
      expect(
        visibleLegend,
        "banner visible with card open → at least one legend element must be measured",
      ).toBeGreaterThanOrEqual(1);
      await expect(banner).toBeEnabled();
    } else {
      // Explicit collapse (MAP-CARDS say-it-once) — not a silent skip.
      expect(bannerHeight, "research banner collapsed height").toBe(0);
    }

    assertConsoleClean(gate);
  });

  test("U3 map controls do not cover a partial hud-scotland wordmark", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openMap(page);

    // MAP-CARDS removes the bottom wordmark at this width — no partial letters.
    const scotland = page.locator(".hud-scotland");
    if ((await scotland.count()) > 0) {
      await expect(scotland).toBeHidden();
    }

    const layers = page.getByTestId("hud-layers-btn");
    const basemap = page.getByTestId("basemap-switcher");
    const logo = page.locator(".hud-wordmark");
    await expect(layers).toBeVisible();
    await expect(basemap).toBeVisible();
    await expect(logo).toBeVisible();

    await assertNoBoxOverlap(layers, logo, "Layers vs logo");
    await assertNoBoxOverlap(basemap, logo, "basemap vs logo");

    // No stray visible text from the removed scotland stack.
    const stray = await page.evaluate(() => {
      const el = document.querySelector(".hud-scotland");
      if (!el) return null;
      const style = getComputedStyle(el);
      if (style.display === "none" || style.visibility === "hidden") return null;
      const text = (el.textContent || "").replace(/\s+/g, " ").trim();
      const box = el.getBoundingClientRect();
      if (box.width < 1 || box.height < 1) return null;
      return { text: text.slice(0, 80), box: { w: box.width, h: box.height } };
    });
    expect(stray, `partial hud-scotland visible: ${JSON.stringify(stray)}`).toBeNull();

    assertConsoleClean(gate);
  });

  test("SW-056 open Layers, pick place → sheet collapses; card clear of banner/pill", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapChrome(page);
    await openMap(page);

    const layersBtn = page.getByTestId("hud-layers-btn");
    await layersBtn.click();
    const layersPanel = page.getByTestId("layers-panel");
    await expect(layersPanel).toBeVisible();
    await expect(page.locator(".app-shell")).toHaveClass(/tools-open/);

    // Wait for MapLibre test hook, then pick a place while Layers is open.
    // (Full-detent Layers marks .map-stage inert — use map.fire like GIS e2e.)
    await expect
      .poll(
        async () =>
          page.evaluate(() =>
            Boolean(
              (window as unknown as { __map?: { fire: unknown } }).__map &&
                typeof (window as unknown as { __map?: { fire: unknown } }).__map
                  ?.fire === "function",
            ),
          ),
        { timeout: 60_000 },
      )
      .toBe(true);

    await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: {
            fire(type: string, ev: object): void;
            project(lngLat: { lng: number; lat: number }): {
              x: number;
              y: number;
            };
          };
        }
      ).__map;
      if (!map) throw new Error("window.__map missing");
      const lngLat = { lng: -3.1883, lat: 55.9533 };
      map.fire("click", {
        lngLat,
        point: map.project(lngLat),
        originalEvent: new MouseEvent("click"),
      });
    });
    // Map-click identify is debounced ~150ms.
    await page.waitForTimeout(220);

    const card = page.getByTestId("place-card");
    await expect(card).toBeVisible({ timeout: 30_000 });
    // Sheet must collapse so the card has room.
    await expect(layersPanel).toHaveCount(0);
    await expect(page.locator(".app-shell")).not.toHaveClass(/tools-open/);
    await expect(page.locator(".app-shell")).toHaveClass(/place-open/);

    // Visible card chrome is the panel slot (inner place-card may scroll).
    const slot = page.getByTestId("map-panel-slot");
    await expect(slot).toBeVisible();
    await expect(slot).toHaveAttribute("data-panel", "place");
    const slotBox = await slot.boundingBox();
    expect(slotBox, "place panel slot box").toBeTruthy();
    expect(slotBox!.y, "card top").toBeGreaterThanOrEqual(0);
    expect(slotBox!.x, "card left").toBeGreaterThanOrEqual(0);
    expect(slotBox!.y + slotBox!.height, "card bottom").toBeLessThanOrEqual(
      844 + 0.5,
    );
    expect(slotBox!.x + slotBox!.width, "card right").toBeLessThanOrEqual(
      390 + 0.5,
    );
    // Slot must claim real space (peek/half), not a collapsed stub.
    expect(slotBox!.height, "card height").toBeGreaterThanOrEqual(44);

    const title = card.locator(".place-card-title").first();
    await expect(title).toBeVisible();
    // Title must sit inside the visible slot (not under a collapsed Layers sheet).
    const titleBox = await title.boundingBox();
    expect(titleBox, "card title box").toBeTruthy();
    expect(titleBox!.y, "title top in slot").toBeGreaterThanOrEqual(slotBox!.y - 0.5);
    expect(
      titleBox!.y + titleBox!.height,
      "title bottom in slot",
    ).toBeLessThanOrEqual(slotBox!.y + slotBox!.height + 0.5);

    // Overlap checks: run whenever banner/pill is visible; otherwise assert the
    // MAP-CARDS expectation that neither is on screen with a place card open.
    let overlapChecks = 0;
    const banner = page.locator(".research-banner-map");
    const bannerHeight = await banner.evaluate(
      (el) => el.getBoundingClientRect().height,
    );
    if (bannerHeight > 0.5) {
      await assertNoBoxOverlap(
        banner,
        title,
        "research notice vs card title",
      );
      overlapChecks += 1;
    }
    const legendPill = page.getByRole("button", { name: "Show legend" });
    if (
      (await legendPill.count()) > 0 &&
      (await legendPill.first().isVisible().catch(() => false))
    ) {
      await assertNoBoxOverlap(
        legendPill.first(),
        title,
        "Show legend pill vs card title",
      );
      overlapChecks += 1;
    }
    const legendStrip = page.getByTestId("legend-strip");
    if (
      (await legendStrip.count()) > 0 &&
      (await legendStrip.first().isVisible().catch(() => false))
    ) {
      await assertNoBoxOverlap(
        legendStrip.first(),
        title,
        "legend strip vs card title",
      );
      overlapChecks += 1;
    }
    if (overlapChecks === 0) {
      // Expected after MAP-CARDS: banner height 0; Show legend / strip absent
      // while the place panel is open (legend-strip only when panel closed).
      expect(bannerHeight, "research notice collapsed").toBe(0);
      await expect(legendPill).toHaveCount(0);
      await expect(legendStrip).toHaveCount(0);
    } else {
      expect(
        overlapChecks,
        "at least one pill/banner vs title overlap check ran",
      ).toBeGreaterThanOrEqual(1);
    }

    assertConsoleClean(gate);
  });
});
