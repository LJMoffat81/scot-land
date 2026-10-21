import {
  injectEsriBasemapKey,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";
import { type Locator, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * MAP-BRAND-1 — shared lockup on the map and content pages.
 * Mark only at ≤480. Wordmark visible above that. No overlap with chrome.
 */

type Box = { x: number; y: number; width: number; height: number };

function overlaps(a: Box, b: Box): boolean {
  return !(
    a.x + a.width <= b.x ||
    b.x + b.width <= a.x ||
    a.y + a.height <= b.y ||
    b.y + b.height <= a.y
  );
}

async function boxOf(locator: Locator): Promise<Box | null> {
  if ((await locator.count()) === 0) return null;
  if (!(await locator.isVisible())) return null;
  return locator.boundingBox();
}

async function assertClear(a: Locator, b: Locator, label: string) {
  const left = await boxOf(a);
  const right = await boxOf(b);
  if (!left || !right) return;
  expect(overlaps(left, right), label).toBe(false);
}

const WIDTHS = [1280, 768, 480, 390, 360] as const;

for (const width of WIDTHS) {
  test.describe(`MAP-BRAND-1 ${width}`, () => {
    test.use({ viewport: { width, height: width >= 768 ? 800 : 844 } });

    test("shared lockup, breakpoint, and no overlap", async ({ page }) => {
      test.setTimeout(120_000);
      await page.goto("/about");
      const aboutBrand = page.getByTestId("site-nav-brand");
      await expect(aboutBrand).toBeVisible();
      await expect(aboutBrand).toHaveAttribute("aria-label", "Scot-LAND home");
      if (width <= 480) {
        await expect(aboutBrand.locator(".site-nav-wordmark")).toBeHidden();
      } else {
        await expect(aboutBrand.locator(".site-nav-wordmark")).toBeVisible();
        await expect(aboutBrand.locator(".site-nav-wordmark")).toHaveText("Scot-LAND");
      }

      await injectEsriBasemapKey(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      const brand = page.locator(".hud-brand").getByTestId("site-nav-brand");
      await expect(brand).toBeVisible();
      await expect(brand.locator("img")).toHaveAttribute("src", /\/logo-mark-h3\.png$/);
      const tap = await brand.boundingBox();
      expect(tap!.width).toBeGreaterThanOrEqual(44);
      expect(tap!.height).toBeGreaterThanOrEqual(44);
      if (width <= 480) {
        await expect(brand.locator(".site-nav-wordmark")).toBeHidden();
      } else {
        await expect(brand.locator(".site-nav-wordmark")).toBeVisible();
      }
      await expect(page.locator(".hud-wordmark")).toHaveCount(0);

      const frame = await brand.evaluate((el) => {
        const style = getComputedStyle(el);
        return {
          radius: style.borderRadius,
          shadow: style.boxShadow,
          background: style.backgroundColor,
        };
      });
      expect(frame.radius).toBe("0px");
      expect(frame.shadow).toBe("none");
      expect(frame.background).toBe("rgba(0, 0, 0, 0)");

      const search = page.locator(".hud-search");
      const layers = page.getByTestId("hud-layers-btn");
      const banner = page.getByTestId("research-banner");
      const basemap = page.getByTestId("basemap-switcher");
      await assertClear(brand, search, "lockup vs search");
      await assertClear(brand, layers, "lockup vs Layers");
      await assertClear(brand, banner, "lockup vs banner");
      await assertClear(brand, basemap, "lockup vs basemap");

      await page.locator("#place-query").fill("55.95330, -3.18830");
      await page.locator(".hud-search-go").click();
      const card = page.getByTestId("place-card");
      await expect(card).toBeVisible({ timeout: 30_000 });
      await assertClear(brand, card, "lockup vs place card");
    });
  });
}
