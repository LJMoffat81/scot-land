/**
 * ESRI-KEY-PROD-1 B1/B2 — build-time Esri key presence / absence.
 * Runs under playwright.buildkey.config.ts (no E2E hooks).
 */
import { expect, test, type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import {
  attachConsoleGate,
  CI_TINY_PNG,
  EMPTY_GLYPH_PBF,
  openMap,
  registerOpenFreeMapFontStub,
  stubCiTileDataQuiet,
  stubMapCardsBackend,
} from "../ci/_mapCardsHelpers";

registerOpenFreeMapFontStub();

const FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

/** Exact hostnames from CSP-ESRI-1 ALLOWED_ORIGINS. */
const ESRI_HOSTS = [
  "basemapstyles-api.arcgis.com",
  "ibasemaps-api.arcgis.com",
  "basemaps-api.arcgis.com",
  "cdn.arcgis.com",
] as const;

const STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

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

function hostnameOf(url: string): string | null {
  try {
    return new URL(url).hostname;
  } catch {
    return null;
  }
}

function isEsriHost(url: string): boolean {
  const host = hostnameOf(url);
  return host !== null && (ESRI_HOSTS as readonly string[]).includes(host);
}

async function routeEsriByHostname(page: Page, style: EsriStyle) {
  await page.route(
    (url) => isEsriHost(url.toString()),
    async (route) => {
      const url = route.request().url();
      const host = hostnameOf(url);
      if (host === "basemapstyles-api.arcgis.com") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(style),
        });
        return;
      }
      if (host === "cdn.arcgis.com") {
        if (url.endsWith(".json") || url.includes(".json?")) {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify({
              image: "root.png",
              width: 1,
              height: 1,
            }),
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
      if (host === "ibasemaps-api.arcgis.com") {
        await route.fulfill({
          status: 200,
          contentType: "image/png",
          body: CI_TINY_PNG,
        });
        return;
      }
      // basemaps-api.arcgis.com — glyphs / vector tiles / VectorTileServer JSON
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

function assertConsoleStrict(gate: ReturnType<typeof attachConsoleGate>) {
  expect(
    gate.consoleErrors,
    `console errors (strict):\n${gate.consoleErrors.join("\n")}`,
  ).toEqual([]);
  expect(
    gate.pageErrors,
    `pageerrors (strict):\n${gate.pageErrors.join("\n")}`,
  ).toEqual([]);
}

test("B1 build-time key shows switcher and hits basemapstyles", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const gate = attachConsoleGate(page);
  const styleReqs: string[] = [];
  page.on("request", (req) => {
    const host = hostnameOf(req.url());
    if (host === "basemapstyles-api.arcgis.com") styleReqs.push(req.url());
  });

  // Window inject must have no effect when hooks are off.
  await page.addInitScript(() => {
    (
      window as unknown as { __E2E_ESRI_BASEMAP_API_KEY__?: string | null }
    ).__E2E_ESRI_BASEMAP_API_KEY__ = null;
  });

  const style = loadFixture();
  await stubMapCardsBackend(page);
  await stubCiTileDataQuiet(page);
  await routeEsriByHostname(page, style);

  await openMap(page);
  const switcher = page.getByTestId("basemap-switcher");
  await expect(switcher).toBeVisible({ timeout: 30_000 });

  await switcher.click();
  await expect
    .poll(() => styleReqs.length, { timeout: 30_000 })
    .toBeGreaterThan(0);
  expect(
    styleReqs.some((u) => u.startsWith(STYLE_URL) || u.includes("basemapstyles-api.arcgis.com")),
  ).toBe(true);

  assertConsoleStrict(gate);
});

test("B2 no build-time key hides switcher and skips ArcGIS", async ({
  page,
}) => {
  test.setTimeout(180_000);
  const gate = attachConsoleGate(page);
  const arcgis: string[] = [];
  page.on("request", (req) => {
    if (isEsriHost(req.url())) arcgis.push(req.url());
  });

  await stubMapCardsBackend(page);
  await stubCiTileDataQuiet(page);
  // Still stub Esri hosts so a leak cannot hit the network; assert count 0.
  await routeEsriByHostname(page, loadFixture());

  await openMap(page);
  await page.waitForTimeout(800);
  await expect(page.getByTestId("basemap-switcher")).toHaveCount(0);
  expect(arcgis).toEqual([]);
  assertConsoleStrict(gate);
});
