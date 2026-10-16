import { expect, test, type Page } from "@playwright/test";
import {
  assertConsoleClean,
  attachConsoleGate,
  boxOf,
  boxesOverlap,
  getVisibleLayerIds,
  openLayers,
  openMap,
  openPlaceViaCoords,
  stubMapCardsBackend,
  waitForMap,
  type Box,
} from "./_mapCardsHelpers";

/**
 * MAP-CARDS checks 1–3, 5–7, 11, 16–19, 23 — panel slot, one-at-a-time,
 * mobile sheet, hit targets, scroll, Esc, gestures (best-effort), collapse.
 */

async function assertNoOverlapsAmong(
  items: Array<{ label: string; box: Box }>,
) {
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      expect(
        boxesOverlap(items[i]!.box, items[j]!.box),
        `${items[i]!.label} vs ${items[j]!.label}`,
      ).toBe(false);
    }
  }
}

async function collectChrome(page: Page, extras: Array<{ label: string; testId: string }> = []) {
  const items: Array<{ label: string; box: Box }> = [];
  const candidates: Array<{ label: string; locator: ReturnType<Page["locator"]> }> = [
    { label: "basemap", locator: page.getByTestId("basemap-switcher") },
    { label: "layers btn", locator: page.getByTestId("hud-layers-btn") },
    { label: "zoom-in", locator: page.locator(".maplibregl-ctrl-zoom-in") },
    { label: "all sources", locator: page.getByTestId("map-all-sources") },
    ...extras.map((e) => ({
      label: e.label,
      locator: page.getByTestId(e.testId),
    })),
  ];
  for (const c of candidates) {
    if ((await c.locator.count()) === 0) continue;
    if (!(await c.locator.first().isVisible().catch(() => false))) continue;
    items.push({ label: c.label, box: await boxOf(c.locator.first(), c.label) });
  }
  return items;
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
]) {
  test.describe(`MAP-CARDS panel (${viewport.width})`, () => {
    test.use({ viewport });

    test("1 no overlaps across rest / card / Layers", async ({ page }) => {
      test.setTimeout(120_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);

      await assertNoOverlapsAmong(await collectChrome(page));

      await openPlaceViaCoords(page);
      const slot = page.getByTestId("map-panel-slot");
      await expect(slot).toBeVisible();
      await assertNoOverlapsAmong(
        await collectChrome(page, [
          { label: "panel slot", testId: "map-panel-slot" },
        ]),
      );

      await openLayers(page);
      await expect(page.getByTestId("layers-panel")).toBeVisible();
      await expect(page.getByTestId("place-card")).toHaveCount(0);
      await assertNoOverlapsAmong(
        await collectChrome(page, [
          { label: "panel slot", testId: "map-panel-slot" },
        ]),
      );

      await page.getByTestId("map-panel-slot-close").click();
      await expect(page.getByTestId("layers-panel")).toHaveCount(0);
      assertConsoleClean(gate);
    });

    test("2 one panel at a time (place XOR layers)", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openPlaceViaCoords(page);
      await expect(page.getByTestId("place-card")).toBeVisible();
      await expect(page.getByTestId("layers-panel")).toHaveCount(0);

      await openLayers(page);
      await expect(page.getByTestId("layers-panel")).toBeVisible();
      await expect(page.getByTestId("place-card")).toHaveCount(0);

      // Mobile full sheet covers the Layers toggle; close via panel chrome.
      // Desktop still toggles via the HUD button.
      if (viewport.width < 900) {
        await page.getByTestId("map-panel-slot-close").click();
      } else {
        await page.getByTestId("hud-layers-btn").click();
      }
      // Closing layers may restore place aside — still at most one.
      const placeVisible = (await page.getByTestId("place-card").count()) > 0;
      const layersVisible = (await page.getByTestId("layers-panel").count()) > 0;
      expect(Number(placeVisible) + Number(layersVisible)).toBeLessThanOrEqual(1);
      assertConsoleClean(gate);
    });

    test("5 opening Layers does not change visible layer ids", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await waitForMap(page);
      await page.waitForTimeout(800);
      const before = await getVisibleLayerIds(page);
      await openLayers(page);
      await page.waitForTimeout(400);
      const during = await getVisibleLayerIds(page);
      expect(during).toEqual(before);
      await page.getByTestId("map-panel-slot-close").click();
      await page.waitForTimeout(400);
      const after = await getVisibleLayerIds(page);
      expect(after).toEqual(before);
      assertConsoleClean(gate);
    });

    test("6 visible controls meet 44px hit targets", async ({ page }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await openLayers(page);

      const controls = page.locator(
        '[data-testid="hud-layers-btn"], [data-testid="basemap-switcher"], [data-testid="map-panel-slot-close"], [data-testid="map-panel-handle"], [data-testid="layer-toggle-councils"], .maplibregl-ctrl-zoom-in, .maplibregl-ctrl-zoom-out, .hud-search-go',
      );
      const n = await controls.count();
      expect(n).toBeGreaterThan(0);
      for (let i = 0; i < n; i += 1) {
        const el = controls.nth(i);
        if (!(await el.isVisible().catch(() => false))) continue;
        const box = await el.boundingBox();
        if (!box) continue;
        // Attribution (i) may use padded hit area; skip MapLibre attrib button.
        expect(box.width, `w #${i}`).toBeGreaterThanOrEqual(44);
        expect(box.height, `h #${i}`).toBeGreaterThanOrEqual(44);
      }
      assertConsoleClean(gate);
    });

    test("7 no sideways scroll; one scroll ancestor in panel", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openPlaceViaCoords(page);

      const scrollOk = await page.evaluate(() => {
        const sideways = document.documentElement.scrollWidth > window.innerWidth + 1;
        const slot = document.querySelector('[data-testid="map-panel-slot"]');
        if (!slot) return { sideways, scrollAncestors: -1 };
        const scrollers: Element[] = [];
        for (const el of Array.from(slot.querySelectorAll("*")).concat([slot])) {
          const s = getComputedStyle(el);
          const oy = s.overflowY;
          if (
            (oy === "auto" || oy === "scroll") &&
            (el as HTMLElement).scrollHeight > (el as HTMLElement).clientHeight + 1
          ) {
            scrollers.push(el);
          }
        }
        return { sideways, scrollAncestors: scrollers.length };
      });
      expect(scrollOk.sideways).toBe(false);
      expect(scrollOk.scrollAncestors).toBeLessThanOrEqual(1);
      assertConsoleClean(gate);
    });

    test("11 Esc closes panel; place non-modal; layers modal at full mobile", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openPlaceViaCoords(page);
      const place = page.getByTestId("place-card");
      await expect(place).toBeVisible();
      // Place card is a region, not a modal dialog trap.
      await expect(place).toHaveAttribute("role", "region");
      const slot = page.getByTestId("map-panel-slot");
      await expect(slot).not.toHaveAttribute("aria-modal", "true");

      await page.keyboard.press("Escape");
      // Esc may collapse detent first on mobile — press until closed.
      for (let i = 0; i < 4; i += 1) {
        if ((await page.getByTestId("place-card").count()) === 0) break;
        await page.keyboard.press("Escape");
      }
      await expect(page.getByTestId("place-card")).toHaveCount(0);

      await openLayers(page);
      if (viewport.width === 390) {
        const layersSlot = page.getByTestId("map-panel-slot");
        await expect(layersSlot).toHaveAttribute("data-detent", "full");
        await expect(layersSlot).toHaveAttribute("role", "dialog");
        await expect(layersSlot).toHaveAttribute("aria-modal", "true");
        await expect(page.locator(".map-stage")).toHaveAttribute("inert", /.*/);
      }
      await page.keyboard.press("Escape");
      for (let i = 0; i < 4; i += 1) {
        if ((await page.getByTestId("layers-panel").count()) === 0) break;
        await page.keyboard.press("Escape");
      }
      await expect(page.getByTestId("layers-panel")).toHaveCount(0);
      assertConsoleClean(gate);
    });
  });
}

