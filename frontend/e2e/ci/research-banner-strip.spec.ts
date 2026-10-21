import { registerOpenFreeMapFontStub, stubLayersCouncilsQuiet, CI_OPTIONAL_FAIL_URL, isCiOptionalFailUrl, stubCiTileDataQuiet } from "./_mapCardsHelpers";
import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  RESEARCH_BANNER_BODY,
  RESEARCH_BANNER_LEAD,
  RESEARCH_BANNER_STRIP_COLLAPSED,
} from "../../lib/siteNav";

registerOpenFreeMapFontStub();


/**
 * SW-016 — ≤768px research banner is a one-line strip under the header;
 * tap expands. Must not cover burger, search, or place card.
 * Also: open menu keeps Map + About on top; no console errors
 * (same stub + console gate as site-nav-banner.spec.ts).
 */

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

const PLACE_CARD_FIXTURE = {
  contract: "place_card_v1",
  lat: 55.8609,
  lng: -4.2514,
  place_label: "Glasgow",
  council_name: "Glasgow City",
  data_zone: {
    status: "ok",
    code: "S01014567",
    name: "City Centre South",
    vintage: 2022,
  },
  intermediate_zone: { status: "ok", name: "City Centre" },
  agr_rows: [
    {
      id: "surface",
      label: "Land",
      tag: "proxy",
      status: "in_progress",
      applies: true,
    },
  ],
  constraints: [],
  layers: [],
  links: [],
};

/** Optional static assets whose 404/503 may be ignored (must match URL). */
const KNOWN_OPTIONAL_FAIL_URL = CI_OPTIONAL_FAIL_URL;

function isKnownOptionalFailUrl(url: string): boolean {
  return isCiOptionalFailUrl(url);
}

