import { expect, test, type Locator, type Page } from "@playwright/test";

/**
 * LOGO-H2 — new mark assets, favicons, OG image, header label + tap target,
 * desktop tagline only (hidden ≤600px / 390).
 * LOGO-FIX-1 — absolute prod og/twitter images; no Noun Project credit.
 */

const PROD_OG_IMAGE = "https://scot-land.scot/og-image.png";

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

const TAGLINE = "Land value we all create";

test.beforeEach(async ({ page }) => {
  consoleErrors.length = 0;
  resourceFails.length = 0;
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push(msg.text());
    }
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
      body: JSON.stringify({
        code: null,
        name: null,
        vintage: null,
      }),
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
});

test.afterEach(() => {
  expect(
    resourceFails,
    `unexpected HTTP 404/503:\n${resourceFails
      .map((f) => `${f.status} ${f.url}`)
      .join("\n")}`,
  ).toEqual([]);

  const meaningful = consoleErrors.filter((text) => {
    if (/\bAbortError\b|The user aborted|The operation was aborted/i.test(text)) {
      return false;
    }
    return true;
  });
  expect(
    meaningful,
    `console errors:\n${meaningful.join("\n")}`,
  ).toEqual([]);
});

function pngDimensions(buf: Buffer): { width: number; height: number } {
  // PNG IHDR: bytes 16–23 are width/height (big-endian uint32).
  return {
    width: buf.readUInt32BE(16),
    height: buf.readUInt32BE(20),
  };
}

/** SW-054: og:image + twitter:image must be absolute prod URLs, never localhost. */
async function expectAbsoluteSocialImages(page: Page, path = page.url()) {
  const ogContents = await page
    .locator('meta[property="og:image"]')
    .evaluateAll((els) =>
      els.map((el) => el.getAttribute("content") || ""),
    );
  expect(
    ogContents.some((c) => c === PROD_OG_IMAGE || c.startsWith(`${PROD_OG_IMAGE}?`)),
    `${path}: og:image must be ${PROD_OG_IMAGE}; got ${JSON.stringify(ogContents)}`,
  ).toBe(true);
  expect(
    ogContents.every((c) => !/localhost/i.test(c)),
    `${path}: og:image must not contain localhost; got ${JSON.stringify(ogContents)}`,
  ).toBe(true);

  const twContents = await page
    .locator('meta[name="twitter:image"], meta[property="twitter:image"]')
    .evaluateAll((els) =>
      els.map((el) => el.getAttribute("content") || ""),
    );
  expect(
    twContents.some((c) => c === PROD_OG_IMAGE || c.startsWith(`${PROD_OG_IMAGE}?`)),
    `${path}: twitter:image must be ${PROD_OG_IMAGE}; got ${JSON.stringify(twContents)}`,
  ).toBe(true);
  expect(
    twContents.every((c) => !/localhost/i.test(c)),
    `${path}: twitter:image must not contain localhost; got ${JSON.stringify(twContents)}`,
  ).toBe(true);
}

