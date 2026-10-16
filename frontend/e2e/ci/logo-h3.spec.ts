import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test, type Page } from "@playwright/test";

/**
 * LOGO-H3 — header, map mark, and preload use /logo-mark-h3.png.
 * The retired filename must not appear in public HTML.
 */

const MARK = "/logo-mark-h3.png";

const consoleErrors: string[] = [];
const resourceFails: Array<{ url: string; status: number }> = [];

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  resourceFails.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("pageerror", (err) => {
    consoleErrors.push(String(err));
  });
  page.on("response", (response) => {
    const status = response.status();
    if (status === 404 || status === 503) {
      resourceFails.push({ url: response.url(), status });
    }
  });

  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({
        detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
      }),
    });
  });
  await page.route("**/backend/health**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(HEALTH_OK),
    });
  });
  await page.route("**/backend/layers/catalog**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await page.route("**/backend/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ kind: "places", matches: [] }),
    });
  });
  await page.route("**/backend/layers/open/data-zones**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
    });
  });
  await page.route("**/backend/layers/context/data-zones/at**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ code: null, name: null, vintage: null }),
    });
  });
  await page.route("**/backend/platform/place**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        contract: "place_card_v1",
        lat: 55.95,
        lng: -3.19,
        place_label: null,
        agr_rows: [],
        constraints: [],
        layers: [],
        links: [],
      }),
    });
  });
  await page.route("**/api/catalog.json", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ layers: [] }),
    });
  });
  await stubLayersAddQuiet(page);
});

test.afterEach(() => {
  expect(
    resourceFails,
    `unexpected HTTP 404/503:\n${resourceFails.map((f) => `${f.status} ${f.url}`).join("\n")}`,
  ).toEqual([]);
  const meaningful = consoleErrors.filter(
    (text) => !/\bAbortError\b|The user aborted|The operation was aborted/i.test(text),
  );
  expect(meaningful, `console errors:\n${meaningful.join("\n")}`).toEqual([]);
});

function pngDimensions(buf: Buffer): { width: number; height: number } {
  return {
    width: buf.readUInt32BE(16),
    height: buf.readUInt32BE(20),
  };
}

async function expectMark(page: Page, selector: string) {
  const img = page.locator(selector);
  await expect(img).toBeVisible();
  await expect(img).toHaveAttribute("src", new RegExp(`${MARK}$`));
  await expect
    .poll(async () =>
      img.evaluate((el: HTMLImageElement) =>
        el.complete ? el.naturalWidth : 0,
      ),
    )
    .toBeGreaterThan(0);
}

async function expectPreload(page: Page) {
  const hrefs = await page.locator('link[rel="preload"][as="image"]').evaluateAll(
    (els) => els.map((el) => el.getAttribute("href") || ""),
  );
  expect(
    hrefs.some((href) => href.endsWith(MARK)),
    `preload image hrefs: ${JSON.stringify(hrefs)}`,
  ).toBe(true);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`LOGO-H3 header ${viewport.width}×${viewport.height}`, () => {
    test.use({ viewport: { width: viewport.width, height: viewport.height } });

    test("map HUD mark and preload", async ({ page }) => {
      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor();
      await expectMark(page, ".hud-wordmark img");
      await expectPreload(page);
      await expect(page.locator('footer img[src*="scot-land-mark"]')).toHaveCount(0);
    });

    test("content header mark and preload", async ({ page }) => {
      await page.goto("/about");
      await expectMark(page, "[data-testid=site-nav-brand] img");
      await expectPreload(page);
      await expect(page.locator('footer img[src*="scot-land-mark"]')).toHaveCount(0);
    });
  });
}

test.describe("LOGO-H3 static marks", () => {
  test("social images, manifest icons, and no retired filename in HTML", async ({
    request,
  }) => {
    const pages = ["/", "/about", "/data", "/roadmap"];
    for (const path of pages) {
      const res = await request.get(path);
      expect(res.status(), path).toBe(200);
      const html = await res.text();
      expect(html, path).not.toContain("scot-land-mark");

      const og = [
        ...html.matchAll(/property=["']og:image["'][^>]*content=["']([^"']+)["']/gi),
      ]
        .map((m) => m[1])
        .concat(
          [...html.matchAll(/content=["']([^"']+)["'][^>]*property=["']og:image["']/gi)].map(
            (m) => m[1],
          ),
        );
      const tw = [
        ...html.matchAll(
          /(?:name|property)=["']twitter:image["'][^>]*content=["']([^"']+)["']/gi,
        ),
      ]
        .map((m) => m[1])
        .concat(
          [
            ...html.matchAll(
              /content=["']([^"']+)["'][^>]*(?:name|property)=["']twitter:image["']/gi,
            ),
          ].map((m) => m[1]),
        );
      expect(og.length, path).toBeGreaterThan(0);
      expect(tw.length, path).toBeGreaterThan(0);
      expect(og.every((url) => url.split("?")[0].endsWith("/og-image.png")), path).toBe(true);
      expect(tw.every((url) => url.split("?")[0].endsWith("/og-image.png")), path).toBe(true);

      const manifestHref = html.match(
        /<link[^>]*rel=["']manifest["'][^>]*href=["']([^"']+)["']/i,
      )?.[1];
      expect(manifestHref, path).toBe("/site.webmanifest");
    }

    const ogRes = await request.get("/og-image.png");
    expect(ogRes.status()).toBe(200);
    const { width, height } = pngDimensions(Buffer.from(await ogRes.body()));
    expect(width).toBe(1200);
    expect(height).toBe(630);

    const manifestRes = await request.get("/site.webmanifest");
    expect(manifestRes.status()).toBe(200);
    const manifest = (await manifestRes.json()) as {
      icons: Array<{ src: string }>;
    };
    expect(manifest.icons.map((icon) => icon.src).sort()).toEqual([
      "/icon-192.png",
      "/icon-512.png",
    ]);
    for (const icon of ["/icon-192.png", "/icon-512.png"]) {
      const iconRes = await request.get(icon);
      expect(iconRes.status(), icon).toBe(200);
    }

    const mark = await request.get(MARK);
    expect(mark.status()).toBe(200);
  });
});