test.describe("SW-016 research banner strip 390x844", () => {
  test.use({ viewport: { width: 390, height: 844 } });

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

    // Catch-all first (Playwright is LIFO — later routes win).
    await page.route("**/backend/**", async (route) => {
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({
          detail: `e2e stub: unhandled ${route.request().method()} ${route.request().url()}`,
        }),
      });
    });

    await page.route("**/backend/boundaries/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(EMPTY_FC),
      });
    });
    await stubLayersCouncilsQuiet(page);
    await stubCiTileDataQuiet(page);

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
    await page.route(
      "**/backend/layers/context/data-zones/at**",
      async (route) => {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            code: null,
            name: null,
            vintage: null,
          }),
        });
      },
    );
    await page.route("**/backend/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_CARD_FIXTURE),
      });
    });
    await page.route("**/platform/place**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PLACE_CARD_FIXTURE),
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
    const unknownResourceFails = resourceFails.filter(
      (fail) => !isKnownOptionalFailUrl(fail.url),
    );
    expect(
      unknownResourceFails,
      `unexpected HTTP 404/503:\n${unknownResourceFails
        .map((f) => `${f.status} ${f.url}`)
        .join("\n")}`,
    ).toEqual([]);

    const meaningful = consoleErrors.filter((text) => {
      if (
        /\bAbortError\b|The user aborted|The operation was aborted/i.test(text)
      ) {
        return false;
      }
      if (
        /Failed to load resource: the server responded with a status of (404|503)/i.test(
          text,
        )
      ) {
        if (KNOWN_OPTIONAL_FAIL_URL.some((re) => re.test(text))) return false;
        if (!/https?:\/\//i.test(text) && unknownResourceFails.length === 0) {
          return false;
        }
        return true;
      }
      return true;
    });
    expect(
      meaningful,
      `console errors on map strip e2e:\n${meaningful.join("\n")}`,
    ).toEqual([]);
  });

  test("collapsed strip expands and clears burger, search, and place card", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    // MAP-HINTS-OFF-1: strip behaviour stays on content pages; map has no banner.
    await openMap(page);
    await expect(page.getByTestId("research-banner")).toHaveCount(0);
    const burger = page.getByTestId("site-nav-menu-btn");
    const search = page.locator("#place-query");
    await expect(burger).toBeVisible();
    await expect(search).toBeVisible();
    await assertCenterTappable(burger, "burger menu");
    await assertCenterTappable(search, "search field");

    await page.goto("/data");
    const banner = page.getByTestId("research-banner");
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toHaveAttribute("data-strip", "1");
    await expect(banner).toHaveAttribute("data-expanded", "0");
    await expect(banner).toHaveAttribute("data-banner-variant", "default");

    const toggle = page.getByTestId("research-banner-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(banner.locator(".research-banner-text")).toHaveText(
      RESEARCH_BANNER_STRIP_COLLAPSED,
    );
    await expect(banner).not.toContainText(
      "Annual Ground Rent figures are not published yet",
    );

    const contentBurger = page.getByTestId("site-nav-menu-btn");
    await expect(contentBurger).toBeVisible();
    await assertBannerClears(banner, contentBurger, "burger menu");
    await assertCenterTappable(contentBurger, "burger menu");

    await contentBurger.click();
    const panel = page.getByTestId("site-nav-panel");
    await expect(panel).toBeVisible();
    const menuLinks = panel.getByRole("link");
    await expect(menuLinks.nth(0)).toHaveText("Map");
    await expect(menuLinks.nth(1)).toHaveText("About");
    const mapBox = await menuLinks.nth(0).boundingBox();
    const aboutBox = await menuLinks.nth(1).boundingBox();
    expect(mapBox, "Map link box").toBeTruthy();
    expect(aboutBox, "About link box").toBeTruthy();
    expect(mapBox!.y, "Map should be near the top").toBeLessThan(200);
    expect(aboutBox!.y, "About should sit under Map").toBeGreaterThan(
      mapBox!.y,
    );
    expect(aboutBox!.y, "About should stay near the top").toBeLessThan(280);
    await assertLinkTopmost(menuLinks.nth(0), "Map");
    await assertLinkTopmost(menuLinks.nth(1), "About");
    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();

    const collapsedFit = await banner.locator(".research-banner-text").evaluate((el) => {
      const range = document.createRange();
      range.selectNodeContents(el);
      const lines = [...range.getClientRects()].filter(
        (rect) => rect.width > 0 && rect.height > 0,
      );
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      let more: DOMRect | null = null;
      let node = walker.nextNode();
      while (node) {
        const value = node.textContent ?? "";
        const index = value.lastIndexOf("More");
        if (index >= 0) {
          const word = document.createRange();
          word.setStart(node, index);
          word.setEnd(node, index + "More".length);
          more = word.getBoundingClientRect();
          break;
        }
        node = walker.nextNode();
      }
      return {
        lines: lines.length,
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        moreTop: more?.top ?? -1,
        moreBottom: more?.bottom ?? -1,
        moreLeft: more?.left ?? -1,
        moreRight: more?.right ?? -1,
        moreWidth: more?.width ?? 0,
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
      };
    });
    expect(collapsedFit.moreWidth).toBeGreaterThan(0);
    expect(collapsedFit.moreLeft).toBeGreaterThanOrEqual(0);
    expect(collapsedFit.moreRight).toBeLessThanOrEqual(collapsedFit.innerWidth);
    expect(collapsedFit.moreTop).toBeGreaterThanOrEqual(0);
    expect(collapsedFit.moreBottom).toBeLessThanOrEqual(collapsedFit.innerHeight);
    expect(collapsedFit.scrollWidth).toBeLessThanOrEqual(collapsedFit.clientWidth);
    expect(collapsedFit.lines).toBeGreaterThan(0);
    expect(collapsedFit.lines).toBeLessThanOrEqual(2);

    await toggle.click();
    await expect(banner).toHaveAttribute("data-expanded", "1");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(banner).toHaveAttribute("data-banner-variant", "default");
    await expect(banner.locator(".research-banner-text")).toHaveText(
      `${RESEARCH_BANNER_LEAD} ${RESEARCH_BANNER_BODY}`,
    );
    await expect(banner).not.toContainText("experimental");
    await assertBannerClears(banner, contentBurger, "burger with banner expanded");
    await assertCenterTappable(contentBurger, "burger with banner expanded");

    await toggle.click();
    await expect(banner).toHaveAttribute("data-expanded", "0");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await expect(banner.locator(".research-banner-text")).toHaveText(
      RESEARCH_BANNER_STRIP_COLLAPSED,
    );

    // Map place-card chrome stays usable with no banner.
    await openMap(page);
    await expect(page.getByTestId("research-banner")).toHaveCount(0);
    await search.fill("55.86090, -4.25140");
    await page.locator(".hud-search-go").click();
    const card = page.getByTestId("place-card");
    const cardTitle = page.getByTestId("place-card-place");
    const cardClose = page.getByRole("button", { name: "Close place card" });
    await expect(card).toBeVisible({ timeout: 30_000 });
    await expect(cardTitle).toBeVisible();
    await expect(page.getByTestId("research-banner")).toHaveCount(0);
    await assertCenterTappable(cardTitle, "place card title");
    await assertCenterTappable(cardClose, "place card close");
    await assertCenterTappable(burger, "burger with place card open");
    await assertCenterTappable(search, "search with place card open");
  });

  test("methodology strip expands and shows experimental", async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto("/methodology");

    const banner = page.getByTestId("research-banner");
    await expect(banner).toBeVisible({ timeout: 15_000 });
    await expect(banner).toHaveAttribute("data-strip", "1");
    await expect(banner).toHaveAttribute("data-banner-variant", "methodology");
    await expect(banner).toHaveAttribute("data-expanded", "0");
    await expect(banner.locator(".research-banner-text")).toHaveText(
      RESEARCH_BANNER_STRIP_COLLAPSED,
    );
    await expect(banner).not.toContainText("experimental");

    const toggle = page.getByTestId("research-banner-toggle");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-expanded", "false");
    await toggle.click();

    await expect(banner).toHaveAttribute("data-expanded", "1");
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    await expect(banner).toContainText("experimental");
    await expect(banner.locator(".research-banner-text")).toContainText(
      "Scot-LAND is experimental",
    );
  });

  test("suggestions open collapse expanded strip so first result is tappable", async ({
    page,
  }) => {
    test.setTimeout(90_000);

    await page.route("**/backend/place**", async (route) => {
      const url = new URL(route.request().url());
      const q = (url.searchParams.get("q") || "").toUpperCase();
      if (q.includes("EH1")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            kind: "places",
            matches: [
              {
                label: "EH1 1YZ, Edinburgh",
                lat: 55.9508,
                lng: -3.1875,
              },
              {
                label: "EH1 1AA, Edinburgh",
                lat: 55.9533,
                lng: -3.1883,
              },
            ],
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ kind: "places", matches: [] }),
      });
    });

    await openMap(page);
    // MAP-HINTS-OFF-1: no banner on map — suggestions stay tappable without strip.
    await expect(page.getByTestId("research-banner")).toHaveCount(0);

    const search = page.locator("#place-query");
    await search.fill("EH1 1YZ");
    const first = page.locator("#place-suggestions button").first();
    await expect(first).toBeVisible({ timeout: 20_000 });
    await expect(first).toContainText(/EH1/i);

    await expect(page.locator(".app-shell")).toHaveClass(/suggest-open/);
    await expect(page.getByTestId("research-banner")).toHaveCount(0);

    // First suggestion must be the top hit.
    await assertCenterTappable(first, "first suggestion");
    const suggestBox = await first.boundingBox();
    expect(suggestBox, "first suggestion box").toBeTruthy();
    const mid = {
      x: suggestBox!.x + suggestBox!.width / 2,
      y: suggestBox!.y + suggestBox!.height / 2,
    };
    const hit = await page.evaluate(({ x, y }) => {
      const el = document.elementFromPoint(x, y);
      return (
        el?.closest("button")?.textContent?.trim() ?? el?.tagName ?? "none"
      );
    }, mid);
    expect(hit).toMatch(/EH1/i);

    await first.click();
    await expect(page.getByTestId("place-card")).toBeVisible({
      timeout: 30_000,
    });
  });
});

