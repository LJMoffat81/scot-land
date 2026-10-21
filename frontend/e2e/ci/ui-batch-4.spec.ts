import { assertConsoleClean, attachConsoleGate, injectEsriBasemapKey, openMap, registerOpenFreeMapFontStub, stubMapCardsBackend, waitForMap } from "./_mapCardsHelpers";
import { test, expect } from "./_fixtures";
import { type Page } from "@playwright/test";

import { AREA_LEVELS } from "../../lib/areaLevels";

registerOpenFreeMapFontStub();

const SEA = { lat: 56.5, lng: -1.5 };


async function assertMoreInView(page: Page) {
  const banner = page.getByTestId("research-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toHaveAttribute("data-expanded", "0");
  const fit = await banner.locator(".research-banner-text").evaluate((el) => {
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
  expect(fit.moreWidth).toBeGreaterThan(0);
  expect(fit.moreLeft).toBeGreaterThanOrEqual(0);
  expect(fit.moreRight).toBeLessThanOrEqual(fit.innerWidth + 0.5);
  expect(fit.moreTop).toBeGreaterThanOrEqual(0);
  expect(fit.moreBottom).toBeLessThanOrEqual(fit.innerHeight + 0.5);
  expect(fit.scrollWidth).toBeLessThanOrEqual(fit.clientWidth + 1);
}

test.describe("UI-BATCH-4 contact links off", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("no page links to /about#contact", async ({ page }) => {
    test.setTimeout(180_000);
    await stubMapCardsBackend(page);
    const sitemap = await page.request.get("/sitemap.xml");
    expect(sitemap.ok()).toBe(true);
    const xml = await sitemap.text();
    const paths = [
      ...new Set(
        [...xml.matchAll(/<loc>([^<]+)<\/loc>/g)].map(
          (match) => new URL(match[1]!).pathname,
        ),
      ),
    ];
    expect(paths.length).toBeGreaterThan(5);
    for (const path of paths) {
      await page.goto(path);
      await expect(page.locator('a[href="/about#contact"]')).toHaveCount(0);
    }
  });
});

test.describe("UI-BATCH-4 about and developers", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("about has no first person singular phrases", async ({ page }) => {
    await stubMapCardsBackend(page);
    await page.goto("/about");
    const text = await page.getByTestId("mission-page").innerText();
    expect(text).toContain("Why we are building this");
    expect(text).toContain("This map is our answer to that gap");
    expect(text).not.toContain(" I am ");
    expect(text).not.toContain(" my answer ");
    expect(text).not.toMatch(/\bI\b/);
    expect(text).not.toMatch(/\bmy\b/i);
    expect(text).not.toMatch(/\bme\b/i);
    expect(text).not.toMatch(/\bmine\b/i);
  });

  test("developers footer has no Source code text", async ({ page }) => {
    await stubMapCardsBackend(page);
    await page.goto("/developers");
    await expect(page.getByText("Source code", { exact: true })).toHaveCount(0);
    const text = await page.locator("body").innerText();
    expect(text).not.toContain("Source code");
  });
});

test.describe("UI-BATCH-4 levels", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("roadmap and How it works list the five levels", async ({ page }) => {
    await stubMapCardsBackend(page);
    await page.goto("/roadmap");
    const levels = page.getByTestId("roadmap-level");
    await expect(levels).toHaveCount(AREA_LEVELS.length);
    for (const level of AREA_LEVELS) {
      await expect(levels.filter({ hasText: level })).toHaveCount(1);
    }
    const roadmapText = await page.locator("body").innerText();
    expect(roadmapText).not.toMatch(/neighbourhood/i);
    expect(roadmapText).not.toContain("£");

    await page.goto("/methodology");
    const how = page.getByTestId("methodology-levels");
    await expect(how.getByRole("listitem")).toHaveCount(AREA_LEVELS.length);
    for (const level of AREA_LEVELS) {
      await expect(how).toContainText(level);
    }
    await expect(page.getByTestId("methodology-levels-note")).toBeVisible();
    const howText = await page.locator("body").innerText();
    expect(howText).not.toMatch(/neighbourhood/i);
    expect(howText).not.toContain("£");
  });
});

for (const viewport of [
  { width: 390, height: 844 },
  { width: 360, height: 740 },
] as const) {
  test.describe(`UI-BATCH-4 map banner ${viewport.width}`, () => {
    test.use({ viewport });

    test("collapsed map banner keeps More in view", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      // MAP-HINTS-OFF-1: banner gone from map — strip fit runs on a content page.
      await openMap(page);
      await expect(page.getByTestId("research-banner")).toHaveCount(0);
      await page.goto("/data");
      await assertMoreInView(page);
      assertConsoleClean(gate);
    });
  });
}

test.describe("UI-BATCH-4 mobile style label", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("style button is Aerial toggle (no Detailed/Simple label)", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    await injectEsriBasemapKey(page);
    await stubMapCardsBackend(page);
    await openMap(page);
    const toggle = page.getByTestId("basemap-switcher");
    await expect(toggle).toBeVisible();
    await expect(toggle).toHaveAttribute("aria-label", "Aerial map");
    await expect(toggle).toHaveAttribute("aria-pressed", "false");
    await expect(toggle).not.toContainText("Detailed");
    await expect(toggle).not.toContainText("Simple");
    await expect(toggle).not.toContainText("Aerial");
    await expect(page.getByTestId("basemap-toggle-narrow")).toHaveCount(0);
    const box = await toggle.boundingBox();
    expect(box).toBeTruthy();
    expect(box!.width).toBeGreaterThanOrEqual(44);
    expect(box!.height).toBeGreaterThanOrEqual(44);
    const face = toggle.locator(".basemap-switcher-face");
    await expect(face).toBeVisible();
    const faceBox = await face.boundingBox();
    expect(faceBox).toBeTruthy();
    expect(faceBox!.width).toBeGreaterThan(0);
    expect(faceBox!.height).toBeGreaterThan(0);
    expect(faceBox!.x).toBeGreaterThanOrEqual(box!.x - 1);
    expect(faceBox!.x + faceBox!.width).toBeLessThanOrEqual(
      box!.x + box!.width + 1,
    );
    expect(faceBox!.y).toBeGreaterThanOrEqual(0);
    expect(faceBox!.y + faceBox!.height).toBeLessThanOrEqual(844);
  });
});

test.describe("UI-BATCH-4 empty data zone", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("empty at-sea data-zones/at shows no card and no console error", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await page.route("**/layers/context/data-zones/at**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: "{}",
      });
    });
    await openMap(page);
    await waitForMap(page);
    const seen = page.waitForResponse(
      (response) => response.url().includes("data-zones/at") && response.ok(),
    );
    await page.evaluate(({ lat, lng }) => {
      const map = (
        window as unknown as {
          __map?: {
            fire(type: string, ev: object): void;
            project(lngLat: { lng: number; lat: number }): { x: number; y: number };
          };
        }
      ).__map;
      if (!map) throw new Error("window.__map missing");
      const lngLat = { lng, lat };
      map.fire("click", {
        lngLat,
        point: map.project(lngLat),
        originalEvent: new MouseEvent("click"),
      });
    }, SEA);
    await seen;
    await expect(page.getByTestId("place-card")).toHaveCount(0);
    await expect(page.getByTestId("map-panel-slot")).toHaveCount(0);
    assertConsoleClean(gate);
  });
});
