/**
 * Shared stubs and probes for MAP-CARDS-REDESIGN e2e under e2e/ci/.
 * Not a Playwright spec — imported by *.spec.ts only.
 */
import { expect, test, type Page, type Route } from "@playwright/test";
import {
  attachStrictConsoleGate,
  getStrictGateForPage,
  registerStrictGate,
  type StrictConsoleGate,
} from "./_consoleGate";

export const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

export const EMPTY_FC = { type: "FeatureCollection", features: [] };

/**
 * Glyphs protobuf with one font stack and no glyphs.
 * MapLibre accepts it and draws nothing for that range.
 */
export const EMPTY_GLYPH_PBF = Buffer.from(
  "ChoKEU9wZW4gU2FucyBSZWd1bGFyEgUwLTI1NQ==",
  "base64",
);

export async function fulfillEmptyGlyph(route: Route) {
  await route.fulfill({
    status: 200,
    contentType: "application/x-protobuf",
    body: EMPTY_GLYPH_PBF,
  });
}

/** Answer glyph ranges here so CI never fetches tiles.openfreemap.org fonts. */
export async function stubOpenFreeMapFonts(page: Page) {
  await page.route("**/tiles.openfreemap.org/fonts/**", async (route) => {
    await fulfillEmptyGlyph(route);
  });
}

/**
 * File-level hook. Call at the top of each CI spec so the route is registered
 * on that file. A shared module body would attach only to the first importer.
 */
export function registerOpenFreeMapFontStub() {
  test.beforeEach(async ({ page }) => {
    await stubOpenFreeMapFonts(page);
  });
}

/**
 * CI-STABILISE-1 — empty FeatureCollection for the default-view councils fetch.
 * Call after any backend catch-all route so Playwright LIFO wins.
 */
export async function stubLayersCouncilsQuiet(
  page: Page,
  body: typeof EMPTY_FC = EMPTY_FC,
) {
  await page.route("**/backend/layers/councils**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

/** 1×1 PNG — stub raster tiles so MapLibre never depends on live CDN in CI. */
export const CI_TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

/**
 * Stub raster tile bytes only (OpenFreeMap z/x/y, parcel/context tiles, imagery).
 * Style / sprite / glyph JSON stay on the network or other stubs.
 */
export async function stubCiTileDataQuiet(page: Page) {
  await page.route("**/tiles.openfreemap.org/**", async (route) => {
    const url = route.request().url();
    if (/\/fonts\//i.test(url)) {
      await fulfillEmptyGlyph(route);
      return;
    }
    // Raster tiles only — never style.json / sprite.json.
    if (/\.png(?:\?|$)/i.test(url) || /\/\d+\/\d+\/\d+(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "image/png",
        body: CI_TINY_PNG,
      });
      return;
    }
    await route.continue();
  });
  await page.route("**/api/parcels/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  await page.route("**/api/context/**/tiles/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  await page.route("**/ArcGIS/rest/services/World_Imagery/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  // ARCH-2b: ScotlandMap always fetches the tiles manifest. Empty tilesets
  // keeps catch-all **/backend/** → 404 stubs from poisoning the console gate.
  await stubArch2bTilesQuiet(page);
}

/** Quiet /v1/tiles when a spec does not exercise ARCH-2b layers. */
export async function stubArch2bTilesQuiet(page: Page) {
  // Single handler (LIFO-safe). Specs that need real tiles register more
  // specific routes afterwards so they win.
  await page.route("**/backend/v1/tiles/**", async (route) => {
    const url = route.request().url();
    if (/\/manifest\.json(?:\?|$)/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ schema: 1, tilesets: {} }),
      });
      return;
    }
    if (/\/values\//i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          layer: "dz2022",
          version: "2026-10-22.d28ecc72",
          measure: "pop_density",
          values: {},
        }),
      });
      return;
    }
    // Empty MVT body — MapLibre ignores; no console 404.
    await route.fulfill({
      status: 200,
      contentType: "application/vnd.mapbox-vector-tile",
      body: Buffer.alloc(0),
    });
  });
}

export const LIVE_LAYER_IDS = [
  "1",
  "access_services",
  "grid3",
  "3",
  "4",
  "9",
  "designations",
  "crofting",
  "councils",
  "data_zones",
] as const;

/** Switches with no geometry: absent from the panel (roadmap). */
export const HIDDEN_LAYER_IDS = [
  "flood",
  "deprivation",
  "conservation",
  "listed",
  "stops",
  "8",
  "vdl",
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
      gloss: "The yearly rental value of the land under homes, without the buildings.",
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
      gloss: "Rent from natural resources such as wind, water, minerals and fish farm sites.",
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
      gloss: "What nature gives us for free, such as peat holding carbon. Estimate only.",
    },
  ],
  constraints: [],
  layers: [],
  links: [],
};