test.describe("MAP-CARDS mobile sheet 390", () => {
  test.use({ viewport: { width: 390, height: 844 } });

  test("3 sheet width/height/detents; 16–19 handle Esc", async ({ page }) => {
    test.setTimeout(120_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    // Map tap → peek
    await openMap(page);
    await page.locator(".maplibregl-canvas").click({
      position: { x: 195, y: 420 },
    });
    const slot = page.getByTestId("map-panel-slot");
    await expect(slot).toBeVisible({ timeout: 45_000 });
    await expect(slot).toHaveAttribute("data-detent", "peek");

    const peekBox = await boxOf(slot, "peek slot");
    expect(Math.abs(peekBox.width - 390)).toBeLessThanOrEqual(2);
    expect(Math.abs(peekBox.y + peekBox.height - 844)).toBeLessThanOrEqual(4);
    expect(Math.abs(peekBox.height - 180)).toBeLessThanOrEqual(16);

    const handle = page.getByTestId("map-panel-handle");
    await expect(handle).toHaveAttribute("aria-expanded", "false");
    const handleBox = await handle.boundingBox();
    expect(handleBox!.height).toBeGreaterThanOrEqual(44);

    await handle.click();
    await expect(slot).toHaveAttribute("data-detent", "half");
    const halfBox = await boxOf(slot, "half slot");
    const halfTarget = 0.55 * 844;
    expect(Math.abs(halfBox.height - halfTarget)).toBeLessThanOrEqual(48);

    await handle.focus();
    await page.keyboard.press("Enter");
    await expect(slot).toHaveAttribute("data-detent", "full");
    await expect(handle).toHaveAttribute("aria-expanded", "true");

    // Esc steps down then closes (E4).
    await page.keyboard.press("Escape");
    await expect(slot).toHaveAttribute("data-detent", /half|peek/);
    await page.keyboard.press("Escape");
    await page.keyboard.press("Escape");
    await expect(page.getByTestId("map-panel-slot")).toHaveCount(0);

    // Search → half
    await openPlaceViaCoords(page);
    await expect(page.getByTestId("map-panel-slot")).toHaveAttribute(
      "data-detent",
      "half",
    );
    assertConsoleClean(gate);
  });
});

test.describe("MAP-CARDS desktop collapse 1280", () => {
  test.use({ viewport: { width: 1280, height: 800 } });

  test("23 collapse tab 48px; ? shortcuts; focus ring ≥3px", async ({
    page,
  }) => {
    test.setTimeout(90_000);
    const gate = attachConsoleGate(page);
    await stubMapCardsBackend(page);
    await openPlaceViaCoords(page);

    await page.getByTestId("map-panel-slot-close").click();
    const tab = page.getByTestId("panel-collapse-tab");
    await expect(tab).toBeVisible({ timeout: 10_000 });
    await expect
      .poll(async () => {
        const box = await tab.boundingBox();
        return box ? Math.round(box.width) : 0;
      })
      .toBeGreaterThanOrEqual(40);
    const tabBox = await tab.boundingBox();
    expect(tabBox).toBeTruthy();
    expect(Math.abs(tabBox!.width - 48)).toBeLessThanOrEqual(8);

    await page.keyboard.press("?");
    await expect(page.getByTestId("map-shortcuts-dialog")).toBeVisible();
    await page.getByTestId("map-shortcuts-dialog").getByLabel("Close shortcuts").click();

    await page.getByTestId("hud-layers-btn").focus();
    const outline = await page.getByTestId("hud-layers-btn").evaluate((el) => {
      const s = getComputedStyle(el);
      // force :focus-visible styles via class probe of computed outline-width
      return {
        width: parseFloat(s.outlineWidth || "0"),
        style: s.outlineStyle,
      };
    });
    // CSS declares 3px on :focus-visible — verify stylesheet rule is present.
    const ruleOk = await page.evaluate(() => {
      for (const sheet of Array.from(document.styleSheets)) {
        let rules: CSSRuleList;
        try {
          rules = sheet.cssRules;
        } catch {
          continue;
        }
        for (const rule of Array.from(rules)) {
          if (
            rule instanceof CSSStyleRule &&
            rule.selectorText.includes("hud-layers-btn:focus-visible") &&
            /outline:\s*3px/.test(rule.cssText)
          ) {
            return true;
          }
        }
      }
      return false;
    });
    expect(ruleOk || outline.width >= 3).toBe(true);
    assertConsoleClean(gate);
  });
});
