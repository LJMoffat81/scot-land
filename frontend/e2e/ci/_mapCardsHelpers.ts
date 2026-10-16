/**
 * Shared stubs and probes for MAP-CARDS-REDESIGN e2e under e2e/ci/.
 * Not a Playwright spec — imported by *.spec.ts only.
 */
import { expect, type Page } from "@playwright/test";

export const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

export const EMPTY_FC = { type: "FeatureCollection", features: [] };

export const LIVE_LAYER_IDS = [
  "1",
  "access_services",
  "vdl",
  "hla",
  "3",
  "4",
  "9",
  "8",
  "designations",
  "flood",
  "crofting",
  "councils",
  "data_zones",
] as const;

export const BANNED_VISIBLE =
  /\b(natural capital|ledger|what3words|map reference)\b/i;

export const PRE_POUND =
  "We're not showing amounts yet while we check our method.";

export const PLACE_FIXTURE = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "City Centre",
  council_name: "Glasgow City",
  dwellings: 410,
  sales_year_from: 2019,
  sales_year_to: 2023,
  confidence: "Medium",
  dz_code: "S01014567",
  source_crs: "EPSG:27700",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre", code: "S02002645" },
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "proxy",
      class: "proxy",
      status: "in_progress",
      applies: true,
      range: "not yet estimated",
      unit: null,
      confidence: null,
      method: null,
      gloss: "The yearly value of the land under homes.",
      of_which: [],
    },
    {
      id: "resource",
      label: "Natural resource rents",
      tag: "market",
      class: "market",
      status: "coming_soon",
      applies: true,
      range: "not yet estimated",
      unit: null,
      confidence: null,
      method: null,
      gloss: "Rents from things like wind, minerals and fish farming.",
    },
    {
      id: "nature",
      label: "Services of nature",
      tag: "shadow",
      class: "shadow",
      status: "coming_soon",
      applies: true,
      range: "not yet estimated",
      unit: null,
      confidence: null,
      method: null,
      gloss: "Value from nature's services, such as peat holding carbon.",
    },
  ],
  constraints: [],
  layers: [],
  links: [],
};

export type ConsoleGate = {
  consoleErrors: string[];
  pageErrors: string[];
};

export function attachConsoleGate(page: Page): ConsoleGate {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => pageErrors.push(String(err)));
  return { consoleErrors, pageErrors };
}

export function filterNoise(errors: string[]): string[] {
  return errors.filter((text) => {
    // Keep real exceptions (stack traces); drop CDN / network / resource noise only.
    if (
      /favicon|Download the React DevTools|AbortError|aborted|net::ERR_|Failed to fetch|400|404|503|Service Unavailable/i.test(
        text,
      )
    ) {
      return false;
    }
    // MapLibre sprite/glyph CDN failures (no app stack).
    if (/sprite|glyph/i.test(text) && /failed|error|load|404|503/i.test(text)) {
      return false;
    }
    return true;
  });
}

export function assertConsoleClean(gate: ConsoleGate) {
  expect(
    filterNoise(gate.consoleErrors),
    `console errors:\n${gate.consoleErrors.join("\n")}`,
  ).toEqual([]);
  expect(
    filterNoise(gate.pageErrors),
    `pageerrors:\n${gate.pageErrors.join("\n")}`,
  ).toEqual([]);
}

export type StubOpts = {
  place?: Record<string, unknown>;
  gbpLive?: boolean;
  /** Delayed platform/place responses keyed by lat (for race tests). */
  placeDelayMs?: number;
  placeByLat?: Record<string, Record<string, unknown>>;
};

/**
 * Quiet backend + gbp-live + catalog so CI has no live FastAPI.
 * Routes registered last win for overlapping patterns in Playwright LIFO.
 */