async function openMap(page: Page) {
  await page.goto("/");
  await page.locator(".maplibregl-canvas").waitFor();
  await page.locator("#place-query").waitFor();
}

type Box = { x: number; y: number; width: number; height: number };

function overlaps(a: Box, b: Box) {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

/** Banner must not geometrically cover the target. */
async function assertBannerClears(
  banner: Locator,
  target: Locator,
  label: string,
) {
  await expect(banner, "banner").toBeVisible();
  await expect(target, label).toBeVisible();
  const bannerBox = await banner.boundingBox();
  const targetBox = await target.boundingBox();
  expect(bannerBox, "banner box").toBeTruthy();
  expect(targetBox, `${label} box`).toBeTruthy();
  expect(
    overlaps(bannerBox!, targetBox!),
    `${label} overlaps research banner`,
  ).toBe(false);
}

/**
 * Centre of a menu link must be the topmost hit (elementFromPoint → that link).
 */
async function assertLinkTopmost(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const result = await locator.evaluate((el, expected) => {
    const box = el.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const hit = document.elementFromPoint(x, y);
    const link = hit?.closest?.("a") as HTMLAnchorElement | null;
    const text = link?.textContent?.trim() ?? "";
    return {
      text,
      ok: text === expected,
      x,
      y,
      tag: hit?.tagName ?? "none",
    };
  }, label);
  expect(
    result.ok,
    `${label} centre not topmost (hit "${result.text || result.tag}" at ${result.x.toFixed(1)}, ${result.y.toFixed(1)})`,
  ).toBe(true);
}

/**
 * Centre of the control must not sit under the research banner.
 * (Other chrome such as the service-busy strip is out of SW-016 scope.)
 */
async function assertCenterTappable(locator: Locator, label: string) {
  await expect(locator, label).toBeVisible();
  const result = await locator.evaluate((el) => {
    const box = el.getBoundingClientRect();
    const x = box.left + box.width / 2;
    const y = box.top + box.height / 2;
    const hit = document.elementFromPoint(x, y);
    const banner = hit?.closest?.(
      '[data-testid="research-banner"]',
    ) as Element | null;
    const describe = (node: Element | null) => {
      if (!node) return "nothing";
      const id = node.id ? `#${node.id}` : "";
      const cls = (node.getAttribute("class") || "")
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .map((name) => `.${name}`)
        .join("");
      return `${node.tagName.toLowerCase()}${id}${cls}`;
    };
    return {
      blockedByBanner: !!banner,
      hit: describe(hit),
      x,
      y,
    };
  });
  expect(
    result.blockedByBanner,
    `${label} centre covered by research banner (hit ${result.hit} at ${result.x.toFixed(1)}, ${result.y.toFixed(1)})`,
  ).toBe(false);
}
