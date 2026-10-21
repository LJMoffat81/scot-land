import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * UI-FIX-4 — layers padding, right-column Layers, peek, search, map tap,
 * no map-card experimental footer, panel=place reload, focus, one Layers close.
 * Asserts can fail. 390×844 and 1280×800. No public amounts.
 */

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const EXPERIMENTAL =
  "Experimental estimate, not an official valuation. It is not a bill, and it does not change what you pay.";

function cardFor(label: string, lat: number, lng: number) {
  return {
    contract: "place_card_v1",
    lat,
    lng,
    place_label: label,
    council_name: "Council",
    data_zone: {
      status: "ok",
      code: "S01008677",
      name: "Zone",
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
}

async function stubMap(page: Page) {
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
    if (/\/platform\/place/i.test(url)) {
      const u = new URL(url);
      const lat = Number(u.searchParams.get("lat"));
      const label = Math.abs(lat - 55.9533) < 0.05 ? "Old Town" : "Inverness";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(cardFor(label, lat || 55.9533, -3.1883)),
      });
      return;
    }
    if (/\/place\?/i.test(url) && !/platform\/place/i.test(url)) {
      const u = new URL(url);
      const q = (u.searchParams.get("q") ?? "").trim();
      const eh1 = q.toUpperCase().startsWith("EH1");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(
          eh1
            ? {
                kind: "places",
                matches: [
                  {
                    label: "EH1 1YZ",
                    lat: 55.9533,
                    lng: -3.1883,
                  },
                ],
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

async function waitMap(page: Page) {
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
}

function boxesOverlap(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
) {
  if (a.width <= 0 || a.height <= 0 || b.width <= 0 || b.height <= 0) return false;
  const x = Math.min(a.x + a.width, b.x + b.width) - Math.max(a.x, b.x);
  const y = Math.min(a.y + a.height, b.y + b.height) - Math.max(a.y, b.y);
  return x > 0 && y > 0;
}

async function openLayers(page: Page) {
  await page.getByTestId("hud-layers-btn").click();
  await expect(page.getByTestId("layers-panel")).toBeVisible();
}

test.describe("UI-FIX-4 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  // QUARANTINE CI-DEDUP-1 Q4: flaky on unrelated PRs, runs 39507837359; owner Eng Lead; exit = 10 consecutive green quarantine runs then remove tag, or fix by 2026-11-21.
  test("padding, peek, search, map tap, footer, reload, focus, one close @quarantine", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await stubMap(page);
    await page.goto("/");
    await waitMap(page);

    const detailed = page.getByTestId("basemap-switcher");
    const strip = page.locator(".research-banner-map");
    await expect(detailed).toBeVisible();
    await expect(strip).toBeVisible();
    const detailedBox = await detailed.boundingBox();
    const stripBox = await strip.boundingBox();
    expect(detailedBox).toBeTruthy();
    expect(stripBox).toBeTruthy();
    expect(detailedBox!.width).toBeGreaterThan(0);
    expect(detailedBox!.height).toBeGreaterThan(0);
    expect(stripBox!.width).toBeGreaterThan(0);
    expect(stripBox!.height).toBeGreaterThan(0);
    expect(boxesOverlap(detailedBox!, stripBox!)).toBe(false);

    await openLayers(page);
    const pad = await page.locator(".layers-panel").evaluate((el) => {
      const s = getComputedStyle(el);
      return {
        left: parseFloat(s.paddingLeft),
        right: parseFloat(s.paddingRight),
      };
    });
    expect(pad.left).toBeGreaterThanOrEqual(12);
    expect(pad.right).toBeGreaterThanOrEqual(12);

    const layersSlot = page.locator('[data-panel="layers"]');
    await expect(layersSlot.getByRole("button", { name: /close/i })).toHaveCount(1);

    await page.locator("#place-query").fill("EH1");
    const suggest = page.locator("#place-suggestions");
    await expect(suggest).toBeVisible({ timeout: 15_000 });
    await suggest.getByRole("option").first().click();
    await expect(page.getByTestId("layers-panel")).toHaveCount(0);
    await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });

    await page.getByTestId("place-card-close").click();
    await expect(page.getByTestId("place-card")).toHaveCount(0);

    await openLayers(page);
    const canvas = page.locator(".maplibregl-canvas");
    const tap = await page.evaluate(() => {
      const map = (
        window as unknown as {
          __map?: {
            project(ll: { lng: number; lat: number }): { x: number; y: number };
          };
        }
      ).__map;
      const canvasEl = document.querySelector(".maplibregl-canvas");
      const sheet = document.querySelector('[data-panel="layers"]');
      if (!map || !canvasEl || !sheet) return null;
      const c = canvasEl.getBoundingClientRect();
      const s = sheet.getBoundingClientRect();
      const candidates = [
        { lng: -4.2, lat: 58.4 },
        { lng: -3.2, lat: 58.8 },
        { lng: -5.1, lat: 58.2 },
        { lng: -3.1883, lat: 55.9533 },
      ];
      for (const place of candidates) {
        const p = map.project(place);
        const absY = c.top + p.y;
        if (
          p.x > 24 &&
          p.x < c.width - 24 &&
          absY > c.top + 70 &&
          absY < s.top - 12
        ) {
          return { x: p.x, y: p.y };
        }
      }
      return null;
    });
    expect(tap, "visible land above the Layers sheet").toBeTruthy();
    await canvas.click({ position: tap! });
    await expect(page.getByTestId("layers-panel")).toHaveCount(0, {
      timeout: 15_000,
    });
    await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("map-panel-slot")).toHaveAttribute(
      "data-detent",
      "peek",
    );
    await expect(page.getByTestId("place-card-place")).toBeVisible();
    await expect(page.getByTestId("place-card-figure-status")).toBeVisible();
    await expect(page.getByTestId("place-card-footer")).toBeVisible();
    await expect(page.getByTestId("place-card-footer")).toHaveText(EXPERIMENTAL);

    const peek = await page.evaluate(() => {
      const pick = (sel: string) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        if (
          r.width <= 0 ||
          r.height <= 0 ||
          s.display === "none" ||
          s.visibility === "hidden"
        ) {
          return null;
        }
        return { x: r.x, y: r.y, width: r.width, height: r.height };
      };
      return {
        title: pick('[data-testid="place-card-place"]'),
        rent: pick('[data-testid="place-card-figure-status"]'),
        disclaimer: pick('[data-testid="place-card-footer"]'),
        slot: pick('[data-testid="map-panel-slot"]'),
      };
    });
    expect(peek.title).toBeTruthy();
    expect(peek.rent).toBeTruthy();
    expect(peek.disclaimer).toBeTruthy();
    expect(peek.slot).toBeTruthy();
    const inside = (
      item: { x: number; y: number; width: number; height: number },
      slot: { x: number; y: number; width: number; height: number },
    ) => {
      expect(item.y).toBeGreaterThanOrEqual(slot.y - 1);
      expect(item.x).toBeGreaterThanOrEqual(slot.x - 1);
      expect(item.y + item.height).toBeLessThanOrEqual(slot.y + slot.height + 1);
      expect(item.x + item.width).toBeLessThanOrEqual(slot.x + slot.width + 1);
    };
    inside(peek.title!, peek.slot!);
    inside(peek.rent!, peek.slot!);
    inside(peek.disclaimer!, peek.slot!);
    expect(boxesOverlap(peek.title!, peek.rent!)).toBe(false);
    expect(boxesOverlap(peek.title!, peek.disclaimer!)).toBe(false);
    expect(boxesOverlap(peek.rent!, peek.disclaimer!)).toBe(false);
    const peekScroll = await page.getByTestId("map-panel-scroll").evaluate((el) => el.scrollTop);
    expect(peekScroll).toBe(0);

    await expect(page.getByTestId("place-card-footer")).toContainText(EXPERIMENTAL);
    await expect(page.getByTestId("research-banner")).toContainText(
      "Research estimate",
    );
    await expect(page.getByTestId("map-footer-line")).toContainText(
      "Research estimate",
    );
  });

  test("panel=place reload has a heading", async ({ page }) => {
    test.setTimeout(90_000);
    await stubMap(page);
    await page.goto("/?panel=place&c=-3.18830,55.95330");
    await waitMap(page);
    const heading = page.getByTestId("place-card-place");
    await expect(heading).toBeVisible({ timeout: 30_000 });
    const text = (await heading.innerText()).trim();
    expect(text.length).toBeGreaterThan(0);
  });
});

