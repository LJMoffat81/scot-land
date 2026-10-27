/**
 * FRONTEND-BATCH-1 — default people/km² view, wording sweep, how-we-built titles.
 * Widths 1280×800 and 390×844. Console errors fail. Red-first on 7af495eb for
 * T-D1, T-D3 paint, T-C1 text, T-W2.
 */
import { test, expect } from "./_fixtures";
import { type Page, type Route } from "@playwright/test";
import {
  DEFAULT_VIEW_METRIC_ID,
  DEFAULT_VIEW_METRIC_IS_NON_GBP,
  metricById,
  rangeLegendTitle,
} from "../../lib/mapColourRamps";
import { paintForMetricWithNoData } from "../../lib/mapLicenceCredits";
import { assertConsoleClean, attachConsoleGate, CI_TINY_PNG, EMPTY_GLYPH_PBF, injectEsriBasemapKey, openLayers, openMap, registerOpenFreeMapFontStub, stubMapCardsBackend, type ConsoleGate } from "./_mapCardsHelpers";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

registerOpenFreeMapFontStub();

const ESRI_STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

const ESRI_FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

type EsriStyle = {
  sprite: string;
  glyphs: string;
  sources: Record<
    string,
    { tiles?: string[]; url?: string; attribution?: string; type?: string }
  >;
  layers?: Array<Record<string, unknown>>;
};

function loadEsriFixture(): EsriStyle {
  if (!existsSync(ESRI_FIXTURE_PATH)) {
    throw new Error("fixture missing: esri-imagery-style.json");
  }
  return JSON.parse(readFileSync(ESRI_FIXTURE_PATH, "utf8")) as EsriStyle;
}

