import { expect, test, type Page } from "@playwright/test";

/**
 * BANNER-FIT-1 (SW-074) — collapsed research banner on content pages at 390.
 * Two lines, no horizontal clip, and More stays inside the viewport.
 */

const PAGES = ["/about", "/developers/api"] as const;

async function assertCollapsedBannerFits(page: Page) {
  const banner = page.getByTestId("research-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toHaveAttribute("data-strip", "1");
  await expect(banner).toHaveAttribute("data-expanded", "0");

  const text = banner.locator(".research-banner-text");
  const fit = await text.evaluate((el) => {
    const style = getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight);
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
    const bannerEl = el.closest("[data-testid='research-banner']");
    const bannerStyle = bannerEl ? getComputedStyle(bannerEl) : null;
    const pad = bannerStyle
      ? parseFloat(bannerStyle.paddingTop) + parseFloat(bannerStyle.paddingBottom)
      : 0;
    const border = bannerStyle
      ? parseFloat(bannerStyle.borderTopWidth) +
        parseFloat(bannerStyle.borderBottomWidth)
      : 0;
    return {
      scrollWidth: el.scrollWidth,
      clientWidth: el.clientWidth,
      lines: lines.length,
      lineHeight,
      pad,
      border,
      moreTop: more?.top ?? -1,
      moreBottom: more?.bottom ?? -1,
      moreLeft: more?.left ?? -1,
      moreRight: more?.right ?? -1,
      moreWidth: more?.width ?? 0,
      innerWidth: window.innerWidth,
      innerHeight: window.innerHeight,
      bannerHeight: bannerEl?.getBoundingClientRect().height ?? 0,
    };
  });

  expect(fit.moreWidth).toBeGreaterThan(0);
  expect(fit.moreLeft).toBeGreaterThanOrEqual(0);
  expect(fit.moreRight).toBeLessThanOrEqual(fit.innerWidth);
  expect(fit.moreTop).toBeGreaterThanOrEqual(0);
  expect(fit.moreBottom).toBeLessThanOrEqual(fit.innerHeight);
  expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth);
  expect(fit.lines).toBeLessThanOrEqual(2);
  expect(fit.lines).toBeGreaterThan(0);
  const contentHeight = fit.bannerHeight - fit.pad - fit.border;
  expect(contentHeight).toBeLessThanOrEqual(fit.lineHeight * 2 + 8);
}

test.describe("BANNER-FIT-1 at 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  for (const path of PAGES) {
    test(`${path} collapsed banner wraps and keeps More visible`, async ({
      page,
    }) => {
      await page.goto(path);
      await assertCollapsedBannerFits(page);
    });
  }
});