export async function stubMapCardsBackend(page: Page, opts: StubOpts = {}) {
  const place = opts.place ?? PLACE_FIXTURE;
  const gbpLive = opts.gbpLive ?? false;
  const delayMs = opts.placeDelayMs ?? 0;

  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: gbpLive }),
    });
  });
  await page.route("**/platform/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: gbpLive }),
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
    if (/\/layers\/catalog/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ version: 2, layers: [] }),
      });
      return;
    }
    if (/\/platform\/place/i.test(url) || /\/api\/place\.json/i.test(url)) {
      const u = new URL(url);
      const latKey = u.searchParams.get("lat") ?? "";
      const body =
        (opts.placeByLat && opts.placeByLat[latKey]) ||
        (opts.placeByLat &&
          Object.entries(opts.placeByLat).find(([k]) =>
            latKey.startsWith(k),
          )?.[1]) ||
        place;
      if (delayMs > 0) {
        await new Promise((r) => setTimeout(r, delayMs));
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(body),
      });
      return;
    }
    if (/\/layers\/context\/data-zones\/at/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          code: "S01014567",
          name: "City Centre South",
          vintage: 2022,
        }),
      });
      return;
    }
    if (/\/place\?/i.test(url) && !/platform\/place/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
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
      // Always a FeatureCollection for geo-ish paths; bare {} makes MapLibre
      // console.error(Error) with text "Error" (invalid GeoJSON).
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
  await page.route("**/health**", async (route) => {
    // Fulfill all health probes (including /backend/health). Continuing to the
    // Next rewrite yields 503 and noisy console errors in CI without an API.
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
}

export async function openMap(page: Page, path = "/") {
  await page.goto(path);
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  await page.locator("#place-query").waitFor();
}

/**
 * Expand a Layers accordion group if it exists and is collapsed.
 * Re-queries the toggle so a remount mid-click does not hang Playwright.
 */
export async function ensureLayersGroupOpen(page: Page, key: string) {
  const toggle = page.getByTestId(`layers-group-toggle-${key}`);
  if ((await toggle.count()) === 0) return;
  await toggle.scrollIntoViewIfNeeded().catch(() => undefined);
  if ((await toggle.getAttribute("aria-expanded")) === "true") return;
  await toggle.click({ timeout: 15_000 });
  await expect(toggle).toHaveAttribute("aria-expanded", "true", {
    timeout: 10_000,
  });
}

export async function openLayers(page: Page) {
  const btn = page.getByTestId("hud-layers-btn");
  await expect(btn).toBeVisible({ timeout: 30_000 });
  if ((await page.getByTestId("layers-panel").count()) === 0) {
    await btn.click();
  }
  await expect(page.getByTestId("layers-panel")).toBeVisible({
    timeout: 15_000,
  });
  // Belt-and-braces: land + places hold the toggles most specs assert on.
  await ensureLayersGroupOpen(page, "land");
  await ensureLayersGroupOpen(page, "places");
}

/** Raise map zoom so in-range legends show Lower/Higher (not the zoom gate). */
export async function ensureMapZoomAtLeast(page: Page, minZoom: number) {
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const map = (
            window as unknown as {
              __map?: { setZoom(n: number): void; getZoom(): number };
            }
          ).__map;
          return Boolean(map && typeof map.getZoom === "function");
        }),
      { timeout: 60_000 },
    )
    .toBe(true);
  await page.evaluate((z) => {
    const map = (
      window as unknown as {
        __map?: { setZoom(n: number): void; getZoom(): number };
      }
    ).__map;
    if (!map) throw new Error("window.__map missing");
    if (map.getZoom() < z) map.setZoom(z);
  }, minZoom);
  await expect
    .poll(async () => getMapZoom(page), { timeout: 15_000 })
    .toBeGreaterThanOrEqual(minZoom);
}

