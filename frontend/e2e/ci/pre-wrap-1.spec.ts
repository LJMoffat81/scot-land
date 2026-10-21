import { registerOpenFreeMapFontStub } from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test } from "./_fixtures";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * PRE-WRAP-1 — no horizontal overflow on public pages.
 * Widths 1280 and 390. No skips.
 */

const PUBLIC_PAGES = [
  "/",
  "/map",
  "/about",
  "/methodology",
  "/data",
  "/developers",
  "/developers/api",
  "/developers/checks",
  "/developers/glossary",
  "/roadmap",
  "/how-we-built-this",
  "/place",
] as const;

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

async function stubQuiet(page: Page) {
  await page.route("**/backend/**", async (route) => {
    const url = route.request().url();
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
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        layers: [
          {
            id: "data_zones",
            label: "Area boundaries",
            description: "The small areas we report on",
            developer_note:
              "Ingest joins the 2011 and 2022 boundary extracts on the zone code before the public description is shown. https://example.invalid/very-long-source-path-that-must-stay-inside-the-card",
            licence: "OGL v3.0",
          },
        ],
      }),
    });
  });
  await page.route("**/api/gbp-live**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ enabled: false }),
    });
  });
  await stubLayersAddQuiet(page);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`PRE-WRAP-1 ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("public pages do not scroll sideways and code stays in its box", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      await stubQuiet(page);

      for (const path of PUBLIC_PAGES) {
        const response = await page.goto(path, { waitUntil: "domcontentloaded" });
        expect(response?.status(), path).toBeLessThan(400);
        if (path === "/" || path === "/map") {
          await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
        }

        const fit = await page.evaluate(() => {
          const root = document.scrollingElement ?? document.documentElement;
          const offenders: string[] = [];
          for (const el of document.querySelectorAll("pre, code")) {
            if (el.scrollWidth > el.clientWidth + 1) {
              const text = (el.textContent ?? "").replace(/\s+/g, " ").trim().slice(0, 80);
              offenders.push(
                `${el.tagName} scroll ${el.scrollWidth} client ${el.clientWidth} ${text}`,
              );
            }
          }
          return {
            scrollWidth: root.scrollWidth,
            innerWidth: window.innerWidth,
            offenders,
          };
        });

        expect(
          fit.scrollWidth,
          `${path} document.scrollWidth ${fit.scrollWidth} > innerWidth ${fit.innerWidth}`,
        ).toBeLessThanOrEqual(fit.innerWidth);
        expect(fit.offenders, `${path} overflowing pre/code`).toEqual([]);
      }
    });
  });
}
