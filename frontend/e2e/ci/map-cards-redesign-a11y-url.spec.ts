
import AxeBuilder from "@axe-core/playwright";
import { test, expect } from "./_fixtures";
import { registerOpenFreeMapFontStub, attachConsoleGate, assertConsoleClean, openLayers, openMap, openPlaceViaCoords, stubMapCardsBackend } from "./_mapCardsHelpers";
import { type Page } from "@playwright/test";

registerOpenFreeMapFontStub();

/**
 * MAP-CARDS checks 13–15, 17, 25 — axe, keyboard, URL state.
 */

async function axeSerious(page: Page) {
  const results = await new AxeBuilder({ page })
    .disableRules(["color-contrast"]) // sampled separately where practical
    .analyze();
  const bad = results.violations.filter((v) =>
    ["serious", "critical"].includes(v.impact || ""),
  );
  expect(
    bad,
    bad.map((v) => `${v.id}: ${v.help}`).join("\n"),
  ).toEqual([]);
}

for (const viewport of [
  { width: 1280, height: 800 },
  { width: 390, height: 844 },
  { width: 768, height: 1024 },
]) {
  test.describe(`MAP-CARDS a11y/url (${viewport.width})`, () => {
    test.use({ viewport });

    test("13+25 axe rest / card / Layers", async ({ page }) => {
      test.setTimeout(180_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await axeSerious(page);

      await openPlaceViaCoords(page);
      await axeSerious(page);

      await openLayers(page);
      await axeSerious(page);
      assertConsoleClean(gate);
    });

    test("14 keyboard: Tab, Esc, switches, skip-ish search focus", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await openMap(page);
      await openLayers(page);

      const landToggle = page.getByTestId("layers-group-toggle-land");
      await expect(landToggle).toHaveAttribute("aria-expanded", /.+/);
      if ((await landToggle.getAttribute("aria-expanded")) !== "true") {
        await landToggle.click();
      }
      const sw = page.getByTestId("layer-toggle-access_services");
      await expect(sw).toHaveAttribute("role", "switch");
      await sw.focus();
      const before = await sw.getAttribute("aria-checked");
      await page.keyboard.press("Space");
      await expect(sw).toHaveAttribute(
        "aria-checked",
        before === "true" ? "false" : "true",
      );

      await page.getByTestId("map-panel-slot-close").click();
      await page.locator("#place-query").focus();
      await expect(page.locator("#place-query")).toBeFocused();
      assertConsoleClean(gate);
    });

    // QUARANTINE CI-DEDUP-1b-r2 Q6: goBack after close lands on panel=place
    // (history race with place= + panel=layers deep-link under quiet stubs).
    // Owner Eng Lead; exit = history contract for panel=layers round-trip, or
    // fix by 2026-11-21.
    test("15+17 URL state place/panel/layers/z/c round-trip @quarantine", async ({
      page,
    }) => {
      test.setTimeout(90_000);
      const gate = attachConsoleGate(page);
      await stubMapCardsBackend(page);
      await page.goto(
        "/?place=S01014567&panel=layers&layers=councils,access_services&z=8&c=-4.25,55.86",
      );
      await page.locator(".maplibregl-canvas").waitFor({ timeout: 60_000 });
      await expect(page.getByTestId("layers-panel")).toBeVisible({
        timeout: 30_000,
      });
      await expect(page.getByTestId("layer-toggle-access_services")).toHaveAttribute(
        "aria-checked",
        "true",
      );

      const url = page.url();
      expect(url).toMatch(/panel=layers/);
      expect(url).toMatch(/layers=/);
      // No place selection as raw lat/lng-only identity when place= is set
      expect(url).toMatch(/place=/);

      await page.getByTestId("map-panel-slot-close").click();
      await page.goBack();
      await expect(page.getByTestId("layers-panel")).toBeVisible({
        timeout: 15_000,
      });
      assertConsoleClean(gate);
    });
  });
}
