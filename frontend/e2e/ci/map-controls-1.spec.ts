import AxeBuilder from "@axe-core/playwright";
import {
  openMap,
  registerOpenFreeMapFontStub,
  stubMapCardsBackend,
} from "./_mapCardsHelpers";
import { expect, test, type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * MAP-CONTROLS-1 — MC1–MC12 as amended.
 * Detailed loads the OpenFreeMap Liberty style directly. Never /api/ofm.
 */

const LIBERTY = "https://tiles.openfreemap.org/styles/liberty";

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
        if (url.includes("/styles/") || url.includes("/api/ofm")) {
          styleUrls.push(url);
        }
      });
      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForCamera(page);

      expect(styleUrls.some((url) => url.includes("/api/ofm"))).toBe(false);
      expect(styleUrls.some((url) => url.includes("tiles.openfreemap.org"))).toBe(
        true,
      );

      const narrow = viewport.width <= 900;
      if (!narrow) {
        const group = page.getByRole("radiogroup", { name: "Map style" });
        await expect(group).toBeVisible();
        const simple = page.getByRole("radio", { name: "Simple" });
        const detailed = page.getByRole("radio", { name: "Detailed" });
        await expect(simple).toHaveAttribute("aria-checked", "true");
        await expect(detailed).toHaveAttribute("aria-checked", "false");
        await expect(simple).toHaveAttribute("tabindex", "0");
        await expect(detailed).toHaveAttribute("tabindex", "-1");

        const before = await camera(page);
        const seen = styleUrls.length;
        await detailed.click();
        await expect(detailed).toHaveAttribute("aria-checked", "true");
        await expect
          .poll(() => styleUrls.length, { timeout: 20_000 })
          .toBeGreaterThan(seen);
        const liberty = styleUrls.filter((url) => url.includes("styles/liberty"));
        expect(liberty.length).toBeGreaterThan(0);
        expect(liberty.every((url) => url.startsWith(LIBERTY))).toBe(true);
        expect(styleUrls.some((url) => url.includes("/api/ofm"))).toBe(false);
        await waitForCamera(page);
        const after = await camera(page);
        expect(Math.abs(after.lng - before.lng)).toBeLessThanOrEqual(1e-5);
        expect(Math.abs(after.lat - before.lat)).toBeLessThanOrEqual(1e-5);
        expect(Math.abs(after.zoom - before.zoom)).toBeLessThanOrEqual(0.01);

        await detailed.focus();
        await page.keyboard.press("ArrowLeft");
        await expect(simple).toHaveAttribute("aria-checked", "true");
        await expect(simple).toBeFocused();
        await expect(detailed).toHaveAttribute("tabindex", "-1");
        const ring = await simple.evaluate((el) => {
          const style = getComputedStyle(el);
          return {
            outline: style.outlineColor,
            width: style.outlineWidth,
            shadow: style.boxShadow,
          };
        });
        expect(ring.width).toBe("3px");
        expect(ring.shadow).toContain("11, 30, 58");

        const pill = await group.boundingBox();
        const zoomGroup = page.locator(
          ".maplibregl-ctrl-bottom-right .maplibregl-ctrl-group",
        );
        const zoomBox = await zoomGroup.boundingBox();
        const zoomIn = await page.locator(".maplibregl-ctrl-zoom-in").boundingBox();
        const zoomOut = await page.locator(".maplibregl-ctrl-zoom-out").boundingBox();
        expect(pill!.height).toBeCloseTo(48, 0);
        expect(zoomBox!.width).toBeCloseTo(48, 0);
        expect(zoomIn!.height).toBeCloseTo(48, 0);
        expect(zoomOut!.height).toBeCloseTo(48, 0);
        expect(Math.abs(pill!.x + pill!.width - (zoomBox!.x + zoomBox!.width))).toBeLessThanOrEqual(1);
        const gap = zoomBox!.y - (pill!.y + pill!.height);
        expect(Math.abs(gap - 8)).toBeLessThanOrEqual(1);

        const pillStyle = await group.evaluate((el) => {
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
            border: style.borderTopWidth + " " + style.borderTopStyle + " " + style.borderTopColor,
            shadow: style.boxShadow,
          };
        });
        expect(pillStyle.radius).toBe("24px");
        expect(zoomStyle.radius).toBe("24px");
        expect(pillStyle.border).toContain("1px");
        expect(pillStyle.border).toContain("107, 118, 132");
        expect(pillStyle.shadow).toBe(zoomStyle.shadow);

        const selectedColors = await simple.evaluate((el) => {
          const style = getComputedStyle(el);
          return { color: style.color, background: style.backgroundColor };
        });
        expect(
          contrast(parseRgb(selectedColors.color), parseRgb(selectedColors.background)),
        ).toBeGreaterThanOrEqual(4.5);
      } else {
        await expect(page.locator(".basemap-switcher-wide")).toBeHidden();
        const toggle = page.getByTestId("basemap-toggle-narrow");
        await expect(toggle).toBeVisible();
        const box = await toggle.boundingBox();
        expect(box!.width).toBeGreaterThanOrEqual(48);
        expect(box!.height).toBeCloseTo(48, 0);
        await expect(toggle).toHaveText("Detailed");
        await expect(toggle).toHaveAttribute("aria-pressed", "false");
        const before = await camera(page);
        await toggle.click();
        await expect(toggle).toHaveAttribute("aria-pressed", "true");
        await expect
          .poll(() => styleUrls.some((url) => url.includes("styles/liberty")))
          .toBe(true);
        expect(styleUrls.some((url) => url.includes("/api/ofm"))).toBe(false);
        await waitForCamera(page);
        const after = await camera(page);
        expect(Math.abs(after.lng - before.lng)).toBeLessThanOrEqual(1e-5);
        expect(Math.abs(after.lat - before.lat)).toBeLessThanOrEqual(1e-5);
        expect(Math.abs(after.zoom - before.zoom)).toBeLessThanOrEqual(0.01);
        expect(box!.width).toBeGreaterThanOrEqual(44);
        expect(box!.height).toBeGreaterThanOrEqual(44);
      }

      const controls = [
        page.locator(".maplibregl-ctrl-zoom-in"),
        page.locator(".maplibregl-ctrl-zoom-out"),
        narrow
          ? page.getByTestId("basemap-toggle-narrow")
          : page.getByRole("radiogroup", { name: "Map style" }),
      ];
      for (const control of controls) {
        const box = await control.boundingBox();
        expect(box!.width).toBeGreaterThanOrEqual(44);
        expect(box!.height).toBeGreaterThanOrEqual(44);
      }

      await expect(page.locator(".basemap-switcher-preview")).toHaveCount(0);
      await expect(page.getByTestId("basemap-switcher")).not.toContainText("Light");
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

  test("opens Simple and keeps z/c after Detailed", async ({ page }) => {
    test.setTimeout(120_000);
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
    await expect(page.getByTestId("basemap-option-light")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    await page.getByTestId("basemap-option-detailed").click();
    await expect(page.getByTestId("basemap-option-detailed")).toHaveAttribute(
      "aria-checked",
      "true",
    );
    const url = new URL(page.url());
    expect(url.searchParams.get("z")).toBe("12");
    expect(url.searchParams.get("c")).toBe("-3.18830,55.95330");
  });
});