function assertAbsoluteSocialImagesInHtml(html: string, path: string) {
  const og = [...html.matchAll(/property=["']og:image["'][^>]*content=["']([^"']+)["']/gi)]
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

  expect(
    og.some((c) => c === PROD_OG_IMAGE || c.startsWith(`${PROD_OG_IMAGE}?`)),
    `${path}: og:image must be ${PROD_OG_IMAGE}; got ${JSON.stringify(og)}`,
  ).toBe(true);
  expect(
    og.every((c) => c && !/localhost/i.test(c)),
    `${path}: og:image must not contain localhost; got ${JSON.stringify(og)}`,
  ).toBe(true);
  expect(
    tw.some((c) => c === PROD_OG_IMAGE || c.startsWith(`${PROD_OG_IMAGE}?`)),
    `${path}: twitter:image must be ${PROD_OG_IMAGE}; got ${JSON.stringify(tw)}`,
  ).toBe(true);
  expect(
    tw.every((c) => c && !/localhost/i.test(c)),
    `${path}: twitter:image must not contain localhost; got ${JSON.stringify(tw)}`,
  ).toBe(true);
}

test.describe("LOGO-H2 static assets", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("favicon, apple-touch, PWA icons, mark and OG image return 200", async ({
    request,
  }) => {
    const paths = [
      "/favicon.ico",
      "/favicon-16.png",
      "/favicon-32.png",
      "/favicon.svg",
      "/apple-touch-icon.png",
      "/icon-192.png",
      "/icon-512.png",
      "/og-image.png",
      "/scot-land-mark.png",
      "/site.webmanifest",
      "/logo-mark.svg",
    ];
    for (const path of paths) {
      const res = await request.get(path);
      expect(res.status(), path).toBe(200);
    }

    const og = await request.get("/og-image.png");
    const body = Buffer.from(await og.body());
    const { width, height } = pngDimensions(body);
    expect(width).toBe(1200);
    expect(height).toBe(630);
  });
});

test.describe("LOGO-H2 desktop chrome", () => {
  test.use({ viewport: { width: 1100, height: 800 } });

  test("content brand aria-label, tagline once, og/twitter images", async ({
    page,
  }) => {
    await page.goto("/about");

    const brand = page.getByTestId("site-nav-brand");
    await expect(brand).toHaveAttribute("aria-label", "Scot-LAND home");

    const taglines = page.locator(".site-nav-tagline");
    await expect(taglines).toHaveCount(1);
    await expect(taglines).toBeVisible();
    await expect(taglines).toHaveText(TAGLINE);

    // Tagline must not appear elsewhere in the page chrome (footer/nav dupes).
    const bodyTaglineMatches = page.getByText(TAGLINE, { exact: true });
    await expect(bodyTaglineMatches).toHaveCount(1);

    await expectAbsoluteSocialImages(page);
  });

  test("LOGO-FIX-1: every public page has absolute prod og/twitter images", async ({
    request,
  }) => {
    const paths = [
      "/",
      "/about",
      "/methodology",
      "/data",
      "/developers",
      "/developers/api",
      "/developers/checks",
      "/developers/glossary",
    ];
    for (const path of paths) {
      const res = await request.get(path);
      expect(res.status(), path).toBe(200);
      assertAbsoluteSocialImagesInHtml(await res.text(), path);
    }
  });

  test("LOGO-FIX-1: Noun Project / Coquet absent on about", async ({
    page,
  }) => {
    await page.goto("/about");
    const body = await page.locator("body").innerText();
    expect(body).not.toMatch(/Noun Project/i);
    expect(body).not.toMatch(/Coquet/i);
    await expect(
      page.getByText("Scot-LAND logo: original design."),
    ).toBeVisible();
  });

  test("map HUD brand aria-label is Scot-LAND home", async ({ page }) => {
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    const hudBrand = page.locator("a.hud-wordmark");
    await expect(hudBrand).toHaveAttribute("aria-label", "Scot-LAND home");
    // No tagline in map chrome.
    await expect(page.locator(".hud-brand .site-nav-tagline")).toHaveCount(0);
  });
});

test.describe("LOGO-H2 mobile (390×844)", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("brand tap target ≥44px; tagline hidden; no horizontal scroll", async ({
    page,
  }) => {
    await page.goto("/about");

    const brand = page.getByTestId("site-nav-brand");
    await expect(brand).toBeVisible();
    await expect(brand).toHaveAttribute("aria-label", "Scot-LAND home");
    await expect(brand.locator(".site-nav-wordmark")).toBeHidden();
    await expect(brand.locator(".site-nav-tagline")).toBeHidden();

    const box = await brand.boundingBox();
    expect(box, "brand bounding box").not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(44);
    expect(box!.height).toBeGreaterThanOrEqual(44);

    const noHScroll = await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    );
    expect(noHScroll).toBe(true);

    const header = page.getByTestId("site-nav");
    await assertLogoDoesNotCoverText(
      brand.locator("img"),
      header,
      "content brand logo",
    );
  });

  test("map HUD brand tap target ≥44px and no tagline", async ({ page }) => {
    await page.goto("/");
    await page.locator(".maplibregl-canvas").waitFor();
    const hudLink = page.locator("a.hud-wordmark");
    await expect(hudLink).toHaveAttribute("aria-label", "Scot-LAND home");
    const box = await hudLink.boundingBox();
    expect(box, "hud brand bounding box").not.toBeNull();
    expect(box!.width).toBeGreaterThanOrEqual(44);
    expect(box!.height).toBeGreaterThanOrEqual(44);
    await expect(page.getByText(TAGLINE, { exact: true })).toHaveCount(0);
  });
});

type Box = {
  x: number;
  y: number;
  width: number;
  height: number;
  label: string;
};

/** Reuse SW-020 geometry helper idea: logo must not cover visible header text. */
async function assertLogoDoesNotCoverText(
  logo: Locator,
  header: Locator,
  label: string,
) {
  const logoBox = await logo.boundingBox();
  expect(logoBox, `${label} box`).not.toBeNull();

  const textBoxes = await header.evaluate((root) => {
    const out: Box[] = [];
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node: Node | null = walker.nextNode();
    while (node) {
      const text = (node.textContent || "").replace(/\s+/g, " ").trim();
      if (text.length > 0) {
        const parent = node.parentElement;
        if (parent && !parent.classList.contains("sr-only")) {
          const style = getComputedStyle(parent);
          if (
            style.display !== "none" &&
            style.visibility !== "hidden" &&
            Number(style.opacity) > 0
          ) {
            const r = parent.getBoundingClientRect();
            if (r.width > 0 && r.height > 0) {
              out.push({
                x: r.x,
                y: r.y,
                width: r.width,
                height: r.height,
                label: text.slice(0, 40),
              });
            }
          }
        }
      }
      node = walker.nextNode();
    }
    return out;
  });

  const lb = logoBox!;
  for (const tb of textBoxes) {
    // Ignore text that is the logo's own empty alt / decorative wrappers with
    // no meaningful overlap check needed when the wordmark/tagline are hidden.
    const overlapX = lb.x < tb.x + tb.width && lb.x + lb.width > tb.x;
    const overlapY = lb.y < tb.y + tb.height && lb.y + lb.height > tb.y;
    expect(
      overlapX && overlapY,
      `${label} overlaps header text "${tb.label}"`,
    ).toBe(false);
  }
}
