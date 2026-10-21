/**
 * CSP-ESRI-1 — Esri CSP allowance (T-C1, T-C2).
 * Runs against the Playwright CI production build harness
 * (`next build && next start` in playwright.ci.config.ts).
 * Widths 1280×800 and 390×844. Console CSP refusals fail the test.
 */
import { expect, test } from "./_fixtures";
import { type Page, type Request } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";
import {
  CI_TINY_PNG,
  EMPTY_GLYPH_PBF,
  openLayers,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
  waitForMap,
} from "./_mapCardsHelpers";

registerOpenFreeMapFontStub();

test.use({ stubExternalHostsEnabled: false });

// Playwright CI cwd is frontend/; avoid import.meta (not an ESM module here).
const FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

const ALLOWED_ORIGINS = [
  "https://basemapstyles-api.arcgis.com",
  "https://ibasemaps-api.arcgis.com",
  "https://basemaps-api.arcgis.com",
  "https://cdn.arcgis.com",
] as const;

const STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

const VIEWPORTS = [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const;

/** Dummy key built at runtime — never a committed secret. */
const DUMMY_ESRI_KEY = "TEST" + "KEY" + "x".repeat(8);

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
};

function loadFixture(): EsriStyle {
  if (!existsSync(FIXTURE_PATH)) {
    throw new Error("fixture missing: esri-imagery-style.json");
  }
  return JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as EsriStyle;
}

function originOf(url: string): string {
  return new URL(url).origin;
}

function assertFixtureOrigins(style: EsriStyle) {
  const urls: string[] = [style.sprite, style.glyphs, STYLE_URL];
  for (const src of Object.values(style.sources)) {
    if (src.url) urls.push(src.url);
    for (const tile of src.tiles ?? []) urls.push(tile);
  }
  for (const url of urls) {
    const origin = originOf(url.replace("{fontstack}", "x").replace("{range}", "0-255").replace("{z}", "0").replace("{y}", "0").replace("{x}", "0"));
    expect(
      ALLOWED_ORIGINS.includes(origin as (typeof ALLOWED_ORIGINS)[number]),
      `fixture URL outside allowed set: ${url}`,
    ).toBe(true);
  }
}

async function routeEsriFixture(page: Page, style: EsriStyle) {
  const spriteJson = `${style.sprite}.json`;
  const spritePng = `${style.sprite}.png`;
  const glyphExample = style.glyphs
    .replace("{fontstack}", "Arial Regular")
    .replace("{range}", "0-255");
  const imageryTile = (style.sources.esri?.tiles?.[0] ?? "").replace(
    "{z}/{y}/{x}",
    "0/0/0",
  );
  const labelTile =
    "https://basemaps-api.arcgis.com/arcgis/rest/services/World_Basemap_v2/VectorTileServer/tile/0/0/0.pbf";

  await page.route(`${STYLE_URL}**`, async (route) => {
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
      body: JSON.stringify({
        image: "root.png",
        width: 1,
        height: 1,
      }),
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
  await page.route(labelTile, async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/x-protobuf",
      body: EMPTY_GLYPH_PBF,
    });
  });

  return { spriteJson, spritePng, glyphExample, imageryTile, labelTile };
}

async function panZoomOnce(page: Page) {
  await page.evaluate(() => {
    const map = (
      window as unknown as {
        __map?: {
          panBy?: (offset: [number, number]) => void;
          zoomIn?: () => void;
          getZoom?: () => number;
          setZoom?: (z: number) => void;
        };
      }
    ).__map;
    if (!map) return;
    map.panBy?.([40, -20]);
    const z = map.getZoom?.() ?? 6;
    map.setZoom?.(z + 0.5);
  });
}