export async function openPlaceViaCoords(
  page: Page,
  lat = 55.8609,
  lng = -4.2514,
) {
  await page.goto(`/?lat=${lat}&lng=${lng}`);
  await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
  const card = page.getByTestId("place-card");
  // Prefer deep-link boot; only click if the card never mounts.
  try {
    await expect(card).toBeVisible({ timeout: 20_000 });
    return card;
  } catch {
    /* fall through to identify click clear of the 380px desktop panel */
  }
  const canvas = page.locator(".maplibregl-canvas");
  const box = await canvas.boundingBox();
  const width = box?.width ?? 1280;
  // Desktop: click in the uncovered map (right of the 380px panel + gap).
  const x = width >= 900 ? Math.min(width - 80, 380 + 120) : width / 2;
  const y = box ? Math.min(Math.max(box.height * 0.45, 220), box.height - 80) : 300;
  await canvas.click({ position: { x, y } });
  await expect(card).toBeVisible({ timeout: 45_000 });
  return card;
}

export type Box = { x: number; y: number; width: number; height: number };

export function boxesOverlap(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

export async function boxOf(
  locator: ReturnType<Page["locator"]>,
  label: string,
): Promise<Box> {
  const box = await locator.boundingBox();
  if (!box) throw new Error(`${label}: missing bounding box`);
  return box;
}

export async function visibleMapText(page: Page): Promise<string> {
  return page.evaluate(() => {
    const skip = (el: Element) => {
      const s = getComputedStyle(el);
      if (s.display === "none" || s.visibility === "hidden") return true;
      if (el.getAttribute("aria-hidden") === "true") return true;
      return false;
    };
    const walk = (node: Node): string => {
      if (node.nodeType === Node.TEXT_NODE) {
        return node.textContent || "";
      }
      if (node.nodeType !== Node.ELEMENT_NODE) return "";
      const el = node as Element;
      if (skip(el)) return "";
      let out = "";
      for (const child of Array.from(el.childNodes)) out += walk(child);
      return out;
    };
    return walk(document.body);
  });
}

export async function waitForMap(page: Page) {
  await expect
    .poll(async () =>
      page.evaluate(() => {
        const map = (
          window as unknown as {
            __map?: {
              isStyleLoaded?: () => boolean;
              getStyle?: () => { sources?: Record<string, unknown> } | undefined;
            };
          }
        ).__map;
        if (!map) return false;
        try {
          return Boolean(map.isStyleLoaded?.() && map.getStyle?.()?.sources);
        } catch {
          return false;
        }
      }),
    )
    .toBe(true);
}

export async function getMapZoom(page: Page): Promise<number> {
  return page.evaluate(() => {
    const map = (window as unknown as { __map?: { getZoom(): number } }).__map;
    if (!map) throw new Error("window.__map missing");
    return map.getZoom();
  });
}

export async function getVisibleLayerIds(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const map = (
      window as unknown as {
        __map?: {
          isStyleLoaded?: () => boolean;
          getStyle():
            | { layers?: Array<{ id: string; layout?: { visibility?: string } }> }
            | undefined;
          getLayoutProperty(id: string, prop: string): unknown;
        };
      }
    ).__map;
    if (!map || !map.isStyleLoaded?.()) return [];
    const style = map.getStyle?.();
    if (!style?.layers) return [];
    const ids: string[] = [];
    for (const layer of style.layers) {
      let vis = layer.layout?.visibility;
      try {
        vis = (map.getLayoutProperty(layer.id, "visibility") as string) || vis;
      } catch {
        /* layer may lack layout */
      }
      if (vis !== "none") ids.push(layer.id);
    }
    return ids.sort();
  });
}

export async function getStyleSourceIds(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const map = (
      window as unknown as {
        __map?: {
          isStyleLoaded?: () => boolean;
          getStyle(): { sources?: Record<string, unknown> } | undefined;
        };
      }
    ).__map;
    if (!map || !map.isStyleLoaded?.()) return [];
    const style = map.getStyle?.();
    if (!style?.sources) return [];
    return Object.keys(style.sources);
  });
}

export function countMatches(text: string, re: RegExp): number {
  const flags = re.flags.includes("g") ? re.flags : `${re.flags}g`;
  const copy = new RegExp(re.source, flags);
  return (text.match(copy) || []).length;
}
