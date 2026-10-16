import { stubLayersAddQuiet } from "./_layersAddStub";
import { expect, test, type Page } from "@playwright/test";

/**
 * LOGO-FIT-1 — map logo has no white badge. The mark matches /about.
 * Tap target stays ≥44px via transparent padding. No skips.
 */

const MARK = "/logo-mark-h3.png";

const HEALTH_OK = {
  status: "ok",
  routers: {
    "api.agr_routes": { loaded: true },
    "api.platform_routes": { loaded: true },
  },
};

const EMPTY_FC = { type: "FeatureCollection", features: [] };

async function stubMapBackend(page: Page) {
  await page.route("**/backend/**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(EMPTY_FC),
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
      body: JSON.stringify({ layers: [] }),
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
  test.describe(`LOGO-FIT-1 ${viewport.width}`, () => {
    test.use({ viewport });

    test("map logo wrapper has no badge and matches the about mark", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      await stubMapBackend(page);

      await page.goto("/about");
      const aboutLogo = page.getByTestId("site-nav-brand").locator("img");
      await expect(aboutLogo).toBeVisible();
      await expect(aboutLogo).toHaveAttribute("src", MARK);
      const aboutBox = await aboutLogo.boundingBox();
      expect(aboutBox, "about logo box").not.toBeNull();

      await page.goto("/");
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      const wrapper = page.locator("a.hud-wordmark");
      const mapLogo = wrapper.locator("img");
      await expect(wrapper).toBeVisible();
      await expect(mapLogo).toBeVisible();
      await expect(mapLogo).toHaveAttribute("src", MARK);

      const style = await wrapper.evaluate((el) => {
        const computed = getComputedStyle(el);
        return {
          backgroundColor: computed.backgroundColor,
          backgroundImage: computed.backgroundImage,
          borderTopWidth: computed.borderTopWidth,
          borderRightWidth: computed.borderRightWidth,
          borderBottomWidth: computed.borderBottomWidth,
          borderLeftWidth: computed.borderLeftWidth,
          borderTopStyle: computed.borderTopStyle,
          borderRightStyle: computed.borderRightStyle,
          borderBottomStyle: computed.borderBottomStyle,
          borderLeftStyle: computed.borderLeftStyle,
        };
      });
      expect(style.backgroundColor).toBe("rgba(0, 0, 0, 0)");
      expect(style.backgroundImage).toBe("none");
      expect(style.borderTopWidth).toBe("0px");
      expect(style.borderRightWidth).toBe("0px");
      expect(style.borderBottomWidth).toBe("0px");
      expect(style.borderLeftWidth).toBe("0px");
      expect(style.borderTopStyle).toBe("none");
      expect(style.borderRightStyle).toBe("none");
      expect(style.borderBottomStyle).toBe("none");
      expect(style.borderLeftStyle).toBe("none");

      const mapBox = await mapLogo.boundingBox();
      const tapBox = await wrapper.boundingBox();
      expect(mapBox, "map logo box").not.toBeNull();
      expect(tapBox, "map logo tap target").not.toBeNull();
      expect(mapBox!.width).toBe(aboutBox!.width);
      expect(mapBox!.height).toBe(aboutBox!.height);
      expect(mapBox!.width).toBe(40);
      expect(mapBox!.height).toBe(40);
      expect(tapBox!.width).toBeGreaterThanOrEqual(44);
      expect(tapBox!.height).toBeGreaterThanOrEqual(44);
    });
  });
}
