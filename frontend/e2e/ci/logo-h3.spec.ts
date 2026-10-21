import {
  isCiOptionalFailUrl,
  registerOpenFreeMapFontStub,
  stubCiTileDataQuiet,
  stubLayersCouncilsQuiet,
} from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test } from "./_fixtures";
import { type APIRequestContext, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();


/**
 * LOGO-H3 — header, map mark, and preload use /logo-mark-h3.png.
 * The retired filename must not appear in public HTML.
 */

const MARK = "/logo-mark-h3.png";
const CACHE_QUERY = "?v=h3";

const FAVICON_URLS = [
  `/favicon.ico${CACHE_QUERY}`,
  `/favicon.svg${CACHE_QUERY}`,
  `/favicon-16.png${CACHE_QUERY}`,
  `/favicon-32.png${CACHE_QUERY}`,
  `/apple-touch-icon.png${CACHE_QUERY}`,
] as const;

const MANIFEST_ICON_URLS = [
  `/icon-192.png${CACHE_QUERY}`,
  `/icon-512.png${CACHE_QUERY}`,
] as const;

const OG_IMAGE_SUFFIX = `/og-image.png${CACHE_QUERY}`;

const SOCIAL_PAGES = ["/", "/about", "/data", "/roadmap"] as const;

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

  await stubLayersCouncilsQuiet(page);

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
  await stubCiTileDataQuiet(page);
});

test.afterEach(() => {
  const unknownResourceFails = resourceFails.filter(
    (fail) => !isCiOptionalFailUrl(fail.url),
  );
  expect(
    unknownResourceFails,
    `unexpected HTTP 404/503:\n${unknownResourceFails.map((f) => `${f.status} ${f.url}`).join("\n")}`,
  ).toEqual([]);
  const meaningful = consoleErrors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
      return true;
  });
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

function metaContents(html: string, attr: "property" | "name", key: string): string[] {
  const tags = html.match(/<meta\b[^>]*>/gi) ?? [];
  const values: string[] = [];
  for (const tag of tags) {
    if (!new RegExp(`\\b${attr}=["']${key}["']`, "i").test(tag)) continue;
    const content = tag.match(/\bcontent=["']([^"']+)["']/i);
    if (content) values.push(content[1]);
  }
  return values;
}

function linkHrefsByRel(html: string, rel: string): string[] {
  const tags = html.match(/<link\b[^>]*>/gi) ?? [];
  const hrefs: string[] = [];
  for (const tag of tags) {
    const relMatch = tag.match(/\brel=["']([^"']+)["']/i);
    if (!relMatch) continue;
    const rels = relMatch[1].toLowerCase().split(/\s+/);
    if (!rels.includes(rel)) continue;
    const href = tag.match(/\bhref=["']([^"']+)["']/i);
    if (href) hrefs.push(href[1]);
  }
  return hrefs;
}

function localAssetUrl(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) {
    const parsed = new URL(url);
    return `${parsed.pathname}${parsed.search}`;
  }
  return url;
}

async function expectAssetOk(request: APIRequestContext, url: string) {
  expect(url.includes(CACHE_QUERY), url).toBe(true);
  const target = localAssetUrl(url);
  expect(target.includes(CACHE_QUERY), target).toBe(true);
  const res = await request.get(target);
  expect(res.status(), target).toBe(200);
  return res;
}