test.describe("UI-FIX-4 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("padding, right column, controls, banner, title, focus, one close", async ({
    page,
  }) => {
    test.setTimeout(120_000);
    await stubMap(page);
    await page.goto("/");
    await waitMap(page);
    await page.locator("#place-query").fill("55.95330, -3.18830");
    await page.locator(".hud-search-go").click();
    await expect(page.getByTestId("place-card")).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("place-card-place")).toBeVisible({
      timeout: 30_000,
    });

    const slotBox = await page.getByTestId("map-panel-slot").boundingBox();
    const titleBox = await page.getByTestId("place-card-place").boundingBox();
    expect(slotBox).toBeTruthy();
    expect(titleBox).toBeTruthy();
    expect(titleBox!.y - slotBox!.y).toBeLessThanOrEqual(24);

    const before = await page.evaluate(() => {
      const pick = (sel: string) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width, height: r.height };
      };
      return {
        zoom: pick(".maplibregl-ctrl-zoom-in"),
        detailed: pick('[data-testid="basemap-switcher"]'),
        attrib: pick(".maplibregl-ctrl-attrib-button"),
      };
    });

    await openLayers(page);
    await page.waitForTimeout(500);
    await expect(page.getByTestId("place-card")).toBeVisible();
    const column = page.getByTestId("layers-column");
    await expect(column).toBeVisible();
    const colBox = await column.boundingBox();
    expect(colBox).toBeTruthy();
    expect(colBox!.x).toBeGreaterThan((slotBox?.x ?? 0) + (slotBox?.width ?? 0) - 8);

    const after = await page.evaluate(() => {
      const pick = (sel: string) => {
        const el = document.querySelector(sel);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return { x: r.x, y: r.y };
      };
      return {
        zoom: pick(".maplibregl-ctrl-zoom-in"),
        detailed: pick('[data-testid="basemap-switcher"]'),
        attrib: pick(".maplibregl-ctrl-attrib-button"),
      };
    });
    for (const key of ["zoom", "detailed", "attrib"] as const) {
      const a = before[key];
      const b = after[key];
      expect(a, key).toBeTruthy();
      expect(b, key).toBeTruthy();
      expect(Math.abs(a!.x - b!.x), `${key} x`).toBeLessThanOrEqual(4);
      expect(Math.abs(a!.y - b!.y), `${key} y`).toBeLessThanOrEqual(4);
    }

    const bannerLeft = await page.locator(".research-banner-map").evaluate((el) => {
      return el.getBoundingClientRect().left;
    });
    expect(bannerLeft).toBeGreaterThanOrEqual(0);

    const pad = await page.locator(".layers-panel").evaluate((el) => {
      const s = getComputedStyle(el);
      return {
        left: parseFloat(s.paddingLeft),
        right: parseFloat(s.paddingRight),
      };
    });
    expect(pad.left).toBeGreaterThanOrEqual(16);
    expect(pad.right).toBeGreaterThanOrEqual(16);

    await expect(column.getByRole("button", { name: /close/i })).toHaveCount(1);
    const disclaimer = page.getByTestId("place-card-footer");
    await expect(disclaimer).toBeVisible();
    await expect(disclaimer).toContainText(EXPERIMENTAL);
    const disclaimerBox = await disclaimer.boundingBox();
    const visibleCard = await page.getByTestId("map-panel-slot").boundingBox();
    expect(disclaimerBox).toBeTruthy();
    expect(visibleCard).toBeTruthy();
    expect(disclaimerBox!.y).toBeGreaterThanOrEqual(visibleCard!.y - 1);
    expect(disclaimerBox!.y + disclaimerBox!.height).toBeLessThanOrEqual(
      visibleCard!.y + visibleCard!.height + 1,
    );
    const cardScroll = await page
      .getByTestId("map-panel-slot")
      .getByTestId("map-panel-scroll")
      .evaluate((el) => el.scrollTop);
    expect(cardScroll).toBe(0);
    await expect(page.getByTestId("research-banner")).toContainText(
      "Research estimate",
    );

    await page.locator("#place-query").focus();
    let sawFocus = false;
    for (let i = 0; i < 40; i += 1) {
      await page.keyboard.press("Tab");
      const hit = await page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        if (!el) return null;
        const focus = el.classList.contains("map-panel-slot-focus")
          ? el
          : el.closest(".map-panel-slot--place");
        if (!focus) return null;
        const s = getComputedStyle(el);
        return { outline: s.outlineStyle, shadow: s.boxShadow };
      });
      if (!hit) continue;
      const outlined = hit.outline !== "none" && hit.outline !== "";
      const shadowed = Boolean(hit.shadow) && hit.shadow !== "none";
      expect(outlined || shadowed).toBe(true);
      sawFocus = true;
      break;
    }
    expect(sawFocus).toBe(true);
  });
});
