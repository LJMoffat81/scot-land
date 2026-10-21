/**
 * FRONTEND-BATCH-3 r4 — SHOWTHRU (0.55) + SW-082 + SW-083 + Idea 80 + T-C4.
 * Viewports 1280×800 and 390×844. Console errors fail the test.
 */
import { expect, test } from "./_fixtures";
import { type Page, type Request, type Route } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import {
  CHOROPLETH_FILL_OPACITY,
  NODATA_HATCH_OPACITY,
  metricById,
} from "../../lib/mapColourRamps";
import {
  looksLikeFullPostcode,
  POSTCODES_ONLY,
} from "../../lib/api";
import {
  SUGGEST_LAYER_COPY,
  SUGGEST_LAYER_HREF,
} from "../../components/SuggestLayerSection";
import {
  assertConsoleClean,
  attachConsoleGate,
  CI_TINY_PNG,
  DUMMY_ESRI_KEY,
  EMPTY_GLYPH_PBF,
  injectEsriBasemapKey,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

const FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

const STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

const ALLOWED_ORIGINS = [
  "https://basemapstyles-api.arcgis.com",
  "https://ibasemaps-api.arcgis.com",
  "https://basemaps-api.arcgis.com",
  "https://cdn.arcgis.com",
] as const;

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const;

const EMAIL_RE = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/;
const BANNED_BODY = /neighbou?rhood|neighborhood/i;
const FORM_ID = "pwpublic";
/** Must match ContactForm LAYER_SUGGESTION_PREFIX (avoid importing the client module). */
const LAYER_SUGGESTION_PREFIX = "Layer suggestion: ";

type EsriStyle = {
  sprite: string;
  glyphs: string;
  sources: Record<
    string,
    {
      tiles?: string[];
      url?: string;
      attribution?: string;
      type?: string;
    }
  >;
  layers?: Array<Record<string, unknown>>;
};

type MapProbe = {
  getLayer(id: string): unknown;
  getLayoutProperty(id: string, prop: string): unknown;
  getPaintProperty(id: string, prop: string): unknown;
  getStyle(): {
    layers?: Array<{
      id: string;
      type?: string;
      paint?: Record<string, unknown>;
      layout?: Record<string, unknown>;
    }>;
  };
  isStyleLoaded?: () => boolean;
  jumpTo?(opts: { zoom: number; center?: [number, number] }): void;
  once?(event: string, cb: () => void): void;
};

function loadFixture(): EsriStyle {
  if (!existsSync(FIXTURE_PATH)) {
    throw new Error("fixture missing: esri-imagery-style.json");
  }
  return JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as EsriStyle;
}

async function routeEsriFixture(page: Page, style: EsriStyle) {
  await page.route(`${STYLE_URL}**`, async (route) => {
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
      body: CI_TINY_PNG,
    });
  });
  await page.route("**/basemaps-api.arcgis.com/**/*.pbf**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/x-protobuf",
      body: EMPTY_GLYPH_PBF,
    });
  });
  await page.route("**/ibasemaps-api.arcgis.com/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "image/png",
      body: CI_TINY_PNG,
    });
  });
  await page.route(
    "**/basemaps-api.arcgis.com/**/VectorTileServer**",
    async (route) => {
      const url = route.request().url();
      if (/\.pbf/i.test(url)) {
        await route.fulfill({
          status: 200,
          contentType: "application/x-protobuf",
          body: EMPTY_GLYPH_PBF,
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          tiles: [
            "https://basemaps-api.arcgis.com/arcgis/rest/services/World_Basemap_v2/VectorTileServer/tile/{z}/{y}/{x}.pbf",
          ],
          minzoom: 0,
          maxzoom: 22,
        }),
      });
    },
  );
}

const COUNCIL_FC = {
  type: "FeatureCollection",
  features: [
    {
      type: "Feature",
      properties: {
        name: "Glasgow City",
        population_density_per_km2: 3520,
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-4.32, 55.82],
            [-4.18, 55.82],
            [-4.18, 55.9],
            [-4.32, 55.9],
            [-4.32, 55.82],
          ],
        ],
      },
    },
    {
      type: "Feature",
      properties: {
        name: "Highland",
        // Missing density → no-data hatch path stays live for opacity asserts.
      },
      geometry: {
        type: "Polygon",
        coordinates: [
          [
            [-5.2, 57.0],
            [-4.6, 57.0],
            [-4.6, 57.5],
            [-5.2, 57.5],
            [-5.2, 57.0],
          ],
        ],
      },
    },
  ],
} as const;