function expectVersionedHead(html: string, path: string) {
  expect(html, path).not.toContain("scot-land-mark");

  const og = metaContents(html, "property", "og:image");
  const tw = [
    ...metaContents(html, "name", "twitter:image"),
    ...metaContents(html, "property", "twitter:image"),
  ];
  expect(og.length, `${path} og:image`).toBeGreaterThan(0);
  expect(tw.length, `${path} twitter:image`).toBeGreaterThan(0);
  for (const url of og) {
    expect(url.endsWith(OG_IMAGE_SUFFIX), `${path} og:image ${url}`).toBe(true);
  }
  for (const url of tw) {
    expect(url.endsWith(OG_IMAGE_SUFFIX), `${path} twitter:image ${url}`).toBe(true);
  }

  const iconHrefs = [
    ...linkHrefsByRel(html, "icon"),
    ...linkHrefsByRel(html, "apple-touch-icon"),
  ];
  for (const expected of FAVICON_URLS) {
    const matches = iconHrefs.filter(
      (href) => href === expected || href.endsWith(expected),
    );
    expect(matches, `${path} missing ${expected}; got ${JSON.stringify(iconHrefs)}`).toEqual(
      expect.arrayContaining([expect.stringContaining(CACHE_QUERY)]),
    );
    expect(matches.length, `${path} ${expected}`).toBeGreaterThan(0);
    for (const href of matches) {
      expect(href.includes(CACHE_QUERY), `${path} icon ${href}`).toBe(true);
    }
  }

  const manifestHrefs = linkHrefsByRel(html, "manifest");
  expect(manifestHrefs, path).toContain(`/site.webmanifest${CACHE_QUERY}`);
  for (const href of manifestHrefs) {
    expect(href, path).toBe(`/site.webmanifest${CACHE_QUERY}`);
  }
  return { og, tw, iconHrefs };
}

async function expectManifestIcons(request: APIRequestContext) {
  const manifestRes = await request.get("/site.webmanifest");
  expect(manifestRes.status()).toBe(200);
  const manifest = (await manifestRes.json()) as {
    icons: Array<{ src: string }>;
  };
  expect(manifest.icons.map((icon) => icon.src).sort()).toEqual(
    [...MANIFEST_ICON_URLS].sort(),
  );
  for (const icon of manifest.icons) {
    await expectAssetOk(request, icon.src);
  }
}

async function expectHeadAssetsOk(
  request: APIRequestContext,
  html: string,
  path: string,
) {
  const head = expectVersionedHead(html, path);
  for (const url of [...head.og, ...head.tw]) {
    await expectAssetOk(request, url);
  }
  for (const expected of FAVICON_URLS) {
    const href =
      head.iconHrefs.find((item) => item === expected || item.endsWith(expected)) ?? "";
    expect(href.includes(CACHE_QUERY), `${path} ${expected} got ${href}`).toBe(true);
    await expectAssetOk(request, href);
  }
  await expectManifestIcons(request);
  return head;
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
      await expectMark(page, "[data-testid=site-nav-brand] img");
      await expectPreload(page);
      await expect(page.locator('footer img[src*="scot-land-mark"]')).toHaveCount(0);
    });

    test("content header mark and preload", async ({ page }) => {
      await page.goto("/about");
      await expectMark(page, "[data-testid=site-nav-brand] img");
      await expectPreload(page);
      await expect(page.locator('footer img[src*="scot-land-mark"]')).toHaveCount(0);
    });

    test("icons, manifest icons, and social images use ?v=h3 and return 200", async ({
      page,
      request,
    }) => {
      for (const path of SOCIAL_PAGES) {
        await page.goto(path);
        if (path === "/") {
          await page.locator(".maplibregl-canvas").waitFor();
        }
        await expectHeadAssetsOk(request, await page.content(), path);
      }
    });
  });
}

test.describe("LOGO-H3 static marks", () => {
  test("social images, manifest icons, and no retired filename in HTML", async ({
    request,
  }) => {
    for (const path of SOCIAL_PAGES) {
      const res = await request.get(path);
      expect(res.status(), path).toBe(200);
      const html = await res.text();
      const { og } = await expectHeadAssetsOk(request, html, path);
      const ogRes = await request.get(localAssetUrl(og[0]));
      expect(ogRes.status(), path).toBe(200);
      const { width, height } = pngDimensions(Buffer.from(await ogRes.body()));
      expect(width, path).toBe(1200);
      expect(height, path).toBe(630);
    }

    const mark = await request.get(MARK);
    expect(mark.status()).toBe(200);
  });
});