async function routeEsriFixture(page: Page, style: EsriStyle) {
  const spriteJson = `${style.sprite}.json`;
  const spritePng = `${style.sprite}.png`;

  await page.route(`${ESRI_STYLE_URL}**`, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(style),
    });
  });
  await page.route(spriteJson, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ image: "root.png", width: 1, height: 1 }),
    });
  });
  await page.route(spritePng, async (route) => {
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
}

const ROLE_LINES = [
  "Engineering Lead: runs the building work, writes specs and reviews code.",
  "Wording & UX Reviewer: keeps every page clear and easy to use.",
  "Georgist Economist: keeps the work true to land value principles.",
  "Land Value Econometrician: models land values from sales and building costs, and tests how well the model fits.",
  "GIS & Open Data: finds public data, checks its licence and joins it to areas.",
  "Test Engineer: writes the automated tests that guard every change.",
  "Live Site Checker: tests the live site after every change.",
  "Outside Comms: drafts outside messages, which are only sent once a person approves them.",
  "Methods Auditor: checks each method is sound and written down before it is used.",
  "Property Tax & Land Law: checks the work against tax and land law.",
  "Visual Designer: looks after the look of the site and maps.",
  "Project Lead: plans the work and holds it to our rules.",
] as const;

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
        population_density_per_km2: 9,
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

const POP_METRIC = metricById("pop_density")!;
const EXPECTED_POP_PAINT = paintForMetricWithNoData(
  POP_METRIC.property,
  POP_METRIC.stops,
);

const BANNED_BODY =
  /neighbou?rhood|neighborhood|natural capital|what3words|\bledger\b/i;

type MapProbe = {
  getLayer(id: string): unknown;
  getLayoutProperty(id: string, prop: string): unknown;
  getPaintProperty(id: string, prop: string): unknown;
  jumpTo(opts: { zoom: number; center?: [number, number] }): void;
  once(event: string, cb: () => void): void;
  getStyle(): {
    layers?: Array<{
      id: string;
      paint?: Record<string, unknown>;
      layout?: Record<string, unknown>;
    }>;
  };
  isStyleLoaded?: () => boolean;
};

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

async function layoutVis(page: Page, layerId: string): Promise<string> {
  return page.evaluate((id) => {
    const map = (window as unknown as { __map?: MapProbe }).__map;
    if (!map) throw new Error("window.__map missing");
    return String(map.getLayoutProperty(id, "visibility") ?? "visible");
  }, layerId);
}

async function fillPaint(page: Page): Promise<unknown> {
  return page.evaluate(() => {
    const map = (window as unknown as { __map?: MapProbe }).__map;
    if (!map) throw new Error("window.__map missing");
    return map.getPaintProperty("council-fill", "fill-color");
  });
}

async function jumpToZoom(page: Page, zoom: number): Promise<void> {
  await page.evaluate(async (z) => {
    const map = (window as unknown as { __map?: MapProbe }).__map;
    if (!map) throw new Error("window.__map missing");
    await new Promise<void>((resolve) => {
      map.once("idle", () => resolve());
      map.jumpTo({ zoom: z, center: [-4.2, 56.8] });
    });
  }, zoom);
}

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

async function stubLayersCouncils(
  page: Page,
  body: unknown,
  status = 200,
) {
  await page.route("**/layers/councils**", async (route: Route) => {
    await route.fulfill({
      status,
      contentType: "application/json",
      body: typeof body === "string" ? body : JSON.stringify(body),
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

async function waitFillVisible(page: Page) {
  await expect
    .poll(async () => layoutVis(page, "council-fill"), { timeout: 45_000 })
    .toBe("visible");
}

async function openDefaultMap(page: Page, gate: ConsoleGate) {
  await stubMapCardsBackend(page, { gbpLive: false });
  await stubCouncilsOk(page);
  await openMap(page, "/?layers=councils");
  await getMap(page);
  await jumpToZoom(page, 6);
  await waitFillVisible(page);
  assertConsoleClean(gate);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`FRONTEND-BATCH-1 ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport });

    test("T-D1 default measure people/km² at z6", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await openDefaultMap(page, gate);

      await expect(layoutVis(page, "council-fill")).resolves.toBe("visible");
      const paint = await fillPaint(page);
      expect(paint).toEqual(EXPECTED_POP_PAINT);
      const expectedTitle = rangeLegendTitle(
        metricById(DEFAULT_VIEW_METRIC_ID)!,
      );
      expect(expectedTitle).not.toBe("");
      await openLayers(page);
      await expect(page.getByTestId("map-range-legend-title")).toHaveText(
        expectedTitle,
      );
      assertConsoleClean(gate);
    });

    test("T-D2 no £ on default view", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await openDefaultMap(page, gate);
      await expect(page.locator("body")).not.toContainText("£");
      await openLayers(page);
      const title = await page.getByTestId("map-range-legend-title").innerText();
      expect(title).not.toMatch(/£/);
      assertConsoleClean(gate);
    });

    test("T-D3 unit guard — paint binds population_density_per_km2", async ({
      page,
    }) => {
      test.setTimeout(120_000);
      expect(DEFAULT_VIEW_METRIC_IS_NON_GBP).toBe(true);
      expect(metricById(DEFAULT_VIEW_METRIC_ID)?.unit).not.toBe("£");
      expect(DEFAULT_VIEW_METRIC_ID).toBe("pop_density");

      const gate = attachConsoleGate(page);
      await openDefaultMap(page, gate);
      const paint = await fillPaint(page);
      const serial = JSON.stringify(paint);
      expect(serial).toContain("population_density_per_km2");
      expect(serial).not.toMatch(/median_price|average_price_gbp|annual_ground_rent/);
      assertConsoleClean(gate);
    });

    test("T-D4 fallback when /layers/councils is 503", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      // Intentional councils 503 fallback path.
      gate.expectError({
        urlPath: "/backend/layers/councils",
        status: 503,
        count: 1,
      });
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubLayersCouncils(page, { detail: "unavailable" }, 503);
      await openMap(page, "/?layers=councils");
      await getMap(page);
      await jumpToZoom(page, 6);
      await expect
        .poll(async () => layoutVis(page, "council-line"), { timeout: 45_000 })
        .toBe("visible");
      await expect(layoutVis(page, "council-fill")).resolves.toBe("none");
      await expect(page.locator("body")).not.toContainText("£");
      assertConsoleClean(gate);
    });

    test("T-D4b malformed 200 {} keeps fill hidden", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubLayersCouncils(page, {});
      await openMap(page, "/?layers=councils");
      await getMap(page);
      await jumpToZoom(page, 6);
      await expect
        .poll(async () => layoutVis(page, "council-line"), { timeout: 45_000 })
        .toBe("visible");
      await expect(layoutVis(page, "council-fill")).resolves.toBe("none");
      await expect(page.locator("body")).not.toContainText("£");
      assertConsoleClean(gate);
    });

    test('T-D4b malformed 200 {"type":"Feature"} keeps fill hidden', async ({
      page,
    }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubLayersCouncils(page, { type: "Feature" });
      await openMap(page, "/?layers=councils");
      await getMap(page);
      await jumpToZoom(page, 6);
      await expect
        .poll(async () => layoutVis(page, "council-line"), { timeout: 45_000 })
        .toBe("visible");
      await expect(layoutVis(page, "council-fill")).resolves.toBe("none");
      await expect(page.locator("body")).not.toContainText("£");
      assertConsoleClean(gate);
    });

    test("T-D5 zoom band boundaries z4.9 / z5 / z8 / z9", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await openDefaultMap(page, gate);

      await jumpToZoom(page, 4.9);
      await expect
        .poll(async () => layoutVis(page, "council-fill"), { timeout: 30_000 })
        .toBe("none");

      await jumpToZoom(page, 5);
      await expect
        .poll(async () => layoutVis(page, "council-fill"), { timeout: 30_000 })
        .toBe("visible");

      await jumpToZoom(page, 8);
      await expect
        .poll(async () => layoutVis(page, "council-fill"), { timeout: 30_000 })
        .toBe("none");

      await jumpToZoom(page, 9);
      await expect
        .poll(async () => layoutVis(page, "council-fill"), { timeout: 30_000 })
        .toBe("none");
      assertConsoleClean(gate);
    });

    test("T-D6 basemap residential/landuse/building paint untouched", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      const styleByUrl = new Map<string, { layers?: Array<Record<string, unknown>> }>();
      const esriFixture = loadEsriFixture();
      page.on("response", async (response) => {
        const url = response.url();
        if (!/tiles\.openfreemap\.org\/styles\/positron/i.test(url)) {
          return;
        }
        if (!response.ok()) return;
        try {
          const json = (await response.json()) as {
            layers?: Array<Record<string, unknown>>;
          };
          styleByUrl.set(url, json);
        } catch {
          /* ignore non-JSON */
        }
      });

      await injectEsriBasemapKey(page);
      await routeEsriFixture(page, esriFixture);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      await getMap(page);

      async function assertBasemapUntouched(styleKey: RegExp) {
        const entry = [...styleByUrl.entries()].find(([u]) => styleKey.test(u));
        expect(entry, `captured style for ${styleKey}`).toBeTruthy();
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
              /* layer may lack fill-color */
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
      }

      await assertBasemapUntouched(/positron/i);

      const toggle = page.getByTestId("basemap-switcher");
      await expect(toggle).toBeVisible();
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-pressed", "true");
      await getMap(page);
      // Aerial fixture has no residential/landuse/building fills — Positron
      // paint check above is the T-D6 shading guard; Aerial must load cleanly.
      await expect
        .poll(
          async () =>
            page.evaluate(() => {
              const map = (window as unknown as { __map?: MapProbe }).__map;
              if (!map) return false;
              try {
                return Boolean(map.getLayer("esri-imagery") || map.getLayer("background"));
              } catch {
                return false;
              }
            }),
          { timeout: 60_000 },
        )
        .toBe(true);
      expect(esriFixture.layers?.some((l) => l.id === "esri-imagery")).toBe(true);
      assertConsoleClean(gate);
    });

    test("T-C1 contact form hidden; soon text updated", async ({ page }) => {
      test.setTimeout(60_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await page.goto("/about");
      await expect(page.getByTestId("contact-form")).toHaveCount(0);
      await expect(page.getByTestId("contact-form-soon")).toHaveText(
        "Contact form not open yet. Please check back.",
      );
      await page.goto("/how-we-built-this");
      await expect(
        page.getByRole("link", { name: /get in touch/i }),
      ).toHaveCount(0);
      assertConsoleClean(gate);
    });

    test("T-W1 banned words absent on public pages", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      for (const path of [
        "/",
        "/about",
        "/methodology",
        "/roadmap",
        "/how-we-built-this",
        "/developers/api",
      ]) {
        await page.goto(path);
        const text = await page.locator("body").innerText();
        expect(text, path).not.toMatch(BANNED_BODY);
        expect(text, path).not.toContain("£");
      }
      assertConsoleClean(gate);
    });

    test("T-W2 wording rows 3–8", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });

      await page.goto("/methodology");
      const rollup = page.locator("#rollup p").first();
      await expect(rollup).toContainText(
        "Every figure belongs to a Data Zone. Data Zones fit inside council areas, and council areas make up Scotland.",
      );
      await expect(rollup).not.toContainText("Intermediate");

      await page.goto("/developers/api");
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(
        "Developer API and bulk data: later",
      );
      await expect(page.getByTestId("api-teaser")).toContainText(
        "The map stays free to use. Bulk data and the API may be paid services later.",
      );

      await page.goto("/roadmap");
      for (const name of [
        "Oil and gas",
        "Fishing quota",
        "Fish-farm seabed leases",
        "Offshore wind and seabed",
      ]) {
        const row = page
          .getByTestId("roadmap-aim-row")
          .filter({ hasText: name });
        await expect(
          row.getByTestId("roadmap-aim-status"),
        ).toHaveText("Later");
      }
      assertConsoleClean(gate);
    });

    test("T-H1 how we built this titles and Laurie scope", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await page.goto("/how-we-built-this");

      const roles = page.getByTestId("how-we-built-roles").getByRole("listitem");
      await expect(roles).toHaveCount(12);
      for (let i = 0; i < ROLE_LINES.length; i += 1) {
        await expect(roles.nth(i)).toHaveText(ROLE_LINES[i]);
      }

      const pageText = await page.locator("body").innerText();
      expect(pageText).not.toMatch(
        /Plain-English|Map Specialist|Data Scout|Data scouting|Coordination:|Outreach:/,
      );
      await expect(page.locator('a[href*="github.com"]')).toHaveCount(0);
      const laurieMatches = pageText.match(
        /Laurie Moffat, an independent volunteer/g,
      );
      expect(laurieMatches).toEqual([
        "Laurie Moffat, an independent volunteer",
      ]);

      // Binding: qualified|chartered only on intro + roles test ids.
      const introText = await page.getByTestId("how-we-built-intro").innerText();
      const rolesText = await page.getByTestId("how-we-built-roles").innerText();
      expect(introText).not.toMatch(/\b(qualified|chartered)\b/i);
      expect(rolesText).not.toMatch(/\b(qualified|chartered)\b/i);

      for (const path of [
        "/",
        "/about",
        "/methodology",
        "/data",
        "/roadmap",
        "/developers",
        "/developers/api",
        "/developers/glossary",
        "/why-land-value",
        "/mission",
      ]) {
        await page.goto(path);
        const text = await page.locator("body").innerText();
        expect(text, path).not.toMatch(/Laurie|Moffat/);
      }
      assertConsoleClean(gate);
    });

    test("T-L1 layers structure LAND then PLACES AND BOUNDARIES", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page, { gbpLive: false });
      await stubCouncilsOk(page);
      await openMap(page, "/");
      await openLayers(page);
      const headers = page.getByTestId("layers-nav-header");
      await expect(headers).toHaveCount(2);
      const land = (await headers.nth(0).innerText()).trim();
      const places = (await headers.nth(1).innerText()).trim();
      expect([land, places]).toEqual(["LAND", "PLACES AND BOUNDARIES"]);
      assertConsoleClean(gate);
    });
  });
}

// Node-side unit guard lives with the suite (T-D3) so CI always runs it.
test("T-D3 node: DEFAULT_VIEW_METRIC_ID is not a £ metric", () => {
  expect(DEFAULT_VIEW_METRIC_IS_NON_GBP).toBe(true);
  expect(metricById(DEFAULT_VIEW_METRIC_ID)?.unit !== "£").toBe(true);
});