const BOUNDARIES_FC = {
  type: "FeatureCollection",
  features: COUNCIL_FC.features.map((f) => ({
    type: "Feature" as const,
    properties: { name: f.properties.name },
    geometry: f.geometry,
  })),
};

async function stubCouncilsOk(page: Page) {
  await page.route("**/layers/councils**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(COUNCIL_FC),
    });
  });
  await page.route("**/boundaries/councils**", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(BOUNDARIES_FC),
    });
  });
}

async function getMap(page: Page): Promise<void> {
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const map = (window as unknown as { __map?: MapProbe }).__map;
          return Boolean(map && map.isStyleLoaded?.());
        }),
      { timeout: 60_000 },
    )
    .toBe(true);
}

async function jumpToZoom(page: Page, zoom: number): Promise<void> {
  await page.evaluate(async (z) => {
    const map = (window as unknown as { __map?: MapProbe }).__map;
    if (!map?.jumpTo) throw new Error("window.__map missing");
    await new Promise<void>((resolve) => {
      map.once?.("idle", () => resolve());
      map.jumpTo!({ zoom: z, center: [-4.2, 56.8] });
    });
  }, zoom);
}

async function paintOpacity(page: Page, layerId: string): Promise<unknown> {
  return page.evaluate((id) => {
    const map = (window as unknown as { __map?: MapProbe }).__map;
    if (!map) throw new Error("window.__map missing");
    return map.getPaintProperty(id, "fill-opacity");
  }, layerId);
}

const COUNCIL_LAYER_IDS = [
  "council-fill",
  "council-nodata-hatch",
  "council-line",
] as const;

/** T-S2b: council layers sit below the first symbol (default/Simple basemap). */
async function assertCouncilBelowSymbols(page: Page) {
  const order = await page.evaluate((councilIds) => {
    const map = (window as unknown as { __map?: MapProbe }).__map;
    if (!map) throw new Error("window.__map missing");
    const layers = map.getStyle().layers ?? [];
    const ids = layers.map((l) => l.id);
    const types = layers.map((l) => l.type ?? "");
    const firstSym = types.findIndex((t) => t === "symbol");
    const council: Record<string, number> = {};
    for (const id of councilIds) council[id] = ids.indexOf(id);
    return { firstSym, council };
  }, [...COUNCIL_LAYER_IDS]);
  expect(order.firstSym, "first symbol layer").toBeGreaterThanOrEqual(0);
  for (const id of COUNCIL_LAYER_IDS) {
    expect(order.council[id], id).toBeGreaterThanOrEqual(0);
    expect(order.council[id], `${id} below first symbol`).toBeLessThan(
      order.firstSym,
    );
  }
}

/**
 * T-S2a / O2-AERIAL-1: real pinned Esri fixture has no symbols; every council
 * layer sits above `esri-imagery`.
 */
async function assertCouncilAboveEsriImagery(page: Page) {
  const order = await page.evaluate((councilIds) => {
    const map = (window as unknown as { __map?: MapProbe }).__map;
    if (!map) throw new Error("window.__map missing");
    const layers = map.getStyle().layers ?? [];
    const ids = layers.map((l) => l.id);
    const types = layers.map((l) => l.type ?? "");
    const imagery = ids.indexOf("esri-imagery");
    const symbolCount = types.filter((t) => t === "symbol").length;
    const council: Record<string, number> = {};
    for (const id of councilIds) council[id] = ids.indexOf(id);
    return { imagery, symbolCount, council };
  }, [...COUNCIL_LAYER_IDS]);
  expect(order.symbolCount, "Aerial fixture has no symbol layers").toBe(0);
  expect(order.imagery, "esri-imagery present").toBeGreaterThanOrEqual(0);
  for (const id of COUNCIL_LAYER_IDS) {
    expect(order.council[id], id).toBeGreaterThanOrEqual(0);
    expect(order.council[id], `${id} above esri-imagery`).toBeGreaterThan(
      order.imagery,
    );
  }
}