/** Strict gate attached by the `./_fixtures` auto fixture (WeakMap lookup). */
export type ConsoleGate = StrictConsoleGate;

/**
 * Return the page's already-attached strict gate.
 * CI specs must import `test` from `./_fixtures` so the auto fixture attaches it.
 *
 * Exception: e2e/build-key (outside 1b-r2 allowed files) still imports this
 * helper under raw @playwright/test — attach a strict gate for that caller only.
 * E10 keeps throwing for a bare newPage() with no fixtures.
 */
export function attachConsoleGate(page: Page): ConsoleGate {
  const existing = getStrictGateForPage(page);
  if (existing) return existing;

  const stack = new Error().stack ?? "";
  if (/e2e[/\\]build-key[/\\]|esri-key-build\.spec/.test(stack)) {
    const gate = attachStrictConsoleGate(page);
    registerStrictGate(page, gate);
    return gate;
  }

  throw new Error("CONSOLE_GATE: no strict gate attached to this page");
}

/** Delegate to the strict gate (CI-DEDUP-1b-r2). */
export function assertConsoleClean(gate: ConsoleGate) {
  gate.assertClean();
}

export type StubOpts = {
  place?: Record<string, unknown>;
  gbpLive?: boolean;
  /** Delayed platform/place responses keyed by lat (for race tests). */
  placeDelayMs?: number;
  placeByLat?: Record<string, Record<string, unknown>>;
  /**
   * Improvement Service layer ids whose extract is present.
   * Default keeps vacant land (existing map tests). Other IS rows stay absent.
   */
  spatialHubLayerIds?: readonly string[];
  /** sepa_flood_dz has rows — the flood switch may show. */
  floodDzLoaded?: boolean;
};

/**
 * Quiet backend + gbp-live + catalog so CI has no live FastAPI.
 * Routes registered last win for overlapping patterns in Playwright LIFO.
 */
export async function stubMapCardsBackend(page: Page, opts: StubOpts = {}) {
  const place = opts.place ?? PLACE_FIXTURE;
  const gbpLive = opts.gbpLive ?? false;
  const delayMs = opts.placeDelayMs ?? 0;
  const spatialHubLayerIds = opts.spatialHubLayerIds ?? ["vdl"];

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

  // Specific backend stubs only — no global **/backend/** (CI-DEDUP-1b-r2 P2).
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  // Local browser apiJson prefixes /backend → /backend/api/*.json (ledger, catalog, …).
  await page.route("**/backend/api/**", async (route) => {
    const url = route.request().url();
    if (/ledger\.json/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          rows: [],
          checks: [],
          excluded: [],
          benchmarks: [],
        }),
      });
      return;
    }
    if (/catalog\.json/i.test(url)) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ layers: [] }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [], rows: [], checks: [] }),
    });
  });
  await page.route("**/api/ledger.json**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        rows: [],
        checks: [],
        excluded: [],
        benchmarks: [],
      }),
    });
  });
  // Broad geo stubs first — LIFO: catalog / manifest / DZ registered below win.
  for (const pattern of [
    "**/backend/layers/**",
    "**/backend/boundaries/**",
    "**/backend/w3w-grid**",
    "**/backend/parcels**",
  ] as const) {
    await page.route(pattern, async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
    });
  }
  await page.route("**/backend/layers/add/tiles-manifest**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 1,
        sources: spatialHubLayerIds.map((id) => ({
          layer_id: id,
          display_id: id,
        })),
      }),
    });
  });
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        version: 2,
        layers: [],
        flood_dz_loaded: opts.floodDzLoaded === true,
      }),
    });
  });
  await page.route("**/backend/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        code: "S01014567",
        name: "City Centre South",
        vintage: 2022,
      }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    const url = route.request().url();
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
  });
  await page.route("**/backend/place**", async (route) => {
    if (/platform\/place/i.test(route.request().url())) {
      await route.continue();
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
    });
  });

  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  // Same idea as the raster tile stub: answer glyph ranges here so CI never
  // fetches tiles.openfreemap.org fonts. The live map still requests that host.
  await stubOpenFreeMapFonts(page);
  await stubArch2bTilesQuiet(page);
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

/** Dummy Esri key for Aerial e2e — assembled at runtime, never committed. */
export const DUMMY_ESRI_KEY = "TEST" + "KEY" + "x".repeat(8);

/**
 * Inject an Esri basemap key for E2E_HOOKS builds (add before first navigation).
 * Pass `null` or `""` to force the no-key path; `"   "` for whitespace-as-unset.
 */
export async function injectEsriBasemapKey(
  page: Page,
  key: string | null = DUMMY_ESRI_KEY,
) {
  await page.addInitScript((value) => {
    (
      window as unknown as { __E2E_ESRI_BASEMAP_API_KEY__?: string | null }
    ).__E2E_ESRI_BASEMAP_API_KEY__ = value;
  }, key);
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
