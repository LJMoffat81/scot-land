/**
 * CI-DEDUP-1b-r2 — Playwright fixtures for every e2e/ci spec.
 * Auto-applies exact-host stubs + strict console gate (assert on teardown).
 * csp-esri-1: test.use({ externalHostStub: false }).
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  test as base,
  expect,
  type BrowserContext,
  type Page,
  type Route,
} from "@playwright/test";
import {
  EXTERNAL_HOSTS,
  attachStrictConsoleGate,
  isExternalHost,
  registerStrictGate,
  type StrictConsoleGate,
} from "./_consoleGate";

/** 1×1 PNG — same bytes as CI_TINY_PNG in helpers. */
const CI_TINY_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

/** Empty-but-valid glyph protobuf (same as map-cards helper). */
const EMPTY_GLYPH_PBF = Buffer.from(
  "ChoKEU9wZW4gU2FucyBSZWd1bGFyEgUwLTI1NQ==",
  "base64",
);

export type ExternalHostStub = {
  /** Per-hostname fulfilled request counts. */
  hits: Record<string, number>;
};

function esriStyleBody(): string {
  return readFileSync(
    join(process.cwd(), "e2e", "fixtures", "esri-imagery-style.json"),
    "utf8",
  );
}

function ofmStyleBody(): string {
  return readFileSync(
    join(process.cwd(), "e2e", "fixtures", "ofm-style-min.json"),
    "utf8",
  );
}

/**
 * Route listed hosts only (hostname equality). Style / tiles / glyph-sprite / else 204.
 * No test-specific pathnames. Unlisted hosts are not stubbed.
 */
export async function stubExternalHosts(
  context: BrowserContext,
): Promise<ExternalHostStub> {
  const hits: Record<string, number> = Object.fromEntries(
    EXTERNAL_HOSTS.map((h) => [h, 0]),
  );
  const esriBody = esriStyleBody();
  const ofmBody = ofmStyleBody();

  await context.route(
    (url) => {
      try {
        return isExternalHost(new URL(url).hostname);
      } catch {
        return false;
      }
    },
    async (route: Route) => {
      const reqUrl = route.request().url();
      let hostname = "";
      let pathname = "";
      try {
        const u = new URL(reqUrl);
        hostname = u.hostname;
        pathname = u.pathname;
      } catch {
        await route.fulfill({ status: 204 });
        return;
      }
      if (!isExternalHost(hostname)) {
        await route.continue();
        return;
      }
      hits[hostname] = (hits[hostname] ?? 0) + 1;

      const lower = pathname.toLowerCase();

      // Vector tile source metadata (TileJSON) — not a tile byte range.
      if (/\/VectorTileServer\/?$/i.test(pathname) || /\/VectorTileServer$/i.test(pathname)) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            tiles: [
              `https://${hostname}${pathname.replace(/\/?$/, "")}/tile/{z}/{y}/{x}.pbf`,
            ],
            minzoom: 0,
            maxzoom: 22,
          }),
        });
        return;
      }

      // Raster / tile image bytes
      if (
        /\.(png|jpe?g|webp|gif)($|\?)/i.test(pathname) ||
        /\/tile\//i.test(pathname) ||
        /\/MapServer\/tile\//i.test(pathname) ||
        /\/\d+\/\d+\/\d+(?:\.pbf)?($|\?)/i.test(pathname)
      ) {
        // Vector .pbf tile ranges use the glyph protobuf; raster uses PNG.
        if (/\.pbf($|\?)/i.test(pathname) && !/\/fonts\//i.test(pathname)) {
          await route.fulfill({
            status: 200,
            contentType: "application/x-protobuf",
            body: EMPTY_GLYPH_PBF,
          });
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "image/png",
          body: CI_TINY_PNG,
        });
        return;
      }

      // Fonts / glyph ranges / vector .pbf
      if (/\/fonts\//i.test(pathname) || /\.pbf($|\?)/i.test(pathname)) {
        await route.fulfill({
          status: 200,
          contentType: "application/x-protobuf",
          body: EMPTY_GLYPH_PBF,
        });
        return;
      }

      // Sprite index / image
      if (/sprite/i.test(lower) && /\.json($|\?)/i.test(pathname)) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: "{}",
        });
        return;
      }
      if (/sprite/i.test(lower)) {
        await route.fulfill({
          status: 200,
          contentType: "image/png",
          body: CI_TINY_PNG,
        });
        return;
      }

      // Style JSON — OFM from ofm-style-min; Esri from pinned imagery fixture
      if (
        /\/styles\//i.test(pathname) ||
        /style\.json/i.test(pathname) ||
        hostname === "basemapstyles-api.arcgis.com"
      ) {
        const body =
          hostname === "tiles.openfreemap.org" ? ofmBody : esriBody;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body,
        });
        return;
      }

      // Anything else on listed hosts → 204
      await route.fulfill({ status: 204 });
    },
  );

  return { hits };
}

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

const QUIET_PLACE = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "City Centre",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre", code: "S02002645" },
  dwellings: 410,
  agr_rows: [],
  constraints: [],
  layers: [],
  links: [],
};

/**
 * Quiet same-origin API defaults so Next rewrites do not 503 without FastAPI.
 * Specific paths only — never a global backend catch-all (P2). Specs override via LIFO.
 */
async function stubCiOriginQuiet(page: Page): Promise<void> {
  // Favicons / apple icons — same-origin 404s must not fail the strict gate.
  await page.route("**/favicon.ico**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  await page.route("**/apple-touch-icon**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
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
  // Local browser apiJson prefixes /backend → /backend/api/*.json
  await page.route("**/backend/api/**", async (route) => {
    const url = route.request().url();
    const emptyList = JSON.stringify({ layers: [], rows: [], checks: [] });
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
      body: emptyList,
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
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/backend/layers/add/tiles-manifest**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ version: 1, sources: [] }),
    });
  });
  await page.route("**/platform/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ version: 2, layers: [] }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(QUIET_PLACE),
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
}

type CiDedupFixtures = {
  /**
   * When false, skip EXTERNAL_HOSTS routing (csp-esri-1 keeps its own arcgis route).
   * Default true. Only csp-esri-1 may set false.
   */
  externalHostStub: boolean;
  /** Shared stub handle (hit counters) when stubbing is enabled. */
  hostStub: ExternalHostStub | null;
  /** Strict gate attached to the page (also via attachConsoleGate WeakMap). */
  gate: StrictConsoleGate;
  /** Auto fixture: stub + gate before body; assertClean on teardown. */
  _ciDedup1bAuto: void;
};

export const test = base.extend<CiDedupFixtures>({
  externalHostStub: [true, { option: true }],

  hostStub: async ({ context, externalHostStub }, use) => {
    if (!externalHostStub) {
      await use(null);
      return;
    }
    const handle = await stubExternalHosts(context);
    await use(handle);
  },

  gate: async ({ page }, use) => {
    await stubCiOriginQuiet(page);
    const gate = attachStrictConsoleGate(page);
    registerStrictGate(page, gate);
    await use(gate);
  },

  _ciDedup1bAuto: [
    async ({ hostStub, gate }, use) => {
      void hostStub;
      await use();
      gate.assertClean();
    },
    { auto: true },
  ],
});

export { expect, EXTERNAL_HOSTS };
export type { StrictConsoleGate };