async function toggleBasemap(page: Page) {
  const toggle = page.getByTestId("basemap-switcher");
  await expect(toggle).toBeVisible();
  const before = await toggle.getAttribute("aria-pressed");
  await toggle.click();
  await expect(toggle).toHaveAttribute(
    "aria-pressed",
    before === "true" ? "false" : "true",
  );
  await getMap(page);
  // Remount uses key={mapStyle}; wait until council layers exist again.
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const map = (window as unknown as { __map?: MapProbe }).__map;
          if (!map) return false;
          try {
            return Boolean(map.getLayer("council-fill"));
          } catch {
            return false;
          }
        }),
      { timeout: 60_000 },
    )
    .toBe(true);
}

async function openShowthruMap(page: Page) {
  const style = loadFixture();
  await injectEsriBasemapKey(page);
  await routeEsriFixture(page, style);
  await stubMapCardsBackend(page, { gbpLive: false });
  await stubCouncilsOk(page);
  await openMap(page, "/");
  await getMap(page);
  await jumpToZoom(page, 6);
  await expect
    .poll(async () => paintOpacity(page, "council-fill"), { timeout: 45_000 })
    .toBe(CHOROPLETH_FILL_OPACITY);
}

async function assertNoMailtoOrEmail(page: Page) {
  await expect(page.locator('a[href^="mailto:"]')).toHaveCount(0);
  const body = await page.locator("body").innerText();
  expect(body).not.toMatch(EMAIL_RE);
}

async function enableContactFormE2e(page: Page) {
  await page.addInitScript(
    ({ enabled, formId }) => {
      (
        window as Window & {
          __E2E_CONTACT_FORM_ENABLED__?: boolean;
          __E2E_CONTACT_FORM_ID__?: string;
        }
      ).__E2E_CONTACT_FORM_ENABLED__ = enabled;
      (
        window as Window & { __E2E_CONTACT_FORM_ID__?: string }
      ).__E2E_CONTACT_FORM_ID__ = formId;
    },
    { enabled: true, formId: FORM_ID },
  );
}

