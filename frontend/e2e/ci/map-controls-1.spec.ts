import AxeBuilder from "@axe-core/playwright";
import {
  CI_TINY_PNG,
  EMPTY_GLYPH_PBF,
  injectEsriBasemapKey,
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";
import { expect, test } from "./_fixtures";
import { type Page } from "@playwright/test";
import { existsSync, readFileSync } from "node:fs";
import { join } from "node:path";

registerOpenFreeMapFontStub();

/**
 * MAP-CONTROLS-1 r3 — MC1–MC14 equivalents.
 * Aerial loads Esri imagery via fixture. Never /api/ofm.
 */

const ESRI_STYLE_URL =
  "https://basemapstyles-api.arcgis.com/arcgis/rest/services/styles/v2/styles/arcgis/imagery";

const FIXTURE_PATH = join(
  process.cwd(),
  "e2e",
  "fixtures",
  "esri-imagery-style.json",
);

type EsriStyle = {
  sprite: string;
  glyphs: string;
  sources: Record<
    string,
    { tiles?: string[]; url?: string; attribution?: string; type?: string }
  >;
};

function loadEsriFixture(): EsriStyle {
  if (!existsSync(FIXTURE_PATH)) {
    throw new Error("fixture missing: esri-imagery-style.json");
  }
  return JSON.parse(readFileSync(FIXTURE_PATH, "utf8")) as EsriStyle;
}

async function routeEsriFixture(page: Page, style: EsriStyle) {
  const spriteJson = `${style.sprite}.json`;
  const spritePng = `${style.sprite}.png`;

  await page.route(`${ESRI_STYLE_URL}**`, async (route) => {
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
      body: JSON.stringify({ image: "root.png", width: 1, height: 1 }),
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
}

function relLum(channel: number): number {
  const s = channel / 255;
  return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
}

function contrast(a: number[], b: number[]): number {
  const lum = (rgb: number[]) =>
    0.2126 * relLum(rgb[0]!) + 0.7152 * relLum(rgb[1]!) + 0.0722 * relLum(rgb[2]!);
  const left = lum(a);
  const right = lum(b);
  const lighter = Math.max(left, right);
  const darker = Math.min(left, right);
  return (lighter + 0.05) / (darker + 0.05);
}

function parseRgb(value: string): number[] {
  const match = value.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/);
  expect(match, value).toBeTruthy();
  return [Number(match![1]), Number(match![2]), Number(match![3])];
}

async function camera(page: Page) {
  return page.locator("#map").evaluate((el) => ({
    lng: Number((el as HTMLElement).dataset.lng || "NaN"),
    lat: Number((el as HTMLElement).dataset.lat || "NaN"),
    zoom: Number((el as HTMLElement).dataset.zoom || "NaN"),
  }));
}

async function waitForCamera(page: Page) {
  await expect
    .poll(async () => (await camera(page)).zoom, { timeout: 20_000 })
    .toBeGreaterThan(0);
}

async function prepareMap(page: Page) {
  await injectEsriBasemapKey(page);
  await routeEsriFixture(page, loadEsriFixture());
  await stubMapCardsBackend(page);
  await openMap(page);
  await waitForCamera(page);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
] as const) {
  test.describe(`MAP-CONTROLS-1 ${viewport.width}`, () => {
    test.use({ viewport });

    test("styles, sizes, contrast, and no style proxy", async ({ page }) => {
      test.setTimeout(120_000);
      const styleUrls: string[] = [];
      page.on("request", (request) => {
        const url = request.url();
        if (
          url.includes("/styles/") ||
          url.includes("/api/ofm") ||
          /arcgis\.com/i.test(url)
        ) {
          styleUrls.push(url);
        }
      });
      await prepareMap(page);

      expect(styleUrls.some((url) => url.includes("/api/ofm"))).toBe(false);
      expect(styleUrls.some((url) => url.includes("tiles.openfreemap.org"))).toBe(
        true,
      );

      await expect(page.getByRole("radiogroup", { name: "Map style" })).toHaveCount(
        0,
      );
      await expect(page.getByTestId("basemap-option-light")).toHaveCount(0);
      await expect(page.getByTestId("basemap-option-detailed")).toHaveCount(0);
      await expect(page.getByTestId("basemap-toggle-narrow")).toHaveCount(0);
      await expect(page.getByText("Detailed", { exact: true })).toHaveCount(0);
      await expect(page.locator(".basemap-switcher-wide")).toHaveCount(0);
      await expect(page.locator(".basemap-switcher-preview")).toHaveCount(0);
      await expect(page.locator(".maplibregl-ctrl-attrib")).toHaveCount(0);

      const toggle = page.getByTestId("basemap-switcher");
      await expect(toggle).toBeVisible();
      await expect(toggle).toHaveAttribute("aria-label", "Aerial map");
      await expect(toggle).toHaveAttribute("title", "Aerial map");
      await expect(toggle).toHaveAttribute("aria-pressed", "false");
      const face = toggle.locator(".basemap-switcher-face");
      await expect(face).not.toContainText("Light");
      await expect(face).not.toContainText("Detailed");
      await expect(face).not.toContainText("Simple");
      await expect(face).not.toContainText("Aerial");

      const box = await toggle.boundingBox();
      expect(box!.width).toBeCloseTo(48, 0);
      expect(box!.height).toBeCloseTo(48, 0);
      expect(box!.width).toBeGreaterThanOrEqual(44);
      expect(box!.height).toBeGreaterThanOrEqual(44);

      const before = await camera(page);
      const seen = styleUrls.length;
      await toggle.click();
      await expect(toggle).toHaveAttribute("aria-pressed", "true");
      await expect
        .poll(() => styleUrls.length, { timeout: 20_000 })
        .toBeGreaterThan(seen);
      const imagery = styleUrls.filter((url) =>
        url.includes("basemapstyles-api.arcgis.com"),
      );
      expect(imagery.length).toBeGreaterThan(0);
      expect(
        imagery.every((url) => url.startsWith(ESRI_STYLE_URL)),
      ).toBe(true);
      expect(styleUrls.some((url) => url.includes("/api/ofm"))).toBe(false);
      expect(styleUrls.some((url) => /styles\/liberty/i.test(url))).toBe(false);
      await waitForCamera(page);
      const after = await camera(page);
      expect(Math.abs(after.lng - before.lng)).toBeLessThanOrEqual(1e-5);
      expect(Math.abs(after.lat - before.lat)).toBeLessThanOrEqual(1e-5);
      expect(Math.abs(after.zoom - before.zoom)).toBeLessThanOrEqual(0.01);

      await expect(page.getByRole("tooltip")).toHaveText(
        "Simple map",
      );

      await toggle.focus();
      const ring = await toggle.evaluate((el) => {
        const style = getComputedStyle(el);
        return {
          outline: style.outlineColor,
          width: style.outlineWidth,
          shadow: style.boxShadow,
        };
      });
      expect(ring.width).toBe("3px");
      expect(ring.shadow).toContain("11, 30, 58");

      const zoomGroup = page.locator(
        ".maplibregl-ctrl-bottom-right .maplibregl-ctrl-group",
      );
      const toggleBox = await toggle.boundingBox();
      const zoomBox = await zoomGroup.boundingBox();
      const zoomIn = await page.locator(".maplibregl-ctrl-zoom-in").boundingBox();
      const zoomOut = await page.locator(".maplibregl-ctrl-zoom-out").boundingBox();
      expect(toggleBox!.width).toBeCloseTo(48, 0);
      expect(toggleBox!.height).toBeCloseTo(48, 0);
      expect(zoomBox!.width).toBeCloseTo(48, 0);
      expect(zoomIn!.height).toBeCloseTo(48, 0);
      expect(zoomOut!.height).toBeCloseTo(48, 0);
      expect(
        Math.abs(toggleBox!.x + toggleBox!.width - (zoomBox!.x + zoomBox!.width)),
      ).toBeLessThanOrEqual(1);
      const gap = zoomBox!.y - (toggleBox!.y + toggleBox!.height);
      expect(Math.abs(gap - 8)).toBeLessThanOrEqual(1);

      const toggleStyle = await toggle.evaluate((el) => {
        const style = getComputedStyle(el);
        return {
          radius: style.borderRadius,
          border: style.border,
          shadow: style.boxShadow,
        };
      });
      const zoomStyle = await zoomGroup.evaluate((el) => {
        const style = getComputedStyle(el);
        return {
          radius: style.borderRadius,
          border:
            style.borderTopWidth +
            " " +
            style.borderTopStyle +
            " " +
            style.borderTopColor,
          shadow: style.boxShadow,
        };
      });
      expect(toggleStyle.radius).toBe("24px");
      expect(zoomStyle.radius).toBe("24px");
      expect(toggleStyle.border).toContain("1px");
      // R3.6 pressed adds a 2px accent ring on top of --ctrl-shadow.
      expect(toggleStyle.shadow).toContain("rgba(11, 30, 58, 0.16)");
      expect(toggleStyle.shadow).toContain("rgb(29, 79, 145)");
      expect(zoomStyle.shadow).toContain("rgba(11, 30, 58, 0.16)");

      // Pressed Aerial: accent ring / contrast still readable on the control.
      const pressedColors = await toggle.evaluate((el) => {
        const style = getComputedStyle(el);
        return { color: style.color, background: style.backgroundColor };
      });
      const colorRgb = parseRgb(pressedColors.color);
      const bgRgb = parseRgb(pressedColors.background);
      // Globe/icon colour vs background when pressed — allow white-on-accent.
      if (pressedColors.background !== "rgba(0, 0, 0, 0)") {
        expect(contrast(colorRgb, bgRgb)).toBeGreaterThanOrEqual(3);
      }

      const controls = [
        page.locator(".maplibregl-ctrl-zoom-in"),
        page.locator(".maplibregl-ctrl-zoom-out"),
        toggle,
      ];
      for (const control of controls) {
        const controlBox = await control.boundingBox();
        expect(controlBox!.width).toBeGreaterThanOrEqual(44);
        expect(controlBox!.height).toBeGreaterThanOrEqual(44);
      }

      await expect(page.getByText("Show the area at map centre")).toHaveCount(0);

      const axe = await new AxeBuilder({ page })
        .include(".basemap-switcher")
        .include(".maplibregl-ctrl-bottom-right")
        .analyze();
      expect(axe.violations).toEqual([]);
    });
  });
}

test.describe("MAP-CONTROLS-1 deep link", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("opens Simple and keeps z/c after Aerial", async ({ page }) => {
    test.setTimeout(120_000);
    await injectEsriBasemapKey(page);
    await routeEsriFixture(page, loadEsriFixture());
    await stubMapCardsBackend(page);
    await page.goto("/map?z=12&c=-3.18830,55.95330");
    await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
    await expect
      .poll(async () => (await camera(page)).zoom, { timeout: 20_000 })
      .toBeGreaterThan(11);
    const view = await camera(page);
    expect(Math.abs(view.zoom - 12)).toBeLessThanOrEqual(0.01);
    expect(Math.abs(view.lng - -3.1883)).toBeLessThanOrEqual(1e-4);
    expect(Math.abs(view.lat - 55.9533)).toBeLessThanOrEqual(1e-4);
    const toggle = page.getByTestId("basemap-switcher");
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-pressed", "true");
    const url = new URL(page.url());
    expect(url.searchParams.get("z")).toBe("12");
    expect(url.searchParams.get("c")).toBe("-3.18830,55.95330");
    expect(url.searchParams.get("style")).toBeNull();
  });
});
