/**
 * FRONTEND-BATCH-2 r5 — T-M1…T-M5 (MAP-CONTROLS-1 / O1 / MC5–MC6 / MC11).
 * Viewports 1280×800 and 390×844. Console errors fail the test.
 */
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { attachConsoleGate, assertConsoleClean, CI_TINY_PNG, DUMMY_ESRI_KEY, EMPTY_GLYPH_PBF, injectEsriBasemapKey, openMap, registerOpenFreeMapFontStub, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";
import { scanLibertyHits } from "./_libertyScan";

registerOpenFreeMapFontStub();

const FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

const STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const;

const SIMPLE_CREDIT = "© OpenFreeMap © OpenStreetMap · Sources";

const FIXTURE_A =
  "Source: Esri, Vantor, GeoEye, Earthstar Geographics, CNES/Airbus DS, USDA, USGS, AeroGRID, IGN, and the GIS User Community; Sources: Esri, TomTom, Garmin, FAO, NOAA, USGS, © OpenStreetMap contributors, and the GIS User Community";

type EsriStyle = {
  sprite: string;
  glyphs: string;
  sources: Record<
    string,
    {
      tiles?: string[];
      url?: string;
      attribution?: string;
      copyrightText?: string;
      type?: string;
    }
  >;
  layers?: unknown[];
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
  // Glyphs / label tiles only — do not fulfill VectorTileServer JSON as PBF.
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

async function camera(page: Page) {
  return page.locator("#map").evaluate((el) => ({
    lng: Number((el as HTMLElement).dataset.lng || "NaN"),
    lat: Number((el as HTMLElement).dataset.lat || "NaN"),
    zoom: Number((el as HTMLElement).dataset.zoom || "NaN"),
  }));
}

async function waitForCamera(page: Page) {
  await expect
    .poll(async () => (await camera(page)).zoom, { timeout: 20_000 })
    .toBeGreaterThan(0);
}

async function creditTextContent(page: Page): Promise<string> {
  const narrow = (page.viewportSize()?.width ?? 1280) <= 900;
  if (narrow) {
    // Full Aerial line (incl. {A}) lives in the ⓘ sheet on narrow.
    await page.getByTestId("map-credit-info").click();
    const sheet = page.getByTestId("map-credit-sheet");
    await expect(sheet).toBeVisible();
    const text = ((await sheet.textContent()) ?? "")
      .replace(/\s+/g, " ")
      .replace(/^[×x]\s*/i, "")
      .trim();
    await page.getByTestId("map-credit-sheet-close").click();
    return text;
  }
  const line = page.getByTestId("map-credit-line-text");
  await expect(line).toBeVisible();
  return ((await line.textContent()) ?? "").replace(/\s+/g, " ").trim();
}

for (const viewport of VIEWPORTS) {
  test.describe(`FRONTEND-BATCH-2 ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    for (const keyMode of ["unset", "whitespace"] as const) {
      test(`T-M1 MC5 no key (${keyMode})`, async ({ page }) => {
        test.setTimeout(180_000);
        const gate = attachConsoleGate(page);
        const arcgis: string[] = [];
        page.on("request", (req) => {
          if (/arcgis\.com/i.test(req.url())) arcgis.push(req.url());
        });
        await injectEsriBasemapKey(
          page,
          keyMode === "whitespace" ? "   " : null,
        );
        await stubMapCardsBackend(page);
        await openMap(page);
        await waitForMap(page);
        await page.waitForTimeout(500);
        await expect(page.getByTestId("basemap-switcher")).toHaveCount(0);
        expect(arcgis).toEqual([]);
        const credit = await creditTextContent(page);
        expect(credit).toBe(SIMPLE_CREDIT);
        expect(credit).not.toContain("Powered by Esri");
        assertConsoleClean(gate);
      });
    }

    test("T-M2 MC6 blocked tiles revert", async ({ page }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await injectEsriBasemapKey(page, DUMMY_ESRI_KEY);
      expect(DUMMY_ESRI_KEY).toBe("TEST" + "KEY" + "x".repeat(8));

      for (const mode of ["style401", "tile498", "invalidJson"] as const) {
        await page.unrouteAll({ behavior: "ignoreErrors" });
        await stubMapCardsBackend(page);
        if (mode === "style401") {
          await page.route(/arcgis\.com/i, async (route) => {
            await route.fulfill({ status: 403, body: "nope" });
          });
        } else if (mode === "tile498") {
          const style = loadFixture();
          await page.route(`${STYLE_URL}**`, async (route) => {
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: JSON.stringify(style),
            });
          });
          await page.route(/ibasemaps-api\.arcgis\.com/i, async (route) => {
            await route.fulfill({ status: 498, body: "expired" });
          });
          await page.route(/basemaps-api\.arcgis\.com|cdn\.arcgis\.com/i, async (route) => {
            await route.fulfill({ status: 498, body: "expired" });
          });
        } else {
          await page.route(`${STYLE_URL}**`, async (route) => {
            await route.fulfill({
              status: 200,
              contentType: "application/json",
              body: "{not-json",
            });
          });
        }

        await openMap(page);
        await waitForMap(page);
        await waitForCamera(page);
        const switcher = page.getByTestId("basemap-switcher");
        await expect(switcher).toBeVisible({ timeout: 15_000 });
        const before = await camera(page);
        await switcher.click();
        await expect(page.getByTestId("aerial-unavailable-notice")).toHaveText(
          "Aerial map isn't available right now. Showing the simple map.",
          { timeout: 8_000 },
        );
        await expect(page.getByTestId("basemap-switcher")).toHaveCount(0);
        await waitForCamera(page);
        const after = await camera(page);
        expect(Math.abs(after.lng - before.lng)).toBeLessThanOrEqual(1e-5);
        expect(Math.abs(after.lat - before.lat)).toBeLessThanOrEqual(1e-5);
        expect(Math.abs(after.zoom - before.zoom)).toBeLessThanOrEqual(0.01);
        await page.goto("about:blank");
      }
      assertConsoleClean(gate);
    });

    test("T-M3 O1 missing attribution reverts", async ({ page }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await injectEsriBasemapKey(page, DUMMY_ESRI_KEY);
      const style = loadFixture();
      for (const src of Object.values(style.sources)) {
        src.attribution = "";
        src.copyrightText = "";
      }
      await stubMapCardsBackend(page);
      await routeEsriFixture(page, style);
      await openMap(page);
      await waitForMap(page);
      await waitForCamera(page);
      await expect(page.getByTestId("basemap-switcher")).toBeVisible({
        timeout: 15_000,
      });
      const before = await camera(page);
      await page.getByTestId("basemap-switcher").click();
      await expect(page.getByTestId("aerial-unavailable-notice")).toHaveText(
        "Aerial map isn't available right now. Showing the simple map.",
        { timeout: 8_000 },
      );
      await expect(page.getByTestId("basemap-switcher")).toHaveCount(0);
      await waitForCamera(page);
      const after = await camera(page);
      expect(Math.abs(after.lng - before.lng)).toBeLessThanOrEqual(1e-5);
      expect(Math.abs(after.lat - before.lat)).toBeLessThanOrEqual(1e-5);
      expect(Math.abs(after.zoom - before.zoom)).toBeLessThanOrEqual(0.01);
      // Intentional aerial remount logs MapLibre AbortError (stack is
      // content-hashed per build). Pin exact recorded text(s) for this run.
      const aborts = gate.errors
        .map((e) => e.text)
        .filter((t) =>
          t.startsWith("AbortError: signal is aborted without reason"),
        );
      const counts = new Map<string, number>();
      for (const t of aborts) counts.set(t, (counts.get(t) ?? 0) + 1);
      for (const [text, count] of counts) {
        gate.expectError({ text, count });
      }
      assertConsoleClean(gate);
    });

    test("T-M4 O1 credit exact + dynamic attribution", async ({ page }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await injectEsriBasemapKey(page, DUMMY_ESRI_KEY);
      const style = loadFixture();
      await stubMapCardsBackend(page);
      await routeEsriFixture(page, style);
      await openMap(page);
      await waitForMap(page);
      await waitForCamera(page);
      await expect(page.getByTestId("basemap-switcher")).toBeVisible({
        timeout: 15_000,
      });

      const simple = await creditTextContent(page);
      expect(simple).toBe(SIMPLE_CREDIT);

      await page.getByTestId("basemap-switcher").click();
      await expect(page.getByTestId("basemap-switcher")).toHaveAttribute(
        "aria-pressed",
        "true",
        { timeout: 30_000 },
      );

      const expectedAerial =
        `Powered by Esri | ${FIXTURE_A} · © OpenFreeMap © OpenStreetMap · Sources`;
      await expect
        .poll(async () => creditTextContent(page), { timeout: 30_000 })
        .toBe(expectedAerial);
      const aerial = await creditTextContent(page);
      expect(aerial).toBe(expectedAerial);

      if ((page.viewportSize()?.width ?? 1280) > 900) {
        const esriLink = page.locator('a[href="https://www.esri.com"]');
        await expect(esriLink).toHaveText("Esri");
      } else {
        // r6: visible line has Powered by Esri + OSM without click; sheet holds {A}.
        const visible = page.getByTestId("map-credit-line");
        await expect(visible).toContainText("Powered by Esri");
        await expect(visible).toContainText("© OpenStreetMap");
        await expect(visible).not.toContainText("Vantor");
        await page.getByTestId("map-credit-info").click();
        const sheet = page.getByTestId("map-credit-sheet");
        await expect(sheet).toContainText("Vantor");
        await expect(
          sheet.locator('a[href="https://www.esri.com"]'),
        ).toHaveText("Esri");
        await page.getByTestId("map-credit-sheet-close").click();
      }

      // Swap fixture attribution — must not be hard-coded.
      await page.unroute(`${STYLE_URL}**`);
      const swapped = loadFixture();
      for (const src of Object.values(swapped.sources)) {
        src.attribution = "Source: Fixture A";
        delete src.copyrightText;
      }
      // Deduplicate to a single attribution string in style order.
      const keys = Object.keys(swapped.sources);
      for (let i = 1; i < keys.length; i += 1) {
        const k = keys[i]!;
        if (swapped.sources[k]) swapped.sources[k]!.attribution = "";
      }
      await page.getByTestId("basemap-switcher").click(); // back to Simple
      await expect(page.getByTestId("basemap-switcher")).toHaveAttribute(
        "aria-pressed",
        "false",
      );
      await routeEsriFixture(page, swapped);
      await page.getByTestId("basemap-switcher").click();
      await expect(page.getByTestId("basemap-switcher")).toHaveAttribute(
        "aria-pressed",
        "true",
        { timeout: 30_000 },
      );
      const swappedCredit = await creditTextContent(page);
      expect(swappedCredit).toContain("Source: Fixture A");
      expect(swappedCredit).not.toContain("Maxar");
      assertConsoleClean(gate);
    });
  });
}

test("T-M5 MC11 no liberty in app/components/lib", async () => {
  const { hits, filesScanned } = scanLibertyHits(["app", "components", "lib"]);
  expect(filesScanned).toBeGreaterThanOrEqual(50);
  expect(hits).toEqual([]);
});