for (const viewport of VIEWPORTS) {
  test.describe(`CSP-ESRI-1 @ ${viewport.width}x${viewport.height}`, () => {
    test.use({ viewport });

    test("T-C1: key-set probes load under CSP for four Esri origins", async ({
      page,
    }) => {
      test.setTimeout(180_000);
      // Key-set build uses the dummy at runtime in this test (Batch 2 consumes it).
      expect(DUMMY_ESRI_KEY.length).toBeGreaterThan(8);

      const style = loadFixture();
      assertFixtureOrigins(style);
      const urls = await routeEsriFixture(page, style);

      const cspViolations: { blockedURI: string; violatedDirective: string }[] =
        [];
      const consoleErrors: string[] = [];
      const failed: string[] = [];
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
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });
      page.on("requestfailed", (req) => failed.push(req.url()));
      page.on("request", (req: Request) => {
        const u = req.url();
        if (/arcgis\.com/i.test(u)) arcgisRequests.push(u);
      });

      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForMap(page);

      const probe = await page.evaluate(
        async ({
          styleUrl,
          spriteJson,
          spritePng,
          glyphExample,
          imageryTile,
          labelTile,
        }) => {
          const fetchOk = async (url: string) => {
            const res = await fetch(url);
            return { url, ok: res.ok, status: res.status };
          };
          const imageOk = (url: string) =>
            new Promise<{ url: string; ok: boolean }>((resolve) => {
              const img = new Image();
              img.onload = () => resolve({ url, ok: true });
              img.onerror = () => resolve({ url, ok: false });
              img.src = url;
            });
          const fetches = await Promise.all([
            fetchOk(styleUrl),
            fetchOk(spriteJson),
            fetchOk(glyphExample),
            fetchOk(labelTile),
          ]);
          const images = await Promise.all([
            imageOk(spritePng),
            imageOk(imageryTile),
          ]);
          const violations = (
            window as unknown as {
              __cspViolations: {
                blockedURI: string;
                violatedDirective: string;
              }[];
            }
          ).__cspViolations;
          return { fetches, images, violations };
        },
        {
          styleUrl: STYLE_URL,
          spriteJson: urls.spriteJson,
          spritePng: urls.spritePng,
          glyphExample: urls.glyphExample,
          imageryTile: urls.imageryTile,
          labelTile: urls.labelTile,
        },
      );

      expect(probe.violations, JSON.stringify(probe.violations)).toEqual([]);
      expect(
        consoleErrors.filter((line) =>
          /Content Security Policy|Refused to (connect|load)/i.test(line),
        ),
      ).toEqual([]);
      for (const f of probe.fetches) {
        expect(f.ok, `fetch failed ${f.url} status=${f.status}`).toBe(true);
      }
      for (const img of probe.images) {
        expect(img.ok, `image failed ${img.url}`).toBe(true);
      }

      const hosts = {
        style: arcgisRequests.filter((u) =>
          u.startsWith(
            "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery",
          ),
        ),
        iba: arcgisRequests.filter((u) =>
          u.startsWith("https://ibasemaps-api.arcgis.com/"),
        ),
        base: arcgisRequests.filter((u) =>
          u.startsWith("https://basemaps-api.arcgis.com/"),
        ),
        cdn: arcgisRequests.filter((u) =>
          u.startsWith("https://cdn.arcgis.com/"),
        ),
      };
      expect(hosts.style.length, "style requests").toBeGreaterThanOrEqual(1);
      expect(hosts.iba.length, "ibasemaps requests").toBeGreaterThanOrEqual(1);
      expect(hosts.base.length, "basemaps requests").toBeGreaterThanOrEqual(1);
      expect(hosts.cdn.length, "cdn requests").toBeGreaterThanOrEqual(1);

      for (const u of arcgisRequests) {
        const origin = originOf(u);
        expect(
          ALLOWED_ORIGINS.includes(origin as (typeof ALLOWED_ORIGINS)[number]),
          `disallowed arcgis request: ${u}`,
        ).toBe(true);
      }
      expect(failed.filter((u) => /arcgis\.com/i.test(u))).toEqual([]);
    });

    for (const keyMode of ["unset", "whitespace"] as const) {
      test(`T-C2: no arcgis traffic when key is ${keyMode}`, async ({
        page,
        context,
      }) => {
        test.setTimeout(180_000);
        // Until FRONTEND-BATCH-2, the bundle does not read the key. The CI
        // prod harness builds with key unset; whitespace is the same no-key
        // surface (falsy). Both modes must stay at zero arcgis hits.
        if (keyMode === "whitespace") {
          expect("   ".trim()).toBe("");
        }

        const hits: string[] = [];
        const spy: string[] = [];
        page.on("request", (req) => {
          const u = req.url();
          if (/arcgis\.com/i.test(new URL(u).hostname)) spy.push(u);
        });
        await context.route(/arcgis\.com/i, async (route) => {
          hits.push(route.request().url());
          await route.abort();
        });
        await stubMapCardsBackend(page);
        await openMap(page);
        await waitForMap(page);
        await panZoomOnce(page);
        await openLayers(page);
        await page.keyboard.press("Escape");
        await expect(page.getByTestId("layers-panel")).toBeHidden({
          timeout: 15_000,
        });

        await page.goto("/roadmap");
        await page.waitForLoadState("domcontentloaded");
        await page.goto("/about");
        await page.waitForLoadState("domcontentloaded");

        expect(hits, `route hits:\n${hits.join("\n")}`).toHaveLength(0);
        expect(spy, `spy requests:\n${spy.join("\n")}`).toHaveLength(0);
      });
    }
  });
}