for (const viewport of VIEWPORTS) {
  test.describe(`FRONTEND-BATCH-3 ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport });

    test("T-S1 opacity pinned at 0.55 (Simple and after Simple→Aerial→Simple)", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      expect(CHOROPLETH_FILL_OPACITY).toBe(0.55);
      expect(NODATA_HATCH_OPACITY).toBe(0.55);

      await openShowthruMap(page);
      expect(await paintOpacity(page, "council-fill")).toBe(0.55);
      expect(await paintOpacity(page, "council-nodata-hatch")).toBe(0.55);

      await toggleBasemap(page); // → Aerial
      await toggleBasemap(page); // → Simple
      expect(await paintOpacity(page, "council-fill")).toBe(0.55);
      expect(await paintOpacity(page, "council-nodata-hatch")).toBe(0.55);
      assertConsoleClean(gate);
    });

    test("T-S2b default basemap: council layers below first symbol", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await openShowthruMap(page);
      await assertCouncilBelowSymbols(page);
      assertConsoleClean(gate);
    });

    test("T-S2a Aerial: council layers above esri-imagery (no fixture symbols)", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      const fixture = loadFixture();
      const fixtureHasSymbol = (fixture.layers ?? []).some(
        (l) => (l as { type?: string }).type === "symbol",
      );
      expect(fixtureHasSymbol, "pinned Esri fixture must have no symbols").toBe(
        false,
      );

      await openShowthruMap(page);
      await toggleBasemap(page); // → Aerial
      await assertCouncilAboveEsriImagery(page);
      assertConsoleClean(gate);
    });

    test("T-S3 legend alpha matches fill alpha", async ({ page }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await openShowthruMap(page);

      const fillOpacity = await paintOpacity(page, "council-fill");
      expect(fillOpacity).toBe(0.55);

      const colourSwatches = page.locator(
        ".map-range-legend-list > li:not([data-testid='map-range-legend-no-data']) .map-range-legend-swatch",
      );
      await expect(colourSwatches.first()).toBeVisible({ timeout: 30_000 });
      const count = await colourSwatches.count();
      expect(count).toBeGreaterThan(0);

      const pop = metricById("pop_density")!;
      const stopColors = pop.stops.map(([, c]) => c);

      for (let i = 0; i < count; i += 1) {
        const swatch = colourSwatches.nth(i);
        await expect(swatch).toHaveAttribute(
          "data-swatch-alpha",
          String(fillOpacity),
        );
        await expect(swatch).toHaveAttribute("data-swatch-alpha", "0.55");
        const opacity = await swatch.evaluate(
          (el) => getComputedStyle(el).opacity,
        );
        expect(opacity).toBe("0.55");
        const color = await swatch.getAttribute("data-swatch-color");
        expect(stopColors).toContain(color);
      }

      const nodata = page.locator(".map-range-legend-swatch-nodata");
      await expect(nodata).toBeVisible();
      const nodataOpacity = await nodata.evaluate(
        (el) => getComputedStyle(el).opacity,
      );
      expect(nodataOpacity).toBe("0.55");
      assertConsoleClean(gate);
    });

    test("T-S4 Positron shading + Esri fixture layers unchanged on Aerial", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      const styleByUrl = new Map<
        string,
        { layers?: Array<Record<string, unknown>> }
      >();
      const esriFixture = loadFixture();
      page.on("response", async (response) => {
        const url = response.url();
        if (!/tiles\.openfreemap\.org\/styles\/positron/i.test(url)) return;
        if (!response.ok()) return;
        try {
          const json = (await response.json()) as {
            layers?: Array<Record<string, unknown>>;
          };
          styleByUrl.set(url, json);
        } catch {
          /* ignore */
        }
      });

      await openShowthruMap(page);

      const entry = [...styleByUrl.entries()].find(([u]) =>
        /positron/i.test(u),
      );
      expect(entry, "captured Positron style").toBeTruthy();
      const styleLayers = entry![1].layers ?? [];
      const targetIds = styleLayers
        .map((layer) => String(layer.id ?? ""))
        .filter((id) => /residential|landuse|building/i.test(id));
      expect(targetIds.length).toBeGreaterThan(0);

      const live = await page.evaluate((ids) => {
        const map = (window as unknown as { __map?: MapProbe }).__map;
        if (!map) throw new Error("window.__map missing");
        return ids.map((id) => {
          let fillColor: unknown = null;
          let fillOpacity: unknown = null;
          let visibility: unknown = "visible";
          try {
            fillColor = map.getPaintProperty(id, "fill-color");
          } catch {
            /* optional */
          }
          try {
            fillOpacity = map.getPaintProperty(id, "fill-opacity");
          } catch {
            /* optional */
          }
          try {
            visibility = map.getLayoutProperty(id, "visibility");
          } catch {
            visibility = "visible";
          }
          return { id, fillColor, fillOpacity, visibility };
        });
      }, targetIds);

      for (const row of live) {
        const styleLayer = styleLayers.find((l) => l.id === row.id) as
          | { paint?: Record<string, unknown>; layout?: Record<string, unknown> }
          | undefined;
        expect(styleLayer, row.id).toBeTruthy();
        const paint = styleLayer!.paint ?? {};
        if ("fill-color" in paint) {
          expect(row.fillColor).toEqual(paint["fill-color"]);
        }
        if ("fill-opacity" in paint) {
          expect(row.fillOpacity).toEqual(paint["fill-opacity"]);
        }
        expect(row.visibility).not.toBe("none");
      }

      // Basemap layer id order (excluding app-added) equals Positron JSON order.
      const liveOrder = await page.evaluate((fixtureIds: string[]) => {
        const map = (window as unknown as { __map?: MapProbe }).__map;
        if (!map) throw new Error("window.__map missing");
        const ids = (map.getStyle().layers ?? []).map((l) => l.id);
        return ids.filter((id) => fixtureIds.includes(id));
      }, styleLayers.map((l) => String(l.id ?? "")));
      expect(liveOrder).toEqual(
        styleLayers.map((l) => String(l.id ?? "")).filter(Boolean),
      );

      await toggleBasemap(page); // Aerial
      const fixtureLayerIds = (esriFixture.layers ?? []).map((l) =>
        String(l.id ?? ""),
      );
      expect(fixtureLayerIds.length).toBeGreaterThan(0);

      const aerialCheck = await page.evaluate((fixtureLayers) => {
        const map = (window as unknown as { __map?: MapProbe }).__map;
        if (!map) throw new Error("window.__map missing");
        const liveLayers = map.getStyle().layers ?? [];
        const liveById = new Map(liveLayers.map((l) => [l.id, l]));
        const appPrefix = /^(council-|sl-|map-|grid3|parcel|place-|hover|sel)/i;
        const liveFixtureOrder = liveLayers
          .map((l) => l.id)
          .filter((id) => fixtureLayers.some((f) => f.id === id));
        const expectedOrder = fixtureLayers.map((f) => f.id);
        const paintOk = fixtureLayers.every((f) => {
          const live = liveById.get(f.id);
          if (!live) return false;
          const want = (f.paint ?? {}) as Record<string, unknown>;
          for (const [k, v] of Object.entries(want)) {
            try {
              if (JSON.stringify(map.getPaintProperty(f.id, k)) !== JSON.stringify(v)) {
                return false;
              }
            } catch {
              return false;
            }
          }
          void appPrefix;
          return true;
        });
        return {
          paintOk,
          liveFixtureOrder,
          expectedOrder,
        };
      }, (esriFixture.layers ?? []) as Array<{
        id: string;
        paint?: Record<string, unknown>;
      }>);

      expect(aerialCheck.paintOk).toBe(true);
      expect(aerialCheck.liveFixtureOrder).toEqual(aerialCheck.expectedOrder);
      await assertCouncilAboveEsriImagery(page);

      // O2-AERIAL-1 / T-S4: Aerial → default → Aerial keeps order; no getLayer errors.
      await toggleBasemap(page); // → Simple
      await assertCouncilBelowSymbols(page);
      await toggleBasemap(page); // → Aerial
      await assertCouncilAboveEsriImagery(page);
      assertConsoleClean(gate);
    });

    test("T-S5 no £ / contact / banned words on default view", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      await getMap(page);
      await expect(page.locator("body")).not.toContainText("£");
      const body = await page.locator("body").innerText();
      expect(body).not.toMatch(BANNED_BODY);

      await page.goto("/about");
      await expect(page.getByTestId("contact-form")).toHaveCount(0);
      assertConsoleClean(gate);
    });

    test("T-C4 production CSP: Aerial at real Esri origins, zero violations", async ({
      page,
    }) => {
      test.setTimeout(240_000);
      expect(DUMMY_ESRI_KEY.length).toBeGreaterThan(8);
      const style = loadFixture();
      await routeEsriFixture(page, style);

      const cspViolations: { blockedURI: string; violatedDirective: string }[] =
        [];
      const consoleMessages: string[] = [];
      const arcgisRequests: string[] = [];

      await page.addInitScript(() => {
        const w = window as unknown as {
          __cspViolations: { blockedURI: string; violatedDirective: string }[];
        };
        w.__cspViolations = [];
        document.addEventListener("securitypolicyviolation", (ev) => {
          w.__cspViolations.push({
            blockedURI: ev.blockedURI,
            violatedDirective: ev.violatedDirective,
          });
        });
      });
      page.on("console", (msg) => {
        consoleMessages.push(msg.text());
      });
      page.on("request", (req: Request) => {
        const u = req.url();
        if (/arcgis\.com/i.test(u)) arcgisRequests.push(u);
      });

      await injectEsriBasemapKey(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      await waitForMap(page);

      // Simple → Aerial → Simple → Aerial
      await toggleBasemap(page);
      await toggleBasemap(page);
      await toggleBasemap(page);

      const violations = await page.evaluate(() => {
        return (
          window as unknown as {
            __cspViolations: {
              blockedURI: string;
              violatedDirective: string;
            }[];
          }
        ).__cspViolations;
      });
      cspViolations.push(...violations);
      expect(cspViolations, JSON.stringify(cspViolations)).toEqual([]);
      expect(
        consoleMessages.filter((line) => /Refused to/i.test(line)),
      ).toEqual([]);

      const hosts = {
        style: arcgisRequests.filter((u) =>
          u.startsWith("https://basemapstyles-api.arcgis.com"),
        ),
        iba: arcgisRequests.filter((u) =>
          u.startsWith("https://ibasemaps-api.arcgis.com"),
        ),
        base: arcgisRequests.filter((u) =>
          u.startsWith("https://basemaps-api.arcgis.com"),
        ),
        cdn: arcgisRequests.filter((u) =>
          u.startsWith("https://cdn.arcgis.com"),
        ),
      };
      expect(hosts.style.length).toBeGreaterThanOrEqual(1);
      expect(hosts.iba.length).toBeGreaterThanOrEqual(1);
      expect(hosts.base.length).toBeGreaterThanOrEqual(1);
      expect(hosts.cdn.length).toBeGreaterThanOrEqual(1);

      for (const u of arcgisRequests) {
        const origin = new URL(u).origin;
        expect(
          ALLOWED_ORIGINS.includes(origin as (typeof ALLOWED_ORIGINS)[number]),
          `disallowed: ${u}`,
        ).toBe(true);
        expect(u.startsWith("http://localhost"), u).toBe(false);
        expect(u.startsWith("http://127.0.0.1"), u).toBe(false);
      }
    });

    test("T-R1 flag off: suggest section absent; no mailto/@", async ({
      page,
    }) => {
      test.setTimeout(60_000);
      await page.goto("/roadmap");
      await expect(page.locator("#suggest-a-layer")).toHaveCount(0);
      await expect(page.getByText("Suggest a layer")).toHaveCount(0);
      await expect(page.getByText(SUGGEST_LAYER_COPY)).toHaveCount(0);
      await assertNoMailtoOrEmail(page);

      await page.goto("/about");
      await assertNoMailtoOrEmail(page);
    });

    test("T-R2 flag on: Suggest a layer route pre-fills contact, no submit", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const posts: string[] = [];
      await enableContactFormE2e(page);
      await page.route("**/formspree.io/f/**", async (route) => {
        posts.push(route.request().postData() ?? "");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true }),
        });
      });

      await page.goto("/roadmap");
      await expect(page.locator("#suggest-a-layer")).toHaveCount(1);
      const link = page.getByRole("link", {
        name: "Suggest a layer",
        exact: true,
      });
      await expect(link).toHaveCount(1);
      await expect(link).toHaveAttribute("href", SUGGEST_LAYER_HREF);

      // Order: Suggest heading before Coming to the map.
      const order = await page.evaluate(() => {
        const headings = [...document.querySelectorAll("h2")].map((el) =>
          (el.textContent || "").trim(),
        );
        return {
          suggest: headings.indexOf("Suggest a layer"),
          coming: headings.indexOf("Coming to the map"),
        };
      });
      expect(order.suggest).toBeGreaterThanOrEqual(0);
      expect(order.coming).toBeGreaterThan(order.suggest);

      await link.click();
      await expect(page).toHaveURL(/\/about\?topic=layer#contact/);
      const form = page.getByTestId("contact-form");
      await expect(form).toBeVisible({ timeout: 30_000 });
      await expect(page.locator("#contact")).toBeVisible();
      const message = form.locator('textarea[name="message"]');
      await expect(message).toHaveValue(LAYER_SUGGESTION_PREFIX);
      expect(posts).toEqual([]);
      await assertNoMailtoOrEmail(page);
    });

    test("T-Q1 exactly one status visible per roadmap row", async ({
      page,
    }) => {
      test.setTimeout(60_000);
      await page.goto("/roadmap");

      for (const sectionId of ["#map-layers", "#further-ahead"] as const) {
        const rows = page.locator(`${sectionId} .roadmap-layer-list > li`);
        const n = await rows.count();
        expect(n).toBeGreaterThan(0);
        for (let i = 0; i < n; i += 1) {
          const row = rows.nth(i);
          const full = row.locator(".roadmap-waiting-status-full");
          const short = row.locator(".roadmap-waiting-status-short");
          const fullVisible = await full.isVisible().catch(() => false);
          const shortVisible =
            (await short.count()) > 0
              ? await short.isVisible().catch(() => false)
              : false;
          const visibleCount = Number(fullVisible) + Number(shortVisible);
          expect(visibleCount, `row ${i} in ${sectionId}`).toBe(1);

          const status = fullVisible ? full : short;
          const blurb = row.locator(".roadmap-layer-blurb");
          if ((await blurb.count()) > 0 && (await blurb.isVisible())) {
            const statusBox = await status.boundingBox();
            const blurbBox = await blurb.boundingBox();
            expect(statusBox && blurbBox).toBeTruthy();
            expect(statusBox!.y).toBeGreaterThanOrEqual(
              blurbBox!.y + blurbBox!.height - 1,
            );
          }

          const expectedFull = ((await full.textContent()) || "").trim();
          const expectedShort =
            (await short.count()) > 0
              ? ((await short.textContent()) || "").trim()
              : "";
          const visibleText = ((await status.textContent()) || "").trim();
          if (viewport.width <= 600 && expectedShort) {
            expect(visibleText).toBe(expectedShort);
          } else {
            expect(visibleText).toBe(expectedFull);
          }
        }
      }
    });

    for (const value of ["G63 0AA", "G630AA", "g63 0aa", "  G63  0AA "] as const) {
      test(`T-P1 accepts postcode ${JSON.stringify(value)}`, async ({
        page,
      }) => {
        test.setTimeout(90_000);
        expect(looksLikeFullPostcode(value)).toBe(true);
        const trimmed = value.trim();
        const gate = attachConsoleGate(page);
        let geocodeCount = 0;
        let sentQ = "";
        await stubMapCardsBackend(page, { gbpLive: false });
        // Force agr=false so search uses /geocode/postcode (not /place lookup).
        await page.route("**/layers/catalog**", async (route) => {
          await route.fulfill({ status: 404, body: "absent" });
        });
        await stubCouncilsOk(page);
        await page.route("**/geocode/postcode**", async (route) => {
          geocodeCount += 1;
          const url = new URL(route.request().url());
          sentQ = url.searchParams.get("q") ?? "";
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              postcode: "G63 0AA",
              lat: 56.05,
              lng: -4.45,
            }),
          });
        });
        await openMap(page, "/");
        await getMap(page);
        const input = page.locator("#place-query");
        await input.fill(value);
        await page.locator(".hud-search-go").click();
        await expect
          .poll(() => geocodeCount, { timeout: 30_000 })
          .toBe(1);
        expect(sentQ).toBe(trimmed);
        await expect(input).toHaveValue(trimmed);
        assertConsoleClean(gate);
      });
    }

    for (const value of [
      "G63",
      "G63 0A",
      "063 0AA",
      "G63-0AA",
      "G63 0AA X",
      "",
    ] as const) {
      test(`T-P2 refuses postcode ${JSON.stringify(value)}`, async ({
        page,
      }) => {
        test.setTimeout(90_000);
        expect(looksLikeFullPostcode(value)).toBe(false);
        const gate = attachConsoleGate(page);
        let geocodeCount = 0;
        await stubMapCardsBackend(page, { gbpLive: false });
        await page.route("**/layers/catalog**", async (route) => {
          await route.fulfill({ status: 404, body: "absent" });
        });
        await stubCouncilsOk(page);
        await page.route("**/geocode/postcode**", async (route) => {
          geocodeCount += 1;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({ postcode: "G2 1DU", lat: 55.86, lng: -4.25 }),
          });
        });
        await openMap(page, "/");
        await getMap(page);
        const input = page.locator("#place-query");
        if (value === "") {
          // Go is disabled when empty; Enter still runs the refuse path.
          await input.focus();
          await input.press("Enter");
        } else {
          await input.fill(value);
          await page.locator(".hud-search-go").click();
        }
        await expect(page.getByText(POSTCODES_ONLY, { exact: true })).toBeVisible({
          timeout: 15_000,
        });
        expect(geocodeCount).toBe(0);
        assertConsoleClean(gate);
      });
    }

    test("T-P3 search input word-spacing keeps postcode space visible", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      await getMap(page);
      const spacing = await page.locator("#place-query").evaluate((el) => {
        const cs = getComputedStyle(el);
        return {
          wordSpacing: cs.wordSpacing,
          fontSize: cs.fontSize,
        };
      });
      expect(spacing.wordSpacing).not.toBe("0px");
      expect(spacing.wordSpacing).not.toBe("normal");
      const px = Number.parseFloat(spacing.wordSpacing);
      const fontPx = Number.parseFloat(spacing.fontSize);
      // Spec: ≥ 3px at a 14px font → scale floor with actual font size.
      const minPx = 3 * (fontPx / 14);
      expect(px).toBeGreaterThanOrEqual(minPx - 0.01);
      assertConsoleClean(gate);
    });
  });
}
